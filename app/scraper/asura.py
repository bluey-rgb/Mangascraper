"""Scraper for AsuraScans (https://asurascans.com/).

URL shapes (confirmed by inspecting the live site):
  - Series : https://asurascans.com/comics/{slug}-{hash}
  - Chapter: https://asurascans.com/comics/{slug}-{hash}/chapter/{number}

The site is server-rendered, so the data we need is right in the HTML and we
can parse it with BeautifulSoup — no headless browser required.

If AsuraScans redesigns, this file is the only place that should need changes.
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.scraper import fetch
from app.scraper.base import ChapterInfo, Scraper, SeriesInfo, register

BASE_URL = "https://asurascans.com"
NAME = "asurascans"

# Matches the chapter number inside a chapter URL, e.g. ".../chapter/10.5"
_CHAPTER_NUM_RE = re.compile(r"/chapter/([0-9]+(?:\.[0-9]+)?)")


def matches(url: str) -> bool:
    return "asurascans.com" in url or "asuracomic.net" in url


def _clean_title(raw: str) -> str:
    """Turn the <title>/og:title into just the series name.

    e.g. "The Sword Emperor's Rise of Namgung | Asura Scans" -> the name only.
    """
    return raw.split("|")[0].strip()


def get_series(url: str) -> SeriesInfo:
    """Fetch a series page and return its title, cover, and full chapter list."""
    soup = BeautifulSoup(fetch.get(url).text, "html.parser")

    # --- Title: prefer og:title, fall back to <h1>, then <title> ---
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = _clean_title(og_title["content"])
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    if not title and soup.title:
        title = _clean_title(soup.title.get_text())

    # --- Cover image: og:image ---
    cover_url = ""
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        cover_url = og_image["content"]

    # --- Chapters: every link containing /chapter/<number> ---
    # The page also has "First Chapter" / "Latest Chapter" shortcut buttons that
    # point at chapters we already list, so we dedupe by chapter number and
    # build a clean title from the number itself.
    chapters_by_number = {}
    for a in soup.find_all("a", href=True):
        m = _CHAPTER_NUM_RE.search(a["href"])
        if not m:
            continue
        number = m.group(1)
        if number in chapters_by_number:
            continue
        chapters_by_number[number] = ChapterInfo(
            number=number,
            title=f"Chapter {number}",
            url=urljoin(BASE_URL, a["href"]),
        )

    # Sort newest-first by numeric value (so "10" > "9", and "10.5" sits right).
    chapters = sorted(
        chapters_by_number.values(),
        key=lambda c: float(c.number),
        reverse=True,
    )

    if not title:
        raise ValueError(f"Could not parse a title from {url} — is it a series page?")

    return SeriesInfo(title=title, cover_url=cover_url, chapters=chapters)


def get_chapter_pages(url: str) -> list:
    """Fetch a chapter page and return the ordered list of page image URLs."""
    soup = BeautifulSoup(fetch.get(url).text, "html.parser")

    pages = []
    seen = set()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        # Chapter page images live under /chapters/ on the CDN. This filters out
        # the cover, avatars, icons, and ads.
        if not src or "/chapters/" not in src:
            continue
        if src in seen:
            continue
        seen.add(src)
        pages.append(src)

    return pages


# Make this scraper discoverable by the rest of the app.
register(
    Scraper(
        name=NAME,
        matches=matches,
        get_series=get_series,
        get_chapter_pages=get_chapter_pages,
    )
)
