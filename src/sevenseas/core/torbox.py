"""Torbox API client -- wraps the official torbox-api SDK."""

import logging
import re
from dataclasses import dataclass

import httpx
from torbox_api import TorboxApi

log = logging.getLogger(__name__)


API_VERSION = "v1"
_TORBOX_API_BASE = "https://api.torbox.app"


@dataclass
class TorrentStatus:
    torbox_id: int
    state: str
    progress: float
    speed_bps: int
    total_bytes: int
    name: str


class TorboxClient:
    """High-level wrapper around the Torbox API SDK."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._sdk = TorboxApi(access_token=api_key)
        self._http = httpx.Client(
            base_url=_TORBOX_API_BASE,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    def create_torrent(self, magnet: str) -> int:
        """Send a magnet link to Torbox. Returns the torbox torrent ID."""
        result = self._sdk.torrents.create_torrent(
            api_version=API_VERSION,
            request_body={"magnet": magnet},
        )
        torrent_id = int(result.data.torrent_id)
        log.info("create_torrent: torbox_id=%s", torrent_id)
        return torrent_id

    def check_status(self, torbox_id: int) -> TorrentStatus | None:
        """Poll the status of a torrent on Torbox."""
        # Use direct HTTP — the SDK breaks deserialization for single-object responses
        resp = self._http.get(
            f"/{API_VERSION}/api/torrents/mylist",
            params={"id": torbox_id},
        )
        resp.raise_for_status()
        body = resp.json()
        t = body.get("data")
        if not t:
            log.warning("check_status(%d): no data returned", torbox_id)
            return None
        # If list (no id filter), grab first match; if dict (id filter), use directly
        if isinstance(t, list):
            matches = [x for x in t if x.get("id") == torbox_id]
            t = matches[0] if matches else None
            if not t:
                return None
        log.debug("check_status(%d): state=%s progress=%s",
                  torbox_id, t.get("download_state"), t.get("progress"))
        return TorrentStatus(
            torbox_id=t.get("id", torbox_id),
            state=t.get("download_state", "unknown"),
            progress=t.get("progress", 0.0),
            speed_bps=int(t.get("download_speed", 0)),
            total_bytes=int(t.get("size", 0)),
            name=t.get("name", ""),
        )

    def get_download_url(self, torbox_id: int, file_id: int | None = None, zip_link: bool = False) -> str:
        """Get a direct download URL for a completed torrent.

        Args:
            torbox_id: The Torbox torrent ID.
            file_id: Specific file ID to download, or None for zip of all files.
            zip_link: If True, return a zip link for all files.
        """
        # Use direct HTTP — the SDK doesn't pass the required 'token' query param
        params = {
            "token": self._api_key,
            "torrent_id": torbox_id,
        }
        if file_id is not None:
            params["file_id"] = file_id
        if zip_link:
            params["zip_link"] = "true"
        resp = self._http.get(
            f"/{API_VERSION}/api/torrents/requestdl",
            params=params,
        )
        resp.raise_for_status()
        body = resp.json()
        log.info("get_download_url: success for torbox_id=%d", torbox_id)
        return body["data"]

    def check_cached(self, info_hash: str) -> bool:
        """Check if a torrent hash is already cached on Torbox servers."""
        result = self._sdk.torrents.get_torrent_cached_availability(
            api_version=API_VERSION,
            hash=info_hash,
        )
        if not result.data:
            return False
        # result.data may be a dict or typed object
        if isinstance(result.data, dict):
            return bool(result.data.get(info_hash))
        return bool(getattr(result.data, info_hash, None))

    def validate_api_key(self) -> bool:
        """Validate the API key by fetching user info."""
        try:
            self._sdk.user.get_user_data(api_version=API_VERSION)
            return True
        except Exception:
            return False

    @staticmethod
    def extract_hash_from_magnet(magnet: str) -> str | None:
        """Extract the info hash from a magnet URI."""
        match = re.search(r"btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})", magnet)
        return match.group(1).lower() if match else None
