"""Library view — shows installed games."""

import logging
import os
import shutil
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango

from sevenseas.ui.widgets.game_card import GameCard

log = logging.getLogger(__name__)


class LibraryView(Gtk.Box):
    """Grid of installed games with launch/manage actions."""

    def __init__(self, library_service, steam=None, config=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._library = library_service
        self._steam = steam
        self._config = config

        title = Gtk.Label(label="Library")
        title.add_css_class("title-1")
        title.set_margin_top(16)
        title.set_margin_bottom(12)
        self.append(title)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

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
        scroll.set_child(self._flow)

        self._empty = Gtk.Label(label="No games installed yet")
        self._empty.add_css_class("dim-label")
        self._empty.set_vexpand(True)
        self.append(self._empty)

    def refresh(self) -> None:
        while child := self._flow.get_first_child():
            self._flow.remove(child)
        games = self._library.get_installed()
        self._empty.set_visible(len(games) == 0)
        for game in games:
            card = _LibraryCard(
                game, on_delete=self._on_delete,
                steam=self._steam, config=self._config,
            )
            self._flow.append(card)

    def _on_delete(self, game) -> None:
        """Delete a game: remove files, Steam shortcut, and DB entry."""
        # Remove Steam shortcut
        if game.steam_shortcut_id and self._steam:
            try:
                self._steam.remove_shortcut(game.steam_shortcut_id)
            except Exception as e:
                log.warning("Failed to remove Steam shortcut: %s", e)

        # Remove game files from disk
        if game.install_path and os.path.isdir(game.install_path):
            games_base = self._config.games_dir if self._config else None
            real_path = os.path.realpath(game.install_path)
            if games_base and not real_path.startswith(os.path.realpath(games_base)):
                log.warning("Refusing to delete path outside games dir: %s", real_path)
            else:
                try:
                    shutil.rmtree(real_path)
                    log.info("Deleted game files: %s", real_path)
                except Exception as e:
                    log.warning("Failed to delete game files: %s", e)

        # Remove from database
        self._library.delete_game(game.id)
        log.info("Deleted game from library: %s (id=%d)", game.title, game.id)

        # Refresh the view
        self.refresh()


class _LibraryCard(Gtk.Box):
    """A library game card with Launch and Delete buttons."""

    def __init__(self, game, on_delete=None, steam=None, config=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        from sevenseas.ui.widgets.game_card import CARD_WIDTH, IMAGE_HEIGHT
        self.set_size_request(CARD_WIDTH, -1)
        self.add_css_class("game-card")
        self.set_overflow(Gtk.Overflow.HIDDEN)

        self._game = game
        self._on_delete = on_delete
        self._steam = steam
        self._config = config

        # Cover image with rounded frame
        image_frame = Gtk.Box()
        image_frame.set_size_request(CARD_WIDTH, IMAGE_HEIGHT)
        image_frame.set_overflow(Gtk.Overflow.HIDDEN)
        image_frame.add_css_class("game-card-image")
        self.append(image_frame)

        image_overlay = Gtk.Overlay()
        image_overlay.set_size_request(CARD_WIDTH, IMAGE_HEIGHT)
        image_frame.append(image_overlay)

        placeholder = Gtk.Image.new_from_icon_name("applications-games-symbolic")
        placeholder.set_pixel_size(48)
        placeholder.set_opacity(0.3)
        placeholder.set_halign(Gtk.Align.CENTER)
        placeholder.set_valign(Gtk.Align.CENTER)
        image_overlay.set_child(placeholder)

        image = Gtk.Picture()
        image.set_size_request(CARD_WIDTH, IMAGE_HEIGHT)
        image.set_content_fit(Gtk.ContentFit.COVER)
        image.set_hexpand(True)
        image.set_vexpand(True)
        image_overlay.add_overlay(image)
        self._image = image
        self._placeholder = placeholder

        # Try SteamGridDB local art first, fall back to cover_url
        grid_art = self._find_grid_art()
        if grid_art:
            image.set_filename(grid_art)
            placeholder.set_visible(False)
        elif game.cover_url:
            self._load_thumbnail(game.cover_url)
        else:
            image.set_visible(False)

        # Info area
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_margin_top(6)
        info_box.set_margin_start(2)
        info_box.set_margin_end(2)
        self.append(info_box)

        # Title
        title_label = Gtk.Label(label=game.title)
        title_label.set_halign(Gtk.Align.START)
        title_label.set_valign(Gtk.Align.START)
        title_label.set_ellipsize(Pango.EllipsizeMode.END)
        title_label.set_lines(2)
        title_label.set_max_width_chars(24)
        title_label.set_wrap(True)
        title_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        title_label.add_css_class("game-card-title")
        title_label.set_tooltip_text(game.title)
        info_box.append(title_label)

        # Delete button (small, subtle)
        delete_btn = Gtk.Button(icon_name="user-trash-symbolic")
        delete_btn.add_css_class("flat")
        delete_btn.add_css_class("destructive-action")
        delete_btn.set_tooltip_text("Delete game")
        delete_btn.set_halign(Gtk.Align.START)
        delete_btn.connect("clicked", self._on_delete_clicked)
        info_box.append(delete_btn)

    def _on_delete_clicked(self, button) -> None:
        # Show confirmation dialog
        dialog = Adw.AlertDialog(
            heading=f"Delete {self._game.title}?",
            body="This will remove the game files from disk and cannot be undone.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.connect("response", self._on_confirm_delete)
        dialog.present(self.get_root())

    def _on_confirm_delete(self, dialog, response) -> None:
        if response == "delete" and self._on_delete:
            self._on_delete(self._game)

    def _find_grid_art(self) -> str | None:
        """Find local SteamGridDB grid art (portrait cover) for this game."""
        if not self._steam or not self._game.steam_shortcut_id:
            return None
        # Artwork files use the unsigned form of the shortcut ID
        art_id = self._game.steam_shortcut_id & 0xFFFFFFFF
        for grid_dir in self._steam.get_grid_dirs():
            for ext in (".jpg", ".png"):
                path = grid_dir / f"{art_id}p{ext}"
                if path.exists():
                    return str(path)
        return None

    def _load_thumbnail(self, url):
        """Load thumbnail async, reusing cache logic."""
        from sevenseas.ui.widgets.game_card import (
            _CACHE_DIR, cache_path_for_url, atomic_write_cache,
        )

        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = cache_path_for_url(url)

        if cache_path.exists():
            self._image.set_filename(str(cache_path))
            self._placeholder.set_visible(False)
            return

        def download():
            try:
                import httpx
                resp = httpx.get(url, follow_redirects=True, timeout=15.0)
                resp.raise_for_status()
                atomic_write_cache(cache_path, resp.content)
                GLib.idle_add(self._set_image, str(cache_path))
            except Exception:
                pass

        thread = threading.Thread(target=download, daemon=True)
        thread.start()

    def _set_image(self, path):
        try:
            self._image.set_filename(path)
            self._image.set_visible(True)
            self._placeholder.set_visible(False)
        except Exception:
            pass
