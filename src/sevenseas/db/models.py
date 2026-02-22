"""SQLite schema definition and table creation."""

import os
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


def get_db(db_path: str) -> sqlite3.Connection:
    """Open a database connection and ensure schema exists."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    os.chmod(db_path, 0o600)  # Owner read/write only
    conn.execute("PRAGMA journal_mode=WAL")  # Safe concurrent reads/writes
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    return conn
