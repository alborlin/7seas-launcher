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
        with patch("sevenseas.core.steam.Path.home", return_value=tmp_path):
            shortcuts = SteamShortcuts()
            paths = shortcuts._find_userdata_dirs()
            assert len(paths) >= 1
            assert any("12345" in str(p) for p in paths)


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


def test_generate_artwork_id():
    """generate_artwork_id returns unsigned 32-bit ID for artwork filenames."""
    from sevenseas.core.steam import SteamShortcuts
    uid = SteamShortcuts.generate_artwork_id("TestGame", "/usr/bin/test")
    assert uid > 0
    assert uid <= 0xFFFFFFFF


def test_get_grid_dirs(tmp_path):
    """get_grid_dirs returns grid directory paths for each Steam user."""
    from sevenseas.core.steam import SteamShortcuts
    steam = SteamShortcuts()
    user_dir = tmp_path / "userdata" / "12345" / "config"
    user_dir.mkdir(parents=True)
    grid_dir = user_dir / "grid"
    grid_dir.mkdir()
    steam._userdata_dirs = [user_dir]

    dirs = steam.get_grid_dirs()
    assert len(dirs) == 1
    assert dirs[0] == grid_dir
