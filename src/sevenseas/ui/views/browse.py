"""Browse views — New Releases, Top 50, Top 150."""

import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from sevenseas.ui.widgets.game_card import GameCard

INITIAL_BATCH = 30
LOAD_MORE_BATCH = 10


class BrowseView(Gtk.Box):
    """Generic browse page that loads a listing from the scraper."""

    def __init__(self, title: str, fetch_func, on_card_click=None, paginated: bool = False) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._fetch_func = fetch_func
        self._on_card_click = on_card_click
        self._loaded = False
        self._paginated = paginated
        self._current_page = 1
        self._loading = False
        self._total_count = 0

        # Title row with count
        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        title_row.set_margin_top(16)
        title_row.set_margin_bottom(12)
        title_row.set_margin_start(16)
        title_row.set_margin_end(16)
        self.append(title_row)

        title_label = Gtk.Label(label=title)
        title_label.add_css_class("title-1")
        title_label.set_hexpand(True)
        title_label.set_halign(Gtk.Align.START)
        title_row.append(title_label)

        self._status = Gtk.Label()
        self._status.add_css_class("dim-label")
        self._status.set_halign(Gtk.Align.END)
        self._status.set_valign(Gtk.Align.CENTER)
        title_row.append(self._status)

        self._spinner = Gtk.Spinner()
        self._spinner.set_halign(Gtk.Align.END)
        self._spinner.set_valign(Gtk.Align.CENTER)
        title_row.append(self._spinner)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

        self._scroll_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll.set_child(self._scroll_box)

        self._flow = Gtk.FlowBox()
        self._flow.set_valign(Gtk.Align.START)
        self._flow.set_max_children_per_line(8)
        self._flow.set_min_children_per_line(2)
        self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow.set_homogeneous(False)
        self._flow.set_column_spacing(8)
        self._flow.set_row_spacing(12)
        self._flow.set_margin_start(16)
        self._flow.set_margin_end(16)
        self._scroll_box.append(self._flow)

        # Load More button (only for paginated views)
        self._load_more_btn = Gtk.Button(label="Load More")
        self._load_more_btn.add_css_class("pill")
        self._load_more_btn.set_halign(Gtk.Align.CENTER)
        self._load_more_btn.set_margin_top(12)
        self._load_more_btn.set_margin_bottom(12)
        self._load_more_btn.connect("clicked", self._on_load_more)
        self._load_more_btn.set_visible(False)
        self._scroll_box.append(self._load_more_btn)


    def load(self) -> None:
        if self._loaded:
            return
        self._spinner.start()
        self._loading = True
        thread = threading.Thread(target=self._fetch, daemon=True)
        thread.start()

    def _fetch(self, start_page: int = 1) -> None:
        try:
            batch_size = INITIAL_BATCH if start_page == 1 else LOAD_MORE_BATCH
            if self._paginated:
                all_results = []
                page = start_page
                while len(all_results) < batch_size:
                    page_results = self._fetch_func(page=page)
                    if not page_results:
                        break
                    all_results.extend(page_results)
                    page += 1
                # Trim to exact batch size
                all_results = all_results[:batch_size]
                self._current_page = page - 1
                GLib.idle_add(self._display, all_results, start_page)
            else:
                results = self._fetch_func()
                GLib.idle_add(self._display, results, start_page)
        except Exception as e:
            GLib.idle_add(self._show_error, str(e))

    def _display(self, results, page: int = 1) -> None:
        self._spinner.stop()
        self._loaded = True
        self._loading = False
        if page == 1:
            while child := self._flow.get_first_child():
                self._flow.remove(child)
            self._total_count = 0
        if not results and page == 1:
            self._status.set_text("No games found")
            self._load_more_btn.set_visible(False)
            return
        self._total_count += len(results)
        self._status.set_text(f"{self._total_count} games")
        for r in results:
            card = GameCard(
                title=r.title,
                size_info=r.size_info,
                thumbnail_url=r.thumbnail,
                on_action=lambda _title, card=None, r=r: self._on_card_clicked(r, card),
            )
            self._flow.append(card)
        # Show Load More if paginated and we got a full batch
        if self._paginated and len(results) > 0:
            self._load_more_btn.set_visible(True)
            self._load_more_btn.set_sensitive(True)
            self._load_more_btn.set_label("Load More")
        else:
            self._load_more_btn.set_visible(False)

    def _on_load_more(self, button: Gtk.Button) -> None:
        if self._loading:
            return
        self._loading = True
        next_page = self._current_page + 1
        button.set_sensitive(False)
        button.set_label("Loading...")
        self._spinner.start()
        thread = threading.Thread(
            target=self._fetch, args=(next_page,), daemon=True
        )
        thread.start()

    def _on_card_clicked(self, game_result, source_card=None) -> None:
        if self._on_card_click:
            self._on_card_click(game_result, source_card)

    def _show_error(self, msg: str) -> None:
        self._spinner.stop()
        self._loading = False
        self._status.set_text(f"Error: {msg}")
