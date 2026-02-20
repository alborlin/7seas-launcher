# 7-Seas Launcher Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Linux GTK4 app that downloads games from FitGirl Repacks via the Torbox debrid API and installs them through Bottles, with a basic library and Steam integration.

**Architecture:** Modular service architecture — independent Python modules for each concern (scraping, downloading, extracting, installing, library management). GTK4/Libadwaita UI calls services via callbacks. SQLite for persistence.

**Tech Stack:** Python 3.11+, GTK4/Libadwaita (PyGObject), torbox-api SDK, httpx, BeautifulSoup4, sqlite3, vdf, pytest

**Reference design:** `docs/plans/2026-02-19-seven-seas-launcher-design.md`

---

## Phase 1: Project Scaffolding & Database

### Task 1: Create project skeleton with pyproject.toml

**Files:**
- Create: `pyproject.toml`
- Create: `src/sevenseas/__init__.py`
- Create: `src/sevenseas/core/__init__.py`
- Create: `src/sevenseas/db/__init__.py`
- Create: `src/sevenseas/ui/__init__.py`
- Create: `src/sevenseas/ui/views/__init__.py`
- Create: `src/sevenseas/ui/widgets/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "seven-seas-launcher"
version = "0.1.0"
description = "Linux game installer via Torbox and Bottles"
requires-python = ">=3.11"
dependencies = [
    "PyGObject>=3.46",
    "torbox-api>=0.1.0",
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
    "vdf>=3.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[project.scripts]
seven-seas = "sevenseas.app:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

**Step 2: Create package __init__.py files**

`src/sevenseas/__init__.py`:
```python
"""7-Seas Launcher — Linux game installer via Torbox and Bottles."""

__version__ = "0.1.0"
```

All other `__init__.py` files are empty.

`tests/conftest.py`:
```python
"""Shared test fixtures."""

import sqlite3
import pytest

from sevenseas.db.models import create_tables


