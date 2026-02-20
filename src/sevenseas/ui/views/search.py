"""Search view — search FitGirl Repacks and display results."""

import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from sevenseas.ui.widgets.game_card import GameCard


class SearchView(Gtk.Box):
    """Search page with search bar and results grid."""

    def __init__(self, scraper, on_install=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._scraper = scraper
        self._on_install = on_install

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        search_box.set_margin_top(12)
        search_box.set_margin_start(12)
        search_box.set_margin_end(12)
        self.append(search_box)

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search FitGirl Repacks...")
        self._search_entry.set_hexpand(True)
        self._search_entry.connect("activate", self._on_search)
        search_box.append(self._search_entry)

        self._spinner = Gtk.Spinner()
        search_box.append(self._spinner)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.append(scroll)

        self._results_flow = Gtk.FlowBox()
        self._results_flow.set_valign(Gtk.Align.START)
        self._results_flow.set_max_children_per_line(6)
        self._results_flow.set_min_children_per_line(2)
        self._results_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._results_flow.set_homogeneous(True)
        scroll.set_child(self._results_flow)

        self._empty_label = Gtk.Label(label="Search for a game to get started")
        self._empty_label.add_css_class("dim-label")
        self._empty_label.set_vexpand(True)
        self.append(self._empty_label)

    def _on_search(self, entry: Gtk.SearchEntry) -> None:
        query = entry.get_text().strip()
        if not query:
            return
        self._spinner.start()
        self._empty_label.set_visible(False)
        thread = threading.Thread(target=self._do_search, args=(query,), daemon=True)
        thread.start()

    def _do_search(self, query: str) -> None:
        try:
            results = self._scraper.search(query)
            GLib.idle_add(self._display_results, results)
        except Exception as e:
            GLib.idle_add(self._show_error, str(e))

    def _display_results(self, results) -> None:
        self._spinner.stop()
        while child := self._results_flow.get_first_child():
            self._results_flow.remove(child)
        if not results:
            self._empty_label.set_text("No results found")
            self._empty_label.set_visible(True)
            return
        for r in results:
            card = GameCard(
                title=r.title,
                size_info=r.size_info,
                on_action=lambda title, url=r.url: self._on_install_clicked(title, url),
            )
            self._results_flow.append(card)

    def _on_install_clicked(self, title: str, url: str) -> None:
        if self._on_install:
            self._on_install(title, url)

    def _show_error(self, message: str) -> None:
        self._spinner.stop()
        self._empty_label.set_text(f"Error: {message}")
        self._empty_label.set_visible(True)
