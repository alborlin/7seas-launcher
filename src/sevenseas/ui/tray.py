"""System tray icon — runs as a subprocess.

Uses AyatanaAppIndicator3 (GTK3) which cannot coexist with GTK4 in-process.
The main app spawns this as a subprocess.
Clicking "Show" sends SIGUSR1 to the parent, clicking "Quit" sends SIGTERM.
Polls parent PID to self-exit if the parent dies.
"""

import os
import signal
import sys

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gtk, GLib, AyatanaAppIndicator3


def _parent_alive(pid):
    """Check if parent process is still running."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main():
    parent_pid = int(sys.argv[1]) if len(sys.argv) > 1 else os.getppid()

    # Use logo if available, fall back to generic icon
    logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "logo", "7seas-nobg.png")
    icon = logo_path if os.path.exists(logo_path) else "applications-games-symbolic"

    indicator = AyatanaAppIndicator3.Indicator.new(
        "seven-seas-launcher",
        icon,
        AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
    )
    indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
    indicator.set_title("7-Seas Launcher")

    def _on_quit(_item):
        os.kill(parent_pid, signal.SIGTERM)
        Gtk.main_quit()

    menu = Gtk.Menu()

    show_item = Gtk.MenuItem(label="Show 7-Seas")
    show_item.connect("activate", lambda _: os.kill(parent_pid, signal.SIGUSR1))
    menu.append(show_item)

    quit_item = Gtk.MenuItem(label="Quit")
    quit_item.connect("activate", _on_quit)
    menu.append(quit_item)

    menu.show_all()
    indicator.set_menu(menu)

    # Exit cleanly when parent kills us
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    signal.signal(signal.SIGINT, lambda *_: Gtk.main_quit())

    # Poll: exit if parent process dies
    def _check_parent():
        if not _parent_alive(parent_pid):
            Gtk.main_quit()
            return False
        return True
    GLib.timeout_add_seconds(2, _check_parent)

    Gtk.main()


if __name__ == "__main__":
    main()
