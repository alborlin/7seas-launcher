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
        # Return existing game if slug already exists (e.g. retry after failure)
        existing = self.get_by_slug(slug)
        if existing:
            self.update_status(existing.id, "new")
            return existing
        cursor = self._db.execute(
            """INSERT INTO games (title, slug, source_url, cover_url, size_bytes)
               VALUES (?, ?, ?, ?, ?)""",
            (title, slug, source_url, cover_url, size_bytes),
        )
        self._db.commit()
        return self.get_by_id(cursor.lastrowid)

    def get_by_slug(self, slug: str) -> Game | None:
        row = self._db.execute(
            "SELECT * FROM games WHERE slug = ?", (slug,)
        ).fetchone()
        return _row_to_game(row) if row else None

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
