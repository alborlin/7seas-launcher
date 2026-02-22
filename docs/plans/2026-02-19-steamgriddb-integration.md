# SteamGridDB Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fetch game artwork (grid, hero, logo, icon) from SteamGridDB and save it to Steam's grid directory when adding non-Steam shortcuts, so games have proper artwork in the Steam library.

**Architecture:** New `SteamGridDBClient` in `sevenseas/core/steamgriddb.py` wraps the SteamGridDB REST API v2 using httpx. After the downloader pipeline adds a Steam shortcut (Step 7), it calls the client to search for the game by title, fetch the highest-scored artwork for each type, and download them to `~/.local/share/Steam/userdata/<uid>/config/grid/` with Steam's expected filenames. API key is stored in the settings DB alongside the Torbox key.

**Tech Stack:** httpx (already in use), SteamGridDB REST API v2 (no SDK)

---

### Task 1: Add `steamgriddb_api_key` config property

**Files:**
- Modify: `src/sevenseas/core/config.py:34-48`

**Step 1: Add the property**

Add after the `torbox_api_key` property in `config.py`:

```python
@property
def steamgriddb_api_key(self) -> str | None:
    return self.get("steamgriddb_api_key")
```

**Step 2: Run existing tests to verify nothing broke**

Run: `source .venv/bin/activate && python -m pytest tests/ -v`
Expected: All 60 tests PASS

**Step 3: Commit**

```bash
git add src/sevenseas/core/config.py
git commit -m "feat: add steamgriddb_api_key config property"
```

---

### Task 2: Create `SteamGridDBClient` with search and image fetching

**Files:**
- Create: `src/sevenseas/core/steamgriddb.py`
- Create: `tests/test_steamgriddb.py`

**Step 1: Write the failing tests**

Create `tests/test_steamgriddb.py`:

```python
"""Tests for the SteamGridDB API client."""

import json
from unittest.mock import MagicMock, patch

import pytest

from sevenseas.core.steamgriddb import SteamGridDBClient


@pytest.fixture
def client():
    return SteamGridDBClient(api_key="test-key")


def test_search_game(client):
    """search_game returns list of results with id and name."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "success": True,
        "data": [
            {"id": 2254, "name": "Half-Life 2", "types": ["steam"], "verified": True},
            {"id": 9999, "name": "Half-Life 2: Episode One", "types": ["steam"], "verified": True},
        ],
    }
    mock_resp.raise_for_status = MagicMock()
    client._http = MagicMock()
    client._http.get.return_value = mock_resp

    results = client.search_game("Half-Life 2")
    assert len(results) == 2
    assert results[0]["id"] == 2254
    assert results[0]["name"] == "Half-Life 2"
    client._http.get.assert_called_once_with("/search/autocomplete/Half-Life 2")


def test_search_game_no_results(client):
    """search_game returns empty list when no matches."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"success": True, "data": []}
    mock_resp.raise_for_status = MagicMock()
    client._http = MagicMock()
    client._http.get.return_value = mock_resp

    results = client.search_game("xyznonexistent")
    assert results == []


def test_get_artwork_urls(client):
    """get_artwork_urls returns dict with grid/hero/logo/icon URLs."""
    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "/grids/" in url:
            resp.json.return_value = {"success": True, "data": [
                {"id": 1, "score": 5, "url": "https://cdn.steamgriddb.com/grid/abc.png"},
            ]}
        elif "/heroes/" in url:
            resp.json.return_value = {"success": True, "data": [
                {"id": 2, "score": 3, "url": "https://cdn.steamgriddb.com/hero/def.png"},
            ]}
        elif "/logos/" in url:
            resp.json.return_value = {"success": True, "data": [
                {"id": 3, "score": 4, "url": "https://cdn.steamgriddb.com/logo/ghi.png"},
            ]}
        elif "/icons/" in url:
            resp.json.return_value = {"success": True, "data": [
                {"id": 4, "score": 2, "url": "https://cdn.steamgriddb.com/icon/jkl.png"},
            ]}
        else:
            resp.json.return_value = {"success": True, "data": []}
        return resp

    client._http = MagicMock()
    client._http.get.side_effect = mock_get

    urls = client.get_artwork_urls(game_id=2254)
    assert urls["grid"] == "https://cdn.steamgriddb.com/grid/abc.png"
    assert urls["hero"] == "https://cdn.steamgriddb.com/hero/def.png"
    assert urls["logo"] == "https://cdn.steamgriddb.com/logo/ghi.png"
    assert urls["icon"] == "https://cdn.steamgriddb.com/icon/jkl.png"


def test_get_artwork_urls_missing_types(client):
    """get_artwork_urls handles missing artwork gracefully."""
    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"success": True, "data": []}
        return resp

    client._http = MagicMock()
    client._http.get.side_effect = mock_get

    urls = client.get_artwork_urls(game_id=2254)
    assert urls["grid"] is None
    assert urls["hero"] is None
    assert urls["logo"] is None
    assert urls["icon"] is None


def test_get_artwork_urls_picks_highest_score(client):
    """get_artwork_urls picks the image with the highest score."""
    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "/grids/" in url:
            resp.json.return_value = {"success": True, "data": [
                {"id": 1, "score": 2, "url": "https://cdn.steamgriddb.com/grid/low.png"},
                {"id": 2, "score": 8, "url": "https://cdn.steamgriddb.com/grid/high.png"},
                {"id": 3, "score": 5, "url": "https://cdn.steamgriddb.com/grid/mid.png"},
            ]}
        else:
            resp.json.return_value = {"success": True, "data": []}
        return resp

    client._http = MagicMock()
    client._http.get.side_effect = mock_get

    urls = client.get_artwork_urls(game_id=2254)
    assert urls["grid"] == "https://cdn.steamgriddb.com/grid/high.png"
```

**Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_steamgriddb.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sevenseas.core.steamgriddb'`

**Step 3: Write the implementation**

Create `src/sevenseas/core/steamgriddb.py`:

```python
"""SteamGridDB API client — fetches game artwork for Steam library."""

import logging
import os
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_BASE_URL = "https://www.steamgriddb.com/api/v2"


class SteamGridDBClient:
    """Fetches game artwork from SteamGridDB."""

    def __init__(self, api_key: str) -> None:
        self._http = httpx.Client(
            base_url=_BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15.0,
        )

    def search_game(self, name: str) -> list[dict]:
        """Search for a game by name. Returns list of result dicts."""
        resp = self._http.get(f"/search/autocomplete/{name}")
        resp.raise_for_status()
        return resp.json().get("data", [])

    def get_artwork_urls(self, game_id: int) -> dict[str, str | None]:
        """Fetch the best artwork URL for each type (grid, hero, logo, icon)."""
        urls = {}
        queries = {
            "grid": ("/grids/game/{id}", {"dimensions": "600x900", "types": "static"}),
            "hero": ("/heroes/game/{id}", {"types": "static"}),
            "logo": ("/logos/game/{id}", {"types": "static"}),
            "icon": ("/icons/game/{id}", {"types": "static"}),
        }
        for art_type, (endpoint, params) in queries.items():
            try:
                resp = self._http.get(
                    endpoint.format(id=game_id),
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
                if data:
                    best = max(data, key=lambda x: x.get("score", 0))
                    urls[art_type] = best["url"]
                else:
                    urls[art_type] = None
            except Exception as e:
                log.warning("SteamGridDB: failed to fetch %s for game %d: %s", art_type, game_id, e)
                urls[art_type] = None
        return urls

    def download_image(self, url: str, dest_path: str) -> bool:
        """Download an image from URL to local path. Returns True on success."""
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=30.0)
            resp.raise_for_status()
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(resp.content)
            log.info("Downloaded artwork to %s", dest_path)
            return True
        except Exception as e:
            log.warning("Failed to download %s: %s", url, e)
            return False
```

**Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_steamgriddb.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/sevenseas/core/steamgriddb.py tests/test_steamgriddb.py
git commit -m "feat: add SteamGridDB API client with search and artwork fetching"
```

---

### Task 3: Add artwork file path helpers to `SteamShortcuts`

**Files:**
- Modify: `src/sevenseas/core/steam.py:10-47`
- Modify: `tests/test_steam.py`

**Step 1: Write the failing tests**

Add to `tests/test_steam.py`:

```python
def test_generate_artwork_id():
    """generate_artwork_id returns unsigned 32-bit ID for artwork filenames."""
    from sevenseas.core.steam import SteamShortcuts
    uid = SteamShortcuts.generate_artwork_id("TestGame", "/usr/bin/test")
    # Must be unsigned (positive) and 32-bit
    assert uid > 0
    assert uid <= 0xFFFFFFFF


