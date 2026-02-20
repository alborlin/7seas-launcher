# 7-Seas Launcher — Design Document

**Date:** 2026-02-19
**Status:** Approved

## Overview

7-Seas Launcher is a Linux desktop application for downloading games from FitGirl Repacks via the Torbox debrid API and installing them through Bottles (Wine). It provides a basic game library with Steam integration for launching installed games.

## Requirements

- Search and browse FitGirl Repacks (search, newest, top 50/month, top 150/year)
- Download games via Torbox debrid service (magnet → Torbox cloud → local download)
- Fully automated installation: extract archives → run installer via Bottles → files in ~/Games
- Basic game library showing installed games
- Add installed games as non-Steam shortcuts in Steam
- SQLite database for game library, download tracking, and settings

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| UI Framework | GTK4 + Libadwaita (via PyGObject) |
| HTTP Client | httpx (async, for streaming downloads) |
| Torbox API | torbox-api (official Python SDK) |
| Scraping | BeautifulSoup4 + lxml |
| Database | SQLite3 (stdlib) |
| Archive Extraction | 7z CLI (subprocess) |
| Wine/Install | Bottles CLI (bottles-cli) |
| Steam Shortcuts | vdf library |
| Build System | Meson |
| Testing | pytest |

## Architecture: Modular Service Architecture

Each core concern is an independent service module. The UI layer calls services through callbacks/signals. Services do not depend on each other directly — the pipeline orchestrator in `downloader.py` coordinates the workflow.

```
seven-seas-launcher/
├── src/
│   └── sevenseas/
│       ├── __init__.py
│       ├── app.py                  # GtkApplication subclass, entry point
│       ├── core/
│       │   ├── __init__.py
│       │   ├── torbox.py           # Torbox API client (wraps official SDK)
│       │   ├── scraper.py          # FitGirl repack page scraper
│       │   ├── downloader.py       # Download manager (Torbox + HTTP pull)
│       │   ├── extractor.py        # Archive extraction (7z, rar, zip)
│       │   ├── installer.py        # Bottles CLI integration
│       │   ├── library.py          # Game library service (CRUD)
│       │   ├── steam.py            # Steam non-Steam shortcut writer
│       │   └── config.py           # App settings manager
│       ├── db/
│       │   ├── __init__.py
│       │   ├── models.py           # SQLite schema
│       │   └── migrations.py       # Schema versioning
│       └── ui/
│           ├── __init__.py
│           ├── window.py           # Main AdwApplicationWindow
│           ├── views/
│           │   ├── search.py       # Search FitGirl / browse results
│           │   ├── browse.py       # New, Top 50, Top 150 pages
│           │   ├── downloads.py    # Active downloads & progress
│           │   ├── library.py      # Installed games grid
│           │   └── settings.py     # Configuration page
│           └── widgets/
│               ├── game_card.py    # Game cover + info card
│               ├── download_row.py # Download progress row
│               └── search_row.py   # Search result row
├── data/
│   ├── com.sevenseas.Launcher.desktop
│   ├── com.sevenseas.Launcher.metainfo.xml
│   ├── icons/
│   └── ui/                         # Optional .ui XML templates
├── tests/
│   ├── test_scraper.py
│   ├── test_torbox.py
│   ├── test_downloader.py
│   ├── test_installer.py
│   ├── test_library.py
│   ├── test_steam.py
│   └── fixtures/                   # Saved HTML pages for scraper tests
├── pyproject.toml
├── meson.build
└── README.md
```

**App ID:** `com.sevenseas.Launcher`

**XDG Paths:**
- Config: `~/.config/seven-seas/`
- Data: `~/.local/share/seven-seas/` (SQLite DB, cached metadata)
- Cache: `~/.cache/seven-seas/` (downloaded archives, cover art cache)
- Games: `~/Games/` (final install location, configurable)

## Database Schema

```sql
CREATE TABLE games (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    slug        TEXT UNIQUE NOT NULL,
    install_path TEXT,
    exe_path    TEXT,
    size_bytes  INTEGER,
    cover_url   TEXT,
    cover_local TEXT,
    source_url  TEXT,
    status      TEXT NOT NULL DEFAULT 'new',
    steam_shortcut_id INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE downloads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     INTEGER NOT NULL REFERENCES games(id),
    torbox_id   INTEGER,
    magnet_uri  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    progress    REAL DEFAULT 0.0,
    speed_bps   INTEGER DEFAULT 0,
    total_bytes INTEGER,
    dl_bytes    INTEGER DEFAULT 0,
    error_msg   TEXT,
    started_at  TEXT,
    completed_at TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE install_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     INTEGER NOT NULL REFERENCES games(id),
    step        TEXT NOT NULL,
    status      TEXT NOT NULL,
    output      TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);
```

**Game status values:** `new` → `downloading` → `extracting` → `installing` → `installed` → `failed`

**Download status values:** `pending` → `queued` → `downloading` → `seeding` → `completed` → `failed`

## Core Workflow

### End-to-End Pipeline

