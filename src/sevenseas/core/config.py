"""Application settings backed by SQLite."""

import os
import sqlite3


class ConfigService:
    """Read/write app settings from the settings table."""

    _DEFAULTS = {
        "games_dir": os.path.expanduser("~/Games"),
        "bottles_name": "7seas-installer",
        "auto_add_steam": "true",
        "download_method": "torbox",
        "bt_host": "localhost",
        "bt_port": "",
        "bt_username": "",
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
    def steamgriddb_api_key(self) -> str | None:
        return self.get("steamgriddb_api_key")

    @property
    def auto_add_steam(self) -> bool:
        return self.get("auto_add_steam", "true").lower() == "true"

    @property
    def download_method(self) -> str:
        return self.get("download_method", "torbox")

    @property
    def bt_host(self) -> str:
        return self.get("bt_host", "localhost")

    @property
    def bt_port(self) -> str:
        return self.get("bt_port", "")

    @property
    def bt_username(self) -> str:
        return self.get("bt_username", "")

    @property
    def bt_password(self) -> str | None:
        return self.get("bt_password")

    @property
    def proton_version(self) -> str | None:
        """Internal name of the preferred Proton compat tool, or None for Steam default."""
        val = self.get("proton_version")
        return val if val else None
