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
        data_dir = os.path.join(
            os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
            "seven-seas",
        )
        os.makedirs(data_dir, exist_ok=True)
        self.db = get_db(os.path.join(data_dir, "sevenseas.db"))
        self.config = ConfigService(self.db)

        services = {
            "config": self.config,
            "scraper": FitGirlScraper(),
            "library": LibraryService(self.db),
            "extractor": Extractor(),
            "installer": BottlesInstaller(self.config.bottles_name),
            "steam": SteamShortcuts(),
        }

        win = self.props.active_window
        if not win:
            win = MainWindow(application=self, services=services, db=self.db)

        if not self.config.torbox_api_key:
            win.show_settings()

        win.present()


def main() -> None:
    app = SevenSeasApp()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