@pytest.fixture
def db():
    """In-memory SQLite database with schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    yield conn
    conn.close()
```

**Step 3: Create directory structure**

```bash
mkdir -p src/sevenseas/{core,db,ui/{views,widgets}} tests/fixtures data/icons
touch src/sevenseas/{core,db,ui,ui/views,ui/widgets}/__init__.py
touch tests/__init__.py
```

**Step 4: Install in dev mode and verify import**

```bash
pip install -e ".[dev]"
python -c "import sevenseas; print(sevenseas.__version__)"
```

Expected: `0.1.0`

**Step 5: Commit**

```bash
git add pyproject.toml src/ tests/ data/
git commit -m "feat: scaffold project structure with pyproject.toml"
```

---

### Task 2: Database schema and models

**Files:**
- Create: `src/sevenseas/db/models.py`
- Create: `tests/test_db.py`

**Step 1: Write the failing test**

`tests/test_db.py`:
```python
"""Tests for database schema and operations."""

import sqlite3

from sevenseas.db.models import create_tables


def test_create_tables_creates_all_tables(db):
    """All four tables should exist after create_tables."""
    cursor = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row["name"] for row in cursor.fetchall()]
    assert "downloads" in tables
    assert "games" in tables
    assert "install_log" in tables
    assert "settings" in tables


def test_games_table_columns(db):
    """Games table should have all required columns."""
    cursor = db.execute("PRAGMA table_info(games)")
    columns = {row["name"] for row in cursor.fetchall()}
    expected = {
        "id", "title", "slug", "install_path", "exe_path", "size_bytes",
        "cover_url", "cover_local", "source_url", "status",
        "steam_shortcut_id", "created_at", "updated_at",
    }
    assert expected == columns


def test_games_slug_unique_constraint(db):
    """Inserting duplicate slugs should raise IntegrityError."""
    db.execute(
        "INSERT INTO games (title, slug) VALUES (?, ?)",
        ("Game One", "game-one"),
    )
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO games (title, slug) VALUES (?, ?)",
            ("Game One Copy", "game-one"),
        )


def test_downloads_foreign_key(db):
    """Downloads should reference a valid game."""
    db.execute("PRAGMA foreign_keys = ON")
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO downloads (game_id, magnet_uri) VALUES (?, ?)",
            (9999, "magnet:?xt=urn:btih:abc"),
        )


def test_settings_upsert(db):
    """Settings should support upsert via INSERT OR REPLACE."""
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("k", "v1"))
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("k", "v2"))
    row = db.execute("SELECT value FROM settings WHERE key = ?", ("k",)).fetchone()
    assert row["value"] == "v2"


def test_games_default_status(db):
    """New games should default to 'new' status."""
    db.execute("INSERT INTO games (title, slug) VALUES (?, ?)", ("Test", "test"))
    row = db.execute("SELECT status FROM games WHERE slug = ?", ("test",)).fetchone()
    assert row["status"] == "new"
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_db.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'sevenseas.db.models'` (or `ImportError`)

**Step 3: Write minimal implementation**

`src/sevenseas/db/models.py`:
```python
"""SQLite schema definition and table creation."""

import sqlite3

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    slug            TEXT UNIQUE NOT NULL,
    install_path    TEXT,
    exe_path        TEXT,
    size_bytes      INTEGER,
    cover_url       TEXT,
    cover_local     TEXT,
    source_url      TEXT,
    status          TEXT NOT NULL DEFAULT 'new',
    steam_shortcut_id INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS downloads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         INTEGER NOT NULL REFERENCES games(id),
    torbox_id       INTEGER,
    magnet_uri      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    progress        REAL DEFAULT 0.0,
    speed_bps       INTEGER DEFAULT 0,
    total_bytes     INTEGER,
    dl_bytes        INTEGER DEFAULT 0,
    error_msg       TEXT,
    started_at      TEXT,
    completed_at    TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS install_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         INTEGER NOT NULL REFERENCES games(id),
    step            TEXT NOT NULL,
    status          TEXT NOT NULL,
    output          TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);
"""


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't exist."""
    conn.executescript(_SCHEMA)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def get_db(db_path: str) -> sqlite3.Connection:
    """Open a database connection and ensure schema exists."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    return conn
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_db.py -v
```

Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/sevenseas/db/models.py tests/test_db.py
git commit -m "feat: add SQLite database schema and models"
```

---

### Task 3: Config service

**Files:**
- Create: `src/sevenseas/core/config.py`
- Create: `tests/test_config.py`

**Step 1: Write the failing test**

`tests/test_config.py`:
```python
"""Tests for the config service."""

from sevenseas.core.config import ConfigService


def test_get_returns_default_when_key_missing(db):
    config = ConfigService(db)
    assert config.get("nonexistent", "default") == "default"


def test_set_and_get(db):
    config = ConfigService(db)
    config.set("torbox_api_key", "abc123")
    assert config.get("torbox_api_key") == "abc123"


def test_set_overwrites_existing(db):
    config = ConfigService(db)
    config.set("key", "v1")
    config.set("key", "v2")
    assert config.get("key") == "v2"


def test_default_games_dir(db):
    config = ConfigService(db)
    import os
    expected = os.path.expanduser("~/Games")
    assert config.games_dir == expected


def test_custom_games_dir(db):
    config = ConfigService(db)
    config.set("games_dir", "/tmp/mygames")
    assert config.games_dir == "/tmp/mygames"


def test_default_bottles_name(db):
    config = ConfigService(db)
    assert config.bottles_name == "7seas-installer"


def test_torbox_api_key_property(db):
    config = ConfigService(db)
    assert config.torbox_api_key is None
    config.set("torbox_api_key", "test-key")
    assert config.torbox_api_key == "test-key"


def test_auto_add_steam_default_true(db):
    config = ConfigService(db)
    assert config.auto_add_steam is True
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_config.py -v
```

Expected: FAIL — `ImportError`

**Step 3: Write minimal implementation**

`src/sevenseas/core/config.py`:
```python
"""Application settings backed by SQLite."""

import os
import sqlite3


class ConfigService:
    """Read/write app settings from the settings table."""

    _DEFAULTS = {
        "games_dir": os.path.expanduser("~/Games"),
        "bottles_name": "7seas-installer",
        "auto_add_steam": "true",
    }

    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self._db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row is not None:
            return row["value"]
        return self._DEFAULTS.get(key, default)

    def set(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._db.commit()

    @property
    def games_dir(self) -> str:
        return self.get("games_dir", self._DEFAULTS["games_dir"])

    @property
    def bottles_name(self) -> str:
        return self.get("bottles_name", self._DEFAULTS["bottles_name"])

    @property
    def torbox_api_key(self) -> str | None:
        return self.get("torbox_api_key")

    @property
    def auto_add_steam(self) -> bool:
        return self.get("auto_add_steam", "true").lower() == "true"
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: All 8 tests PASS

**Step 5: Commit**

```bash
git add src/sevenseas/core/config.py tests/test_config.py
git commit -m "feat: add config service with SQLite-backed settings"
```

---

## Phase 2: Core Services (Backend)

### Task 4: Game library service

**Files:**
- Create: `src/sevenseas/core/library.py`
- Create: `tests/test_library.py`

**Step 1: Write the failing test**

`tests/test_library.py`:
```python
"""Tests for the game library service."""

import pytest

from sevenseas.core.library import LibraryService, Game


def test_add_game(db):
    lib = LibraryService(db)
    game = lib.add_game(title="Elden Ring", slug="elden-ring", source_url="https://example.com")
    assert game.id is not None
    assert game.title == "Elden Ring"
    assert game.slug == "elden-ring"
    assert game.status == "new"


def test_add_duplicate_slug_raises(db):
    lib = LibraryService(db)
    lib.add_game(title="Game", slug="game")
    with pytest.raises(Exception):
        lib.add_game(title="Game 2", slug="game")


def test_get_by_id(db):
    lib = LibraryService(db)
    created = lib.add_game(title="Test", slug="test")
    fetched = lib.get_by_id(created.id)
    assert fetched is not None
    assert fetched.title == "Test"


def test_get_by_id_returns_none_for_missing(db):
    lib = LibraryService(db)
    assert lib.get_by_id(9999) is None


def test_get_installed(db):
    lib = LibraryService(db)
    lib.add_game(title="A", slug="a")
    g2 = lib.add_game(title="B", slug="b")
    lib.update_status(g2.id, "installed")
    installed = lib.get_installed()
    assert len(installed) == 1
    assert installed[0].slug == "b"


def test_get_by_status(db):
    lib = LibraryService(db)
    lib.add_game(title="A", slug="a")
    lib.add_game(title="B", slug="b")
    new_games = lib.get_by_status("new")
    assert len(new_games) == 2


def test_update_status(db):
    lib = LibraryService(db)
    game = lib.add_game(title="X", slug="x")
    lib.update_status(game.id, "downloading")
    updated = lib.get_by_id(game.id)
    assert updated.status == "downloading"


def test_update_game_fields(db):
    lib = LibraryService(db)
    game = lib.add_game(title="X", slug="x")
    lib.update_game(game.id, install_path="/home/user/Games/X", exe_path="game.exe")
    updated = lib.get_by_id(game.id)
    assert updated.install_path == "/home/user/Games/X"
    assert updated.exe_path == "game.exe"


def test_delete_game(db):
    lib = LibraryService(db)
    game = lib.add_game(title="Del", slug="del")
    lib.delete_game(game.id)
    assert lib.get_by_id(game.id) is None
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_library.py -v
```

Expected: FAIL — `ImportError`

**Step 3: Write minimal implementation**

`src/sevenseas/core/library.py`:
```python
"""Game library service — CRUD operations on the games table."""

import sqlite3
from dataclasses import dataclass


@dataclass
class Game:
    id: int
    title: str
    slug: str
    install_path: str | None = None
    exe_path: str | None = None
    size_bytes: int | None = None
    cover_url: str | None = None
    cover_local: str | None = None
    source_url: str | None = None
    status: str = "new"
    steam_shortcut_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


def _row_to_game(row: sqlite3.Row) -> Game:
    return Game(**{k: row[k] for k in row.keys()})


class LibraryService:
    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db

    def add_game(
        self,
        title: str,
        slug: str,
        source_url: str | None = None,
        cover_url: str | None = None,
        size_bytes: int | None = None,
    ) -> Game:
        cursor = self._db.execute(
            """INSERT INTO games (title, slug, source_url, cover_url, size_bytes)
               VALUES (?, ?, ?, ?, ?)""",
            (title, slug, source_url, cover_url, size_bytes),
        )
        self._db.commit()
        return self.get_by_id(cursor.lastrowid)

    def get_by_id(self, game_id: int) -> Game | None:
        row = self._db.execute(
            "SELECT * FROM games WHERE id = ?", (game_id,)
        ).fetchone()
        return _row_to_game(row) if row else None

    def get_installed(self) -> list[Game]:
        return self.get_by_status("installed")

    def get_by_status(self, status: str) -> list[Game]:
        rows = self._db.execute(
            "SELECT * FROM games WHERE status = ? ORDER BY updated_at DESC",
            (status,),
        ).fetchall()
        return [_row_to_game(r) for r in rows]

    def update_status(self, game_id: int, status: str) -> None:
        self._db.execute(
            "UPDATE games SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, game_id),
        )
        self._db.commit()

    def update_game(self, game_id: int, **fields) -> None:
        allowed = {
            "title", "install_path", "exe_path", "size_bytes",
            "cover_url", "cover_local", "source_url", "steam_shortcut_id",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [game_id]
        self._db.execute(
            f"UPDATE games SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        self._db.commit()

    def delete_game(self, game_id: int) -> None:
        self._db.execute("DELETE FROM install_log WHERE game_id = ?", (game_id,))
        self._db.execute("DELETE FROM downloads WHERE game_id = ?", (game_id,))
        self._db.execute("DELETE FROM games WHERE id = ?", (game_id,))
        self._db.commit()
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_library.py -v
```

Expected: All 9 tests PASS

**Step 5: Commit**

```bash
git add src/sevenseas/core/library.py tests/test_library.py
git commit -m "feat: add game library service with CRUD operations"
```

---

### Task 5: FitGirl scraper

**Files:**
- Create: `src/sevenseas/core/scraper.py`
- Create: `tests/test_scraper.py`
- Create: `tests/fixtures/fitgirl_search.html` (saved HTML fixture)
- Create: `tests/fixtures/fitgirl_detail.html` (saved HTML fixture)

**Step 1: Save HTML fixtures**

Before writing tests, you need sample HTML from FitGirl's site to test against. Fetch these manually or with a tool and save them:

- `tests/fixtures/fitgirl_search.html` — a search results page from fitgirl-repacks.site
- `tests/fixtures/fitgirl_detail.html` — a single game detail page from fitgirl-repacks.site
- `tests/fixtures/fitgirl_latest.html` — the latest repacks page

Use `httpx` to fetch these for the fixtures:
```bash
python -c "
import httpx
# Fetch search results page
r = httpx.get('https://fitgirl-repacks.site/?s=elden+ring', follow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
open('tests/fixtures/fitgirl_search.html', 'w').write(r.text)
# Fetch a detail page (use any known repack URL)
r = httpx.get('https://fitgirl-repacks.site/category/lossless-repack/', follow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
open('tests/fixtures/fitgirl_latest.html', 'w').write(r.text)
"
```

Note: The exact URLs and HTML structure should be inspected at implementation time to confirm CSS selectors. The implementation below uses selectors based on the known FitGirl WordPress theme structure, but **the implementing engineer must verify selectors against the actual fetched HTML fixtures before finalizing.**

**Step 2: Write the failing test**

`tests/test_scraper.py`:
```python
"""Tests for FitGirl scraper — uses saved HTML fixtures."""

import os
import pytest

from sevenseas.core.scraper import FitGirlScraper, GameResult, GameDetail


@pytest.fixture
def scraper():
    return FitGirlScraper()


@pytest.fixture
def search_html():
    path = os.path.join(os.path.dirname(__file__), "fixtures", "fitgirl_search.html")
    if not os.path.exists(path):
        pytest.skip("Fixture fitgirl_search.html not found — fetch it first")
    with open(path) as f:
        return f.read()


@pytest.fixture
def latest_html():
    path = os.path.join(os.path.dirname(__file__), "fixtures", "fitgirl_latest.html")
    if not os.path.exists(path):
        pytest.skip("Fixture fitgirl_latest.html not found — fetch it first")
    with open(path) as f:
        return f.read()


def test_parse_search_results(scraper, search_html):
    """Should parse game results from search page HTML."""
    results = scraper.parse_listing(search_html)
    assert len(results) > 0
    for r in results:
        assert isinstance(r, GameResult)
        assert r.title
        assert r.url.startswith("http")


def test_game_result_has_title_and_url(scraper, search_html):
    results = scraper.parse_listing(search_html)
    first = results[0]
    assert first.title != ""
    assert "fitgirl" in first.url or "http" in first.url


def test_parse_latest(scraper, latest_html):
    """Should parse the latest repacks page."""
    results = scraper.parse_listing(latest_html)
    assert len(results) > 0


def test_extract_magnet_from_detail():
    """Should extract magnet link from detail page HTML."""
    html = '''<html><body>
    <a href="magnet:?xt=urn:btih:abc123&dn=Test+Game">Magnet</a>
    </body></html>'''
    scraper = FitGirlScraper()
    detail = scraper.parse_detail(html, "https://fitgirl-repacks.site/test-game/")
    assert detail.magnet_uri.startswith("magnet:")
    assert "abc123" in detail.magnet_uri


def test_extract_magnet_returns_none_when_absent():
    html = '<html><body><p>No magnet here</p></body></html>'
    scraper = FitGirlScraper()
    detail = scraper.parse_detail(html, "https://fitgirl-repacks.site/test/")
    assert detail.magnet_uri is None


def test_slug_from_url():
    scraper = FitGirlScraper()
    assert scraper.slug_from_url("https://fitgirl-repacks.site/elden-ring/") == "elden-ring"
    assert scraper.slug_from_url("https://fitgirl-repacks.site/some-game/") == "some-game"
```

**Step 3: Run test to verify it fails**

```bash
pytest tests/test_scraper.py -v
```

Expected: FAIL — `ImportError`

**Step 4: Write minimal implementation**

`src/sevenseas/core/scraper.py`:
```python
"""FitGirl Repacks scraper — parses search, listing, and detail pages."""

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
_BASE_URL = "https://fitgirl-repacks.site"


@dataclass
class GameResult:
    title: str
    url: str
    thumbnail: str | None = None
    size_info: str | None = None


@dataclass
class GameDetail:
    title: str
    url: str
    magnet_uri: str | None = None
    description: str | None = None
    size_info: str | None = None
    screenshots: list[str] = field(default_factory=list)


class FitGirlScraper:
    """Scrapes FitGirl Repacks for game listings and detail pages."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        )

    def search(self, query: str) -> list[GameResult]:
        resp = self._client.get(f"{_BASE_URL}/", params={"s": query})
        resp.raise_for_status()
        return self.parse_listing(resp.text)

    def get_latest(self) -> list[GameResult]:
        resp = self._client.get(f"{_BASE_URL}/category/lossless-repack/")
        resp.raise_for_status()
        return self.parse_listing(resp.text)

    def get_top_monthly(self) -> list[GameResult]:
        resp = self._client.get(f"{_BASE_URL}/popular-repacks/")
        resp.raise_for_status()
        return self.parse_listing(resp.text)

    def get_top_yearly(self) -> list[GameResult]:
        resp = self._client.get(f"{_BASE_URL}/popular-repacks-of-the-year/")
        resp.raise_for_status()
        return self.parse_listing(resp.text)

    def get_detail(self, url: str) -> GameDetail:
        resp = self._client.get(url)
        resp.raise_for_status()
        return self.parse_detail(resp.text, url)

    def parse_listing(self, html: str) -> list[GameResult]:
        """Parse a listing/search results page and return GameResult items."""
        soup = BeautifulSoup(html, "lxml")
        results = []
        # FitGirl uses WordPress — articles are in <article> tags or .post entries
        for article in soup.select("article"):
            title_el = article.select_one(".entry-title a, h1 a, h2 a")
            if title_el is None:
                continue
            title = title_el.get_text(strip=True)
            url = title_el.get("href", "")
            # Try to find thumbnail
            img = article.select_one("img")
            thumbnail = img.get("src") if img else None
            # Try to extract size from text
            text = article.get_text()
            size_match = re.search(
                r"(?:Original Size|Repack Size)[:\s]*([\d.]+\s*[GMTK]B)",
                text, re.IGNORECASE,
            )
            size_info = size_match.group(1) if size_match else None
            results.append(GameResult(
                title=title, url=url, thumbnail=thumbnail, size_info=size_info,
            ))
        return results

    def parse_detail(self, html: str, url: str) -> GameDetail:
        """Parse a game detail page and extract magnet link and metadata."""
        soup = BeautifulSoup(html, "lxml")
        title_el = soup.select_one(".entry-title, h1.entry-title")
        title = title_el.get_text(strip=True) if title_el else ""
        # Find magnet link
        magnet_link = soup.select_one('a[href^="magnet:"]')
        magnet_uri = magnet_link["href"] if magnet_link else None
        # Description
        entry = soup.select_one(".entry-content")
        description = entry.get_text(strip=True)[:500] if entry else None
        # Size
        text = soup.get_text()
        size_match = re.search(
            r"(?:Repack Size)[:\s]*([\d.]+\s*[GMTK]B)",
            text, re.IGNORECASE,
        )
        size_info = size_match.group(1) if size_match else None
        # Screenshots
        screenshots = []
        for img in soup.select(".entry-content img"):
            src = img.get("src", "")
            if src and "screenshot" in src.lower() or img.get("data-lazy-src"):
                screenshots.append(img.get("data-lazy-src", src))
        return GameDetail(
            title=title, url=url, magnet_uri=magnet_uri,
            description=description, size_info=size_info, screenshots=screenshots,
        )

    @staticmethod
    def slug_from_url(url: str) -> str:
        """Extract the slug from a FitGirl URL path."""
        path = urlparse(url).path.strip("/")
        # The last path segment is the slug
        return path.split("/")[-1] if path else ""
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/test_scraper.py -v
```

Expected: Tests using fixtures may skip if not fetched yet. `test_extract_magnet_from_detail`, `test_extract_magnet_returns_none_when_absent`, and `test_slug_from_url` should PASS.

**Step 6: Fetch fixtures and run all tests**

```bash
python -c "
import httpx
c = httpx.Client(headers={'User-Agent': 'Mozilla/5.0'}, follow_redirects=True)
r = c.get('https://fitgirl-repacks.site/?s=elden+ring')
open('tests/fixtures/fitgirl_search.html', 'w').write(r.text)
r = c.get('https://fitgirl-repacks.site/category/lossless-repack/')
open('tests/fixtures/fitgirl_latest.html', 'w').write(r.text)
"
pytest tests/test_scraper.py -v
```

Expected: All tests PASS (if selectors match — adjust selectors if needed based on actual HTML)

**Step 7: Commit**

```bash
git add src/sevenseas/core/scraper.py tests/test_scraper.py tests/fixtures/
git commit -m "feat: add FitGirl repacks scraper with search and detail parsing"
```

---

### Task 6: Torbox API client

**Files:**
- Create: `src/sevenseas/core/torbox.py`
- Create: `tests/test_torbox.py`

**Step 1: Write the failing test**

`tests/test_torbox.py`:
```python
"""Tests for Torbox API client — uses mocked SDK responses."""

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
    mock_sdk.torrents.check_cached.return_value = MagicMock(
        data={"abc123": {"name": "Test", "size": 100}}
    )
    assert client.check_cached("abc123") is True


