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
