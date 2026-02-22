"""Bottles CLI integration for running Windows installers."""

import logging
import os
import shutil
import subprocess

log = logging.getLogger(__name__)


class InstallError(Exception):
    """Raised when a Bottles installation step fails."""


class BottlesInstaller:
    """Manages game installation through Bottles (Wine prefix manager)."""

    def __init__(self, bottle_name: str = "7seas-installer") -> None:
        self._bottle_name = bottle_name
        self._cached_bottles_cmd: list[str] | None = None

    def _bottles_cmd(self) -> list[str]:
        """Determine the correct bottles-cli invocation (cached after first call)."""
        if self._cached_bottles_cmd is not None:
            return self._cached_bottles_cmd
        if shutil.which("bottles-cli"):
            self._cached_bottles_cmd = ["bottles-cli"]
            return self._cached_bottles_cmd
        # Try flatpak
        try:
            result = subprocess.run(
                ["flatpak", "run", "--command=bottles-cli",
                 "com.usebottles.bottles", "list", "bottles"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                self._cached_bottles_cmd = [
                    "flatpak", "run", "--command=bottles-cli",
                    "com.usebottles.bottles",
                ]
                return self._cached_bottles_cmd
        except FileNotFoundError:
            pass
        self._cached_bottles_cmd = ["bottles-cli"]
        return self._cached_bottles_cmd

    def ensure_bottle(self) -> None:
        """Create the installer bottle if it doesn't already exist."""
        cmd = self._bottles_cmd()
        result = subprocess.run(
            cmd + ["list", "bottles"],
            capture_output=True, text=True,
        )
        if self._bottle_name in result.stdout:
            log.info("Bottle '%s' already exists", self._bottle_name)
            return
        log.info("Creating bottle '%s'", self._bottle_name)
        result = subprocess.run(
            cmd + ["new", "--bottle-name", self._bottle_name,
                   "--environment", "gaming"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise InstallError(f"Failed to create bottle: {result.stderr}")

    def run_installer(
        self, exe_path: str, extra_args: list[str] | None = None,
        proc_callback=None,
    ) -> bool:
        """Run an .exe installer through Bottles.

        Args:
            proc_callback: If provided, called with the Popen object so the
                           caller can kill the process for cancellation.
        """
        cmd = self._bottles_cmd()
        args = cmd + ["run", "-b", self._bottle_name, "-e", exe_path]
        if extra_args:
            args.extend(["--", *extra_args])
        log.info("Running installer: %s", " ".join(args))
        # FitGirl repacks decompress heavily compressed data and can
        # take 1-2+ hours for large games.  4-hour timeout.
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc_callback:
            proc_callback(proc)
        try:
            stdout, stderr = proc.communicate(timeout=14400)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            raise
        log.info("Installer stdout: %s", stdout[-500:] if stdout else "")
        log.info("Installer stderr: %s", stderr[-500:] if stderr else "")
        if proc.returncode != 0:
            raise InstallError(
                f"Bottles installer failed (code {proc.returncode}): {stderr}"
            )
        return True

    def find_installed_game(self) -> str | None:
        """Find the most recently installed game directory in the Bottles prefix.

        Scans common install locations in drive_c for non-system directories
        that contain game executables.
        """
        bottle_dir = self._get_bottle_dir()
        if not bottle_dir:
            return None
        drive_c = os.path.join(bottle_dir, "drive_c")
        if not os.path.isdir(drive_c):
            return None

        # System directories to skip
        system_dirs = {
            "windows", "programdata", "users",
            "common files", "internet explorer",
            "windows media player", "windows nt",
        }

        candidates = []
        for search_dir in [
            os.path.join(drive_c, "Games"),
            os.path.join(drive_c, "Program Files"),
            os.path.join(drive_c, "Program Files (x86)"),
            drive_c,
        ]:
            if not os.path.isdir(search_dir):
                continue
            for entry in os.listdir(search_dir):
                full = os.path.join(search_dir, entry)
                if not os.path.isdir(full):
                    continue
                if entry.lower() in system_dirs:
                    continue
                # Check if this directory has any .exe files
                has_exe = any(
                    f.lower().endswith(".exe")
                    for _r, _d, files in os.walk(full)
                    for f in files
                )
                if has_exe:
                    mtime = os.path.getmtime(full)
                    candidates.append((mtime, full))

        if candidates:
            candidates.sort(reverse=True)
            log.info("Found installed game at: %s", candidates[0][1])
            return candidates[0][1]
        return None

    def _get_bottle_dir(self) -> str | None:
        """Find the bottle directory on disk."""
        # Standard Bottles locations
        paths = [
            os.path.expanduser(
                f"~/.var/app/com.usebottles.bottles/data/bottles/bottles/{self._bottle_name}"
            ),
            os.path.expanduser(
                f"~/.local/share/bottles/bottles/{self._bottle_name}"
            ),
        ]
        for p in paths:
            if os.path.isdir(p):
                return p
        return None

    def move_to_games_dir(
        self, source_dir: str, game_name: str, games_base: str
    ) -> str:
        """Move installed files to the games directory."""
        os.makedirs(games_base, exist_ok=True)
        dest = os.path.join(games_base, game_name)
        # Prevent path traversal
        if not os.path.realpath(dest).startswith(os.path.realpath(games_base)):
            raise ValueError(f"Invalid game name: {game_name}")
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(source_dir, dest)
        log.info("Copied game files from %s to %s", source_dir, dest)
        return dest
