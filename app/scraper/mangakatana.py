"""Scraper for MangaKatana (https://mangakatana.com/).

URL shapes:
  - Series : https://mangakatana.com/manga/{slug}.{id}
  - Chapter: https://mangakatana.com/manga/{slug}.{id}/c{number}

The series page lists chapters as normal links. The chapter page loads its
images from a JavaScript array (`var thzq = [...]`), so we read the URLs out of
that array rather than from <img> tags (which are lazy placeholders).
"""
import re

from bs4 import BeautifulSoup

from app.scraper import fetch
from app.scraper.base import ChapterInfo, Scraper, SeriesInfo, fmt_number, register

BASE_URL = "https://mangakatana.com"
NAME = "mangakatana"

# Pull the chapter number out of a chapter URL, e.g. ".../c170" or ".../c10.5"
_CHAPTER_NUM_RE = re.compile(r"/c([0-9]+(?:\.[0-9]+)?)\b")
# The base series URL (without the trailing /cN), e.g. https://.../manga/slug.123
_SERIES_BASE_RE = re.compile(r"(https?://mangakatana\.com/manga/[^/?#]+)")
# The image array embedded in the chapter page.
_THZQ_RE = re.compile(r"var\s+thzq\s*=\s*\[(.*?)\];", re.S)


def matches(url: str) -> bool:
    return "mangakatana.com" in url


def _series_base(url: str) -> str:
    m = _SERIES_BASE_RE.match(url)
    if not m:
        raise ValueError(f"Not a MangaKatana series URL: {url}")
    return m.group(1)


def get_series(url: str) -> SeriesInfo:
    base = _series_base(url)
    soup = BeautifulSoup(fetch.get(base, referer=BASE_URL + "/").text, "html.parser")

    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        og = soup.find("meta", property="og:title")
        title = (og.get("content") if og else "") or "Untitled"

    cover_url = ""
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        cover_url = og_image["content"]

    # Only keep chapter links that belong to *this* series (the page also links
    # to unrelated series in its sidebar).
    chapters_by_number = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith(base):
            continue
        m = _CHAPTER_NUM_RE.search(href)
        if not m:
            continue
        number = fmt_number(m.group(1))
        if number in chapters_by_number:
            continue
        text = a.get_text(strip=True)
        chapters_by_number[number] = ChapterInfo(
            number=number,
            title=text or f"Chapter {number}",
            url=href,
        )

    chapters = sorted(
        chapters_by_number.values(), key=lambda c: float(c.number), reverse=True
    )
    if not title:
        raise ValueError(f"Couldn't parse a title from {url}")
    return SeriesInfo(title=title, cover_url=cover_url, chapters=chapters)


def get_chapter_pages(url: str) -> list:
    html = fetch.get(url, referer=BASE_URL + "/").text
    m = _THZQ_RE.search(html)
    if not m:
        return []
    body = m.group(1)
    # URLs are quoted strings inside the array.
    urls = re.findall(r"'([^']+)'", body) or re.findall(r'"([^"]+)"', body)
    return [u for u in urls if u.startswith("http")]


register(
    Scraper(
        name=NAME,
        matches=matches,
        get_series=get_series,
        get_chapter_pages=get_chapter_pages,
        image_hosts=["mangakatana.com"],
        image_referer="https://mangakatana.com/",
    )
)
