"""Scraper for Flame Comics (https://flamecomics.xyz/).

Flame is a Next.js site that embeds everything we need as JSON inside a
<script id="__NEXT_DATA__"> tag, so we parse that instead of guessing at HTML.

URL shapes:
  - Series : https://flamecomics.xyz/series/{series_id}
  - Chapter: https://flamecomics.xyz/series/{series_id}/{token}
  - Images : https://cdn.flamecomics.xyz/uploads/images/series/{series_id}/{token}/{name}
"""
import ast
import json

from bs4 import BeautifulSoup

from app.scraper import fetch
from app.scraper.base import ChapterInfo, Scraper, SeriesInfo, fmt_number, register

BASE_URL = "https://flamecomics.xyz"
CDN = "https://cdn.flamecomics.xyz/uploads/images/series"
NAME = "flamecomics"


def matches(url: str) -> bool:
    return "flamecomics." in url


def _next_data(url: str) -> dict:
    """Fetch a page and return the parsed __NEXT_DATA__ JSON blob."""
    soup = BeautifulSoup(fetch.get(url, referer=BASE_URL + "/").text, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag:
        raise ValueError(f"Couldn't find page data on {url} — is it a Flame Comics page?")
    return json.loads(tag.string)


def _as_dict(value):
    """Flame's `images` is usually a dict; tolerate it arriving as a string."""
    if isinstance(value, dict):
        return value
    return ast.literal_eval(value)


def get_series(url: str) -> SeriesInfo:
    page = _next_data(url)["props"]["pageProps"]
    series = page["series"]
    sid = series["series_id"]

    title = series.get("title") or "Untitled"
    cover_url = f"{CDN}/{sid}/{series['cover']}" if series.get("cover") else ""

    chapters = []
    for ch in page.get("chapters", []):
        number = fmt_number(ch.get("chapter"))
        chapters.append(
            ChapterInfo(
                number=number,
                title=ch.get("title") or f"Chapter {number}",
                url=f"{BASE_URL}/series/{sid}/{ch['token']}",
            )
        )
    chapters.sort(key=lambda c: _safe_float(c.number), reverse=True)
    return SeriesInfo(title=title, cover_url=cover_url, chapters=chapters)


def get_chapter_pages(url: str) -> list:
    chapter = _next_data(url)["props"]["pageProps"]["chapter"]
    sid = chapter["series_id"]
    token = chapter["token"]
    images = _as_dict(chapter["images"])

    pages = []
    # Keys are "0", "1", "2", ... — read them in numeric order.
    for key in sorted(images, key=lambda k: int(k)):
        name = images[key]["name"]
        pages.append(f"{CDN}/{sid}/{token}/{name}")
    return pages


def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


register(
    Scraper(
        name=NAME,
        matches=matches,
        get_series=get_series,
        get_chapter_pages=get_chapter_pages,
        image_hosts=["flamecomics.xyz"],
        image_referer="https://flamecomics.xyz/",
    )
)
