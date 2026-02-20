"""Bottles CLI integration for running Windows installers."""

import os
import shutil
import subprocess


class InstallError(Exception):
    """Raised when a Bottles installation step fails."""


class BottlesInstaller:
    """Manages game installation through Bottles (Wine prefix manager)."""

    def __init__(self, bottle_name: str = "7seas-installer") -> None:
        self._bottle_name = bottle_name

    def _bottles_cmd(self) -> list[str]:
        """Determine the correct bottles-cli invocation."""
        if shutil.which("bottles-cli"):
            return ["bottles-cli"]
        # Try flatpak
        try:
            result = subprocess.run(
                ["flatpak", "run", "--command=bottles-cli",
                 "com.usebottles.bottles", "--version"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                return [
                    "flatpak", "run", "--command=bottles-cli",
                    "com.usebottles.bottles",
                ]
        except FileNotFoundError:
            pass
        return ["bottles-cli"]

    def ensure_bottle(self) -> None:
        """Create the installer bottle if it doesn't already exist."""
        cmd = self._bottles_cmd()
        result = subprocess.run(
            cmd + ["list", "bottles", "-j"],
            capture_output=True, text=True,
        )
        if self._bottle_name in result.stdout:
            return
        result = subprocess.run(
            cmd + ["new", "--bottle-name", self._bottle_name,
                   "--environment", "gaming"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise InstallError(f"Failed to create bottle: {result.stderr}")

    def run_installer(
        self, exe_path: str, extra_args: list[str] | None = None
    ) -> bool:
        """Run an .exe installer through Bottles."""
        cmd = self._bottles_cmd()
        args = cmd + ["run", "-b", self._bottle_name, "-e", exe_path]
        if extra_args:
            args.extend(["-a", " ".join(extra_args)])
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            raise InstallError(
                f"Bottles installer failed (code {result.returncode}): {result.stderr}"
            )
        return True

    def move_to_games_dir(
        self, source_dir: str, game_name: str, games_base: str
    ) -> str:
        """Move installed files to the games directory."""
        dest = os.path.join(games_base, game_name)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(source_dir, dest)
        return dest
