"""Tests for the download manager / pipeline orchestrator."""

import pytest
from unittest.mock import MagicMock, patch

from sevenseas.core.downloader import DownloadManager, DownloadState


@pytest.fixture
def deps():
    """Mock all dependencies."""
    return {
        "db": MagicMock(),
        "backend": MagicMock(),
        "extractor": MagicMock(),
        "installer": MagicMock(),
        "library": MagicMock(),
        "steam": MagicMock(),
        "config": MagicMock(),
    }


@pytest.fixture
def manager(deps):
    deps["config"].games_dir = "/tmp/Games"
    deps["config"].auto_add_steam = True
    return DownloadManager(**deps)


def test_initial_state(manager):
    assert manager.active_download is None
    assert manager.queue == []


def test_enqueue_download(manager, deps):
    game = MagicMock(id=1, title="Test", slug="test")
    deps["library"].get_by_id.return_value = game
    with patch.object(manager, "_start_next"):
        manager.enqueue(game_id=1, magnet="magnet:?xt=urn:btih:abc")
    assert len(manager.queue) == 1
    assert manager.queue[0].game_id == 1


def test_enqueue_starts_if_idle(manager, deps):
    game = MagicMock(id=1, title="Test", slug="test")
    deps["library"].get_by_id.return_value = game
    with patch.object(manager, "_start_next") as mock_start:
        manager.enqueue(game_id=1, magnet="magnet:?xt=urn:btih:abc")
        mock_start.assert_called_once()


def test_download_state_transitions():
    """Verify the state enum values."""
    assert DownloadState.PENDING.value == "pending"
    assert DownloadState.DOWNLOADING.value == "downloading"
    assert DownloadState.PULLING.value == "pulling"
    assert DownloadState.EXTRACTING.value == "extracting"
    assert DownloadState.INSTALLING.value == "installing"
    assert DownloadState.COMPLETE.value == "complete"
    assert DownloadState.FAILED.value == "failed"


def test_on_progress_callback(manager, deps):
    """Test that progress callbacks are called."""
    callback = MagicMock()
    manager.on_progress(callback)
    from sevenseas.core.downloader import QueueItem
    item = QueueItem(game_id=1, magnet="magnet:test")
    manager._notify_progress(item)
    callback.assert_called_once_with(item)


def test_retry_succeeds_on_third_attempt(manager):
    """Retry should succeed if function succeeds within max_retries."""
    call_count = 0
    def flaky_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("Network error")
        return "success"

    with patch("sevenseas.core.downloader.time.sleep"):  # skip actual sleeping
        result = manager._retry(flaky_func, max_retries=3)
    assert result == "success"
    assert call_count == 3


def test_retry_raises_after_max_attempts(manager):
    """Retry should raise after exhausting all attempts."""
    def always_fail():
        raise ConnectionError("Network error")

    with patch("sevenseas.core.downloader.time.sleep"):
        with pytest.raises(ConnectionError):
            manager._retry(always_fail, max_retries=3)
