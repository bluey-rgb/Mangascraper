"""Shared HTTP fetching.

AsuraScans sits behind Cloudflare and rejects "obvious bot" requests with a
403 error. `curl_cffi` solves this by impersonating a real Chrome browser
(matching its TLS fingerprint), which gets us past the passive bot checks.

Everything that touches the network goes through here so that politeness
(a small delay) and the browser disguise live in one place.
"""
import time

from curl_cffi import requests

# A realistic browser User-Agent. curl_cffi's impersonate handles the deeper
# fingerprinting; this just rounds out the disguise.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Be polite: wait this many seconds between requests so we don't hammer the site.
REQUEST_DELAY_SECONDS = 1.0

_last_request_time = 0.0


def _respect_delay() -> None:
    """Sleep just enough so consecutive requests are spaced out."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_DELAY_SECONDS:
        time.sleep(REQUEST_DELAY_SECONDS - elapsed)
    _last_request_time = time.time()


def get(url: str, referer: str = "https://asurascans.com/", params: dict = None) -> requests.Response:
    """Fetch a URL as if we were Chrome. Raises on HTTP errors.

    `params` is an optional dict of query-string parameters (used by API calls
    such as MangaDex's).
    """
    _respect_delay()
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": referer,
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.get(
        url,
        headers=headers,
        params=params,
        impersonate="chrome",  # the key to defeating Cloudflare
        timeout=30,
    )
    resp.raise_for_status()
    return resp


def get_bytes(url: str, referer: str = "https://asurascans.com/") -> bytes:
    """Fetch raw bytes (used by the image proxy)."""
    return get(url, referer=referer).content
