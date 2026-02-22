"""Game card widget — shows cover art, title, and size info."""

import hashlib
import os
import tempfile
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, GdkPixbuf, Gdk, Pango

_CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "seven-seas" / "covers"
_ALLOWED_IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

CARD_WIDTH = 200
IMAGE_HEIGHT = 270  # portrait aspect ratio for cover art


def cache_path_for_url(url: str, prefix: str = "") -> Path:
    """Return a safe cache file path for a URL (SHA-256, extension whitelist)."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:32]
    ext = os.path.splitext(url.split("?")[0])[-1].lower()
    if ext not in _ALLOWED_IMG_EXTS:
        ext = ".jpg"
    return _CACHE_DIR / f"{prefix}{url_hash}{ext}"


def atomic_write_cache(path: Path, data: bytes) -> None:
    """Write data to cache path atomically via temp file + rename."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=path.suffix)
    try:
        os.write(fd, data)
    except BaseException:
        os.unlink(tmp)
        raise
    finally:
        os.close(fd)
    os.rename(tmp, path)


class GameCard(Gtk.Box):
    """A card displaying game cover art, title, and size info. Clickable."""

    def __init__(
        self,
        title: str,
        size_info: str | None = None,
        thumbnail_url: str | None = None,
        on_action=None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_size_request(CARD_WIDTH, -1)
        self.add_css_class("game-card")
        self.set_overflow(Gtk.Overflow.HIDDEN)

        self._title = title
        self._on_action = on_action

        # Cover image with rounded corners
        image_frame = Gtk.Box()
        image_frame.set_size_request(CARD_WIDTH, IMAGE_HEIGHT)
        image_frame.set_overflow(Gtk.Overflow.HIDDEN)
        image_frame.add_css_class("game-card-image")
        self.append(image_frame)

        image_overlay = Gtk.Overlay()
        image_overlay.set_size_request(CARD_WIDTH, IMAGE_HEIGHT)
        image_frame.append(image_overlay)

        # Placeholder icon (shown when no image)
        self._placeholder_icon = Gtk.Image.new_from_icon_name("applications-games-symbolic")
        self._placeholder_icon.set_pixel_size(48)
        self._placeholder_icon.set_opacity(0.3)
        self._placeholder_icon.set_halign(Gtk.Align.CENTER)
        self._placeholder_icon.set_valign(Gtk.Align.CENTER)
        image_overlay.set_child(self._placeholder_icon)

        # Actual image (overlaid on top)
        self._image = Gtk.Picture()
        self._image.set_size_request(CARD_WIDTH, IMAGE_HEIGHT)
        self._image.set_content_fit(Gtk.ContentFit.COVER)
        self._image.set_hexpand(True)
        self._image.set_vexpand(True)
        image_overlay.add_overlay(self._image)

        # Load thumbnail from URL if provided
        if thumbnail_url:
            self._placeholder_icon.set_visible(False)
            self._load_thumbnail_async(thumbnail_url)
        else:
            self._image.set_visible(False)

        # Info area: title + size
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_margin_top(6)
        info_box.set_margin_start(2)
        info_box.set_margin_end(2)
        self.append(info_box)

        # Title (2 lines, ellipsize, with tooltip)
        title_label = Gtk.Label(label=title)
        title_label.set_halign(Gtk.Align.START)
        title_label.set_valign(Gtk.Align.START)
        title_label.set_ellipsize(Pango.EllipsizeMode.END)
        title_label.set_lines(2)
        title_label.set_max_width_chars(24)
        title_label.set_wrap(True)
        title_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        title_label.add_css_class("game-card-title")
        title_label.set_tooltip_text(title)
        info_box.append(title_label)

        if size_info:
            size_label = Gtk.Label(label=size_info)
            size_label.set_halign(Gtk.Align.START)
            size_label.add_css_class("game-card-subtitle")
            info_box.append(size_label)

        # Whole card is clickable
        click = Gtk.GestureClick()
        click.connect("released", self._on_clicked)
        self.add_controller(click)
        self.set_cursor_from_name("pointer")

    def _on_clicked(self, gesture, n_press, x, y) -> None:
        if self._on_action:
            self._on_action(self._title, self)

    def _load_thumbnail_async(self, url: str) -> None:
        """Download thumbnail in background thread and display it."""
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = cache_path_for_url(url)

        if cache_path.exists():
            self._image.set_filename(str(cache_path))
            return

        def download():
            try:
                import httpx
                resp = httpx.get(url, follow_redirects=True, timeout=15.0)
                resp.raise_for_status()
                atomic_write_cache(cache_path, resp.content)
                GLib.idle_add(self._set_image_from_file, str(cache_path))
            except Exception:
                pass

        thread = threading.Thread(target=download, daemon=True)
        thread.start()

    def _set_image_from_file(self, path: str) -> None:
        try:
            self._image.set_filename(path)
            self._image.set_visible(True)
            self._placeholder_icon.set_visible(False)
        except Exception:
            pass

    def set_thumbnail(self, path: str) -> None:
        try:
            self._image.set_filename(path)
        except Exception:
            pass
