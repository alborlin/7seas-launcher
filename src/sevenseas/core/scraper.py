"""FitGirl Repacks scraper — parses search, listing, and detail pages."""

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
_BASE_URL = "https://fitgirl-repacks.site"


@dataclass
class GameResult:
    title: str
    url: str
    thumbnail: str | None = None
    size_info: str | None = None


@dataclass
class GameDetail:
    title: str
    url: str
    magnet_uri: str | None = None
    description: str | None = None
    size_info: str | None = None
    screenshots: list[str] = field(default_factory=list)


class FitGirlScraper:
    """Scrapes FitGirl Repacks for game listings and detail pages."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        )

    def search(self, query: str) -> list[GameResult]:
        resp = self._client.get(f"{_BASE_URL}/", params={"s": query})
        resp.raise_for_status()
        return self.parse_listing(resp.text)

    def get_latest(self) -> list[GameResult]:
        resp = self._client.get(f"{_BASE_URL}/category/lossless-repack/")
        resp.raise_for_status()
        return self.parse_listing(resp.text)

    def get_top_monthly(self) -> list[GameResult]:
        resp = self._client.get(f"{_BASE_URL}/popular-repacks/")
        resp.raise_for_status()
        return self.parse_listing(resp.text)

    def get_top_yearly(self) -> list[GameResult]:
        resp = self._client.get(f"{_BASE_URL}/popular-repacks-of-the-year/")
        resp.raise_for_status()
        return self.parse_listing(resp.text)

    def get_detail(self, url: str) -> GameDetail:
        resp = self._client.get(url)
        resp.raise_for_status()
        return self.parse_detail(resp.text, url)

    def parse_listing(self, html: str) -> list[GameResult]:
        """Parse a listing/search results page and return GameResult items."""
        soup = BeautifulSoup(html, "lxml")
        results = []
        for article in soup.select("article"):
            title_el = article.select_one(".entry-title a, h1 a, h2 a")
            if title_el is None:
                continue
            title = title_el.get_text(strip=True)
            url = title_el.get("href", "")
            img = article.select_one("img")
            thumbnail = img.get("src") if img else None
            text = article.get_text()
            size_match = re.search(
                r"(?:Original Size|Repack Size)[:\s]*([\d.]+\s*[GMTK]B)",
                text, re.IGNORECASE,
            )
            size_info = size_match.group(1) if size_match else None
            results.append(GameResult(
                title=title, url=url, thumbnail=thumbnail, size_info=size_info,
            ))
        return results

    def parse_detail(self, html: str, url: str) -> GameDetail:
        """Parse a game detail page and extract magnet link and metadata."""
        soup = BeautifulSoup(html, "lxml")
        title_el = soup.select_one(".entry-title, h1.entry-title")
        title = title_el.get_text(strip=True) if title_el else ""
        magnet_link = soup.select_one('a[href^="magnet:"]')
        magnet_uri = magnet_link["href"] if magnet_link else None
        entry = soup.select_one(".entry-content")
        description = entry.get_text(strip=True)[:500] if entry else None
        text = soup.get_text()
        size_match = re.search(
            r"(?:Repack Size)[:\s]*([\d.]+\s*[GMTK]B)",
            text, re.IGNORECASE,
        )
        size_info = size_match.group(1) if size_match else None
        screenshots = []
        for img in soup.select(".entry-content img"):
            src = img.get("src", "")
            if src and ("screenshot" in src.lower() or img.get("data-lazy-src")):
                screenshots.append(img.get("data-lazy-src", src))
        return GameDetail(
            title=title, url=url, magnet_uri=magnet_uri,
            description=description, size_info=size_info, screenshots=screenshots,
        )

    @staticmethod
    def slug_from_url(url: str) -> str:
        """Extract the slug from a FitGirl URL path."""
        path = urlparse(url).path.strip("/")
        return path.split("/")[-1] if path else ""
