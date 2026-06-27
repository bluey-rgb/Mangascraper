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
from urllib.parse import urlparse

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import config
from app.database import get_connection, init_db

# Importing each scraper module registers it. Add new sites here.
from app.scraper import asura, flame, mangadex, mangakatana  # noqa: F401
from app.scraper.base import (
    get_scraper_by_name,
    get_scraper_for_url,
    referer_for_image,
)
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
def library(request: Request, filter: str = "all", sort: str = "title"):
    """Home page: every series you track, with NEW badges and unread counts.

    Query params:
      filter = "all" | "new"        (new = only series with unread new chapters)
      sort   = "title" | "updated"  (updated = most recently added chapter first)
    """
    order_by = "latest_added DESC" if sort == "updated" else "title COLLATE NOCASE"
    where = "WHERE new_count > 0" if filter == "new" else ""

    conn = get_connection()
    series = conn.execute(
        f"""
        SELECT * FROM (
            SELECT s.*,
                   (SELECT COUNT(*) FROM chapters c
                     WHERE c.series_id = s.id AND c.is_new = 1 AND c.is_read = 0)
                     AS new_count,
                   (SELECT COUNT(*) FROM chapters c
                     WHERE c.series_id = s.id AND c.is_read = 0)
                     AS unread_count,
                   (SELECT COUNT(*) FROM chapters c WHERE c.series_id = s.id)
                     AS total_count,
                   (SELECT MAX(c.added_at) FROM chapters c WHERE c.series_id = s.id)
                     AS latest_added
              FROM series s
        )
        {where}
        ORDER BY {order_by}
        """
    ).fetchall()
    conn.close()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "series": series, "filter": filter, "sort": sort},
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

    # Find the neighboring chapters in reading order (ascending by number) so the
    # reader can offer Prev/Next. "Next" advances the story (higher number).
    ordered = conn.execute(
        """
        SELECT id, title FROM chapters
         WHERE series_id = ?
         ORDER BY CAST(number AS REAL) ASC, id ASC
        """,
        (chapter["series_id"],),
    ).fetchall()
    ids = [row["id"] for row in ordered]
    pos = ids.index(chapter_id)
    prev_chapter = ordered[pos - 1] if pos > 0 else None
    next_chapter = ordered[pos + 1] if pos < len(ordered) - 1 else None

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
            "prev_chapter": prev_chapter,
            "next_chapter": next_chapter,
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


def _refresh_one(conn, series) -> int:
    """Re-scrape one series, inserting unseen chapters flagged NEW.

    Returns how many new chapters were added. Shared by the single-series and
    refresh-all routes. Does not commit — the caller does.
    """
    scraper = get_scraper_by_name(series["source"])
    info = scraper.get_series(series["source_url"])

    known_urls = {
        r["url"]
        for r in conn.execute(
            "SELECT url FROM chapters WHERE series_id = ?", (series["id"],)
        ).fetchall()
    }
    added = 0
    for ch in info.chapters:
        if ch.url not in known_urls:
            conn.execute(
                """
                INSERT OR IGNORE INTO chapters
                    (series_id, number, title, url, is_new, added_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (series["id"], ch.number, ch.title, ch.url, _now()),
            )
            added += 1
    conn.execute(
        "UPDATE series SET last_checked_at = ? WHERE id = ?", (_now(), series["id"])
    )
    return added


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
    _refresh_one(conn, series)
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/series/{series_id}", status_code=303)


@app.post("/refresh-all")
def refresh_all():
    """Re-scrape every tracked series. Skips ones that error so one bad site
    doesn't stop the rest."""
    conn = get_connection()
    all_series = conn.execute("SELECT * FROM series").fetchall()
    for series in all_series:
        try:
            _refresh_one(conn, series)
            conn.commit()
        except Exception:
            conn.rollback()  # skip this series; keep going
    conn.close()
    return RedirectResponse(url="/?filter=new&sort=updated", status_code=303)


@app.get("/series/{series_id}/continue")
def continue_series(series_id: int):
    """Jump to the first unread chapter (in reading order). If everything is
    read, fall back to the series page."""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT id FROM chapters
         WHERE series_id = ? AND is_read = 0
         ORDER BY CAST(number AS REAL) ASC, id ASC
         LIMIT 1
        """,
        (series_id,),
    ).fetchone()
    conn.close()
    if row:
        return RedirectResponse(url=f"/read/{row['id']}", status_code=303)
    return RedirectResponse(url=f"/series/{series_id}", status_code=303)


@app.get("/series/{series_id}/first")
def first_chapter(series_id: int):
    """Jump to the very first chapter (lowest number) — start from the beginning."""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT id FROM chapters
         WHERE series_id = ?
         ORDER BY CAST(number AS REAL) ASC, id ASC
         LIMIT 1
        """,
        (series_id,),
    ).fetchone()
    conn.close()
    if row:
        return RedirectResponse(url=f"/read/{row['id']}", status_code=303)
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
    display even if a CDN starts blocking hotlinked requests.

    We only proxy hosts that one of our scrapers recognizes — this stops the
    endpoint from being used to fetch arbitrary URLs.
    """
    host = urlparse(url).hostname or ""
    referer = referer_for_image(host)
    if not referer:
        raise HTTPException(status_code=400, detail="Refusing to proxy that URL")
    try:
        data = get_bytes(url, referer=referer)
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
