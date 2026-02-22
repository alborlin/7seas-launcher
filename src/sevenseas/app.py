"""7-Seas Launcher application entry point."""

import logging
import os
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk, Gdk

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
        # Force dark mode so our navy theme works correctly
        self.get_style_manager().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        self.db = None
        self.config = None

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        # Ctrl+Q force-quit action (works even when running in background)
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])
        # Load bundled fonts (Pirata One for nautical title)
        fonts_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "fonts",
        )
        if os.path.isdir(fonts_dir):
            from ctypes import cdll, c_char_p
            try:
                fc = cdll.LoadLibrary("libfontconfig.so.1")
                fc.FcConfigAppFontAddDir(None, c_char_p(fonts_dir.encode()))
            except OSError:
                pass  # fontconfig not available, fall back to system fonts

        # Load custom navy & gold theme
        css_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "style.css",
        )
        if os.path.exists(css_path):
            provider = Gtk.CssProvider()
            provider.load_from_path(css_path)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    def do_activate(self) -> None:
        data_dir = os.path.join(
            os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
            "seven-seas",
        )
        os.makedirs(data_dir, exist_ok=True)
        os.chmod(data_dir, 0o700)  # Only owner can access

        # Set up file logging
        log_path = os.path.join(data_dir, "sevenseas.log")
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                logging.FileHandler(log_path, mode="a"),
                logging.StreamHandler(sys.stderr),
            ],
        )
        # Quiet noisy third-party loggers
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger().info("7-Seas Launcher starting — log: %s", log_path)

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
