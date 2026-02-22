"""Steam non-Steam shortcut management."""

import logging
import os
import subprocess
import time
import zlib
from pathlib import Path

import vdf

log = logging.getLogger(__name__)

_STEAM_PROCS = ["steam", "steamwebhelper", "steam-runtime-launcher-service"]


class SteamShortcuts:
    """Add and remove non-Steam game shortcuts."""

    def __init__(self) -> None:
        self._userdata_dirs: list[Path] | None = None

    def _find_userdata_dirs(self) -> list[Path]:
        """Find all Steam userdata directories (deduplicated by resolved path)."""
        if self._userdata_dirs is not None:
            return self._userdata_dirs
        steam_paths = [
            Path.home() / ".steam" / "steam" / "userdata",
            Path.home() / ".local" / "share" / "Steam" / "userdata",
        ]
        seen: set[Path] = set()
        dirs = []
        for base in steam_paths:
            if base.exists():
                for user_dir in base.iterdir():
                    if user_dir.is_dir() and user_dir.name.isdigit():
                        config_dir = user_dir / "config"
                        resolved = config_dir.resolve()
                        if config_dir.exists() and resolved not in seen:
                            seen.add(resolved)
                            dirs.append(config_dir)
        self._userdata_dirs = dirs
        return dirs

    @staticmethod
    def generate_shortcut_id(app_name: str, exe_path: str) -> int:
        """Generate a deterministic shortcut ID from name + exe.

        Returns a signed int32 (as required by vdf binary format).
        """
        key = f"{exe_path}{app_name}"
        crc = zlib.crc32(key.encode("utf-8")) & 0xFFFFFFFF
        uid = (crc | 0x80000000) & 0xFFFFFFFF
        # Convert to signed int32 for vdf compatibility
        if uid >= 0x80000000:
            uid -= 0x100000000
        return uid

    @staticmethod
    def generate_artwork_id(app_name: str, exe_path: str) -> int:
        """Generate unsigned 32-bit ID used for artwork filenames."""
        key = f"{exe_path}{app_name}"
        crc = zlib.crc32(key.encode("utf-8")) & 0xFFFFFFFF
        return (crc | 0x80000000) & 0xFFFFFFFF

    def get_grid_dirs(self) -> list[Path]:
        """Return the grid artwork directories for all Steam users."""
        dirs = []
        for config_dir in self._find_userdata_dirs():
            grid_dir = config_dir / "grid"
            grid_dir.mkdir(exist_ok=True)
            dirs.append(grid_dir)
        return dirs

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
            # Skip if shortcut with same appid already exists
            if any(v.get("appid") == shortcut_id for v in existing.values()):
                continue
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

    # --- Proton / Compat Tool support ---

    def _find_steam_root(self) -> Path | None:
        """Find the Steam root directory."""
        candidates = [
            Path.home() / ".steam" / "steam",
            Path.home() / ".local" / "share" / "Steam",
        ]
        for p in candidates:
            if p.exists() and (p / "config").is_dir():
                return p.resolve()
        return None

    def get_compat_tools(self) -> list[dict]:
        """Return available Proton/compat tools sorted by name.

        Each entry: {"name": internal_name, "display_name": human_readable}
        """
        steam_root = self._find_steam_root()
        if not steam_root:
            return []

        tools: list[dict] = []
        seen: set[str] = set()

        # Custom compat tools from compatibilitytools.d
        compat_dir = steam_root / "compatibilitytools.d"
        if compat_dir.is_dir():
            for tool_dir in sorted(compat_dir.iterdir()):
                vdf_path = tool_dir / "compatibilitytool.vdf"
                if not vdf_path.is_file():
                    continue
                try:
                    with open(vdf_path) as f:
                        data = vdf.load(f)
                    for _key, info in data.get("compatibilitytools", {}).get("compat_tools", {}).items():
                        name = _key
                        display = info.get("display_name", name)
                        if name not in seen:
                            seen.add(name)
                            tools.append({"name": name, "display_name": display})
                except Exception:
                    continue

        # Built-in Proton versions from steamapps/common
        builtin_map = {
            "Proton - Experimental": "proton_experimental",
            "Proton Hotfix": "proton_hotfix",
            "Proton 10.0": "proton_10",
            "Proton 9.0 (Beta)": "proton_9",
        }
        common_dir = steam_root / "steamapps" / "common"
        if common_dir.is_dir():
            for display, internal in builtin_map.items():
                if (common_dir / display).is_dir() and internal not in seen:
                    seen.add(internal)
                    tools.append({"name": internal, "display_name": display})

        return tools

    def set_compat_tool(self, shortcut_id: int, tool_name: str) -> None:
        """Set the Proton compat tool for a non-Steam shortcut in config.vdf."""
        steam_root = self._find_steam_root()
        if not steam_root:
            return

        config_path = steam_root / "config" / "config.vdf"
        if not config_path.is_file():
            return

        try:
            with open(config_path) as f:
                data = vdf.load(f)
        except Exception:
            log.warning("Failed to read config.vdf")
            return

        # Navigate to CompatToolMapping, creating intermediate keys if needed
        store = data.setdefault("InstallConfigStore", {})
        software = store.setdefault("Software", {})
        valve = software.setdefault("Valve", {})
        steam = valve.setdefault("Steam", {})
        mapping = steam.setdefault("CompatToolMapping", {})

        # Use the unsigned shortcut ID as the key
        app_key = str(shortcut_id & 0xFFFFFFFF)
        mapping[app_key] = {
            "name": tool_name,
            "config": "",
            "priority": "250",
        }

        try:
            with open(config_path, "w") as f:
                vdf.dump(data, f, pretty=True)
            log.info("Set compat tool '%s' for shortcut %s", tool_name, app_key)
        except Exception as e:
            log.warning("Failed to write config.vdf: %s", e)

    # --- Redistributable / prefix bootstrap ---

    # Common redists to install into every new prefix.
    # Downloaded once to ~/.cache/seven-seas/redists/ and reused.
    _REDISTS = [
        {
            "name": "VC++ 2015-2022 x64",
            "url": "https://aka.ms/vs/17/release/vc_redist.x64.exe",
            "filename": "vc_redist.x64.exe",
        },
        {
            "name": "VC++ 2015-2022 x86",
            "url": "https://aka.ms/vs/17/release/vc_redist.x86.exe",
            "filename": "vc_redist.x86.exe",
        },
    ]

    def _find_wine_binary(self, tool_name: str) -> Path | None:
        """Find the wine64 binary for a given compat tool name."""
        steam_root = self._find_steam_root()
        if not steam_root:
            return None

        # Custom tools in compatibilitytools.d
        custom = steam_root / "compatibilitytools.d" / tool_name / "files" / "bin" / "wine64"
        if custom.is_file():
            return custom

        # Custom tools may use the internal name from the vdf, not the dir name.
        # Scan all dirs and match by vdf key.
        compat_dir = steam_root / "compatibilitytools.d"
        if compat_dir.is_dir():
            for tool_dir in compat_dir.iterdir():
                vdf_path = tool_dir / "compatibilitytool.vdf"
                if not vdf_path.is_file():
                    continue
                try:
                    with open(vdf_path) as f:
                        data = vdf.load(f)
                    for key in data.get("compatibilitytools", {}).get("compat_tools", {}):
                        if key == tool_name:
                            wine = tool_dir / "files" / "bin" / "wine64"
                            if wine.is_file():
                                return wine
                except Exception:
                    continue

        # Built-in Proton versions
        builtin_map = {
            "proton_experimental": "Proton - Experimental",
            "proton_hotfix": "Proton Hotfix",
            "proton_10": "Proton 10.0",
            "proton_9": "Proton 9.0 (Beta)",
        }
        folder = builtin_map.get(tool_name)
        if folder:
            wine = steam_root / "steamapps" / "common" / folder / "files" / "bin" / "wine64"
            if wine.is_file():
                return wine

        return None

    def install_redists(self, shortcut_id: int, tool_name: str) -> None:
        """Download common redists and install them into the game's Proton prefix."""
        steam_root = self._find_steam_root()
        if not steam_root:
            log.warning("Cannot install redists: Steam root not found")
            return

        wine = self._find_wine_binary(tool_name)
        if not wine:
            log.warning("Cannot install redists: wine64 not found for '%s'", tool_name)
            return

        # Ensure the wine binary is executable
        if not os.access(wine, os.X_OK):
            wine.chmod(wine.stat().st_mode | 0o755)

        # Prefix path
        app_id = str(shortcut_id & 0xFFFFFFFF)
        prefix = steam_root / "steamapps" / "compatdata" / app_id / "pfx"

        # Create prefix if it doesn't exist yet
        if not prefix.exists():
            prefix.mkdir(parents=True, exist_ok=True)
            log.info("Bootstrapping prefix %s with wineboot", prefix)
            env = {**os.environ, "WINEPREFIX": str(prefix)}
            subprocess.run(
                [str(wine), "wineboot", "--init"],
                env=env, capture_output=True, timeout=120, check=False,
            )

        # Cache directory for downloaded redists
        cache_dir = Path.home() / ".cache" / "seven-seas" / "redists"
        cache_dir.mkdir(parents=True, exist_ok=True)

        env = {**os.environ, "WINEPREFIX": str(prefix)}

        for redist in self._REDISTS:
            local = cache_dir / redist["filename"]
            # Download if not cached
            if not local.exists():
                log.info("Downloading %s", redist["name"])
                try:
                    import httpx
                    with httpx.stream("GET", redist["url"], follow_redirects=True, timeout=60.0) as r:
                        r.raise_for_status()
                        with open(local, "wb") as f:
                            for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                                f.write(chunk)
                    log.info("Cached %s (%d bytes)", redist["name"], local.stat().st_size)
                except Exception as e:
                    log.warning("Failed to download %s: %s", redist["name"], e)
                    continue

            # Install silently
            log.info("Installing %s into prefix %s", redist["name"], app_id)
            try:
                result = subprocess.run(
                    [str(wine), str(local), "/install", "/quiet", "/norestart"],
                    env=env, capture_output=True, timeout=300, check=False,
                )
                log.info("%s install finished (exit %d)", redist["name"], result.returncode)
            except subprocess.TimeoutExpired:
                log.warning("%s install timed out", redist["name"])
            except Exception as e:
                log.warning("%s install failed: %s", redist["name"], e)

    @staticmethod
    def _steam_pids_alive() -> bool:
        """Check if any Steam-related processes are still running."""
        for proc in _STEAM_PROCS:
            result = subprocess.run(
                ["pgrep", "-x", proc],
                capture_output=True, check=False,
            )
            if result.returncode == 0:
                return True
        return False

    @staticmethod
    def restart() -> None:
        """Restart Steam so it picks up shortcut/config changes."""
        try:
            # Ask Steam to shut down gracefully
            subprocess.run(["steam", "-shutdown"], timeout=10,
                           capture_output=True, check=False)

            # Wait for ALL Steam processes to fully exit — main client,
            # steamwebhelper, steam-runtime-launcher-service, crashpad
            # handlers, zygote children, audio/network utility workers.
            # Using pgrep -f to catch everything with "steam" in its
            # command line, not just exact binary name matches.
            for _ in range(20):
                if not SteamShortcuts._steam_pids_alive():
                    break
                time.sleep(1)
            else:
                # Still running after 20s — SIGTERM the stragglers
                log.warning("Steam processes still alive after 20s, sending SIGTERM")
                for proc in _STEAM_PROCS:
                    subprocess.run(["pkill", "-x", proc],
                                   capture_output=True, check=False)
                # Give SIGTERM a few seconds to work
                for _ in range(5):
                    if not SteamShortcuts._steam_pids_alive():
                        break
                    time.sleep(1)
                else:
                    # Nuclear option — SIGKILL anything left
                    log.warning("Steam processes survived SIGTERM, sending SIGKILL")
                    for proc in _STEAM_PROCS:
                        subprocess.run(["pkill", "-9", "-x", proc],
                                       capture_output=True, check=False)
                    time.sleep(2)

            # Grace period for lock files / IPC sockets to be released
            time.sleep(3)
            # Relaunch in background
            subprocess.Popen(
                ["steam", "-silent"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            log.info("Steam restarted to pick up shortcut changes")
        except Exception as e:
            log.warning("Failed to restart Steam: %s", e)
