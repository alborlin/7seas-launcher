"""Torrent backend protocol and implementations (Torbox, qBittorrent, Transmission)."""

import logging
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

log = logging.getLogger(__name__)


@dataclass
class TorrentProgress:
    backend_id: str
    state: str  # "downloading", "seeding", "error", etc.
    progress: float  # 0.0 to 1.0
    speed_bps: int
    total_bytes: int
    name: str
    download_path: str | None = None


@runtime_checkable
class TorrentBackend(Protocol):
    def add_magnet(self, magnet: str) -> str: ...
    def poll_status(self, backend_id: str) -> TorrentProgress | None: ...
    def get_download_path(self, backend_id: str) -> str | None: ...
    def cancel(self, backend_id: str) -> None: ...
    def requires_pull(self) -> bool: ...
    def get_pull_url(self, backend_id: str) -> str | None: ...
    def validate_connection(self) -> bool: ...


class TorboxBackend:
    """Wraps the existing TorboxClient to implement TorrentBackend."""

    def __init__(self, client) -> None:
        self._client = client

    def add_magnet(self, magnet: str) -> str:
        torbox_id = self._client.create_torrent(magnet)
        return str(torbox_id)

    def poll_status(self, backend_id: str) -> TorrentProgress | None:
        status = self._client.check_status(int(backend_id))
        if status is None:
            return None
        return TorrentProgress(
            backend_id=backend_id,
            state=status.state,
            progress=status.progress,
            speed_bps=status.speed_bps,
            total_bytes=status.total_bytes,
            name=status.name,
        )

    def get_download_path(self, backend_id: str) -> str | None:
        return None  # Torbox uses CDN pull, no local path

    def cancel(self, backend_id: str) -> None:
        pass  # Torbox torrents expire on their own

    def requires_pull(self) -> bool:
        return True

    def get_pull_url(self, backend_id: str) -> str | None:
        return self._client.get_download_url(int(backend_id), zip_link=True)

    def validate_connection(self) -> bool:
        return self._client.validate_api_key()


def _extract_hash_from_magnet(magnet: str) -> str | None:
    """Extract the info hash from a magnet URI."""
    match = re.search(r"btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})", magnet)
    return match.group(1).lower() if match else None


class QBittorrentBackend:
    """Uses qbittorrent-api to manage torrents via a local qBittorrent instance."""

    def __init__(self, host: str, port: int, username: str = "", password: str = "") -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._client = None

    def _ensure_connected(self):
        if self._client is not None:
            return
        import qbittorrentapi

        self._client = qbittorrentapi.Client(
            host=self._host,
            port=self._port,
            username=self._username,
            password=self._password,
        )
        self._client.auth_log_in()

    def add_magnet(self, magnet: str) -> str:
        self._ensure_connected()
        info_hash = _extract_hash_from_magnet(magnet)
        self._client.torrents_add(urls=magnet, category="seven-seas")
        if info_hash:
            return info_hash
        # Fallback: find the most recently added torrent
        torrents = self._client.torrents_info(sort="added_on", reverse=True, limit=1)
        if torrents:
            return torrents[0].hash
        raise RuntimeError("Failed to get torrent hash after adding magnet")

    def poll_status(self, backend_id: str) -> TorrentProgress | None:
        self._ensure_connected()
        torrents = self._client.torrents_info(torrent_hashes=backend_id)
        if not torrents:
            return None
        t = torrents[0]
        state = "downloading"
        if t.state_enum.is_complete:
            state = "seeding"
        elif t.state_enum.is_errored:
            state = "error"
        return TorrentProgress(
            backend_id=backend_id,
            state=state,
            progress=t.progress,  # already 0.0-1.0
            speed_bps=t.dlspeed,
            total_bytes=t.total_size,
            name=t.name,
            download_path=t.content_path,
        )

    def get_download_path(self, backend_id: str) -> str | None:
        self._ensure_connected()
        torrents = self._client.torrents_info(torrent_hashes=backend_id)
        if not torrents:
            return None
        return torrents[0].content_path

    def cancel(self, backend_id: str) -> None:
        self._ensure_connected()
        self._client.torrents_delete(delete_files=True, torrent_hashes=backend_id)

    def requires_pull(self) -> bool:
        return False

    def get_pull_url(self, backend_id: str) -> str | None:
        return None

    def validate_connection(self) -> bool:
        try:
            self._ensure_connected()
            self._client.app_version()
            return True
        except Exception:
            return False


class TransmissionBackend:
    """Uses transmission-rpc to manage torrents via a local Transmission instance."""

    def __init__(self, host: str, port: int, username: str = "", password: str = "") -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._client = None

    def _ensure_connected(self):
        if self._client is not None:
            return
        import transmission_rpc

        kwargs = {"host": self._host, "port": self._port}
        if self._username:
            kwargs["username"] = self._username
        if self._password:
            kwargs["password"] = self._password
        self._client = transmission_rpc.Client(**kwargs)

    def add_magnet(self, magnet: str) -> str:
        self._ensure_connected()
        torrent = self._client.add_torrent(magnet)
        return str(torrent.id)

    def poll_status(self, backend_id: str) -> TorrentProgress | None:
        self._ensure_connected()
        try:
            t = self._client.get_torrent(int(backend_id))
        except Exception:
            return None
        state = "downloading"
        if t.status == "seeding":
            state = "seeding"
        elif t.status in ("stopped", "check pending", "checking"):
            state = t.status
        elif t.error:
            state = "error"
        download_path = f"{t.download_dir}/{t.name}" if t.download_dir and t.name else None
        return TorrentProgress(
            backend_id=backend_id,
            state=state,
            progress=t.progress / 100.0,  # Transmission uses 0-100
            speed_bps=t.rate_download,
            total_bytes=t.total_size,
            name=t.name,
            download_path=download_path,
        )

    def get_download_path(self, backend_id: str) -> str | None:
        self._ensure_connected()
        try:
            t = self._client.get_torrent(int(backend_id))
        except Exception:
            return None
        if t.download_dir and t.name:
            return f"{t.download_dir}/{t.name}"
        return None

    def cancel(self, backend_id: str) -> None:
        self._ensure_connected()
        self._client.remove_torrent(int(backend_id), delete_data=True)

    def requires_pull(self) -> bool:
        return False

    def get_pull_url(self, backend_id: str) -> str | None:
        return None

    def validate_connection(self) -> bool:
        try:
            self._ensure_connected()
            self._client.session_stats()
            return True
        except Exception:
            return False


def create_backend(config) -> TorrentBackend | None:
    """Factory: create the right backend from config settings."""
    method = config.download_method

    if method == "torbox":
        api_key = config.torbox_api_key
        if not api_key:
            return None
        from sevenseas.core.torbox import TorboxClient
        client = TorboxClient(api_key=api_key)
        return TorboxBackend(client)

    if method == "qbittorrent":
        host = config.bt_host or "localhost"
        port = int(config.bt_port or 8080)
        return QBittorrentBackend(
            host=host, port=port,
            username=config.bt_username or "",
            password=config.bt_password or "",
        )

    if method == "transmission":
        host = config.bt_host or "localhost"
        port = int(config.bt_port or 9091)
        return TransmissionBackend(
            host=host, port=port,
            username=config.bt_username or "",
            password=config.bt_password or "",
        )

    log.warning("Unknown download method: %s", method)
    return None
