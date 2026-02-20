"""Browse views — New Releases, Top 50, Top 150."""

import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from sevenseas.ui.widgets.game_card import GameCard


class BrowseView(Gtk.Box):
    """Generic browse page that loads a listing from the scraper."""

    def __init__(self, title: str, fetch_func, on_install=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._fetch_func = fetch_func
        self._on_install = on_install
        self._loaded = False

        title_label = Gtk.Label(label=title)
        title_label.add_css_class("title-1")
        title_label.set_margin_top(16)
        title_label.set_margin_bottom(12)
        self.append(title_label)

        self._spinner = Gtk.Spinner()
        self.append(self._spinner)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.append(scroll)

        self._flow = Gtk.FlowBox()
        self._flow.set_valign(Gtk.Align.START)
        self._flow.set_max_children_per_line(6)
        self._flow.set_min_children_per_line(2)
        self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow.set_homogeneous(True)
        scroll.set_child(self._flow)

        self._status = Gtk.Label()
        self._status.add_css_class("dim-label")
        self.append(self._status)

    def load(self) -> None:
        if self._loaded:
            return
        self._spinner.start()
        thread = threading.Thread(target=self._fetch, daemon=True)
        thread.start()

    def _fetch(self) -> None:
        try:
            results = self._fetch_func()
            GLib.idle_add(self._display, results)
        except Exception as e:
            GLib.idle_add(self._show_error, str(e))

    def _display(self, results) -> None:
        self._spinner.stop()
        self._loaded = True
        while child := self._flow.get_first_child():
            self._flow.remove(child)
        if not results:
            self._status.set_text("No games found")
            return
        self._status.set_text(f"{len(results)} games")
        for r in results:
            card = GameCard(
                title=r.title,
                size_info=r.size_info,
                on_action=lambda title, url=r.url: self._on_install_clicked(title, url),
            )
            self._flow.append(card)

    def _on_install_clicked(self, title: str, url: str) -> None:
        if self._on_install:
            self._on_install(title, url)

    def _show_error(self, msg: str) -> None:
        self._spinner.stop()
        self._status.set_text(f"Error: {msg}")
