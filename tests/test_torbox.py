"""Tests for Torbox API client -- uses mocked SDK responses."""

import pytest
from unittest.mock import MagicMock, patch

from sevenseas.core.torbox import TorboxClient, TorrentStatus


@pytest.fixture
def mock_sdk():
    sdk = MagicMock()
    return sdk


@pytest.fixture
def client(mock_sdk):
    with patch("sevenseas.core.torbox.TorboxApi", return_value=mock_sdk):
        return TorboxClient(api_key="test-key")


def test_create_torrent(client, mock_sdk):
    mock_sdk.torrents.create_torrent.return_value = MagicMock(
        data={"torrent_id": 42}
    )
    torbox_id = client.create_torrent("magnet:?xt=urn:btih:abc123")
    assert torbox_id == 42
    mock_sdk.torrents.create_torrent.assert_called_once()


def test_check_status(client, mock_sdk):
    mock_sdk.torrents.get_torrent_list.return_value = MagicMock(
        data=[{
            "id": 42,
            "download_state": "downloading",
            "progress": 0.5,
            "dlspeed": 1024000,
            "size": 5000000000,
            "name": "Test Game",
        }]
    )
    status = client.check_status(42)
    assert isinstance(status, TorrentStatus)
    assert status.progress == 0.5
    assert status.state == "downloading"
    assert status.speed_bps == 1024000


def test_check_status_returns_none_for_missing(client, mock_sdk):
    mock_sdk.torrents.get_torrent_list.return_value = MagicMock(data=[])
    status = client.check_status(9999)
    assert status is None


def test_get_download_url(client, mock_sdk):
    mock_sdk.torrents.request_download_link.return_value = MagicMock(
        data="https://cdn.torbox.app/dl/abc123"
    )
    url = client.get_download_url(42, file_id=0)
    assert url == "https://cdn.torbox.app/dl/abc123"


def test_check_cached_true(client, mock_sdk):
    mock_sdk.torrents.get_torrent_cached_availability.return_value = MagicMock(
        data={"abc123": {"name": "Test", "size": 100}}
    )
    assert client.check_cached("abc123") is True


def test_check_cached_false(client, mock_sdk):
    mock_sdk.torrents.get_torrent_cached_availability.return_value = MagicMock(data={})
    assert client.check_cached("abc123") is False


def test_validate_api_key_success(client, mock_sdk):
    mock_sdk.user.get_user_data.return_value = MagicMock(
        data={"email": "test@example.com"}
    )
    assert client.validate_api_key() is True


def test_validate_api_key_failure(client, mock_sdk):
    mock_sdk.user.get_user_data.side_effect = Exception("401 Unauthorized")
    assert client.validate_api_key() is False
