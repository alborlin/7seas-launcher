# 7-Seas Launcher

A Linux desktop application for downloading game repacks via Torbox debrid, installing them through Bottles (Wine), and automatically registering them in Steam with artwork from SteamGridDB.

Built with GTK4 + Libadwaita. Nautical theme — navy background, gold accents, Pirata One font.

**App ID:** `com.sevenseas.Launcher`
**Entry point:** `seven-seas` (defined in `pyproject.toml`)

---

## Architecture Overview

```
User clicks Install
        |
        v
FitGirlScraper.get_detail() ─── fetches magnet URI from repack page
        |
        v
TorboxClient.create_torrent() ── sends magnet to Torbox cloud
        |  (poll every 3s)
        v
TorboxClient.get_download_url() ─ gets CDN link once seeded
        |
        v
httpx stream download ─────────── saves .zip to ~/.cache/seven-seas/
        |
        v
Extractor.extract() ──────────── 7z x to temp directory
        |
        v
BottlesInstaller.run_installer() ─ runs setup.exe in Wine prefix
        |
        v
move_to_games_dir() ──────────── copies from drive_c to ~/Games/
        |
        v
SteamShortcuts.add_shortcut() ── writes to shortcuts.vdf
SteamShortcuts.set_compat_tool() writes Proton config to config.vdf
SteamGridDBClient ────────────── downloads grid/hero/logo/icon art
SteamShortcuts.restart() ─────── restarts Steam to pick up changes
```

All pipeline steps run in a daemon thread. UI updates go through `GLib.idle_add()`. Steam-related steps are non-fatal — failures don't abort the install.

---

## Project Structure

```
src/sevenseas/
├── app.py                  # Adw.Application — startup, services, logging
├── core/
│   ├── config.py           # SQLite-backed key/value settings
│   ├── scraper.py          # FitGirl Repacks HTML scraper (httpx + BeautifulSoup)
│   ├── torbox.py           # Torbox debrid API client
│   ├── downloader.py       # Pipeline orchestrator + download queue
│   ├── extractor.py        # 7z archive extraction
│   ├── installer.py        # Bottles (Wine) CLI integration
│   ├── library.py          # Game library CRUD (SQLite)
│   ├── steam.py            # Steam shortcuts, Proton config, restart
│   └── steamgriddb.py      # SteamGridDB artwork fetcher
├── db/
│   └── models.py           # SQLite schema (4 tables)
└── ui/
    ├── window.py           # Main window, sidebar navigation, view routing
    ├── tray.py             # System tray (runs as subprocess — see below)
    ├── views/
    │   ├── browse.py       # New Releases / Top 50 / Top 150 (carousel + grid)
    │   ├── search.py       # Search bar + results
    │   ├── detail.py       # Full game detail page + Install button
    │   ├── downloads.py    # Active download progress list
    │   ├── library.py      # Installed games grid
    │   └── settings.py     # Configuration form
    └── widgets/
        ├── game_card.py    # Cover art card (185x185px)
        └── download_row.py # Progress bar + speed + stage label
```

---

## How Things Work

### Scraper (`core/scraper.py`)

Scrapes `fitgirl-repacks.site` using httpx + BeautifulSoup with lxml parser.

- `search(query)` — `/?s=query`
- `get_latest(page)` — `/category/lossless-repack/page/N/`
- `get_top_monthly()` / `get_top_yearly()` — parses Jetpack widget grids
- `get_detail(url)` — returns `GameDetail` with magnet, sizes, description, genres, sysreqs, screenshots

Screenshots are extracted from `<a>` tags wrapping `<img>` elements. Riotpixels `.240p.jpg` thumbnail suffixes are stripped to get full-size URLs. Donate buttons, icons, and small images are filtered out.

