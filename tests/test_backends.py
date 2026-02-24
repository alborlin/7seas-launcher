"""Tests for torrent backend implementations and factory."""

import pytest
from unittest.mock import MagicMock, patch

from sevenseas.core.backends import (
    TorboxBackend,
    QBittorrentBackend,
    TransmissionBackend,
    TorrentProgress,
    create_backend,
    _extract_hash_from_magnet,
)


# --- Hash extraction ---

def test_extract_hash_from_magnet():
    magnet = "magnet:?xt=urn:btih:abcdef1234567890abcdef1234567890abcdef12&dn=test"
    assert _extract_hash_from_magnet(magnet) == "abcdef1234567890abcdef1234567890abcdef12"


def test_extract_hash_from_magnet_none():
    assert _extract_hash_from_magnet("not-a-magnet") is None


# --- TorboxBackend ---

class TestTorboxBackend:
    @pytest.fixture
    def client(self):
        return MagicMock()

    @pytest.fixture
    def backend(self, client):
        return TorboxBackend(client)

    def test_add_magnet(self, backend, client):
        client.create_torrent.return_value = 42
        result = backend.add_magnet("magnet:?xt=urn:btih:abc")
        assert result == "42"
        client.create_torrent.assert_called_once_with("magnet:?xt=urn:btih:abc")

    def test_poll_status(self, backend, client):
        from sevenseas.core.torbox import TorrentStatus
        client.check_status.return_value = TorrentStatus(
            torbox_id=42, state="downloading", progress=0.5,
            speed_bps=1000, total_bytes=100000, name="test",
        )
        result = backend.poll_status("42")
        assert result is not None
        assert result.progress == 0.5
        assert result.backend_id == "42"

    def test_poll_status_none(self, backend, client):
        client.check_status.return_value = None
        assert backend.poll_status("42") is None

    def test_requires_pull(self, backend):
        assert backend.requires_pull() is True

    def test_get_pull_url(self, backend, client):
        client.get_download_url.return_value = "https://cdn.example.com/file.zip"
        result = backend.get_pull_url("42")
        assert result == "https://cdn.example.com/file.zip"
        client.get_download_url.assert_called_once_with(42, zip_link=True)

    def test_validate_connection(self, backend, client):
        client.validate_api_key.return_value = True
        assert backend.validate_connection() is True

    def test_get_download_path_returns_none(self, backend):
        assert backend.get_download_path("42") is None


# --- QBittorrentBackend ---

class TestQBittorrentBackend:
    @pytest.fixture
    def mock_qbt(self):
        with patch("sevenseas.core.backends.QBittorrentBackend._ensure_connected") as mock:
            backend = QBittorrentBackend("localhost", 8080, "admin", "password")
            backend._client = MagicMock()
            yield backend

    def test_add_magnet_with_hash(self, mock_qbt):
        magnet = "magnet:?xt=urn:btih:abcdef1234567890abcdef1234567890abcdef12&dn=test"
        result = mock_qbt.add_magnet(magnet)
        assert result == "abcdef1234567890abcdef1234567890abcdef12"
        mock_qbt._client.torrents_add.assert_called_once_with(
            urls=magnet, category="seven-seas",
        )

    def test_poll_status(self, mock_qbt):
        torrent = MagicMock()
        torrent.progress = 0.75
        torrent.dlspeed = 5000
        torrent.total_size = 200000
        torrent.name = "game"
        torrent.content_path = "/downloads/game"
        torrent.state_enum.is_complete = False
        torrent.state_enum.is_errored = False
        mock_qbt._client.torrents_info.return_value = [torrent]
        result = mock_qbt.poll_status("abc123")
        assert result is not None
        assert result.progress == 0.75
        assert result.state == "downloading"
        assert result.download_path == "/downloads/game"

    def test_poll_status_complete(self, mock_qbt):
        torrent = MagicMock()
        torrent.progress = 1.0
        torrent.dlspeed = 0
        torrent.total_size = 200000
        torrent.name = "game"
        torrent.content_path = "/downloads/game"
        torrent.state_enum.is_complete = True
        torrent.state_enum.is_errored = False
        mock_qbt._client.torrents_info.return_value = [torrent]
        result = mock_qbt.poll_status("abc123")
        assert result.state == "seeding"

    def test_poll_status_not_found(self, mock_qbt):
        mock_qbt._client.torrents_info.return_value = []
        assert mock_qbt.poll_status("abc123") is None

    def test_get_download_path(self, mock_qbt):
        torrent = MagicMock()
        torrent.content_path = "/downloads/game"
        mock_qbt._client.torrents_info.return_value = [torrent]
        assert mock_qbt.get_download_path("abc") == "/downloads/game"

    def test_cancel(self, mock_qbt):
        mock_qbt.cancel("abc123")
        mock_qbt._client.torrents_delete.assert_called_once_with(
            delete_files=True, torrent_hashes="abc123",
        )

    def test_requires_pull(self, mock_qbt):
        assert mock_qbt.requires_pull() is False

    def test_get_pull_url_returns_none(self, mock_qbt):
        assert mock_qbt.get_pull_url("abc") is None

    def test_validate_connection(self, mock_qbt):
        mock_qbt._client.app_version.return_value = "4.6.0"
        assert mock_qbt.validate_connection() is True


