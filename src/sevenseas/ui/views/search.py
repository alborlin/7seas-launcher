"""Search view — search FitGirl Repacks and display results."""

import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from sevenseas.ui.widgets.game_card import GameCard


class SearchView(Gtk.Box):
    """Search results page — driven by external SearchEntry in the header bar."""

    def __init__(self, scraper, on_card_click=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._scraper = scraper
        self._on_card_click = on_card_click

        # Top row with spinner
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        top_row.set_margin_top(12)
        top_row.set_margin_start(12)
        top_row.set_margin_end(12)
        self.append(top_row)

        self._query_label = Gtk.Label()
        self._query_label.set_halign(Gtk.Align.START)
        self._query_label.set_hexpand(True)
        self._query_label.add_css_class("title-1")
        top_row.append(self._query_label)

        self._spinner = Gtk.Spinner()
        top_row.append(self._spinner)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

        self._results_flow = Gtk.FlowBox()
        self._results_flow.set_valign(Gtk.Align.START)
        self._results_flow.set_max_children_per_line(8)
        self._results_flow.set_min_children_per_line(2)
        self._results_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._results_flow.set_homogeneous(False)
        self._results_flow.set_column_spacing(8)
        self._results_flow.set_row_spacing(12)
        self._results_flow.set_margin_start(16)
        self._results_flow.set_margin_end(16)
        scroll.set_child(self._results_flow)

        self._empty_label = Gtk.Label(label="Search for a game to get started")
        self._empty_label.add_css_class("dim-label")
        self._empty_label.set_vexpand(True)
        self.append(self._empty_label)

    def search(self, query: str) -> None:
        """Trigger a search from external caller (e.g. header bar SearchEntry)."""
        query = query.strip()
        if not query:
            return
        self._query_label.set_text(f'Results for "{query}"')
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
        missing = []
        for r in results:
            card = GameCard(
                title=r.title,
                size_info=r.size_info,
                thumbnail_url=r.thumbnail,
                on_action=lambda _title, card=None, r=r: self._on_card_clicked(r, card),
            )
            self._results_flow.append(card)
            if not r.thumbnail and hasattr(self._scraper, "get_thumbnail"):
                missing.append((r, card))
        # Fetch missing thumbnails sequentially in one background thread
        if missing:
            thread = threading.Thread(
                target=self._fetch_thumbnails, args=(missing,), daemon=True,
            )
            thread.start()

    def _fetch_thumbnails(self, items) -> None:
        """Fetch thumbnails one by one from detail pages."""
        for game_result, card in items:
            try:
                url = self._scraper.get_thumbnail(game_result.url)
                if url:
                    game_result.thumbnail = url
                    GLib.idle_add(self._apply_thumbnail, card, url)
            except Exception:
                pass

    @staticmethod
    def _apply_thumbnail(card, url) -> None:
        """Set thumbnail on card from main thread."""
        card._image.set_visible(True)
        card._placeholder_icon.set_visible(False)
        card._load_thumbnail_async(url)

    def _on_card_clicked(self, game_result, source_card=None) -> None:
        if self._on_card_click:
            self._on_card_click(game_result, source_card)

    def _show_error(self, message: str) -> None:
        self._spinner.stop()
        self._empty_label.set_text(f"Error: {message}")
        self._empty_label.set_visible(True)
