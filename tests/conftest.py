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
