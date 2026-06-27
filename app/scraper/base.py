"""Shared data shapes and a tiny registry of site scrapers.

Each site (AsuraScans now, others later) provides two functions with the same
signatures. Keeping a common shape here means the rest of the app never has to
care *which* site a series came from.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List


@dataclass
class ChapterInfo:
    number: str          # e.g. "12" or "10.5" — kept as text on purpose
    title: str           # e.g. "Chapter 12"
    url: str             # absolute URL to the chapter


@dataclass
class SeriesInfo:
    title: str
    cover_url: str
    chapters: List[ChapterInfo] = field(default_factory=list)


# A scraper module fills these in. We look them up by `source` name.
@dataclass
class Scraper:
    name: str
    matches: Callable[[str], bool]                 # does this URL belong to me?
    get_series: Callable[[str], SeriesInfo]        # series URL -> SeriesInfo
    get_chapter_pages: Callable[[str], List[str]]  # chapter URL -> image URLs


_REGISTRY: Dict[str, Scraper] = {}


def register(scraper: Scraper) -> None:
    _REGISTRY[scraper.name] = scraper


def get_scraper_for_url(url: str) -> Scraper:
    """Pick the scraper that recognizes this URL."""
    for scraper in _REGISTRY.values():
        if scraper.matches(url):
            return scraper
    raise ValueError(f"No scraper knows how to handle this URL: {url}")


def get_scraper_by_name(name: str) -> Scraper:
    return _REGISTRY[name]
