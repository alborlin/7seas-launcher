"""Game detail view — side-by-side layout with cover art on the right."""

import hashlib
import os
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango

from sevenseas.core.scraper import GameResult, GameDetail

_CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "seven-seas" / "covers"


class GameDetailView(Gtk.Box):
    """Detail view with cover art on right, metadata on left, content below."""

    def __init__(self, on_install=None, on_back=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._on_install = on_install
        self._on_back = on_back
        self._current_url: str | None = None
        self._current_title: str | None = None

        # Scrollable content
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

        self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scroll.set_child(self._root)

        # --- Top bar: back button + spinner ---
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        top_bar.set_margin_top(12)
        top_bar.set_margin_start(16)
        top_bar.set_margin_bottom(8)
        self._root.append(top_bar)

        back_btn = Gtk.Button(icon_name="go-previous-symbolic")
        back_btn.add_css_class("detail-back-btn")
        back_btn.set_tooltip_text("Back")
        back_btn.connect("clicked", self._on_back_clicked)
        top_bar.append(back_btn)

        self._spinner = Gtk.Spinner()
        self._spinner.set_margin_start(8)
        top_bar.append(self._spinner)

        # --- Hero section: metadata left, cover art right ---
        hero_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        hero_row.set_margin_start(24)
        hero_row.set_margin_end(24)
        hero_row.set_margin_bottom(24)
        self._root.append(hero_row)

        # Left column: title, badges, genres, install button
        left_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        left_col.set_hexpand(True)
        left_col.set_valign(Gtk.Align.CENTER)
        hero_row.append(left_col)

        self._title_label = Gtk.Label()
        self._title_label.add_css_class("detail-title")
        self._title_label.set_halign(Gtk.Align.START)
        self._title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self._title_label.set_lines(3)
        self._title_label.set_wrap(True)
        self._title_label.set_wrap_mode(Pango.WrapMode.WORD)
        left_col.append(self._title_label)

        # Badges row (size info)
        self._badge_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._badge_row.set_halign(Gtk.Align.START)
        left_col.append(self._badge_row)

        self._repack_badge = Gtk.Label()
        self._repack_badge.add_css_class("detail-size-badge")
        self._repack_badge.set_visible(False)
        self._badge_row.append(self._repack_badge)

        self._original_badge = Gtk.Label()
        self._original_badge.add_css_class("detail-size-badge-dim")
        self._original_badge.set_visible(False)
        self._badge_row.append(self._original_badge)

        self._protondb_badge = Gtk.Button(label="")
        self._protondb_badge.add_css_class("detail-protondb-badge")
        self._protondb_badge.set_visible(False)
        self._protondb_badge.connect("clicked", self._on_protondb_clicked)
        self._badge_row.append(self._protondb_badge)
        self._protondb_appid: str | None = None

        # Genres row
        self._genres_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._genres_box.set_halign(Gtk.Align.START)
        left_col.append(self._genres_box)

        # Install button — bright and prominent
        self._install_btn = Gtk.Button(label="Install")
        self._install_btn.add_css_class("detail-install-btn")
        self._install_btn.set_halign(Gtk.Align.START)
        self._install_btn.connect("clicked", self._on_install_clicked)
        left_col.append(self._install_btn)

        # Right column: cover art (portrait)
        cover_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        cover_frame.add_css_class("detail-cover-frame")
        cover_frame.set_valign(Gtk.Align.CENTER)
        hero_row.append(cover_frame)

        self._cover_image = Gtk.Picture()
        self._cover_image.set_size_request(280, 380)
        self._cover_image.set_content_fit(Gtk.ContentFit.COVER)
        self._cover_image.set_overflow(Gtk.Overflow.HIDDEN)
        self._cover_image.add_css_class("detail-cover-image")
        self._cover_image.set_visible(False)
        cover_frame.append(self._cover_image)

        # --- Content below hero ---
        content_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content_area.set_margin_top(8)
        content_area.set_margin_start(24)
        content_area.set_margin_end(24)
        content_area.set_margin_bottom(32)
        self._root.append(content_area)

        # --- About section ---
        self._about_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._about_section.set_visible(False)
        content_area.append(self._about_section)

        about_heading = Gtk.Label(label="About")
        about_heading.set_halign(Gtk.Align.START)
        about_heading.add_css_class("section-title")
        self._about_section.append(about_heading)

        self._desc_label = Gtk.Label()
        self._desc_label.set_halign(Gtk.Align.START)
        self._desc_label.set_valign(Gtk.Align.START)
        self._desc_label.set_wrap(True)
        self._desc_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self._desc_label.set_selectable(True)
        self._desc_label.add_css_class("detail-description")
        self._about_section.append(self._desc_label)

        # --- System Requirements section ---
        self._sysreq_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._sysreq_section.set_visible(False)
        content_area.append(self._sysreq_section)

        sysreq_heading = Gtk.Label(label="System Requirements")
        sysreq_heading.set_halign(Gtk.Align.START)
        sysreq_heading.add_css_class("section-title")
        self._sysreq_section.append(sysreq_heading)

        self._sysreq_label = Gtk.Label()
        self._sysreq_label.set_halign(Gtk.Align.START)
        self._sysreq_label.set_wrap(True)
        self._sysreq_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self._sysreq_label.add_css_class("detail-sysreq-text")
        self._sysreq_section.append(self._sysreq_label)

        # --- Screenshot gallery ---
        self._gallery_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._gallery_section.set_visible(False)
        content_area.append(self._gallery_section)

        gallery_heading = Gtk.Label(label="Screenshots")
        gallery_heading.set_halign(Gtk.Align.START)
        gallery_heading.add_css_class("section-title")
        self._gallery_section.append(gallery_heading)

        gallery_scroll = Gtk.ScrolledWindow()
        gallery_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        gallery_scroll.set_min_content_height(200)
        self._gallery_section.append(gallery_scroll)

        self._gallery_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        gallery_scroll.set_child(self._gallery_box)

    def show_game(self, game_result: GameResult, scraper) -> None:
        """Load a game into the detail view."""
        self.clear()
        self._current_url = game_result.url
        self._current_title = game_result.title
        self._title_label.set_text(game_result.title)

        if game_result.size_info:
            self._repack_badge.set_text(f"Repack: {game_result.size_info}")
            self._repack_badge.set_visible(True)

        if game_result.thumbnail:
            self._load_image_async(game_result.thumbnail, self._cover_image)
            self._cover_image.set_visible(True)

        self._protondb_badge.set_visible(False)

        self._spinner.start()
        self._install_btn.set_sensitive(False)
        self._install_btn.set_label("Loading...")
        threading.Thread(
            target=self._fetch_detail, args=(game_result.url, scraper), daemon=True
        ).start()
        threading.Thread(
            target=self._fetch_protondb, args=(game_result.title,), daemon=True
        ).start()

    def _fetch_detail(self, url: str, scraper) -> None:
        try:
            detail = scraper.get_detail(url)
            GLib.idle_add(self._populate_detail, detail)
        except Exception as e:
            GLib.idle_add(self._show_error, str(e))

    def _populate_detail(self, detail: GameDetail) -> None:
        self._spinner.stop()
        self._install_btn.set_sensitive(True)
        self._install_btn.set_label("Install")

        if detail.repack_size:
            self._repack_badge.set_text(f"Repack: {detail.repack_size}")
            self._repack_badge.set_visible(True)
        if detail.original_size:
            self._original_badge.set_text(f"Original: {detail.original_size}")
            self._original_badge.set_visible(True)

        for genre in detail.genres:
            pill = Gtk.Label(label=genre)
            pill.add_css_class("detail-tag")
            self._genres_box.append(pill)

        if detail.description:
            self._desc_label.set_text(detail.description)
            self._about_section.set_visible(True)

        if detail.system_requirements:
            self._sysreq_label.set_text(detail.system_requirements)
            self._sysreq_section.set_visible(True)

        # Use all screenshots for the gallery
        gallery_screenshots = detail.screenshots or []

        if gallery_screenshots:
            self._gallery_section.set_visible(True)
            for url in gallery_screenshots:
                pic = Gtk.Picture()
                pic.set_size_request(320, 180)
                pic.set_content_fit(Gtk.ContentFit.COVER)
                pic.set_overflow(Gtk.Overflow.HIDDEN)
                pic.add_css_class("screenshot-thumb")
                self._gallery_box.append(pic)
                self._load_image_async(url, pic)

    def _show_error(self, msg: str) -> None:
        self._spinner.stop()
        self._install_btn.set_label("Install")
        self._install_btn.set_sensitive(True)
        self._repack_badge.set_text(f"Error: {msg}")
        self._repack_badge.set_visible(True)

    def _fetch_protondb(self, title):
        from sevenseas.core.steamgriddb import SteamGridDBClient
        import httpx

        appid = SteamGridDBClient.get_steam_appid(title)
        if not appid:
            return
        try:
            resp = httpx.get(
                f"https://www.protondb.com/api/v1/reports/summaries/{appid}.json",
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            tier = data.get("trendingTier") or data.get("tier")
            if tier:
                GLib.idle_add(self._set_protondb_badge, tier, appid)
        except Exception:
            pass

    def _set_protondb_badge(self, tier, appid):
        display = tier.capitalize()
        self._protondb_badge.set_label(f"ProtonDB: {display}")
        self._protondb_badge.set_tooltip_text("Open on ProtonDB")
        for t in ("platinum", "gold", "silver", "bronze", "borked"):
            self._protondb_badge.remove_css_class(f"protondb-{t}")
        self._protondb_badge.add_css_class(f"protondb-{tier}")
        self._protondb_badge.set_visible(True)
        self._protondb_appid = appid

    def _on_protondb_clicked(self, button):
        if self._protondb_appid:
            Gtk.show_uri(None, f"https://www.protondb.com/app/{self._protondb_appid}", 0)

    def _on_install_clicked(self, button: Gtk.Button) -> None:
        if self._on_install and self._current_title and self._current_url:
            self._on_install(self._current_title, self._current_url)

    def _on_back_clicked(self, button: Gtk.Button) -> None:
        if self._on_back:
            self._on_back()

    def clear(self) -> None:
        """Reset view for reuse."""
        self._title_label.set_text("")
        self._repack_badge.set_text("")
        self._repack_badge.set_visible(False)
        self._original_badge.set_text("")
        self._original_badge.set_visible(False)
        self._protondb_badge.set_label("")
        self._protondb_badge.set_visible(False)
        self._protondb_appid = None
        for t in ("platinum", "gold", "silver", "bronze", "borked"):
            self._protondb_badge.remove_css_class(f"protondb-{t}")
        self._desc_label.set_text("")
        self._about_section.set_visible(False)
        self._sysreq_label.set_text("")
        self._sysreq_section.set_visible(False)
        self._cover_image.set_visible(False)
        self._gallery_section.set_visible(False)
        self._install_btn.set_label("Install")
        self._install_btn.set_sensitive(True)
        self._spinner.stop()
        self._current_url = None
        self._current_title = None
        while child := self._genres_box.get_first_child():
            self._genres_box.remove(child)
        while child := self._gallery_box.get_first_child():
            self._gallery_box.remove(child)

    @staticmethod
    def _load_image_async(url: str, picture: Gtk.Picture) -> None:
        """Download an image in background and set it on a Gtk.Picture."""
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        url_hash = hashlib.md5(url.encode()).hexdigest()
        ext = os.path.splitext(url.split("?")[0])[-1] or ".jpg"
        cache_path = _CACHE_DIR / f"{url_hash}{ext}"

        if cache_path.exists():
            picture.set_filename(str(cache_path))
            return

        def download():
            try:
                import httpx
                resp = httpx.get(url, follow_redirects=True, timeout=15.0)
                resp.raise_for_status()
                cache_path.write_bytes(resp.content)
                GLib.idle_add(picture.set_filename, str(cache_path))
            except Exception:
                pass

        thread = threading.Thread(target=download, daemon=True)
        thread.start()
