"""Torbox API client -- wraps the official torbox-api SDK."""

import re
from dataclasses import dataclass

from torbox_api import TorboxApi


API_VERSION = "v1"


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
        self._sdk = TorboxApi(access_token=api_key)

    def create_torrent(self, magnet: str) -> int:
        """Send a magnet link to Torbox. Returns the torbox torrent ID."""
        result = self._sdk.torrents.create_torrent(
            api_version=API_VERSION,
            request_body={"magnet": magnet},
        )
        return result.data["torrent_id"]

    def check_status(self, torbox_id: int) -> TorrentStatus | None:
        """Poll the status of a torrent on Torbox."""
        result = self._sdk.torrents.get_torrent_list(
            api_version=API_VERSION,
            id_=str(torbox_id),
        )
        torrents = result.data if result.data else []
        for t in torrents:
            if t["id"] == torbox_id:
                return TorrentStatus(
                    torbox_id=t["id"],
                    state=t.get("download_state", "unknown"),
                    progress=t.get("progress", 0.0),
                    speed_bps=t.get("dlspeed", 0),
                    total_bytes=t.get("size", 0),
                    name=t.get("name", ""),
                )
        return None

    def get_download_url(self, torbox_id: int, file_id: int = 0) -> str:
        """Get a direct download URL for a completed torrent."""
        result = self._sdk.torrents.request_download_link(
            api_version=API_VERSION,
            torrent_id=str(torbox_id),
            file_id=str(file_id),
        )
        return result.data

    def check_cached(self, info_hash: str) -> bool:
        """Check if a torrent hash is already cached on Torbox servers."""
        result = self._sdk.torrents.get_torrent_cached_availability(
            api_version=API_VERSION,
            hash=info_hash,
        )
        return bool(result.data and result.data.get(info_hash))

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
