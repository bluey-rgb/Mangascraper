"""Scraper for MangaDex (https://mangadex.org/).

MangaDex has an official, free API, so we use that instead of scraping HTML —
it's more reliable and there's no Cloudflare to fight.

URL shapes the user might paste:
  - Series : https://mangadex.org/title/{uuid}/{slug}
  - Chapter: https://mangadex.org/chapter/{uuid}

API docs: https://api.mangadex.org/docs/
"""
import re

from app.scraper import fetch
from app.scraper.base import ChapterInfo, Scraper, SeriesInfo, fmt_number, register

API = "https://api.mangadex.org"
SITE = "https://mangadex.org"
NAME = "mangadex"
LANG = "en"  # which translation to track

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)


def matches(url: str) -> bool:
    return "mangadex.org" in url


def _api(path: str, params: dict = None) -> dict:
    return fetch.get(API + path, referer=SITE + "/", params=params).json()


def _id_from(url: str) -> str:
    m = _UUID_RE.search(url)
    if not m:
        raise ValueError(f"Couldn't find a MangaDex id in {url}")
    return m.group(0)


def get_series(url: str) -> SeriesInfo:
    manga_id = _id_from(url)
    data = _api(f"/manga/{manga_id}", {"includes[]": "cover_art"})["data"]

    attrs = data["attributes"]
    titles = attrs.get("title", {})
    title = titles.get("en") or (next(iter(titles.values()), "Untitled"))

    # Cover lives in the relationships list.
    cover_url = ""
    for rel in data.get("relationships", []):
        if rel.get("type") == "cover_art":
            file_name = rel.get("attributes", {}).get("fileName")
            if file_name:
                cover_url = f"https://uploads.mangadex.org/covers/{manga_id}/{file_name}"

    chapters = _fetch_chapter_feed(manga_id)
    return SeriesInfo(title=title, cover_url=cover_url, chapters=chapters)


def _fetch_chapter_feed(manga_id: str) -> list:
    """Page through the chapter feed and return one entry per chapter number."""
    seen_numbers = set()
    chapters = []
    offset = 0
    limit = 100
    while True:
        resp = _api(
            f"/manga/{manga_id}/feed",
            {
                "translatedLanguage[]": LANG,
                "order[chapter]": "desc",
                "limit": limit,
                "offset": offset,
                "includeExternalUrl": 0,
            },
        )
        for ch in resp.get("data", []):
            a = ch["attributes"]
            number = fmt_number(a.get("chapter"))
            if number in seen_numbers:  # skip duplicate uploads of the same chapter
                continue
            seen_numbers.add(number)
            label = a.get("title")
            chapters.append(
                ChapterInfo(
                    number=number,
                    title=f"Chapter {number}" + (f" — {label}" if label else ""),
                    url=f"{SITE}/chapter/{ch['id']}",
                )
            )
        total = resp.get("total", 0)
        offset += limit
        if offset >= total or offset > 2000:  # safety cap
            break
    chapters.sort(key=_safe_float, reverse=True)
    return chapters


def get_chapter_pages(url: str) -> list:
    chapter_id = _id_from(url)
    home = _api(f"/at-home/server/{chapter_id}")
    base = home["baseUrl"]
    chapter = home["chapter"]
    chapter_hash = chapter["hash"]
    return [f"{base}/data/{chapter_hash}/{name}" for name in chapter["data"]]


def _safe_float(chapter: ChapterInfo) -> float:
    try:
        return float(chapter.number)
    except (TypeError, ValueError):
        return -1.0


register(
    Scraper(
        name=NAME,
        matches=matches,
        get_series=get_series,
        get_chapter_pages=get_chapter_pages,
        image_hosts=["mangadex.network", "uploads.mangadex.org"],
        image_referer="https://mangadex.org/",
    )
)
