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
