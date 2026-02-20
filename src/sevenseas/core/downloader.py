"""Download manager — orchestrates the full install pipeline."""

import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import httpx

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds


class DownloadState(Enum):
    PENDING = "pending"
    TORBOX_DOWNLOADING = "torbox_downloading"
    PULLING = "pulling"
    EXTRACTING = "extracting"
    INSTALLING = "installing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class QueueItem:
    game_id: int
    magnet: str
    torbox_id: int | None = None
    state: DownloadState = DownloadState.PENDING
    progress: float = 0.0
    speed_bps: int = 0
    error: str | None = None


class DownloadManager:
    """Manages the download queue and orchestrates the install pipeline."""

    def __init__(self, db, torbox, extractor, installer, library, steam, config):
        self._db = db
        self._torbox = torbox
        self._extractor = extractor
        self._installer = installer
        self._library = library
        self._steam = steam
        self._config = config
        self.queue: list[QueueItem] = []
        self.active_download: QueueItem | None = None
        self._on_progress: list[Callable] = []
        self._on_complete: list[Callable] = []
        self._on_error: list[Callable] = []

    def on_progress(self, callback: Callable) -> None:
        self._on_progress.append(callback)

    def on_complete(self, callback: Callable) -> None:
        self._on_complete.append(callback)

    def on_error(self, callback: Callable) -> None:
        self._on_error.append(callback)

    def _notify_progress(self, item: QueueItem) -> None:
        for cb in self._on_progress:
            cb(item)

    def _notify_complete(self, item: QueueItem) -> None:
        for cb in self._on_complete:
            cb(item)

    def _notify_error(self, item: QueueItem) -> None:
        for cb in self._on_error:
            cb(item)

    def enqueue(self, game_id: int, magnet: str) -> QueueItem:
        """Add a game to the download queue."""
        item = QueueItem(game_id=game_id, magnet=magnet)
        self.queue.append(item)
        # Record in DB
        self._db.execute(
            "INSERT INTO downloads (game_id, magnet_uri, status) VALUES (?, ?, ?)",
            (game_id, magnet, "pending"),
        )
        self._db.commit()
        if self.active_download is None:
            self._start_next()
        return item

    def _start_next(self) -> None:
        """Start processing the next item in the queue."""
        if not self.queue:
            self.active_download = None
            return
        item = self.queue[0]
        self.active_download = item
        thread = threading.Thread(target=self._process_item, args=(item,), daemon=True)
        thread.start()

    def _process_item(self, item: QueueItem) -> None:
        """Run the full pipeline for one queue item."""
        try:
            # Step 1: Send to Torbox
            item.state = DownloadState.TORBOX_DOWNLOADING
            self._library.update_status(item.game_id, "downloading")
            item.torbox_id = self._torbox.create_torrent(item.magnet)
            self._notify_progress(item)

            # Step 2: Poll until Torbox has the file
            self._poll_torbox(item)

            # Step 3: Pull file from Torbox CDN
            item.state = DownloadState.PULLING
            self._notify_progress(item)
            local_path = self._pull_from_torbox(item)

            # Step 4: Extract
            item.state = DownloadState.EXTRACTING
            self._library.update_status(item.game_id, "extracting")
            self._notify_progress(item)
            extract_dir = local_path + "_extracted"
            self._extractor.extract(local_path, extract_dir)

            # Step 5: Find and run installer
            item.state = DownloadState.INSTALLING
            self._library.update_status(item.game_id, "installing")
            self._notify_progress(item)
            setup_exe = self._extractor.find_setup_exe(extract_dir)
            if setup_exe:
                self._installer.ensure_bottle()
                self._installer.run_installer(setup_exe, ["/S"])

            # Step 6: Move to games dir
            game = self._library.get_by_id(item.game_id)
            dest = self._installer.move_to_games_dir(
                extract_dir, game.title, self._config.games_dir,
            )
            self._library.update_game(item.game_id, install_path=dest)

            # Step 7: Add to Steam
            if self._config.auto_add_steam:
                exe = self._find_game_exe(dest)
                if exe:
                    self._library.update_game(item.game_id, exe_path=exe)
                    shortcut_id = self._steam.add_shortcut(
                        game.title, os.path.join(dest, exe), dest,
                    )
                    if shortcut_id:
                        self._library.update_game(
                            item.game_id, steam_shortcut_id=shortcut_id,
                        )

            # Done
            item.state = DownloadState.COMPLETE
            item.progress = 1.0
            self._library.update_status(item.game_id, "installed")
            self._notify_complete(item)

        except Exception as e:
            item.state = DownloadState.FAILED
            item.error = str(e)
            self._library.update_status(item.game_id, "failed")
            self._notify_error(item)

        finally:
            if item in self.queue:
                self.queue.remove(item)
            self.active_download = None
            self._start_next()

    def _poll_torbox(self, item: QueueItem) -> None:
        """Poll Torbox until the torrent is complete."""
        import time
        while True:
            status = self._torbox.check_status(item.torbox_id)
            if status is None:
                raise RuntimeError(f"Torrent {item.torbox_id} not found on Torbox")
            item.progress = status.progress
            item.speed_bps = status.speed_bps
            self._notify_progress(item)
            if status.progress >= 1.0:
                break
            time.sleep(3)

    def _retry(self, func, max_retries=MAX_RETRIES):
        """Retry a function with exponential backoff."""
        last_error = None
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                    time.sleep(wait)
        raise last_error

    def _pull_from_torbox(self, item: QueueItem) -> str:
        """Download the file from Torbox CDN to local cache with retry."""
        url = self._torbox.get_download_url(item.torbox_id, file_id=0)
        cache_dir = os.path.expanduser("~/.cache/seven-seas")
        os.makedirs(cache_dir, exist_ok=True)
        local_path = os.path.join(cache_dir, f"download_{item.game_id}")

        def do_download():
            with httpx.stream("GET", url) as response:
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                with open(local_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            item.progress = downloaded / total
                        self._notify_progress(item)
            return local_path

        return self._retry(do_download)

    def _find_game_exe(self, directory: str) -> str | None:
        """Find the main game executable (heuristic)."""
        exclude = {
            "setup.exe", "install.exe", "uninstall.exe", "unins000.exe",
            "vc_redist.x64.exe", "vc_redist.x86.exe", "dxsetup.exe",
        }
        for root, _dirs, files in os.walk(directory):
            for f in files:
                if f.lower().endswith(".exe") and f.lower() not in exclude:
                    return os.path.relpath(os.path.join(root, f), directory)
        return None
