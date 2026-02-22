"""Download progress row widget."""

import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from sevenseas.ui.widgets.game_card import (
    _CACHE_DIR, cache_path_for_url, atomic_write_cache,
)
_THUMB_WIDTH = 320
_THUMB_HEIGHT = 428


def _format_speed(bps: int) -> str:
    if bps < 1024:
        return f"{bps} B/s"
    elif bps < 1024 * 1024:
        return f"{bps / 1024:.1f} KB/s"
    else:
        return f"{bps / (1024 * 1024):.1f} MB/s"


class DownloadRow(Gtk.Box):
    """A row showing download progress with title, stage, progress bar, speed."""

    def __init__(
        self,
        title: str,
        stage: str = "Pending",
        progress: float = 0.0,
        speed_bps: int = 0,
        on_cancel=None,
        on_retry=None,
        cover_url: str | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(12)
        self.set_margin_end(12)

        # Cover thumbnail
        thumb_frame = Gtk.Box()
        thumb_frame.set_size_request(_THUMB_WIDTH, _THUMB_HEIGHT)
        thumb_frame.set_overflow(Gtk.Overflow.HIDDEN)
        thumb_frame.add_css_class("download-row-thumb")
        self.append(thumb_frame)

        thumb_overlay = Gtk.Overlay()
        thumb_overlay.set_size_request(_THUMB_WIDTH, _THUMB_HEIGHT)
        thumb_frame.append(thumb_overlay)

        self._placeholder = Gtk.Image.new_from_icon_name("applications-games-symbolic")
        self._placeholder.set_pixel_size(48)
        self._placeholder.set_opacity(0.3)
        self._placeholder.set_halign(Gtk.Align.CENTER)
        self._placeholder.set_valign(Gtk.Align.CENTER)
        thumb_overlay.set_child(self._placeholder)

        self._thumb_image = Gtk.Picture()
        self._thumb_image.set_size_request(_THUMB_WIDTH, _THUMB_HEIGHT)
        self._thumb_image.set_content_fit(Gtk.ContentFit.COVER)
        self._thumb_image.set_hexpand(False)
        self._thumb_image.set_vexpand(False)
        thumb_overlay.add_overlay(self._thumb_image)

        if cover_url:
            self._placeholder.set_visible(False)
            self._load_thumbnail_async(cover_url)
        else:
            self._thumb_image.set_visible(False)

        # Right side: info + progress
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_hexpand(True)
        self.append(info_box)

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        info_box.append(top_row)

        self._title_label = Gtk.Label(label=title)
        self._title_label.set_halign(Gtk.Align.START)
        self._title_label.set_hexpand(True)
        self._title_label.add_css_class("heading")
        top_row.append(self._title_label)

        self._stage_label = Gtk.Label(label=stage)
        self._stage_label.add_css_class("dim-label")
        top_row.append(self._stage_label)

        self._speed_label = Gtk.Label(label=_format_speed(speed_bps))
        self._speed_label.add_css_class("dim-label")
        top_row.append(self._speed_label)

        # Retry button (visible only during installer)
        self._retry_btn = None
        if on_retry:
            self._retry_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
            self._retry_btn.add_css_class("flat")
            self._retry_btn.set_tooltip_text("Re-run installer after current finishes")
            self._retry_btn.connect("clicked", lambda _: on_retry())
            self._retry_btn.set_visible(False)
            top_row.append(self._retry_btn)

        if on_cancel:
            cancel_btn = Gtk.Button.new_from_icon_name("process-stop-symbolic")
            cancel_btn.add_css_class("flat")
            cancel_btn.connect("clicked", lambda _: on_cancel())
            top_row.append(cancel_btn)

        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_fraction(progress)
        self._progress_bar.set_show_text(True)
        self._progress_bar.set_text(f"{progress * 100:.0f}%")
        info_box.append(self._progress_bar)

    def update(self, stage: str, progress: float, speed_bps: int) -> None:
        self._stage_label.set_text(stage)
        self._progress_bar.set_fraction(min(progress, 1.0))
        self._progress_bar.set_text(f"{progress * 100:.0f}%")
        self._speed_label.set_text(_format_speed(speed_bps))
        if self._retry_btn:
            self._retry_btn.set_visible(stage == "Running Installer")

    def _load_thumbnail_async(self, url: str) -> None:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = cache_path_for_url(url)

        if cache_path.exists():
            self._thumb_image.set_filename(str(cache_path))
            return

        def download():
            try:
                import httpx
                resp = httpx.get(url, follow_redirects=True, timeout=15.0)
                resp.raise_for_status()
                atomic_write_cache(cache_path, resp.content)
                GLib.idle_add(self._set_thumb_from_file, str(cache_path))
            except Exception:
                pass

        threading.Thread(target=download, daemon=True).start()

    def _set_thumb_from_file(self, path: str) -> None:
        try:
            self._thumb_image.set_filename(path)
            self._thumb_image.set_visible(True)
            self._placeholder.set_visible(False)
        except Exception:
            pass
