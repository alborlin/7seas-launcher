"""Steam non-Steam shortcut management."""

import os
import zlib
from pathlib import Path

import vdf


class SteamShortcuts:
    """Add and remove non-Steam game shortcuts."""

    def __init__(self) -> None:
        self._userdata_dirs: list[Path] | None = None

    def _find_userdata_dirs(self) -> list[Path]:
        """Find all Steam userdata directories."""
        if self._userdata_dirs is not None:
            return self._userdata_dirs
        steam_paths = [
            Path.home() / ".steam" / "steam" / "userdata",
            Path.home() / ".local" / "share" / "Steam" / "userdata",
        ]
        dirs = []
        for base in steam_paths:
            if base.exists():
                for user_dir in base.iterdir():
                    if user_dir.is_dir() and user_dir.name.isdigit():
                        config_dir = user_dir / "config"
                        if config_dir.exists():
                            dirs.append(config_dir)
        self._userdata_dirs = dirs
        return dirs

    @staticmethod
    def generate_shortcut_id(app_name: str, exe_path: str) -> int:
        """Generate a deterministic shortcut ID from name + exe."""
        key = f"{exe_path}{app_name}"
        crc = zlib.crc32(key.encode("utf-8")) & 0xFFFFFFFF
        return (crc | 0x80000000) & 0xFFFFFFFF

    @staticmethod
    def build_shortcut_entry(
        app_name: str,
        exe_path: str,
        start_dir: str,
        shortcut_id: int,
        launch_options: str = "",
    ) -> dict:
        """Build a shortcut entry dict for vdf serialization."""
        return {
            "appid": shortcut_id,
            "AppName": app_name,
            "Exe": f'"{exe_path}"',
            "StartDir": f'"{start_dir}"',
            "icon": "",
            "ShortcutPath": "",
            "LaunchOptions": launch_options,
            "IsHidden": 0,
            "AllowDesktopConfig": 1,
            "AllowOverlay": 1,
            "OpenVR": 0,
            "Devkit": 0,
            "DevkitGameID": "",
            "DevkitOverrideAppID": 0,
            "LastPlayTime": 0,
            "tags": {},
        }

    def add_shortcut(
        self,
        app_name: str,
        exe_path: str,
        start_dir: str,
        launch_options: str = "",
    ) -> int | None:
        """Add a non-Steam shortcut. Returns shortcut ID or None if Steam not found."""
        dirs = self._find_userdata_dirs()
        if not dirs:
            return None
        shortcut_id = self.generate_shortcut_id(app_name, exe_path)
        entry = self.build_shortcut_entry(
            app_name, exe_path, start_dir, shortcut_id, launch_options,
        )
        for config_dir in dirs:
            shortcuts_path = config_dir / "shortcuts.vdf"
            shortcuts = {"shortcuts": {}}
            if shortcuts_path.exists():
                with open(shortcuts_path, "rb") as f:
                    try:
                        shortcuts = vdf.binary_load(f)
                    except Exception:
                        shortcuts = {"shortcuts": {}}
            existing = shortcuts.get("shortcuts", {})
            next_idx = str(max((int(k) for k in existing), default=-1) + 1)
            existing[next_idx] = entry
            shortcuts["shortcuts"] = existing
            with open(shortcuts_path, "wb") as f:
                vdf.binary_dump(shortcuts, f)
        return shortcut_id

    def remove_shortcut(self, shortcut_id: int) -> None:
        """Remove a non-Steam shortcut by its ID."""
        for config_dir in self._find_userdata_dirs():
            shortcuts_path = config_dir / "shortcuts.vdf"
            if not shortcuts_path.exists():
                continue
            with open(shortcuts_path, "rb") as f:
                try:
                    shortcuts = vdf.binary_load(f)
                except Exception:
                    continue
            existing = shortcuts.get("shortcuts", {})
            to_remove = [
                k for k, v in existing.items()
                if v.get("appid") == shortcut_id
            ]
            for k in to_remove:
                del existing[k]
            shortcuts["shortcuts"] = existing
            with open(shortcuts_path, "wb") as f:
                vdf.binary_dump(shortcuts, f)
