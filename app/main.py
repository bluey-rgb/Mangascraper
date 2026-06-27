"""The web app: serves the pages you view and the actions behind the buttons.

Run it with:
    uvicorn app.main:app --reload
then open http://localhost:8000

Everything is in this one file so it's easy to follow as a first project:
  - routes that show pages (GET /, /series/{id}, /read/{id})
  - routes that do things (POST /series, /series/{id}/refresh)
  - the image proxy (GET /img) that makes chapter images display
"""
from datetime import datetime, timezone

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import config
from app.database import get_connection, init_db
from app.scraper import asura  # noqa: F401  (importing registers the scraper)
from app.scraper.base import get_scraper_by_name, get_scraper_for_url
from app.scraper.fetch import get_bytes

app = FastAPI(title="Manga Tracker")
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Paths that don't require being logged in.
PUBLIC_PATHS = {"/login"}


@app.middleware("http")
async def require_login(request: Request, call_next):
    """Block every page behind the login, except the login page and static files.

    Because the browser sends our session cookie with every request (including
    the <img> proxy requests), once you're logged in everything just works.
    """
    path = request.url.path
    if (
        path in PUBLIC_PATHS
        or path.startswith("/static")
        or request.session.get("authed")
    ):
        return await call_next(request)
    return RedirectResponse(url="/login", status_code=303)


# SessionMiddleware is added last so it runs first — that way request.session
# already exists when require_login (above) checks it.
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY)


@app.on_event("startup")
def _startup() -> None:
    config.require_password()  # fail fast if no password is configured
    init_db()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    # Already logged in? Go home.
    if request.session.get("authed"):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": None}
    )


@app.post("/login")
def login_submit(request: Request, password: str = Form(...)):
    if password == config.APP_PASSWORD:
        request.session["authed"] = True
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Incorrect password."},
        status_code=401,
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def library(request: Request):
    """Home page: every series you track, with a NEW badge when unread new
    chapters exist."""
    conn = get_connection()
    series = conn.execute(
        """
        SELECT s.*,
               (SELECT COUNT(*) FROM chapters c
                 WHERE c.series_id = s.id AND c.is_new = 1 AND c.is_read = 0)
                 AS new_count,
               (SELECT COUNT(*) FROM chapters c WHERE c.series_id = s.id)
                 AS total_count
          FROM series s
         ORDER BY s.title COLLATE NOCASE
        """
    ).fetchall()
    conn.close()
    return templates.TemplateResponse(
        "index.html", {"request": request, "series": series}
    )


@app.get("/series/{series_id}", response_class=HTMLResponse)
def series_detail(request: Request, series_id: int):
    """One series: its cover and full chapter list (newest first)."""
    conn = get_connection()
    series = conn.execute(
        "SELECT * FROM series WHERE id = ?", (series_id,)
    ).fetchone()
    if series is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Series not found")
    chapters = conn.execute(
        """
        SELECT * FROM chapters
         WHERE series_id = ?
         ORDER BY CAST(number AS REAL) DESC
        """,
        (series_id,),
    ).fetchall()
    conn.close()
    return templates.TemplateResponse(
        "series.html",
        {"request": request, "series": series, "chapters": chapters},
    )


@app.get("/read/{chapter_id}", response_class=HTMLResponse)
def read_chapter(request: Request, chapter_id: int):
    """Read a chapter: scrape its page images and show them top-to-bottom.
    Opening a chapter marks it read and clears its NEW flag."""
    conn = get_connection()
    chapter = conn.execute(
        "SELECT * FROM chapters WHERE id = ?", (chapter_id,)
    ).fetchone()
    if chapter is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Chapter not found")
    series = conn.execute(
        "SELECT * FROM series WHERE id = ?", (chapter["series_id"],)
    ).fetchone()

    scraper = get_scraper_by_name(series["source"])
    pages = scraper.get_chapter_pages(chapter["url"])

    # Mark as read.
    conn.execute(
        "UPDATE chapters SET is_read = 1, is_new = 0 WHERE id = ?", (chapter_id,)
    )
    conn.commit()
    conn.close()

    return templates.TemplateResponse(
        "reader.html",
        {
            "request": request,
            "series": series,
            "chapter": chapter,
            "pages": pages,
        },
    )


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
@app.post("/series")
def add_series(url: str = Form(...)):
    """Add a series by pasting its URL. Scrapes the title, cover, and chapters."""
    url = url.strip()
    try:
        scraper = get_scraper_for_url(url)
        info = scraper.get_series(url)
    except Exception as exc:  # surface a friendly message instead of a 500
        raise HTTPException(status_code=400, detail=f"Couldn't add that series: {exc}")

    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO series (title, source, source_url, cover_url, last_checked_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(source_url) DO UPDATE SET
            title = excluded.title,
            cover_url = excluded.cover_url
        """,
        (info.title, scraper.name, url, info.cover_url, _now()),
    )
    # Get the series id whether it was just inserted or already existed.
    row = conn.execute(
        "SELECT id FROM series WHERE source_url = ?", (url,)
    ).fetchone()
    series_id = row["id"]

    # Insert chapters. On first add nothing is "new" (it's all new to you);
    # we only flag is_new during later refreshes.
    for ch in info.chapters:
        conn.execute(
            """
            INSERT OR IGNORE INTO chapters
                (series_id, number, title, url, added_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (series_id, ch.number, ch.title, ch.url, _now()),
        )
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/series/{series_id}", status_code=303)


@app.post("/series/{series_id}/refresh")
def refresh_series(series_id: int):
    """Re-scrape a series and flag any chapters we hadn't seen before as NEW."""
    conn = get_connection()
    series = conn.execute(
        "SELECT * FROM series WHERE id = ?", (series_id,)
    ).fetchone()
    if series is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Series not found")

    scraper = get_scraper_by_name(series["source"])
    info = scraper.get_series(series["source_url"])

    known_urls = {
        r["url"]
        for r in conn.execute(
            "SELECT url FROM chapters WHERE series_id = ?", (series_id,)
        ).fetchall()
    }
    for ch in info.chapters:
        if ch.url not in known_urls:
            conn.execute(
                """
                INSERT OR IGNORE INTO chapters
                    (series_id, number, title, url, is_new, added_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (series_id, ch.number, ch.title, ch.url, _now()),
            )
    conn.execute(
        "UPDATE series SET last_checked_at = ? WHERE id = ?", (_now(), series_id)
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/series/{series_id}", status_code=303)


@app.post("/series/{series_id}/delete")
def delete_series(series_id: int):
    """Stop tracking a series (also removes its chapters)."""
    conn = get_connection()
    conn.execute("DELETE FROM series WHERE id = ?", (series_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)


# ---------------------------------------------------------------------------
# Image proxy
# ---------------------------------------------------------------------------
@app.get("/img")
def image_proxy(url: str):
    """Fetch a remote chapter image (with the right Referer) and stream it back.

    Browsers load <img src="/img?url=..."> which hits this route, so images
    display even if the CDN ever starts blocking hotlinked requests.
    """
    if "asurascans.com" not in url and "asuracomic.net" not in url:
        raise HTTPException(status_code=400, detail="Refusing to proxy that URL")
    try:
        data = get_bytes(url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Image fetch failed: {exc}")
    # Guess the content type from the extension; default to webp (AsuraScans).
    ext = url.rsplit(".", 1)[-1].lower().split("?")[0]
    content_type = {
        "webp": "image/webp",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
    }.get(ext, "image/webp")
    return Response(content=data, media_type=content_type)
