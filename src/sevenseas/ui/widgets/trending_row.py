"""Trending row widget — thumbnail + title + subtitle for the trending sidebar."""

import threading

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Pango

from sevenseas.ui.widgets.game_card import (
    _CACHE_DIR, cache_path_for_url, atomic_write_cache,
)


class TrendingRow(Gtk.Box):
    """A compact row showing a game thumbnail, title, and size info."""

    def __init__(self, title: str, size_info: str | None = None,
                 thumbnail_url: str | None = None, on_click=None) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.add_css_class("trending-row")
        self.set_margin_start(4)
        self.set_margin_end(4)

        self._on_click = on_click

        # Thumbnail
        self._picture = Gtk.Picture()
        self._picture.set_size_request(56, 56)
        self._picture.set_content_fit(Gtk.ContentFit.COVER)
        self._picture.set_overflow(Gtk.Overflow.HIDDEN)
        self._picture.add_css_class("trending-row-thumb")
        self.append(self._picture)

        if thumbnail_url:
            self._load_thumbnail(thumbnail_url)

        # Text column
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_valign(Gtk.Align.CENTER)
        text_box.set_hexpand(True)
        self.append(text_box)

        title_label = Gtk.Label(label=title)
        title_label.set_halign(Gtk.Align.START)
        title_label.set_ellipsize(Pango.EllipsizeMode.END)
        title_label.set_lines(1)
        title_label.set_max_width_chars(28)
        title_label.add_css_class("trending-row-title")
        text_box.append(title_label)

        if size_info:
            sub_label = Gtk.Label(label=size_info)
            sub_label.set_halign(Gtk.Align.START)
            sub_label.add_css_class("trending-row-subtitle")
            text_box.append(sub_label)

        # Click gesture
        gesture = Gtk.GestureClick()
        gesture.connect("released", self._on_released)
        self.add_controller(gesture)
        self.set_cursor_from_name("pointer")

    def _on_released(self, gesture, n_press, x, y) -> None:
        if self._on_click:
            self._on_click()

    def _load_thumbnail(self, url: str) -> None:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = cache_path_for_url(url)

        if cache_path.exists():
            self._picture.set_filename(str(cache_path))
            return

        def download():
            try:
                import httpx
                resp = httpx.get(url, follow_redirects=True, timeout=15.0)
                resp.raise_for_status()
                atomic_write_cache(cache_path, resp.content)
                GLib.idle_add(self._picture.set_filename, str(cache_path))
            except Exception:
                pass

        threading.Thread(target=download, daemon=True).start()