# --- TransmissionBackend ---

class TestTransmissionBackend:
    @pytest.fixture
    def mock_tr(self):
        with patch("sevenseas.core.backends.TransmissionBackend._ensure_connected") as mock:
            backend = TransmissionBackend("localhost", 9091)
            backend._client = MagicMock()
            yield backend

    def test_add_magnet(self, mock_tr):
        torrent = MagicMock()
        torrent.id = 7
        mock_tr._client.add_torrent.return_value = torrent
        result = mock_tr.add_magnet("magnet:?xt=urn:btih:abc")
        assert result == "7"

    def test_poll_status_divides_progress(self, mock_tr):
        """Transmission progress is 0-100, should be divided by 100."""
        torrent = MagicMock()
        torrent.progress = 75.0  # Transmission uses 0-100
        torrent.status = "downloading"
        torrent.error = 0
        torrent.rate_download = 3000
        torrent.total_size = 500000
        torrent.name = "game"
        torrent.download_dir = "/downloads"
        mock_tr._client.get_torrent.return_value = torrent
        result = mock_tr.poll_status("7")
        assert result is not None
        assert result.progress == 0.75  # 75 / 100
        assert result.state == "downloading"
        assert result.download_path == "/downloads/game"

    def test_poll_status_seeding(self, mock_tr):
        torrent = MagicMock()
        torrent.progress = 100.0
        torrent.status = "seeding"
        torrent.error = 0
        torrent.rate_download = 0
        torrent.total_size = 500000
        torrent.name = "game"
        torrent.download_dir = "/downloads"
        mock_tr._client.get_torrent.return_value = torrent
        result = mock_tr.poll_status("7")
        assert result.state == "seeding"
        assert result.progress == 1.0

    def test_poll_status_not_found(self, mock_tr):
        mock_tr._client.get_torrent.side_effect = Exception("Not found")
        assert mock_tr.poll_status("999") is None

    def test_get_download_path(self, mock_tr):
        torrent = MagicMock()
        torrent.download_dir = "/downloads"
        torrent.name = "game"
        mock_tr._client.get_torrent.return_value = torrent
        assert mock_tr.get_download_path("7") == "/downloads/game"

    def test_cancel(self, mock_tr):
        mock_tr.cancel("7")
        mock_tr._client.remove_torrent.assert_called_once_with(7, delete_data=True)

    def test_requires_pull(self, mock_tr):
        assert mock_tr.requires_pull() is False

    def test_validate_connection(self, mock_tr):
        assert mock_tr.validate_connection() is True
        mock_tr._client.session_stats.assert_called_once()


# --- Factory ---

class TestCreateBackend:
    def test_torbox(self):
        config = MagicMock()
        config.download_method = "torbox"
        config.torbox_api_key = "test-key"
        with patch("sevenseas.core.torbox.TorboxApi"):
            backend = create_backend(config)
        assert isinstance(backend, TorboxBackend)

    def test_torbox_no_key(self):
        config = MagicMock()
        config.download_method = "torbox"
        config.torbox_api_key = None
        assert create_backend(config) is None

    def test_qbittorrent(self):
        config = MagicMock()
        config.download_method = "qbittorrent"
        config.bt_host = "192.168.1.10"
        config.bt_port = "8080"
        config.bt_username = "admin"
        config.bt_password = "pass"
        backend = create_backend(config)
        assert isinstance(backend, QBittorrentBackend)

    def test_transmission(self):
        config = MagicMock()
        config.download_method = "transmission"
        config.bt_host = ""
        config.bt_port = ""
        config.bt_username = ""
        config.bt_password = ""
        backend = create_backend(config)
        assert isinstance(backend, TransmissionBackend)

    def test_unknown_method(self):
        config = MagicMock()
        config.download_method = "deluge"
        assert create_backend(config) is None
