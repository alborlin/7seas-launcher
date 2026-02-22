"""SteamGridDB API client — fetches game artwork for Steam library.

Prefers official Steam CDN artwork when available, falls back to
community-uploaded art from SteamGridDB.
"""

import logging
import os
import re
from urllib.parse import quote

import httpx

log = logging.getLogger(__name__)

_BASE_URL = "https://www.steamgriddb.com/api/v2"
_STEAM_CDN = "https://cdn.akamai.steamstatic.com/steam/apps"

# Steam CDN artwork paths keyed by art type
_STEAM_CDN_PATHS = {
    "grid": "/library_600x900_2x.jpg",
    "hero": "/library_hero.jpg",
    "logo": "/logo.png",
    "icon": "/clienticon.ico",
}


def _clean_for_steam_search(title: str) -> str:
    """Strip repack junk from title for Steam Store search."""
    # Version with separator: "Game – v1.2.3 ..." or "Game, Build 12345 ..."
    clean = re.sub(r"\s*[,\u2013\u2014-]\s*(?:v[\d.].*|Build\s.*)$", "", title).strip()
    # Version without separator: "Game v1.2.3 ..." (space + v + digits)
    clean = re.sub(r"\s+v\d[\d.]*.*$", "", clean).strip()
    # DLC mentions: "+ 3 DLCs ..." or "+ All DLCs ..."
    clean = re.sub(r"\s*\+\s*(?:\d+\s+|All\s+)?DLCs?\b.*$", "", clean, flags=re.IGNORECASE).strip()
    # Bonus content: "+ Bonus OST ..."
    clean = re.sub(r"\s*\+\s*Bonus\b.*$", "", clean, flags=re.IGNORECASE).strip()
    # Named edition keywords: "– GOTY", "- Premium ..."
    clean = re.sub(
        r"\s*[:\u2013\u2014-]\s*(?:Deluxe|Ultimate|Gold|GOTY|Complete|Quartz|Infernal|Premium).*$",
        "", clean, flags=re.IGNORECASE,
    ).strip()
    # Broad "... Edition" after separator: ": Digital Deluxe Edition"
    clean = re.sub(
        r"\s*[:\u2013\u2014-]\s*[\w\s]+Edition\b.*$",
        "", clean, flags=re.IGNORECASE,
    ).strip()
    # Parenthetical versions: "(v1.2.3)"
    clean = re.sub(r"\s*\(.*?v[\d.].*?\)\s*$", "", clean).strip()
    return clean or title


class SteamGridDBClient:
    """Fetches game artwork from SteamGridDB and Steam CDN."""

    def __init__(self, api_key: str) -> None:
        self._http = httpx.Client(
            base_url=_BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15.0,
        )

    def search_game(self, name: str) -> list[dict]:
        """Search for a game by name. Returns list of result dicts."""
        resp = self._http.get(f"/search/autocomplete/{quote(name, safe='')}")
        resp.raise_for_status()
        return resp.json().get("data", [])

    @staticmethod
    def get_steam_appid(name: str) -> int | None:
        """Search the Steam Store for a game and return its AppID."""
        clean = _clean_for_steam_search(name)
        try:
            resp = httpx.get(
                "https://store.steampowered.com/api/storesearch/",
                params={"term": clean, "l": "english", "cc": "US"},
                timeout=15.0,
            )
            items = resp.json().get("items", [])
            if items:
                log.info("Steam Store: '%s' -> appid=%d (%s)", clean, items[0]["id"], items[0]["name"])
                return items[0]["id"]
        except Exception as e:
            log.warning("Steam Store search failed for '%s': %s", clean, e)
        return None

    @staticmethod
    def get_steam_cdn_urls(appid: int) -> dict[str, str | None]:
        """Build Steam CDN artwork URLs and verify they exist."""
        urls = {}
        for art_type, path in _STEAM_CDN_PATHS.items():
            url = f"{_STEAM_CDN}/{appid}{path}"
            try:
                resp = httpx.head(url, follow_redirects=True, timeout=10.0)
                urls[art_type] = url if resp.status_code == 200 else None
            except Exception:
                urls[art_type] = None
        return urls

    def get_artwork_urls(self, game_id: int, steam_appid: int | None = None) -> dict[str, str | None]:
        """Fetch the best artwork URL for each type.

        Prefers official Steam CDN art when *steam_appid* is provided.
        Falls back to the highest-scored SteamGridDB community upload.
        """
        # Start with Steam CDN if we have an AppID
        urls: dict[str, str | None] = {}
        if steam_appid:
            cdn = self.get_steam_cdn_urls(steam_appid)
            for art_type, url in cdn.items():
                if url:
                    urls[art_type] = url
                    log.info("Using Steam CDN for %s (appid=%d)", art_type, steam_appid)

        # Fill any gaps from SteamGridDB community uploads
        queries = {
            "grid": ("/grids/game/{id}", {"dimensions": "600x900", "types": "static"}),
            "hero": ("/heroes/game/{id}", {"types": "static"}),
            "logo": ("/logos/game/{id}", {"types": "static"}),
            "icon": ("/icons/game/{id}", {"types": "static"}),
        }
        for art_type, (endpoint, params) in queries.items():
            if urls.get(art_type):
                continue  # Already have Steam CDN art for this type
            try:
                resp = self._http.get(
                    endpoint.format(id=game_id),
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
                if data:
                    best = max(data, key=lambda x: x.get("score", 0))
                    urls[art_type] = best["url"]
                else:
                    urls[art_type] = None
            except Exception as e:
                log.warning("SteamGridDB: failed to fetch %s for game %d: %s", art_type, game_id, e)
                if art_type not in urls:
                    urls[art_type] = None
        return urls

    def download_image(self, url: str, dest_path: str) -> bool:
        """Download an image from URL to local path. Returns True on success."""
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=30.0)
            resp.raise_for_status()
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(resp.content)
            log.info("Downloaded artwork to %s", dest_path)
            return True
        except Exception as e:
            log.warning("Failed to download %s: %s", url, e)
            return False