def test_check_cached_false(client, mock_sdk):
    mock_sdk.torrents.check_cached.return_value = MagicMock(data={})
    assert client.check_cached("abc123") is False


def test_validate_api_key_success(client, mock_sdk):
    mock_sdk.user.get_user_data.return_value = MagicMock(
        data={"email": "test@example.com"}
    )
    assert client.validate_api_key() is True


def test_validate_api_key_failure(client, mock_sdk):
    mock_sdk.user.get_user_data.side_effect = Exception("401 Unauthorized")
    assert client.validate_api_key() is False
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_torbox.py -v
```

Expected: FAIL — `ImportError`

**Step 3: Write minimal implementation**

`src/sevenseas/core/torbox.py`:
```python
"""Torbox API client — wraps the official torbox-api SDK."""

import re
from dataclasses import dataclass

from torbox_api import TorboxApi


@dataclass
class TorrentStatus:
    torbox_id: int
    state: str
    progress: float
    speed_bps: int
    total_bytes: int
    name: str


class TorboxClient:
    """High-level wrapper around the Torbox API SDK."""

    def __init__(self, api_key: str) -> None:
        self._sdk = TorboxApi(access_token=api_key)

    def create_torrent(self, magnet: str) -> int:
        """Send a magnet link to Torbox. Returns the torbox torrent ID."""
        result = self._sdk.torrents.create_torrent(magnet=magnet)
        return result.data["torrent_id"]

    def check_status(self, torbox_id: int) -> TorrentStatus | None:
        """Poll the status of a torrent on Torbox."""
        result = self._sdk.torrents.get_torrent_list(id=torbox_id)
        torrents = result.data if result.data else []
        for t in torrents:
            if t["id"] == torbox_id:
                return TorrentStatus(
                    torbox_id=t["id"],
                    state=t.get("download_state", "unknown"),
                    progress=t.get("progress", 0.0),
                    speed_bps=t.get("dlspeed", 0),
                    total_bytes=t.get("size", 0),
                    name=t.get("name", ""),
                )
        return None

    def get_download_url(self, torbox_id: int, file_id: int = 0) -> str:
        """Get a direct download URL for a completed torrent."""
        result = self._sdk.torrents.request_download_link(
            torrent_id=torbox_id, file_id=file_id,
        )
        return result.data

    def check_cached(self, info_hash: str) -> bool:
        """Check if a torrent hash is already cached on Torbox servers."""
        result = self._sdk.torrents.check_cached(hashes=[info_hash])
        return bool(result.data and result.data.get(info_hash))

    def validate_api_key(self) -> bool:
        """Validate the API key by fetching user info."""
        try:
            self._sdk.user.get_user_data()
            return True
        except Exception:
            return False

    @staticmethod
    def extract_hash_from_magnet(magnet: str) -> str | None:
        """Extract the info hash from a magnet URI."""
        match = re.search(r"btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})", magnet)
        return match.group(1).lower() if match else None
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_torbox.py -v
```

Expected: All 8 tests PASS

**Step 5: Commit**

```bash
git add src/sevenseas/core/torbox.py tests/test_torbox.py
git commit -m "feat: add Torbox API client wrapping official SDK"
```

---

### Task 7: Archive extractor

**Files:**
- Create: `src/sevenseas/core/extractor.py`
- Create: `tests/test_extractor.py`

**Step 1: Write the failing test**

`tests/test_extractor.py`:
```python
"""Tests for archive extractor."""