1. **Search/Browse** — User searches FitGirl or browses New/Top 50/Top 150 pages
2. **Select** — User picks a game. Scraper fetches detail page, extracts magnet link
3. **Torbox Download** — Magnet sent to Torbox via `createtorrent()`. Poll `mylist` for progress
4. **Pull from Torbox** — Once Torbox has the file, call `requestdl` for CDN URL. Stream-download via httpx to cache dir
5. **Extract** — Shell out to `7z x` to extract the repack archive to a temp directory
6. **Install via Bottles** — Run `bottles-cli run -b 7seas-installer -e setup.exe` with silent flags
7. **Move to ~/Games** — Copy installed files from Bottles' drive_c to `~/Games/<Game Name>/`
8. **Post-install** — Detect main .exe, optionally add as non-Steam shortcut, clean up temp files, update DB

### Service Responsibilities

**scraper.py:**
- `search(query: str) -> list[GameResult]` — search FitGirl
- `get_latest() -> list[GameResult]` — newest uploads page
- `get_top_monthly() -> list[GameResult]` — top 50 of the month
- `get_top_yearly() -> list[GameResult]` — top 150 of the year
- `get_detail(url: str) -> GameDetail` — fetch detail page, extract magnet links, screenshots, description
- Results cached in SQLite with TTL

**torbox.py:**
- `create_torrent(magnet: str) -> int` — send magnet, return torbox_id
- `check_status(torbox_id: int) -> TorrentStatus` — poll download progress
- `get_download_url(torbox_id: int, file_id: int) -> str` — get direct CDN link
- `check_cached(hash: str) -> bool` — check if already cached on Torbox (instant download)
- Wraps official `torbox-api` SDK

**downloader.py:**
- Orchestrates the full pipeline for a game
- Manages download queue (one active download at a time by default)
- Uses `GLib.timeout_add` for periodic polling in GTK main loop
- Emits signals for progress updates (UI subscribes)

**extractor.py:**
- `extract(archive_path: str, dest: str) -> bool` — extract using 7z subprocess
- Handles multi-part archives (.bin files)
- Progress parsing from 7z stdout

**installer.py:**
- `ensure_bottle() -> bool` — create `7seas-installer` bottle if it doesn't exist
- `run_installer(exe_path: str, args: list[str]) -> bool` — run .exe through bottles-cli
- `find_installed_files(bottle_name: str) -> list[str]` — scan bottle's drive_c for new files
- `move_to_games_dir(src: str, game_name: str) -> str` — move to ~/Games/<name>

**library.py:**
- CRUD operations on games table
- `get_installed() -> list[Game]`
- `get_by_status(status: str) -> list[Game]`
- `update_status(game_id: int, status: str)`

**steam.py:**
- `add_shortcut(game_name: str, exe_path: str, start_dir: str) -> int` — add non-Steam game
- `remove_shortcut(shortcut_id: int)`
- Reads/writes `~/.steam/steam/userdata/<id>/config/shortcuts.vdf`
- Auto-detects Steam user ID from userdata directory

## UI Layout

Libadwaita `AdwNavigationSplitView` with sidebar navigation:

```
┌─────────────────────────────────────────────────────────────┐
│  7-Seas Launcher                                    [─][□][×]│
├──────────┬──────────────────────────────────────────────────┤
│          │                                                  │
│  Search  │  (Active view content: card grid, download       │
│  New     │   list, library grid, or settings form)          │
│  Top 50  │                                                  │
│  Top 150 │                                                  │
│  ──────  │                                                  │
│  Downloads│                                                  │
│  Library │                                                  │
│  Settings│                                                  │
│          │                                                  │
├──────────┴──────────────────────────────────────────────────┤
│  Status bar: current download progress                      │
└─────────────────────────────────────────────────────────────┘
```

**Search/Browse views:** Responsive card grid. Each card shows cover art, title, file size, and Install button.

**Downloads view:** List of active/queued/completed downloads. Each row shows title, pipeline stage, progress bar, speed, cancel/retry buttons.

**Library view:** Grid of installed games. Click to launch (via Steam or direct). Right-click context menu for uninstall, open folder, add/remove Steam shortcut.

**Settings view:** Torbox API key, games directory, Bottles prefix name, auto-Steam toggle.

**Bottom status bar:** Persistent, shows active download progress. Click to navigate to Downloads.

## Error Handling

- Each pipeline step is independently retryable
- Failed steps logged to `install_log` with stdout/stderr capture
- User sees notification banner with "Retry" and "View Log" options
- Torbox API errors (rate limit 429, auth 401) show specific guidance
- Network errors during download: automatic retry with exponential backoff (3 attempts)
- Missing Bottles: Settings page shows install instructions
- Missing 7z: Settings page shows install instructions

## Testing Strategy

- **Unit tests**: Each core service mocked and tested independently
- **Scraper tests**: Against saved HTML fixture files (no live network)
- **Database tests**: In-memory SQLite for fast CRUD testing
- **No UI tests initially**: GTK testing is complex, low ROI early on
- **Test runner**: pytest

## Packaging

- **Primary**: Flatpak (matches Bottles' ecosystem, sandboxed)
- **Secondary**: AUR package (Arch Linux native)
- **Development**: `pip install -e .` via pyproject.toml + Meson

## First-Run Setup

1. Settings view opens on first launch
2. User enters Torbox API key (validated against `/v1/api/user/me`)
3. App creates `7seas-installer` Bottles prefix via `bottles-cli new --environment gaming`
4. Games directory confirmed (default `~/Games/`, created if needed)
5. Ready to use
