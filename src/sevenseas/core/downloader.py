"""Download manager — orchestrates the full install pipeline."""

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import httpx

log = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds


class DownloadState(Enum):
    PENDING = "pending"
    TORBOX_DOWNLOADING = "torbox_downloading"
    PULLING = "pulling"
    EXTRACTING = "extracting"
    INSTALLING = "installing"
    MOVING = "moving"
    ADDING_TO_STEAM = "adding_to_steam"
    INSTALLING_REDISTS = "installing_redists"
    FETCHING_ART = "fetching_art"
    RESTARTING_STEAM = "restarting_steam"
    CLEANING_UP = "cleaning_up"
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
        self._cancelled: set[int] = set()
        self._retry_install: set[int] = set()
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
        if self._is_cancelled(item):
            return
        for cb in self._on_progress:
            cb(item)

    def _notify_complete(self, item: QueueItem) -> None:
        for cb in self._on_complete:
            cb(item)

    def _notify_error(self, item: QueueItem) -> None:
        for cb in self._on_error:
            cb(item)

    def request_reinstall(self, game_id: int) -> None:
        """Flag that the installer should re-run after current run finishes."""
        self._retry_install.add(game_id)
        log.info("Reinstall requested for game_id=%d", game_id)

    def cancel(self, game_id: int) -> None:
        """Cancel a download by game_id."""
        self._cancelled.add(game_id)
        # Remove from queue if still pending
        self.queue = [q for q in self.queue if q.game_id != game_id]
        log.info("Cancelled download for game_id=%d", game_id)

    def _is_cancelled(self, item: QueueItem) -> bool:
        return item.game_id in self._cancelled

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

    def _check_cancelled(self, item: QueueItem) -> None:
        """Raise if the download has been cancelled."""
        if self._is_cancelled(item):
            raise RuntimeError("Download cancelled")

    def _process_item(self, item: QueueItem) -> None:
        """Run the full pipeline for one queue item."""
        try:
            # Step 1: Send to Torbox
            log.info("Starting pipeline for game_id=%d", item.game_id)
            item.state = DownloadState.TORBOX_DOWNLOADING
            self._library.update_status(item.game_id, "downloading")
            item.torbox_id = self._torbox.create_torrent(item.magnet)
            log.info("Torbox torrent created: torbox_id=%s", item.torbox_id)
            self._notify_progress(item)

            # Step 2: Poll until Torbox has the file
            self._poll_torbox(item)
            self._check_cancelled(item)

            # Step 3: Pull file from Torbox CDN
            item.state = DownloadState.PULLING
            self._notify_progress(item)
            local_path = self._pull_from_torbox(item)
            self._check_cancelled(item)

            # Step 4: Extract
            item.state = DownloadState.EXTRACTING
            self._library.update_status(item.game_id, "extracting")
            self._notify_progress(item)
            extract_dir = local_path + "_extracted"
            self._extractor.extract(local_path, extract_dir)
            self._check_cancelled(item)

            game = self._library.get_by_id(item.game_id)
            dir_name = self._clean_dir_name(game.title)
            log.info("Cleaned dir name: '%s' (from '%s')", dir_name, game.title)

            # Step 5: Find and run installer
            self._check_cancelled(item)
            item.state = DownloadState.INSTALLING
            self._library.update_status(item.game_id, "installing")
            self._notify_progress(item)
            setup_exe = self._extractor.find_setup_exe(extract_dir)
            used_bottles = False
            if setup_exe:
                log.info("Found setup exe: %s — running through Bottles", setup_exe)
                self._installer.ensure_bottle()
                # Use /DIR to force install into a known location inside drive_c
                install_dir = f"C:\\Games\\{dir_name}"

                # Loop: run installer, check if retry was requested, repeat
                while True:
                    self._installer.run_installer(setup_exe, extra_args=[f'/DIR="{install_dir}"'])
                    used_bottles = True
                    self._check_cancelled(item)
                    if item.game_id not in self._retry_install:
                        break
                    # Retry requested — clear flag and re-run
                    self._retry_install.discard(item.game_id)
                    log.info("Re-running installer for game_id=%d (retry requested)", item.game_id)
                    self._notify_progress(item)

            # Step 6: Move to games dir
            item.state = DownloadState.MOVING
            self._notify_progress(item)
            game_dir = extract_dir
            if used_bottles:
                installed_path = self._installer.find_installed_game()
                if installed_path:
                    log.info("Using Bottles install path: %s", installed_path)
                    game_dir = installed_path
                else:
                    log.warning("Could not find game in Bottles prefix, using extract dir")
            dest = self._installer.move_to_games_dir(
                game_dir, dir_name, self._config.games_dir,
            )
            self._library.update_game(item.game_id, install_path=dest)

            # Step 7: Add to Steam (non-fatal — don't fail the install over this)
            try:
                exe = self._find_game_exe(dest)
                if exe:
                    exe_full = os.path.join(dest, exe)
                    self._library.update_game(item.game_id, exe_path=exe)
                if exe and self._config.auto_add_steam:
                    item.state = DownloadState.ADDING_TO_STEAM
                    self._notify_progress(item)
                    launch_opts = self._build_launch_options(dest)
                    shortcut_id = self._steam.add_shortcut(
                        dir_name, exe_full, dest,
                        launch_options=launch_opts,
                    )
                    if shortcut_id:
                        self._library.update_game(
                            item.game_id, steam_shortcut_id=shortcut_id,
                        )
                        # Always set Proton — every imported game is a Windows exe
                        proton = self._config.proton_version or "proton_experimental"
                        self._steam.set_compat_tool(shortcut_id, proton)
                        # Install common redists (VC++, etc.) into the prefix
                        item.state = DownloadState.INSTALLING_REDISTS
                        self._notify_progress(item)
                        self._steam.install_redists(shortcut_id, proton)
                        # Fetch artwork from SteamGridDB
                        if self._config.steamgriddb_api_key:
                            item.state = DownloadState.FETCHING_ART
                            self._notify_progress(item)
                            self._fetch_steam_artwork(
                                game.title,
                                shortcut_id=shortcut_id,
                            )
                    # Restart Steam so it picks up the new shortcut
                    item.state = DownloadState.RESTARTING_STEAM
                    self._notify_progress(item)
                    self._steam.restart()
            except Exception as e:
                log.warning("Steam shortcut failed for game_id=%d: %s (non-fatal)", item.game_id, e)

            # Cleanup temp files
            item.state = DownloadState.CLEANING_UP
            self._notify_progress(item)
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
                if os.path.isdir(extract_dir):
                    import shutil
                    shutil.rmtree(extract_dir)
                log.info("Cleaned up temp files for game_id=%d", item.game_id)
            except Exception as e:
                log.warning("Failed to clean temp files: %s (non-fatal)", e)

            # Done
            item.state = DownloadState.COMPLETE
            item.progress = 1.0
            self._library.update_status(item.game_id, "installed")
            self._notify_complete(item)

        except Exception as e:
            log.exception("Pipeline failed for game_id=%d: %s", item.game_id, e)
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
        while True:
            status = self._torbox.check_status(item.torbox_id)
            if status is None:
                log.error("Torrent %s not found on Torbox", item.torbox_id)
                raise RuntimeError(f"Torrent {item.torbox_id} not found on Torbox")
            log.debug("Poll torbox_id=%s: state=%s progress=%.1f%%",
                       item.torbox_id, status.state, status.progress * 100)
            item.progress = status.progress
            item.speed_bps = status.speed_bps
            self._notify_progress(item)
            if status.progress >= 1.0:
                break
            if self._is_cancelled(item):
                raise RuntimeError("Download cancelled")
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
        """Download all torrent files from Torbox CDN as a zip with retry."""
        url = self._torbox.get_download_url(item.torbox_id, zip_link=True)
        cache_dir = os.path.expanduser("~/.cache/seven-seas")
        os.makedirs(cache_dir, exist_ok=True)
        local_path = os.path.join(cache_dir, f"download_{item.game_id}.zip")

        def do_download():
            with httpx.stream("GET", url, follow_redirects=True, timeout=300.0) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                with open(local_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        if self._is_cancelled(item):
                            raise RuntimeError("Download cancelled")
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            item.progress = downloaded / total
                        self._notify_progress(item)
            log.info("Downloaded %d bytes to %s", downloaded, local_path)
            return local_path

        return self._retry(do_download)

    @staticmethod
    def _clean_dir_name(title: str) -> str:
        """Turn a raw FitGirl title into a safe, clean directory name.

        Strips version/build/DLC suffixes and illegal filesystem characters.
        """
        # Reuse the search-title cleaner to strip version/edition junk
        name = DownloadManager._clean_title_for_search(title)
        # Strip DLC counts like "+ 2 DLCs", "+ All DLCs"
        name = re.sub(r"\s*\+\s*(?:\d+\s+)?DLCs?\b.*$", "", name, flags=re.IGNORECASE).strip()
        # Remove characters illegal on common filesystems: / \ : * ? " < > |
        name = re.sub(r'[\\/:*?"<>|]', "", name)
        # Collapse dashes/en-dashes/em-dashes with surrounding spaces
        name = re.sub(r"\s*[–—]\s*", " - ", name)
        # Collapse multiple spaces
        name = re.sub(r"\s{2,}", " ", name).strip()
        # Final fallback — if everything was stripped, use the slug-style title
        return name or re.sub(r"[^a-zA-Z0-9 ]", "", title).strip() or "game"

    @staticmethod
    def _clean_title_for_search(title: str) -> str:
        """Strip FitGirl version/build suffixes for cleaner SteamGridDB searches."""
        # Remove version suffixes like "– v1.0.9", ", Build MS19.5738", "+ 2 DLCs"
        clean = re.sub(r"\s*[,–—-]\s*(?:v[\d.].*|Build\s.*)$", "", title).strip()
        # Remove DLC/edition info in parentheses if it includes version
        clean = re.sub(r"\s*\(.*?v[\d.].*?\)\s*$", "", clean).strip()
        # Remove trailing edition markers that come after a dash
        clean = re.sub(r"\s*[–—-]\s*(?:Deluxe|Ultimate|Gold|GOTY|Complete).*$", "", clean, flags=re.IGNORECASE).strip()
        return clean or title

    def _fetch_steam_artwork(self, game_title: str, shortcut_id: int) -> None:
        """Fetch and save artwork from SteamGridDB for a Steam shortcut."""
        from sevenseas.core.steamgriddb import SteamGridDBClient

        try:
            sgdb = SteamGridDBClient(api_key=self._config.steamgriddb_api_key)
            clean_title = self._clean_title_for_search(game_title)
            log.info("SteamGridDB: searching for '%s' (cleaned from '%s')", clean_title, game_title)
            results = sgdb.search_game(clean_title)
            if not results:
                log.info("SteamGridDB: no results for '%s'", clean_title)
                return

            game_id = results[0]["id"]
            steam_appid = sgdb.get_steam_appid(clean_title)
            urls = sgdb.get_artwork_urls(game_id, steam_appid=steam_appid)
            artwork_id = shortcut_id & 0xFFFFFFFF
            grid_dirs = self._steam.get_grid_dirs()

            filename_map = {
                "grid": f"{artwork_id}p",
                "hero": f"{artwork_id}_hero",
                "logo": f"{artwork_id}_logo",
                "icon": f"{artwork_id}_icon",
            }

            for art_type, url in urls.items():
                if not url:
                    continue
                ext = ".png" if url.lower().endswith(".png") else ".jpg"
                for grid_dir in grid_dirs:
                    dest = os.path.join(str(grid_dir), f"{filename_map[art_type]}{ext}")
                    sgdb.download_image(url, dest)

            log.info("SteamGridDB: saved artwork for '%s' (sgdb_id=%d, art_id=%d)", clean_title, game_id, artwork_id)
        except Exception as e:
            log.warning("SteamGridDB artwork fetch failed for '%s': %s (non-fatal)", game_title, e)

    def _find_game_exe(self, directory: str) -> str | None:
        """Find the main game executable using scoring heuristics."""
        exclude = {
            "setup.exe", "install.exe", "uninstall.exe", "unins000.exe",
            "unins001.exe", "vc_redist.x64.exe", "vc_redist.x86.exe",
            "vcredist_x64.exe", "vcredist_x86.exe", "dxsetup.exe",
            "dxwebsetup.exe", "quicksfv.exe", "dotnetfx35.exe",
            "crashreporter.exe", "crashhandler.exe",
        }
        # Patterns that indicate non-game utility exes
        deprioritize = {
            "error", "crash", "report", "update", "launcher", "helper",
            "redist", "dotnet", "directx", "diagnos", "repair", "patch",
            "benchmark", "server", "dedicat", "editor", "tool", "config",
            "setting", "uninst",
        }

        candidates: list[tuple[int, str]] = []
        for root, _dirs, files in os.walk(directory):
            depth = root.replace(directory, "").count(os.sep)
            for f in files:
                low = f.lower()
                if not low.endswith(".exe") or low in exclude:
                    continue
                full = os.path.join(root, f)
                # Skip symlinks that escape the game directory
                if not os.path.realpath(full).startswith(os.path.realpath(directory)):
                    continue
                rel = os.path.relpath(full, directory)
                # Skip exes in _Redist / redist / support subdirs
                if any(part.lower() in ("_redist", "redist", "support", "__support")
                       for part in rel.split(os.sep)[:-1]):
                    continue

                score = 0
                # Prefer root-level exes
                score -= depth * 10
                # Prefer larger files (game exe >> utility exe)
                try:
                    size = os.path.getsize(full)
                    score += min(size // (1024 * 1024), 100)  # +1 per MB, cap 100
                except OSError:
                    pass
                # Deprioritize utility-like names
                stem = low.removesuffix(".exe")
                if any(p in stem for p in deprioritize):
                    score -= 50

                candidates.append((score, rel))

        if not candidates:
            return None
        # Highest score wins
        candidates.sort(key=lambda x: x[0], reverse=True)
        log.info("Exe candidates: %s", [(s, r) for s, r in candidates[:5]])
        return candidates[0][1]

    @staticmethod
    def _build_launch_options(game_dir: str) -> str:
        """Build Proton launch options based on game contents.

        Detects engine type and known DLL requirements to set
        WINEDLLOVERRIDES and other env vars automatically.
        """
        dll_overrides: list[str] = []

        # Collect all filenames in the game directory (top-level + one level deep)
        all_files: set[str] = set()
        for entry in os.listdir(game_dir):
            all_files.add(entry.lower())
            subdir = os.path.join(game_dir, entry)
            if os.path.isdir(subdir):
                for sub in os.listdir(subdir):
                    all_files.add(sub.lower())

        # Note: we do NOT auto-override d3d12.dll — many repacks repurpose it
        # as an offline emulation shim. Forcing builtin (=b) would block the
        # crack from running. Games with genuine Agility SDK conflicts need
        # the override added manually via Steam launch options.

        # Unity IL2CPP / Mono — needs coremessaging disabled
        is_unity = (
            "gameassembly.dll" in all_files
            or "unityplayer.dll" in all_files
        )
        if is_unity:
            dll_overrides.append("coremessaging=d")
            log.info("Detected Unity engine — adding coremessaging=d override")

        # Unreal Engine — xactengine/xaudio often need native overrides
        is_unreal = any(
            f.startswith("engine") and f.endswith(".dll")
            for f in all_files
        ) or "ue4-shootergame.exe" in all_files
        if is_unreal and any(f.startswith("xact") for f in all_files):
            dll_overrides.append("xactengine3_7=n,b")
            log.info("Detected Unreal + xact — adding xactengine override")

        if not dll_overrides:
            return "%command%"

        overrides = ";".join(dll_overrides)
        return f'WINEDLLOVERRIDES="{overrides}" %command%'