import os
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from sevenseas.core.extractor import Extractor, ExtractionError


def test_extract_calls_7z_with_correct_args():
    with patch("sevenseas.core.extractor.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Everything is Ok")
        ext = Extractor()
        ext.extract("/tmp/archive.7z", "/tmp/output")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "7z" in args[0]
        assert "x" in args
        assert "/tmp/archive.7z" in args
        assert any("/tmp/output" in a for a in args)


def test_extract_raises_on_failure():
    with patch("sevenseas.core.extractor.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=2, stderr="Error: file not found")
        ext = Extractor()
        with pytest.raises(ExtractionError):
            ext.extract("/tmp/bad.7z", "/tmp/output")


def test_extract_creates_output_dir(tmp_path):
    dest = tmp_path / "output"
    with patch("sevenseas.core.extractor.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Everything is Ok")
        ext = Extractor()
        ext.extract("/tmp/archive.7z", str(dest))
        assert dest.exists()


def test_find_setup_exe(tmp_path):
    """Should find setup.exe in extracted directory."""
    (tmp_path / "setup.exe").touch()
    (tmp_path / "readme.txt").touch()
    (tmp_path / "data.bin").touch()
    ext = Extractor()
    setup = ext.find_setup_exe(str(tmp_path))
    assert setup is not None
    assert setup.endswith("setup.exe")


def test_find_setup_exe_case_insensitive(tmp_path):
    (tmp_path / "Setup.exe").touch()
    ext = Extractor()
    setup = ext.find_setup_exe(str(tmp_path))
    assert setup is not None


def test_find_setup_exe_returns_none_when_missing(tmp_path):
    (tmp_path / "readme.txt").touch()
    ext = Extractor()
    assert ext.find_setup_exe(str(tmp_path)) is None
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_extractor.py -v
```

Expected: FAIL — `ImportError`

**Step 3: Write minimal implementation**

`src/sevenseas/core/extractor.py`:
```python
"""Archive extraction using 7z CLI."""

import os
import subprocess
from pathlib import Path


class ExtractionError(Exception):
    """Raised when extraction fails."""


class Extractor:
    """Extracts archives using the 7z command-line tool."""

    def __init__(self, sevenz_bin: str = "7z") -> None:
        self._bin = sevenz_bin

    def extract(self, archive_path: str, dest_dir: str) -> None:
        """Extract an archive to the destination directory."""
        os.makedirs(dest_dir, exist_ok=True)
        result = subprocess.run(
            [self._bin, "x", archive_path, f"-o{dest_dir}", "-y"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise ExtractionError(
                f"7z extraction failed (code {result.returncode}): {result.stderr}"
            )

    def find_setup_exe(self, directory: str) -> str | None:
        """Find setup.exe or similar installer in extracted files."""
        setup_names = {"setup.exe", "install.exe", "installer.exe"}
        for root, _dirs, files in os.walk(directory):
            for f in files:
                if f.lower() in setup_names:
                    return os.path.join(root, f)
        return None
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_extractor.py -v
```

Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/sevenseas/core/extractor.py tests/test_extractor.py
git commit -m "feat: add archive extractor using 7z CLI"
```

---

### Task 8: Bottles installer integration

**Files:**
- Create: `src/sevenseas/core/installer.py`
- Create: `tests/test_installer.py`

**Step 1: Write the failing test**

`tests/test_installer.py`:
```python
"""Tests for Bottles CLI integration."""

import os
import pytest
from unittest.mock import patch, MagicMock

from sevenseas.core.installer import BottlesInstaller, InstallError


@pytest.fixture
def installer():
    return BottlesInstaller(bottle_name="test-bottle")


def test_ensure_bottle_creates_if_missing(installer):
    with patch("sevenseas.core.installer.subprocess.run") as mock_run:
        # First call: list bottles (bottle missing)
        # Second call: create bottle
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='[]'),
            MagicMock(returncode=0, stdout='Bottle created'),
        ]
        installer.ensure_bottle()
        assert mock_run.call_count == 2


def test_ensure_bottle_skips_if_exists(installer):
    with patch("sevenseas.core.installer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout='[{"Name": "test-bottle"}]'
        )
        installer.ensure_bottle()
        assert mock_run.call_count == 1  # only list, no create


def test_run_installer_calls_bottles_cli(installer):
    with patch("sevenseas.core.installer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Done")
        result = installer.run_installer("/tmp/setup.exe", ["/S"])
        assert result is True
        args = mock_run.call_args[0][0]
        assert "bottles-cli" in args[0] or "bottles-cli" in " ".join(args)
        assert "/tmp/setup.exe" in " ".join(args)


def test_run_installer_raises_on_failure(installer):
    with patch("sevenseas.core.installer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="Wine error")
        with pytest.raises(InstallError):
            installer.run_installer("/tmp/bad.exe")


def test_move_to_games_dir(installer, tmp_path):
    src = tmp_path / "installed"
    src.mkdir()
    (src / "game.exe").write_text("binary")
    (src / "data.pak").write_text("data")
    dest_base = tmp_path / "Games"
    result = installer.move_to_games_dir(str(src), "TestGame", str(dest_base))
    assert os.path.isfile(os.path.join(result, "game.exe"))
    assert os.path.isfile(os.path.join(result, "data.pak"))
    assert "TestGame" in result


def test_detect_bottles_cli_flatpak_fallback():
    with patch("sevenseas.core.installer.shutil.which", return_value=None):
        with patch("sevenseas.core.installer.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="bottles-cli")
            inst = BottlesInstaller("test")
            cmd = inst._bottles_cmd()
            # Should fall back to flatpak invocation
            assert "flatpak" in cmd[0] or "bottles-cli" in cmd[-1]
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_installer.py -v
```

Expected: FAIL — `ImportError`

**Step 3: Write minimal implementation**

`src/sevenseas/core/installer.py`:
```python
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
        return ["bottles-cli"]  # fallback, will error if not found

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
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_installer.py -v
```

Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/sevenseas/core/installer.py tests/test_installer.py
git commit -m "feat: add Bottles CLI integration for Windows installers"
```

---

### Task 9: Steam shortcut writer

**Files:**
- Create: `src/sevenseas/core/steam.py`
- Create: `tests/test_steam.py`

**Step 1: Write the failing test**

`tests/test_steam.py`:
```python
"""Tests for Steam non-Steam shortcut writer."""

import os
import pytest
from unittest.mock import patch

from sevenseas.core.steam import SteamShortcuts


def test_generate_shortcut_id():
    sid = SteamShortcuts.generate_shortcut_id("Test Game", "/path/to/game.exe")
    assert isinstance(sid, int)
    # Same inputs should produce same ID
    sid2 = SteamShortcuts.generate_shortcut_id("Test Game", "/path/to/game.exe")
    assert sid == sid2


def test_generate_shortcut_id_unique():
    sid1 = SteamShortcuts.generate_shortcut_id("Game A", "/a.exe")
    sid2 = SteamShortcuts.generate_shortcut_id("Game B", "/b.exe")
    assert sid1 != sid2


def test_find_steam_userdata(tmp_path):
    # Create fake Steam userdata structure
    userdata = tmp_path / ".steam" / "steam" / "userdata" / "12345" / "config"
    userdata.mkdir(parents=True)
    with patch.dict(os.environ, {"HOME": str(tmp_path)}):
        shortcuts = SteamShortcuts()
        paths = shortcuts._find_userdata_dirs()
        assert len(paths) == 1
        assert "12345" in str(paths[0])


def test_build_shortcut_entry():
    entry = SteamShortcuts.build_shortcut_entry(
        app_name="Test Game",
        exe_path="/home/user/Games/TestGame/game.exe",
        start_dir="/home/user/Games/TestGame",
        shortcut_id=12345,
    )
    assert entry["AppName"] == "Test Game"
    assert entry["Exe"] == '"/home/user/Games/TestGame/game.exe"'
    assert entry["StartDir"] == '"/home/user/Games/TestGame"'
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_steam.py -v
```

Expected: FAIL — `ImportError`

**Step 3: Write minimal implementation**

`src/sevenseas/core/steam.py`:
```python
"""Steam non-Steam shortcut management."""

import os
import struct
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
        import zlib
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
            # Find next available index
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
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_steam.py -v
```

Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add src/sevenseas/core/steam.py tests/test_steam.py
git commit -m "feat: add Steam non-Steam shortcut writer"
```

---

### Task 10: Download manager (pipeline orchestrator)

**Files:**
- Create: `src/sevenseas/core/downloader.py`
- Create: `tests/test_downloader.py`

**Step 1: Write the failing test**

`tests/test_downloader.py`:
```python
"""Tests for the download manager / pipeline orchestrator."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from sevenseas.core.downloader import DownloadManager, DownloadState


@pytest.fixture
def deps():
    """Mock all dependencies."""
    return {
        "db": MagicMock(),
        "torbox": MagicMock(),
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
    manager.enqueue(game_id=1, magnet="magnet:?xt=urn:btih:abc")
    assert len(manager.queue) == 1
    assert manager.queue[0].game_id == 1


def test_enqueue_starts_if_idle(manager, deps):
    game = MagicMock(id=1, title="Test", slug="test")
    deps["library"].get_by_id.return_value = game
    deps["torbox"].create_torrent.return_value = 42
    with patch.object(manager, "_start_next"):
        manager.enqueue(game_id=1, magnet="magnet:?xt=urn:btih:abc")
        manager._start_next.assert_called_once()


def test_download_state_transitions():
    """Verify the state enum values."""
    assert DownloadState.PENDING.value == "pending"
    assert DownloadState.TORBOX_DOWNLOADING.value == "torbox_downloading"
    assert DownloadState.PULLING.value == "pulling"
    assert DownloadState.EXTRACTING.value == "extracting"
    assert DownloadState.INSTALLING.value == "installing"
    assert DownloadState.COMPLETE.value == "complete"
    assert DownloadState.FAILED.value == "failed"
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_downloader.py -v
```

Expected: FAIL — `ImportError`

**Step 3: Write minimal implementation**

`src/sevenseas/core/downloader.py`:
```python
"""Download manager — orchestrates the full install pipeline."""

import os
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import httpx


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
        # Start in background thread to avoid blocking GTK main loop
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

    def _pull_from_torbox(self, item: QueueItem) -> str:
        """Download the file from Torbox CDN to local cache."""
        url = self._torbox.get_download_url(item.torbox_id, file_id=0)
        cache_dir = os.path.expanduser("~/.cache/seven-seas")
        os.makedirs(cache_dir, exist_ok=True)
        local_path = os.path.join(cache_dir, f"download_{item.game_id}")
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

    def _find_game_exe(self, directory: str) -> str | None:
        """Find the main game executable (heuristic)."""
        for root, _dirs, files in os.walk(directory):
            for f in files:
                if f.lower().endswith(".exe") and f.lower() not in {
                    "setup.exe", "install.exe", "uninstall.exe", "unins000.exe",
                    "vc_redist.x64.exe", "vc_redist.x86.exe", "dxsetup.exe",
                }:
                    return os.path.relpath(os.path.join(root, f), directory)
        return None
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_downloader.py -v
```

Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/sevenseas/core/downloader.py tests/test_downloader.py
git commit -m "feat: add download manager with full install pipeline"
```

---

## Phase 3: GTK4 UI

### Task 11: Application entry point and main window shell

**Files:**
- Create: `src/sevenseas/app.py`
- Create: `src/sevenseas/ui/window.py`

**Step 1: Create the application entry point**

`src/sevenseas/app.py`:
```python
"""7-Seas Launcher application entry point."""

import os
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio

from sevenseas.db.models import get_db
from sevenseas.core.config import ConfigService
from sevenseas.ui.window import MainWindow


class SevenSeasApp(Adw.Application):
    """Main application class."""

    def __init__(self) -> None:
        super().__init__(
            application_id="com.sevenseas.Launcher",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.db = None
        self.config = None

    def do_activate(self) -> None:
        # Initialize database
        data_dir = os.path.join(
            os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
            "seven-seas",
        )
        os.makedirs(data_dir, exist_ok=True)
        self.db = get_db(os.path.join(data_dir, "sevenseas.db"))
        self.config = ConfigService(self.db)

        # Create main window
        win = self.props.active_window
        if not win:
            win = MainWindow(application=self)
        win.present()


def main() -> None:
    app = SevenSeasApp()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
```

**Step 2: Create the main window**

`src/sevenseas/ui/window.py`:
```python
"""Main application window with sidebar navigation."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib


class MainWindow(Adw.ApplicationWindow):
    """Main window with sidebar navigation and content area."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_title("7-Seas Launcher")
        self.set_default_size(1200, 800)

        # Main layout: split view with sidebar
        self._split_view = Adw.NavigationSplitView()
        self.set_content(self._split_view)

        # Sidebar
        sidebar_page = Adw.NavigationPage(title="7-Seas")
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_page.set_child(sidebar_box)

        # Sidebar header
        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_title_widget(Gtk.Label(label="7-Seas"))
        sidebar_box.append(sidebar_header)

        # Navigation list
        nav_list = Gtk.ListBox()
        nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        nav_list.add_css_class("navigation-sidebar")
        nav_list.connect("row-activated", self._on_nav_row_activated)
        sidebar_box.append(nav_list)

        # Browse section
        self._nav_items = []
        for label, icon, view_name in [
            ("Search", "system-search-symbolic", "search"),
            ("New Releases", "document-new-symbolic", "new"),
            ("Top 50", "starred-symbolic", "top50"),
            ("Top 150", "trophy-symbolic", "top150"),
        ]:
            row = self._make_nav_row(label, icon, view_name)
            nav_list.append(row)
            self._nav_items.append((row, view_name))

        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(12)
        sep.set_margin_bottom(12)
        sidebar_box.append(sep)

        # Management section
        nav_list2 = Gtk.ListBox()
        nav_list2.set_selection_mode(Gtk.SelectionMode.SINGLE)
        nav_list2.add_css_class("navigation-sidebar")
        nav_list2.connect("row-activated", self._on_nav_row_activated)
        sidebar_box.append(nav_list2)

        for label, icon, view_name in [
            ("Downloads", "folder-download-symbolic", "downloads"),
            ("Library", "application-x-executable-symbolic", "library"),
            ("Settings", "emblem-system-symbolic", "settings"),
        ]:
            row = self._make_nav_row(label, icon, view_name)
            nav_list2.append(row)
            self._nav_items.append((row, view_name))

        self._split_view.set_sidebar(sidebar_page)

        # Content area (placeholder)
        content_page = Adw.NavigationPage(title="Search")
        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_page.set_child(self._content_box)

        content_header = Adw.HeaderBar()
        self._content_box.append(content_header)

        # Placeholder label
        self._placeholder = Gtk.Label(label="Welcome to 7-Seas Launcher")
        self._placeholder.set_vexpand(True)
        self._content_box.append(self._placeholder)

        # Bottom status bar
        self._status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._status_bar.add_css_class("toolbar")
        self._status_bar.set_margin_start(12)
        self._status_bar.set_margin_end(12)
        self._status_label = Gtk.Label(label="No active downloads")
        self._status_bar.append(self._status_label)
        self._content_box.append(self._status_bar)

        self._split_view.set_content(content_page)

        # View stack for swapping content
        self._views: dict[str, Gtk.Widget] = {}
        self._current_view: str = "search"

    def _make_nav_row(self, label: str, icon_name: str, view_name: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        box.append(icon)
        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        box.append(lbl)
        row.set_child(box)
        row._view_name = view_name
        return row

    def _on_nav_row_activated(self, listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        view_name = getattr(row, "_view_name", None)
        if view_name:
            self._switch_view(view_name)

    def _switch_view(self, view_name: str) -> None:
        """Switch the content area to the named view."""
        self._current_view = view_name
        self._placeholder.set_text(f"View: {view_name}")
        # Views will be implemented in subsequent tasks

    def set_status(self, text: str) -> None:
        """Update the bottom status bar text."""
        self._status_label.set_text(text)
```

**Step 3: Test that the app launches**

```bash
python -c "
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
print('GTK4 + Libadwaita available')
"
```

Expected: `GTK4 + Libadwaita available`

Then test the import:
```bash
python -c "from sevenseas.app import SevenSeasApp; print('App class loaded')"
```

Expected: `App class loaded`

**Step 4: Commit**

```bash
git add src/sevenseas/app.py src/sevenseas/ui/window.py
git commit -m "feat: add GTK4/Libadwaita main window with sidebar navigation"
```

---

### Task 12: Settings view

**Files:**
- Create: `src/sevenseas/ui/views/settings.py`

**Step 1: Create the settings view**

`src/sevenseas/ui/views/settings.py`:
```python
"""Settings view — Torbox API key, paths, preferences."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw


class SettingsView(Gtk.Box):
    """Settings page with Torbox API key, game directory, and preferences."""

    def __init__(self, config, on_api_key_validated=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._config = config
        self._on_api_key_validated = on_api_key_validated

        # Scrollable content
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.append(scroll)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        scroll.set_child(clamp)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(12)
        content.set_margin_end(12)
        clamp.set_child(content)

        # Torbox section
        torbox_group = Adw.PreferencesGroup()
        torbox_group.set_title("Torbox")
        torbox_group.set_description("Configure your Torbox debrid service connection")
        content.append(torbox_group)

        self._api_key_row = Adw.PasswordEntryRow()
        self._api_key_row.set_title("API Key")
        current_key = config.torbox_api_key or ""
        self._api_key_row.set_text(current_key)
        torbox_group.add(self._api_key_row)

        validate_btn = Gtk.Button(label="Validate & Save")
        validate_btn.add_css_class("suggested-action")
        validate_btn.connect("clicked", self._on_validate_clicked)
        torbox_group.add(validate_btn)

        self._api_status = Gtk.Label()
        self._api_status.set_halign(Gtk.Align.START)
        torbox_group.add(self._api_status)

        # Paths section
        paths_group = Adw.PreferencesGroup()
        paths_group.set_title("Paths")
        content.append(paths_group)

        self._games_dir_row = Adw.EntryRow()
        self._games_dir_row.set_title("Games Directory")
        self._games_dir_row.set_text(config.games_dir)
        self._games_dir_row.connect("changed", self._on_games_dir_changed)
        paths_group.add(self._games_dir_row)

        # Bottles section
        bottles_group = Adw.PreferencesGroup()
        bottles_group.set_title("Bottles")
        content.append(bottles_group)

        self._bottles_row = Adw.EntryRow()
        self._bottles_row.set_title("Bottle Name")
        self._bottles_row.set_text(config.bottles_name)
        self._bottles_row.connect("changed", self._on_bottles_changed)
        bottles_group.add(self._bottles_row)

        # Steam section
        steam_group = Adw.PreferencesGroup()
        steam_group.set_title("Steam Integration")
        content.append(steam_group)

        self._steam_switch = Adw.SwitchRow()
        self._steam_switch.set_title("Auto-add to Steam")
        self._steam_switch.set_subtitle("Automatically add installed games as non-Steam shortcuts")
        self._steam_switch.set_active(config.auto_add_steam)
        self._steam_switch.connect("notify::active", self._on_steam_toggle)
        steam_group.add(self._steam_switch)

    def _on_validate_clicked(self, button: Gtk.Button) -> None:
        api_key = self._api_key_row.get_text().strip()
        if not api_key:
            self._api_status.set_text("Please enter an API key")
            return
        self._api_status.set_text("Validating...")
        self._config.set("torbox_api_key", api_key)
        if self._on_api_key_validated:
            self._on_api_key_validated(api_key)

    def _on_games_dir_changed(self, row: Adw.EntryRow) -> None:
        self._config.set("games_dir", row.get_text())

    def _on_bottles_changed(self, row: Adw.EntryRow) -> None:
        self._config.set("bottles_name", row.get_text())

    def _on_steam_toggle(self, switch: Adw.SwitchRow, _param) -> None:
        self._config.set("auto_add_steam", str(switch.get_active()).lower())

    def set_api_status(self, text: str) -> None:
        self._api_status.set_text(text)
```

**Step 2: Test import**

```bash
python -c "from sevenseas.ui.views.settings import SettingsView; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/sevenseas/ui/views/settings.py
git commit -m "feat: add settings view with Torbox API key and preferences"
```

---

### Task 13: Game card widget

**Files:**
- Create: `src/sevenseas/ui/widgets/game_card.py`

**Step 1: Create the game card widget**

`src/sevenseas/ui/widgets/game_card.py`:
```python
"""Game card widget — shows cover art, title, size, and action button."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GdkPixbuf, Gio


class GameCard(Gtk.Box):
    """A card displaying game info with an action button."""

    def __init__(
        self,
        title: str,
        size_info: str | None = None,
        thumbnail_path: str | None = None,
        status: str = "new",
        on_action=None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_size_request(200, 300)
        self.add_css_class("card")
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        self._title = title
        self._on_action = on_action

        # Cover image
        self._image = Gtk.Picture()
        self._image.set_size_request(200, 200)
        self._image.set_content_fit(Gtk.ContentFit.COVER)
        if thumbnail_path:
            self.set_thumbnail(thumbnail_path)
        else:
            placeholder = Gtk.Label(label="No Image")
            placeholder.set_size_request(200, 200)
            placeholder.add_css_class("dim-label")
            self.append(placeholder)
            self._placeholder = placeholder
        self.append(self._image)

        # Info box
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_margin_start(8)
        info_box.set_margin_end(8)
        info_box.set_margin_bottom(8)
        self.append(info_box)

        # Title
        title_label = Gtk.Label(label=title)
        title_label.set_halign(Gtk.Align.START)
        title_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        title_label.set_max_width_chars(25)
        title_label.add_css_class("heading")
        info_box.append(title_label)

        # Size
        if size_info:
            size_label = Gtk.Label(label=size_info)
            size_label.set_halign(Gtk.Align.START)
            size_label.add_css_class("dim-label")
            info_box.append(size_label)

        # Action button
        self._action_btn = Gtk.Button()
        self._action_btn.add_css_class("suggested-action")
        self._update_button_for_status(status)
        self._action_btn.connect("clicked", self._on_button_clicked)
        info_box.append(self._action_btn)

    def _update_button_for_status(self, status: str) -> None:
        labels = {
            "new": "Install",
            "downloading": "Downloading...",
            "extracting": "Extracting...",
            "installing": "Installing...",
            "installed": "Launch",
            "failed": "Retry",
        }
        self._action_btn.set_label(labels.get(status, "Install"))
        self._action_btn.set_sensitive(status in ("new", "installed", "failed"))

    def _on_button_clicked(self, button: Gtk.Button) -> None:
        if self._on_action:
            self._on_action(self._title)

    def set_thumbnail(self, path: str) -> None:
        """Load a thumbnail image from a local file path."""
        try:
            self._image.set_filename(path)
        except Exception:
            pass
```

**Step 2: Test import**

```bash
python -c "from sevenseas.ui.widgets.game_card import GameCard; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/sevenseas/ui/widgets/game_card.py
git commit -m "feat: add game card widget for search results and library"
```

---

### Task 14: Download row widget

**Files:**
- Create: `src/sevenseas/ui/widgets/download_row.py`

**Step 1: Create the download row widget**

`src/sevenseas/ui/widgets/download_row.py`:
```python
"""Download progress row widget."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw


def _format_speed(bps: int) -> str:
    if bps < 1024:
        return f"{bps} B/s"
    elif bps < 1024 * 1024:
        return f"{bps / 1024:.1f} KB/s"
    else:
        return f"{bps / (1024 * 1024):.1f} MB/s"


class DownloadRow(Gtk.Box):
    """A row showing download progress with title, stage, progress bar, speed."""

    def __init__(
        self,
        title: str,
        stage: str = "Pending",
        progress: float = 0.0,
        speed_bps: int = 0,
        on_cancel=None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(12)
        self.set_margin_end(12)

        # Top row: title + stage + cancel
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(top_row)

        self._title_label = Gtk.Label(label=title)
        self._title_label.set_halign(Gtk.Align.START)
        self._title_label.set_hexpand(True)
        self._title_label.add_css_class("heading")
        top_row.append(self._title_label)

        self._stage_label = Gtk.Label(label=stage)
        self._stage_label.add_css_class("dim-label")
        top_row.append(self._stage_label)

        self._speed_label = Gtk.Label(label=_format_speed(speed_bps))
        self._speed_label.add_css_class("dim-label")
        top_row.append(self._speed_label)

        if on_cancel:
            cancel_btn = Gtk.Button.new_from_icon_name("process-stop-symbolic")
            cancel_btn.add_css_class("flat")
            cancel_btn.connect("clicked", lambda _: on_cancel())
            top_row.append(cancel_btn)

        # Progress bar
        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_fraction(progress)
        self._progress_bar.set_show_text(True)
        self._progress_bar.set_text(f"{progress * 100:.0f}%")
        self.append(self._progress_bar)

    def update(self, stage: str, progress: float, speed_bps: int) -> None:
        """Update the row's display."""
        self._stage_label.set_text(stage)
        self._progress_bar.set_fraction(min(progress, 1.0))
        self._progress_bar.set_text(f"{progress * 100:.0f}%")
        self._speed_label.set_text(_format_speed(speed_bps))
```

**Step 2: Test import**

```bash
python -c "from sevenseas.ui.widgets.download_row import DownloadRow; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/sevenseas/ui/widgets/download_row.py
git commit -m "feat: add download progress row widget"
```

---

### Task 15: Search view

**Files:**
- Create: `src/sevenseas/ui/views/search.py`

**Step 1: Create the search view**

`src/sevenseas/ui/views/search.py`:
```python
"""Search view — search FitGirl Repacks and display results."""

import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from sevenseas.ui.widgets.game_card import GameCard


class SearchView(Gtk.Box):
    """Search page with search bar and results grid."""

    def __init__(self, scraper, on_install=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._scraper = scraper
        self._on_install = on_install

        # Search bar
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        search_box.set_margin_top(12)
        search_box.set_margin_start(12)
        search_box.set_margin_end(12)
        self.append(search_box)

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search FitGirl Repacks...")
        self._search_entry.set_hexpand(True)
        self._search_entry.connect("activate", self._on_search)
        search_box.append(self._search_entry)

        # Spinner for loading state
        self._spinner = Gtk.Spinner()
        search_box.append(self._spinner)

        # Scrollable results area
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.append(scroll)

        self._results_flow = Gtk.FlowBox()
        self._results_flow.set_valign(Gtk.Align.START)
        self._results_flow.set_max_children_per_line(6)
        self._results_flow.set_min_children_per_line(2)
        self._results_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._results_flow.set_homogeneous(True)
        scroll.set_child(self._results_flow)

        # Empty state
        self._empty_label = Gtk.Label(label="Search for a game to get started")
        self._empty_label.add_css_class("dim-label")
        self._empty_label.set_vexpand(True)
        self.append(self._empty_label)

    def _on_search(self, entry: Gtk.SearchEntry) -> None:
        query = entry.get_text().strip()
        if not query:
            return
        self._spinner.start()
        self._empty_label.set_visible(False)
        # Run scraper in background thread
        thread = threading.Thread(target=self._do_search, args=(query,), daemon=True)
        thread.start()

    def _do_search(self, query: str) -> None:
        try:
            results = self._scraper.search(query)
            GLib.idle_add(self._display_results, results)
        except Exception as e:
            GLib.idle_add(self._show_error, str(e))

    def _display_results(self, results) -> None:
        self._spinner.stop()
        # Clear existing results
        while child := self._results_flow.get_first_child():
            self._results_flow.remove(child)
        if not results:
            self._empty_label.set_text("No results found")
            self._empty_label.set_visible(True)
            return
        for r in results:
            card = GameCard(
                title=r.title,
                size_info=r.size_info,
                on_action=lambda title, url=r.url: self._on_install_clicked(title, url),
            )
            self._results_flow.append(card)

    def _on_install_clicked(self, title: str, url: str) -> None:
        if self._on_install:
            self._on_install(title, url)

    def _show_error(self, message: str) -> None:
        self._spinner.stop()
        self._empty_label.set_text(f"Error: {message}")
        self._empty_label.set_visible(True)
```

**Step 2: Test import**

```bash
python -c "from sevenseas.ui.views.search import SearchView; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/sevenseas/ui/views/search.py
git commit -m "feat: add search view with FitGirl results grid"
```

---

### Task 16: Browse views (New, Top 50, Top 150)

**Files:**
- Create: `src/sevenseas/ui/views/browse.py`

**Step 1: Create the browse view**

`src/sevenseas/ui/views/browse.py`:
```python
"""Browse views — New Releases, Top 50, Top 150."""

import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from sevenseas.ui.widgets.game_card import GameCard


class BrowseView(Gtk.Box):
    """Generic browse page that loads a listing from the scraper."""

    def __init__(self, title: str, fetch_func, on_install=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._fetch_func = fetch_func
        self._on_install = on_install
        self._loaded = False

        # Title bar
        title_label = Gtk.Label(label=title)
        title_label.add_css_class("title-1")
        title_label.set_margin_top(16)
        title_label.set_margin_bottom(12)
        self.append(title_label)

        # Spinner
        self._spinner = Gtk.Spinner()
        self.append(self._spinner)

        # Scrollable results
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.append(scroll)

        self._flow = Gtk.FlowBox()
        self._flow.set_valign(Gtk.Align.START)
        self._flow.set_max_children_per_line(6)
        self._flow.set_min_children_per_line(2)
        self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow.set_homogeneous(True)
        scroll.set_child(self._flow)

        # Status label
        self._status = Gtk.Label()
        self._status.add_css_class("dim-label")
        self.append(self._status)

    def load(self) -> None:
        """Trigger loading data (call when view becomes visible)."""
        if self._loaded:
            return
        self._spinner.start()
        thread = threading.Thread(target=self._fetch, daemon=True)
        thread.start()

    def _fetch(self) -> None:
        try:
            results = self._fetch_func()
            GLib.idle_add(self._display, results)
        except Exception as e:
            GLib.idle_add(self._show_error, str(e))

    def _display(self, results) -> None:
        self._spinner.stop()
        self._loaded = True
        while child := self._flow.get_first_child():
            self._flow.remove(child)
        if not results:
            self._status.set_text("No games found")
            return
        self._status.set_text(f"{len(results)} games")
        for r in results:
            card = GameCard(
                title=r.title,
                size_info=r.size_info,
                on_action=lambda title, url=r.url: self._on_install_clicked(title, url),
            )
            self._flow.append(card)

    def _on_install_clicked(self, title: str, url: str) -> None:
        if self._on_install:
            self._on_install(title, url)

    def _show_error(self, msg: str) -> None:
        self._spinner.stop()
        self._status.set_text(f"Error: {msg}")
```

**Step 2: Test import**

```bash
python -c "from sevenseas.ui.views.browse import BrowseView; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/sevenseas/ui/views/browse.py
git commit -m "feat: add browse view for New, Top 50, Top 150 pages"
```

---

### Task 17: Downloads view

**Files:**
- Create: `src/sevenseas/ui/views/downloads.py`

**Step 1: Create the downloads view**

`src/sevenseas/ui/views/downloads.py`:
```python
"""Downloads view — active and completed downloads."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from sevenseas.ui.widgets.download_row import DownloadRow


_STAGE_LABELS = {
    "pending": "Pending",
    "torbox_downloading": "Torbox Downloading",
    "pulling": "Downloading from Torbox",
    "extracting": "Extracting",
    "installing": "Installing",
    "complete": "Complete",
    "failed": "Failed",
}


class DownloadsView(Gtk.Box):
    """Shows active downloads and their progress."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        title = Gtk.Label(label="Downloads")
        title.add_css_class("title-1")
        title.set_margin_top(16)
        title.set_margin_bottom(12)
        self.append(title)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.append(scroll)

        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list_box.add_css_class("boxed-list")
        self._list_box.set_margin_start(12)
        self._list_box.set_margin_end(12)
        scroll.set_child(self._list_box)

        self._rows: dict[int, DownloadRow] = {}

        # Empty state
        self._empty = Gtk.Label(label="No downloads")
        self._empty.add_css_class("dim-label")
        self._empty.set_vexpand(True)
        self.append(self._empty)

    def add_download(self, game_id: int, title: str) -> None:
        """Add a new download entry."""
        self._empty.set_visible(False)
        row = DownloadRow(title=title, stage="Pending")
        self._rows[game_id] = row
        self._list_box.append(row)

    def update_download(
        self, game_id: int, state: str, progress: float, speed_bps: int
    ) -> None:
        """Update an existing download's progress."""
        row = self._rows.get(game_id)
        if row:
            stage = _STAGE_LABELS.get(state, state)
            row.update(stage, progress, speed_bps)

    def remove_download(self, game_id: int) -> None:
        """Remove a completed/cancelled download."""
        row = self._rows.pop(game_id, None)
        if row:
            self._list_box.remove(row)
        if not self._rows:
            self._empty.set_visible(True)
```

**Step 2: Test import**

```bash
python -c "from sevenseas.ui.views.downloads import DownloadsView; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/sevenseas/ui/views/downloads.py
git commit -m "feat: add downloads view with progress tracking"
```

---

### Task 18: Library view

**Files:**
- Create: `src/sevenseas/ui/views/library.py`

**Step 1: Create the library view**

`src/sevenseas/ui/views/library.py`:
```python
"""Library view — shows installed games."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from sevenseas.ui.widgets.game_card import GameCard


class LibraryView(Gtk.Box):
    """Grid of installed games with launch/manage actions."""

    def __init__(self, library_service, on_launch=None, on_uninstall=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._library = library_service
        self._on_launch = on_launch
        self._on_uninstall = on_uninstall

        title = Gtk.Label(label="Library")
        title.add_css_class("title-1")
        title.set_margin_top(16)
        title.set_margin_bottom(12)
        self.append(title)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.append(scroll)

        self._flow = Gtk.FlowBox()
        self._flow.set_valign(Gtk.Align.START)
        self._flow.set_max_children_per_line(6)
        self._flow.set_min_children_per_line(2)
        self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow.set_homogeneous(True)
        scroll.set_child(self._flow)

        self._empty = Gtk.Label(label="No games installed yet")
        self._empty.add_css_class("dim-label")
        self._empty.set_vexpand(True)
        self.append(self._empty)

    def refresh(self) -> None:
        """Reload the library from the database."""
        while child := self._flow.get_first_child():
            self._flow.remove(child)
        games = self._library.get_installed()
        self._empty.set_visible(len(games) == 0)
        for game in games:
            card = GameCard(
                title=game.title,
                status="installed",
                on_action=lambda title, g=game: self._on_game_action(g),
            )
            self._flow.append(card)

    def _on_game_action(self, game) -> None:
        if self._on_launch:
            self._on_launch(game)
```

**Step 2: Test import**

```bash
python -c "from sevenseas.ui.views.library import LibraryView; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/sevenseas/ui/views/library.py
git commit -m "feat: add library view showing installed games"
```

---

## Phase 4: Wire Everything Together

### Task 19: Wire up main window with all views and services

**Files:**
- Modify: `src/sevenseas/app.py`
- Modify: `src/sevenseas/ui/window.py`

**Step 1: Update app.py to initialize all services**

Replace `src/sevenseas/app.py` with the version that initializes all services and passes them to the window. Key changes:

- Import and instantiate all core services (scraper, torbox, extractor, installer, library, steam, downloader)
- Pass services to MainWindow
- Handle first-run check (if no API key, show settings first)

```python
"""7-Seas Launcher application entry point."""

import os
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio

from sevenseas.db.models import get_db
from sevenseas.core.config import ConfigService
from sevenseas.core.scraper import FitGirlScraper
from sevenseas.core.library import LibraryService
from sevenseas.core.extractor import Extractor
from sevenseas.core.installer import BottlesInstaller
from sevenseas.core.steam import SteamShortcuts
from sevenseas.ui.window import MainWindow


class SevenSeasApp(Adw.Application):
    """Main application class."""

    def __init__(self) -> None:
        super().__init__(
            application_id="com.sevenseas.Launcher",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.db = None
        self.config = None

    def do_activate(self) -> None:
        # Initialize database
        data_dir = os.path.join(
            os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
            "seven-seas",
        )
        os.makedirs(data_dir, exist_ok=True)
        self.db = get_db(os.path.join(data_dir, "sevenseas.db"))
        self.config = ConfigService(self.db)

        # Initialize services
        services = {
            "config": self.config,
            "scraper": FitGirlScraper(),
            "library": LibraryService(self.db),
            "extractor": Extractor(),
            "installer": BottlesInstaller(self.config.bottles_name),
            "steam": SteamShortcuts(),
        }

        # Torbox client initialized lazily (needs API key)

        # Create main window
        win = self.props.active_window
        if not win:
            win = MainWindow(application=self, services=services, db=self.db)

        # Show settings on first run
        if not self.config.torbox_api_key:
            win.show_settings()

        win.present()


def main() -> None:
    app = SevenSeasApp()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
```

**Step 2: Update window.py to manage views**

Update `src/sevenseas/ui/window.py` to:
- Accept services dict
- Create all view instances
- Wire sidebar navigation to view switching
- Wire install callbacks through to the download manager
- Connect download progress to status bar updates

The key addition is the `_switch_view` method that swaps the content area's child widget, and the `_on_install_requested` callback that coordinates scraping the detail page, extracting the magnet, and enqueuing the download.

```python
# In MainWindow.__init__, after creating sidebar, add:
# self._init_views(services, db)

# New method:
def _init_views(self, services, db):
    """Create all view instances."""
    from sevenseas.ui.views.search import SearchView
    from sevenseas.ui.views.browse import BrowseView
    from sevenseas.ui.views.downloads import DownloadsView
    from sevenseas.ui.views.library import LibraryView
    from sevenseas.ui.views.settings import SettingsView

    scraper = services["scraper"]
    library = services["library"]
    config = services["config"]

    self._views = {
        "search": SearchView(scraper, on_install=self._on_install_requested),
        "new": BrowseView("New Releases", scraper.get_latest, on_install=self._on_install_requested),
        "top50": BrowseView("Top 50 This Month", scraper.get_top_monthly, on_install=self._on_install_requested),
        "top150": BrowseView("Top 150 This Year", scraper.get_top_yearly, on_install=self._on_install_requested),
        "downloads": DownloadsView(),
        "library": LibraryView(library),
        "settings": SettingsView(config, on_api_key_validated=self._on_api_key_validated),
    }
```

(See full implementation in the code — the engineer should merge these changes into the existing window.py, keeping the sidebar navigation intact and adding the view management.)

**Step 3: Test the app launches**

```bash
seven-seas
```

Expected: GTK window opens with sidebar navigation. Clicking sidebar items switches views. Settings view shows on first run.

**Step 4: Commit**

```bash
git add src/sevenseas/app.py src/sevenseas/ui/window.py
git commit -m "feat: wire all views and services into main window"
```

---

### Task 20: Desktop file and metadata

**Files:**
- Create: `data/com.sevenseas.Launcher.desktop`
- Create: `data/com.sevenseas.Launcher.metainfo.xml`

**Step 1: Create .desktop file**

`data/com.sevenseas.Launcher.desktop`:
```ini
[Desktop Entry]
Name=7-Seas Launcher
Comment=Download and install games via Torbox and Bottles
Exec=seven-seas
Icon=com.sevenseas.Launcher
Terminal=false
Type=Application
Categories=Game;
Keywords=games;installer;torbox;bottles;wine;
```

**Step 2: Create metainfo**

`data/com.sevenseas.Launcher.metainfo.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>com.sevenseas.Launcher</id>
  <name>7-Seas Launcher</name>
  <summary>Download and install games via Torbox and Bottles</summary>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>GPL-3.0-or-later</project_license>
  <description>
    <p>
      7-Seas Launcher is a Linux game installer that downloads games
      from FitGirl Repacks via the Torbox debrid API and installs them
      through Bottles. Features a game library with Steam integration.
    </p>
  </description>
  <launchable type="desktop-id">com.sevenseas.Launcher.desktop</launchable>
  <url type="homepage">https://github.com/alex/seven-seas-launcher</url>
  <content_rating type="oars-1.1" />
  <releases>
    <release version="0.1.0" date="2026-02-19">
      <description>
        <p>Initial release</p>
      </description>
    </release>
  </releases>
</component>
```

**Step 3: Commit**

```bash
git add data/
git commit -m "feat: add .desktop file and AppStream metainfo"
```

---

## Phase 5: Polish & Integration Testing

### Task 21: Run the full app and fix integration issues

**Step 1: Install dependencies**

```bash
pip install -e ".[dev]"
```

**Step 2: Run all unit tests**

```bash
pytest tests/ -v
```

Expected: All tests pass

**Step 3: Launch the app and test manually**

```bash
seven-seas
```

Test each flow:
1. Settings: Enter Torbox API key, validate
2. Search: Search for a game, see results
3. Browse: Click New, Top 50, Top 150 — see listings load
4. Install: Click Install on a game — watch the pipeline in Downloads view
5. Library: After install, see game in Library with Launch button

**Step 4: Fix any issues found during manual testing**

(This is an open-ended debugging step — fix issues as they arise)

**Step 5: Run tests again and commit fixes**

```bash
pytest tests/ -v
git add -A
git commit -m "fix: integration fixes from manual testing"
```

---

### Task 22: Add error handling and retry logic

**Files:**
- Modify: `src/sevenseas/core/downloader.py` (add retry with backoff)
- Modify: `src/sevenseas/ui/views/downloads.py` (add retry/error UI)

**Step 1: Add exponential backoff to HTTP downloads in downloader.py**

Add a `_retry` helper that wraps the httpx download with 3 attempts and exponential backoff. Add error display in the downloads view when a download fails, with a "Retry" button.

**Step 2: Test retry logic**

```bash
pytest tests/test_downloader.py -v
```

**Step 3: Commit**

```bash
git add src/sevenseas/core/downloader.py src/sevenseas/ui/views/downloads.py
git commit -m "feat: add retry with exponential backoff for downloads"
```

---

### Task 23: Final commit and tag

**Step 1: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests pass

**Step 2: Tag the release**

```bash
git tag -a v0.1.0 -m "7-Seas Launcher v0.1.0 — initial release"
```

---

## Summary

| Phase | Tasks | What it builds |
|-------|-------|----------------|
| 1: Scaffolding | 1-3 | Project structure, database, config |
| 2: Core Services | 4-10 | Library, scraper, Torbox client, extractor, Bottles installer, Steam shortcuts, download manager |
| 3: GTK4 UI | 11-18 | Main window, settings, game cards, search, browse, downloads, library views |
| 4: Integration | 19-20 | Wire everything together, desktop files |
| 5: Polish | 21-23 | Integration testing, error handling, release tag |

**Total: 23 tasks, ~100 commits**