def test_get_grid_dirs(tmp_path):
    """get_grid_dirs returns grid directory paths for each Steam user."""
    from sevenseas.core.steam import SteamShortcuts
    steam = SteamShortcuts()
    # Create fake userdata structure
    user_dir = tmp_path / "userdata" / "12345" / "config"
    user_dir.mkdir(parents=True)
    grid_dir = user_dir / "grid"
    grid_dir.mkdir()
    steam._userdata_dirs = [user_dir]

    dirs = steam.get_grid_dirs()
    assert len(dirs) == 1
    assert dirs[0] == grid_dir
```

**Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_steam.py::test_generate_artwork_id tests/test_steam.py::test_get_grid_dirs -v`
Expected: FAIL with `AttributeError`

**Step 3: Write the implementation**

Add these methods to the `SteamShortcuts` class in `src/sevenseas/core/steam.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_steam.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/sevenseas/core/steam.py tests/test_steam.py
git commit -m "feat: add artwork ID generation and grid directory helpers to SteamShortcuts"
```

---

### Task 4: Add SteamGridDB API key field to Settings UI

**Files:**
- Modify: `src/sevenseas/ui/views/settings.py:75-85`

**Step 1: Add the SteamGridDB API key field**

In `settings.py`, find the Steam Integration section (line 75). Insert a new `Adw.PasswordEntryRow` for the SteamGridDB API key inside the `steam_group`, right after the `_steam_switch` row:

```python
        self._sgdb_key_row = Adw.PasswordEntryRow()
        self._sgdb_key_row.set_title("SteamGridDB API Key")
        self._sgdb_key_row.set_text(config.steamgriddb_api_key or "")
        self._sgdb_key_row.connect("changed", self._on_sgdb_key_changed)
        steam_group.add(self._sgdb_key_row)
```

And add the handler method:

```python
    def _on_sgdb_key_changed(self, row: Adw.EntryRow) -> None:
        self._config.set("steamgriddb_api_key", row.get_text().strip())
```

**Step 2: Run existing tests to verify nothing broke**

Run: `source .venv/bin/activate && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add src/sevenseas/ui/views/settings.py
git commit -m "feat: add SteamGridDB API key field to settings UI"
```

---

### Task 5: Wire SteamGridDB into the download pipeline

**Files:**
- Modify: `src/sevenseas/core/downloader.py:170-202`

**Step 1: Add artwork fetching after Steam shortcut creation**

In `downloader.py`, inside the Step 7 try block, after the `if shortcut_id:` block that updates `steam_shortcut_id`, add artwork fetching. The modified Step 7 should look like this (only the new code after the existing shortcut logic):

```python
                    # Fetch artwork from SteamGridDB
                    if shortcut_id and self._config.steamgriddb_api_key:
                        self._fetch_steam_artwork(
                            game.title, app_name=game.title, exe_path=launch_exe if used_bottles else exe_full,
                        )
```

Then add this new method to the `DownloadManager` class:

```python
    def _fetch_steam_artwork(self, game_title: str, app_name: str, exe_path: str) -> None:
        """Fetch and save artwork from SteamGridDB for a Steam shortcut."""
        from sevenseas.core.steamgriddb import SteamGridDBClient

        try:
            sgdb = SteamGridDBClient(api_key=self._config.steamgriddb_api_key)
            results = sgdb.search_game(game_title)
            if not results:
                log.info("SteamGridDB: no results for '%s'", game_title)
                return

            game_id = results[0]["id"]
            urls = sgdb.get_artwork_urls(game_id)
            artwork_id = self._steam.generate_artwork_id(app_name, exe_path)
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

            log.info("SteamGridDB: saved artwork for '%s' (sgdb_id=%d)", game_title, game_id)
        except Exception as e:
            log.warning("SteamGridDB artwork fetch failed for '%s': %s (non-fatal)", game_title, e)
```

**Step 2: Run all tests to verify nothing broke**

Run: `source .venv/bin/activate && python -m pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add src/sevenseas/core/downloader.py
git commit -m "feat: fetch SteamGridDB artwork when adding Steam shortcuts"
```

---

### Task 6: End-to-end verification

**Step 1: Verify the full flow manually**

1. Launch the app: `source .venv/bin/activate && python -m sevenseas`
2. Go to Settings, enter your SteamGridDB API key (get one free from https://www.steamgriddb.com/profile/preferences/api)
3. Install a game
4. After install completes, check `~/.local/share/Steam/userdata/<uid>/config/grid/` for new artwork files
5. Open Steam and verify the game shows custom artwork

**Step 2: Run full test suite**

Run: `source .venv/bin/activate && python -m pytest tests/ -v`
Expected: All tests PASS (should be 65+ now)

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete SteamGridDB integration for game artwork"
```
