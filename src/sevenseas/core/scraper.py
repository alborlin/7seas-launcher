"""FitGirl Repacks scraper — parses search, listing, and detail pages."""

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
_BASE_URL = "https://fitgirl-repacks.site"
_RETRY_CODES = {502, 503, 504, 429}
_MAX_RETRIES = 3
_RETRY_DELAY = 2  # seconds, doubled each attempt


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
    original_size: str | None = None
    repack_size: str | None = None
    screenshots: list[str] = field(default_factory=list)
    system_requirements: str | None = None
    genres: list[str] = field(default_factory=list)


class FitGirlScraper:
    """Scrapes FitGirl Repacks for game listings and detail pages."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        )

    def _get(self, url: str, **kwargs) -> httpx.Response:
        """GET with automatic retry on transient server errors (502/503/504/429)."""
        last_exc = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._client.get(url, **kwargs)
                if resp.status_code not in _RETRY_CODES or attempt == _MAX_RETRIES - 1:
                    resp.raise_for_status()
                    return resp
                # Transient error — wait and retry
                time.sleep(_RETRY_DELAY * (attempt + 1))
            except httpx.HTTPStatusError as e:
                if e.response.status_code in _RETRY_CODES and attempt < _MAX_RETRIES - 1:
                    last_exc = e
                    time.sleep(_RETRY_DELAY * (attempt + 1))
                else:
                    raise
        raise last_exc

    def search(self, query: str) -> list[GameResult]:
        resp = self._get(f"{_BASE_URL}/", params={"s": query})
        return self.parse_listing(resp.text)

    def get_latest(self, page: int = 1) -> list[GameResult]:
        if page > 1:
            url = f"{_BASE_URL}/category/lossless-repack/page/{page}/"
        else:
            url = f"{_BASE_URL}/category/lossless-repack/"
        resp = self._get(url)
        return self.parse_listing(resp.text)

    def get_upcoming(self) -> list[str]:
        """Fetch the list of upcoming repacks from the homepage."""
        resp = self._get(f"{_BASE_URL}/")
        return self.parse_upcoming(resp.text)

    @staticmethod
    def parse_upcoming(html: str) -> list[str]:
        """Parse upcoming repack names from the homepage first article."""
        soup = BeautifulSoup(html, "lxml")
        for article in soup.select("article"):
            title_el = article.select_one(".entry-title a, h1 a, h2 a")
            if title_el and "upcoming" in title_el.get_text(strip=True).lower():
                h3 = article.select_one("div.entry-content div h3")
                if not h3:
                    continue
                names = []
                for span in h3.find_all("span", style=True):
                    text = span.get_text(strip=True).lstrip("⇢").strip()
                    if text:
                        names.append(text)
                return names
        return []

    def get_top_monthly(self) -> list[GameResult]:
        resp = self._get(f"{_BASE_URL}/popular-repacks/")
        return self.parse_popular(resp.text)

    def get_top_yearly(self) -> list[GameResult]:
        resp = self._get(f"{_BASE_URL}/popular-repacks-of-the-year/")
        return self.parse_popular(resp.text)

    def get_thumbnail(self, url: str) -> str | None:
        """Fetch a post page and return the first cover image URL."""
        resp = self._get(url)
        soup = BeautifulSoup(resp.text, "lxml")
        entry = soup.select_one(".entry-content")
        if not entry:
            return None
        img = entry.select_one("img.alignleft") or entry.select_one("img")
        if img:
            return img.get("data-lazy-src") or img.get("src")
        return None

    def get_detail(self, url: str) -> GameDetail:
        resp = self._get(url)
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
            # Try alignleft image first (FitGirl listing style), then any img
            img = article.select_one("img.alignleft")
            if img is None:
                img = article.select_one(".entry-content img")
            if img is None:
                img = article.select_one("img")
            thumbnail = None
            if img:
                thumbnail = img.get("data-lazy-src") or img.get("src")
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

    def parse_popular(self, html: str) -> list[GameResult]:
        """Parse a popular/top repacks page (Jetpack widget format)."""
        soup = BeautifulSoup(html, "lxml")
        results = []
        seen_urls: set[str] = set()
        # Jetpack top posts widget uses div.widget-grid-view-image
        for item in soup.select(".widget-grid-view-image"):
            link = item.select_one("a[href]")
            if link is None:
                continue
            url = link.get("href", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            title = link.get("title", "")
            img = link.select_one("img")
            thumbnail = None
            if img:
                thumbnail = img.get("data-lazy-src") or img.get("src")
            results.append(GameResult(
                title=title, url=url, thumbnail=thumbnail, size_info=None,
            ))
        # If Jetpack widget not found, fall back to article-based parsing
        if not results:
            results = self.parse_listing(html)
        return results

    def parse_detail(self, html: str, url: str) -> GameDetail:
        """Parse a game detail page and extract magnet link and metadata."""
        soup = BeautifulSoup(html, "lxml")
        title_el = soup.select_one(".entry-title, h1.entry-title")
        title = title_el.get_text(strip=True) if title_el else ""
        magnet_link = soup.select_one('a[href^="magnet:"]')
        magnet_uri = magnet_link["href"] if magnet_link else None
        entry = soup.select_one(".entry-content")
        text = entry.get_text() if entry else ""

        original_match = re.search(
            r"Original Size[:\s]*([\d./]+\s*[GMTK]B)", text, re.IGNORECASE,
        )
        repack_match = re.search(
            r"Repack Size[:\s]*([\d./]+\s*[GMTK]B)", text, re.IGNORECASE,
        )
        original_size = original_match.group(1) if original_match else None
        repack_size = repack_match.group(1) if repack_match else None

        return GameDetail(
            title=title, url=url, magnet_uri=magnet_uri,
            description=self._extract_description(entry),
            size_info=repack_size,
            original_size=original_size,
            repack_size=repack_size,
            screenshots=self._extract_screenshots(entry),
            system_requirements=self._extract_system_requirements(text),
            genres=self._extract_genres(text),
        )

    @staticmethod
    def _extract_description(entry) -> str | None:
        """Extract game description from spoiler blocks or page text."""
        if not entry:
            return None
        # Check su-spoiler format (current FitGirl style)
        for sp in entry.select(".su-spoiler"):
            title_el = sp.select_one(".su-spoiler-title")
            if title_el and "description" in title_el.get_text(strip=True).lower():
                body = sp.select_one(".su-spoiler-content")
                if body:
                    return body.get_text(strip=True)[:2000]
        # Check bbspoiler / sp-wrap format
        for sp in entry.select(".sp-wrap"):
            head = sp.select_one(".sp-head")
            if head and "description" in head.get_text(strip=True).lower():
                body = sp.select_one(".sp-body")
                if body:
                    return body.get_text(strip=True)[:2000]
        # Fall back to paragraphs before technical sections
        stop_markers = {
            "system requirements", "minimum:", "recommended:",
            "how to install", "download mirrors", "screenshots",
            "repack features", "in-game language", "genres/tags",
            "genre:", "companies:", "languages:", "original size",
            "repack size", "based on",
        }
        paragraphs = []
        # Walk all <p> tags in the entry (handles nested divs)
        for el in entry.select("p"):
            text = el.get_text(strip=True)
            if not text or len(text) < 20:
                continue
            if any(m in text.lower() for m in stop_markers):
                break
            paragraphs.append(text)
        return "\n\n".join(paragraphs) if paragraphs else None

    @staticmethod
    def _extract_system_requirements(text: str) -> str | None:
        """Extract system requirements block from page text."""
        match = re.search(
            r"((?:Minimum|System)\s*Requirements?.*?)(?=Screenshots|How to Install|Download Mirrors|Repack Features|\Z)",
            text, re.IGNORECASE | re.DOTALL,
        )
        if match:
            block = match.group(1).strip()
            # Trim to reasonable length
            lines = block.split("\n")
            cleaned = "\n".join(line.strip() for line in lines if line.strip())
            return cleaned[:1000] if cleaned else None
        return None

    @staticmethod
    def _extract_genres(text: str) -> list[str]:
        """Extract genres from a 'Genre(s):' or 'Genres/Tags:' line."""
        match = re.search(r"Genre[s]?\s*(?:/\s*Tags?)?\s*[:/]\s*([^\n]+)", text, re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            return [g.strip() for g in re.split(r"[,/]", raw) if g.strip()]
        return []

    @staticmethod
    def _extract_screenshots(entry) -> list[str]:
        """Extract screenshot image URLs, filtering out non-game images."""
        if not entry:
            return []
        skip_words = {
            "donate", "button", "icon", "logo", "banner", "adsense",
            "1x1", "torrent-stats", "torrent_stats",
        }
        screenshots = []
        # Find images after the "Screenshots" heading
        screenshot_section = False
        for el in entry.descendants:
            if hasattr(el, "name") and el.name in ("h3", "h2", "h4"):
                heading_text = el.get_text(strip=True).lower()
                if "screenshot" in heading_text:
                    screenshot_section = True
                    continue
                elif screenshot_section:
                    break  # Next section starts
            if not screenshot_section:
                continue
            if hasattr(el, "name") and el.name == "img":
                src = el.get("data-lazy-src") or el.get("src", "")
                if not src:
                    continue
                if any(w in src.lower() for w in skip_words):
                    continue
                # Strip riotpixels thumbnail suffix to get full-size
                src = re.sub(r"\.240p\.\w+$", "", src)
                classes = el.get("class") or []
                if "alignleft" in classes:
                    continue
                # Prefer full-size linked image
                parent_a = el.find_parent("a")
                if parent_a:
                    href = parent_a.get("href", "")
                    if href and any(href.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
                        if href not in screenshots:
                            screenshots.append(href)
                        continue
                if src not in screenshots:
                    screenshots.append(src)
        # If no screenshot section found, fall back to all non-cover images
        if not screenshots:
            for img in entry.select("img"):
                src = img.get("data-lazy-src") or img.get("src", "")
                if not src:
                    continue
                # Strip riotpixels thumbnail suffix to get full-size
                src = re.sub(r"\.240p\.\w+$", "", src)
                if any(w in src.lower() for w in skip_words):
                    continue
                classes = img.get("class") or []
                if "alignleft" in classes:
                    continue
                parent_a = img.find_parent("a")
                if parent_a:
                    href = parent_a.get("href", "")
                    if href and any(href.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
                        if href not in screenshots:
                            screenshots.append(href)
                        continue
                if src not in screenshots:
                    screenshots.append(src)
        return screenshots

    @staticmethod
    def slug_from_url(url: str) -> str:
        """Extract the slug from a FitGirl URL path."""
        path = urlparse(url).path.strip("/")
        return path.split("/")[-1] if path else ""