Descriptions come from `su-spoiler` / `sp-wrap` blocks (FitGirl's spoiler format), falling back to `<p>` tags before "System Requirements" / "How to Install" markers.

### Torbox (`core/torbox.py`)

Uses the official `torbox-api` SDK plus direct httpx calls for endpoints where the SDK has serialization bugs (status check, download URL request).

- `create_torrent(magnet)` — returns internal torrent ID
- `check_status(torbox_id)` — polls `/v1/api/torrents/mylist?id=N`
- `get_download_url(torbox_id, file_id, zip_link)` — gets CDN download link
- `check_cached(info_hash)` — checks if torrent is already on Torbox CDN
- `validate_api_key()` — confirms key works

### Download Pipeline (`core/downloader.py`)

Sequential queue — one download at a time. Each item goes through these states:

| State | Label in UI | What happens |
|---|---|---|
| `PENDING` | Queued | Waiting in queue |
| `TORBOX_DOWNLOADING` | Waiting on Torbox | Torbox cloud is seeding the torrent |
| `PULLING` | Downloading | Streaming .zip from Torbox CDN to local disk |
| `EXTRACTING` | Extracting | `7z x` the archive |
| `INSTALLING` | Running Installer | `bottles-cli run` the setup.exe |
| `MOVING` | Moving to Games | `shutil.copytree` to `~/Games/<title>` |
| `ADDING_TO_STEAM` | Adding to Steam | Writing shortcut + Proton config |
| `FETCHING_ART` | Pulling Media | SteamGridDB artwork download |
| `RESTARTING_STEAM` | Restarting Steam | `steam -shutdown` then `steam -silent` |
| `CLEANING_UP` | Cleaning Up | Delete temp archive + extract dir |
| `COMPLETE` | Complete | Done |
| `FAILED` | Failed | Error occurred |

**Exe finder heuristic:** Scores every `.exe` in the installed directory:
- `+1` per MB of file size (capped at +100)
- `-10` per directory depth level
- `-50` for utility-like names (crash, redist, update, helper, etc.)
- Skips files in `_Redist/`, `redist/`, `support/` subdirectories
- Skips known utility filenames (setup.exe, vc_redist, dxsetup, etc.)

**Launch options auto-detection:**
- Unity games (`gameassembly.dll` or `unityplayer.dll`): adds `WINEDLLOVERRIDES="coremessaging=d"`
- Unreal + XACT: adds `xactengine3_7=n,b`
- Otherwise: plain `%command%`

**Title cleaning for SteamGridDB:** Strips version suffixes (`– v1.0.9`, `, Build MS19.5738`), edition suffixes (`– Deluxe Edition`), and DLC counts (`+ 2 DLCs`).

**Retry logic:** 3 attempts with exponential backoff (`2^attempt` seconds).

### Steam Integration (`core/steam.py`)

**Shortcut IDs:** CRC32 of `"{exe_path}{app_name}"` ORed with `0x80000000`. Stored as signed int32 in binary VDF, unsigned for artwork filenames.

**Adding shortcuts:** Reads/writes `~/.steam/steam/userdata/<uid>/config/shortcuts.vdf` (binary VDF). Iterates all Steam user directories. Skips duplicates by checking `appid`.

**Proton config:** Writes to `~/.steam/steam/config/config.vdf` (text VDF) under `InstallConfigStore.Software.Valve.Steam.CompatToolMapping`. Always forces a Proton version — defaults to `proton_experimental` if none configured.

**Available Proton versions:** Scans `compatibilitytools.d/` for custom tools (GE-Proton, CachyOS Proton, etc.) and checks `steamapps/common/` for built-in versions.

**Artwork placement:** Images saved to `~/.steam/steam/userdata/<uid>/config/grid/`:
- `<art_id>p.jpg` — portrait grid (600x900)
- `<art_id>_hero.jpg` — hero banner
- `<art_id>_logo.png` — logo
- `<art_id>_icon.png` — icon

Where `art_id = shortcut_id & 0xFFFFFFFF`.

**Steam restart:** `steam -shutdown`, poll `pgrep -x steam` up to 15 seconds, then `steam -silent` in background.

### Tray Icon (`ui/tray.py`)

Runs as a **separate subprocess** because AyatanaAppIndicator3 is GTK3 and cannot coexist with GTK4 in the same process.

Communication via UNIX signals:
- "Show" menu item → `SIGUSR1` to parent PID → main window shows
- "Quit" menu item → `SIGTERM` to parent PID → app exits
- Tray polls `os.kill(parent_pid, 0)` every 2 seconds — self-terminates if parent dies

Window close hides to tray instead of quitting (calls `app.hold()` to keep the main loop alive). Downloads continue in the background.

### Bottles Integration (`core/installer.py`)

Auto-detects whether `bottles-cli` is available natively or via Flatpak (`com.usebottles.bottles`).

- `ensure_bottle()` — creates a `7seas-installer` gaming-type bottle if it doesn't exist
- `run_installer(exe_path)` — runs setup.exe with 30-minute timeout, passes `/DIR="C:\Games\<title>"` for silent install path
- `find_installed_game()` — scans `drive_c/Games/`, `drive_c/Program Files/`, `drive_c/Program Files (x86)/` for directories with `.exe` files
- `move_to_games_dir()` — copies from Wine prefix to `~/Games/<title>`

---

## Database

SQLite at `~/.local/share/seven-seas/sevenseas.db`. Four tables:

**`games`** — installed game library
- Status flow: `new` → `downloading` → `extracting` → `installing` → `installed` / `failed`
- Stores `install_path`, `exe_path`, `cover_url`, `steam_shortcut_id`, etc.

**`downloads`** — download tracking (torbox_id, progress, speed, error_msg)

**`install_log`** — step-by-step pipeline log entries

**`settings`** — key/value config store

---

## Configuration

All settings stored in the `settings` table:

| Key | Default | Description |
|---|---|---|
| `torbox_api_key` | *(required)* | Torbox debrid API key |
| `steamgriddb_api_key` | *(optional)* | SteamGridDB API key for artwork |
| `games_dir` | `~/Games` | Where installed games end up |
| `bottles_name` | `7seas-installer` | Wine prefix name in Bottles |
| `auto_add_steam` | `true` | Auto-create non-Steam shortcuts |
| `proton_version` | *(empty = proton_experimental)* | Internal compat tool name |

---

## File Locations

| What | Path |
|---|---|
| Database | `~/.local/share/seven-seas/sevenseas.db` |
| Log file | `~/.local/share/seven-seas/sevenseas.log` |
| Cover image cache | `~/.cache/seven-seas/covers/` |
| Download temp files | `~/.cache/seven-seas/download_<game_id>.zip` |
| Extract temp dir | `~/.cache/seven-seas/extract_<game_id>/` |
| Desktop file | `data/com.sevenseas.Launcher.desktop` |
| CSS theme | `data/style.css` |
| Font | `data/fonts/PirataOne-Regular.ttf` |

---

## Dependencies

**Python packages** (from `pyproject.toml`):
- `PyGObject` >= 3.46 — GTK4/Libadwaita bindings
- `httpx` >= 0.27 — HTTP client
- `beautifulsoup4` >= 4.12 — HTML parsing
- `lxml` >= 5.0 — parser backend
- `vdf` >= 3.4 — Steam VDF file format
- `torbox-api` >= 0.1.0 — Torbox SDK

**System packages** (must be installed separately):
- `7z` (p7zip) — archive extraction
- `bottles-cli` or Flatpak `com.usebottles.bottles` — Wine prefix management
- `steam` — for shortcut integration and restart
- AyatanaAppIndicator3 (GIR) — system tray
- `libfontconfig.so.1` — font loading

**Dev:**
- `pytest`, `pytest-asyncio`

---

## Running Tests

```bash
pytest tests/ -v
```

All tests use mocks/stubs — no live network or filesystem required (except `test_extractor` and `test_installer` which use `tmp_path`). The `conftest.py` fixture provides an in-memory SQLite database.

---

## Things to Know

### Proton is always forced
Every game installed through the launcher is a Windows repack. Proton is always set — defaults to `proton_experimental` if no version is configured in settings.

### d3d12.dll is NOT auto-overridden
Many repacks repurpose `d3d12.dll` as a crack shim (e.g., Battle.net emulator). Forcing `WINEDLLOVERRIDES="d3d12=b"` would break these. If a game needs a d3d12 override, it must be set manually in Steam launch options.

### FitGirl crack DLLs
Common DLL hooks used by FitGirl repacks:
- `winhttp.dll` — Battle.net emulator / online crack (needs `winhttp=n,b` override)
- `d3d12.dll` — sometimes repurposed as crack shim (do NOT override to builtin)
- Various engine-specific DLLs

If a game crashes on launch, check which DLLs the crack hooks through and add appropriate `WINEDLLOVERRIDES` to the Steam launch options.

### The tray is a separate process
GTK3 (AyatanaAppIndicator3) and GTK4 cannot coexist in one process. The tray runs as a child subprocess communicating via UNIX signals. This is not a bug — it's the only way to have both.

### Downloads survive window close
Closing the window hides it to tray. Downloads continue in the background. `Ctrl+Q` force-quits. The window auto-restores when all downloads complete.

### Steam must restart to see new shortcuts
After adding a non-Steam shortcut, the launcher automatically runs `steam -shutdown` then `steam -silent`. This is required — Steam doesn't hot-reload shortcuts.vdf.
