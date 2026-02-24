"""Main application window with top navigation bar."""

import logging
import os
import signal
import subprocess
import sys
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib, GdkPixbuf, Gdk, Graphene

log = logging.getLogger(__name__)


class MainWindow(Adw.ApplicationWindow):
    """Main window with HeaderBar navigation and ViewStack content."""

    def __init__(self, services=None, db=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_title("7-Seas Launcher")
        self.set_default_size(1200, 800)

        # Animation overlay wraps the entire window content
        self._anim_overlay = Gtk.Overlay()
        self.set_content(self._anim_overlay)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._anim_overlay.set_child(root)

        # Floating layer for fly-over animations
        self._anim_fixed = Gtk.Fixed()
        self._anim_fixed.set_can_target(False)  # pass-through clicks
        self._anim_overlay.add_overlay(self._anim_fixed)

        # --- Header bar ---
        header = Adw.HeaderBar()
        header.add_css_class("top-bar")
        root.append(header)

        # Brand group (logo + title) — pack_start
        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        brand.set_valign(Gtk.Align.CENTER)

        logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "logo", "7seas-nobg.png")
        if os.path.exists(logo_path):
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(logo_path, 76, 76, True)
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            logo = Gtk.Image.new_from_paintable(texture)
            logo.set_pixel_size(76)
            logo.add_css_class("top-bar-logo")
            brand.append(logo)

        title_label = Gtk.Label(label="7-SEAS")
        title_label.add_css_class("nautical-title")
        brand.append(title_label)

        header.pack_start(brand)

        # Search entry — pack_start
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search games...")
        self._search_entry.add_css_class("top-bar-search")
        self._search_entry.connect("activate", self._on_search_activate)
        header.pack_start(self._search_entry)

        # ViewSwitcher as title widget (Discover | Browse | Library)
        self._view_stack = Adw.ViewStack()
        self._view_stack.set_vexpand(True)

        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self._view_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        # Settings button — pack_end (added first so it's rightmost)
        settings_btn = Gtk.Button(icon_name="emblem-system-symbolic")
        settings_btn.add_css_class("flat")
        settings_btn.set_tooltip_text("Settings")
        settings_btn.connect("clicked", lambda _b: self._navigate_to("settings"))
        header.pack_end(settings_btn)

        # Downloads button with badge overlay — pack_end
        dl_overlay = Gtk.Overlay()
        dl_btn = Gtk.Button(icon_name="folder-download-symbolic")
        dl_btn.add_css_class("flat")
        dl_btn.set_tooltip_text("Downloads")
        dl_btn.connect("clicked", lambda _b: self._navigate_to("downloads"))
        dl_overlay.set_child(dl_btn)

        self._dl_badge = Gtk.Label(label="0")
        self._dl_badge.add_css_class("download-badge")
        self._dl_badge.set_halign(Gtk.Align.END)
        self._dl_badge.set_valign(Gtk.Align.START)
        self._dl_badge.set_visible(False)
        dl_overlay.add_overlay(self._dl_badge)
        header.pack_end(dl_overlay)

        # --- ViewStack ---
        self._view_stack.connect("notify::visible-child-name", self._on_stack_switch)
        root.append(self._view_stack)

        # --- Status bar ---
        self._status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._status_bar.add_css_class("toolbar")
        self._status_bar.set_margin_start(12)
        self._status_bar.set_margin_end(12)
        self._status_label = Gtk.Label(label="No active downloads")
        self._status_bar.append(self._status_label)
        root.append(self._status_bar)

        # State
        self._views: dict[str, Gtk.Widget] = {}
        self._previous_page: str | None = None
        self._is_background = False
        self._tray_proc: subprocess.Popen | None = None
        self._active_dl_count = 0
        self._active_hero_anim = None

        # Handle window close
        self.connect("close-request", self._on_close_request)

        # SIGUSR1 from tray icon means "show window"
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self._on_tray_show)

        # Wire services
        if services is not None:
            self._init_views(services, db)
            self._navigate_to("discover")

        self._start_tray()

    # --- Navigation ---

    def _navigate_to(self, name: str) -> None:
        """Switch ViewStack to a named page, tracking previous for back nav."""
        current = self._view_stack.get_visible_child_name()
        if current != name:
            self._previous_page = current
        self._view_stack.set_visible_child_name(name)
        view = self._views.get(name)
        if view and hasattr(view, "load"):
            view.load()
        if view and hasattr(view, "refresh"):
            view.refresh()

    def _on_stack_switch(self, stack, pspec) -> None:
        """Called when ViewSwitcher changes the visible tab."""
        name = stack.get_visible_child_name()
        if not name:
            return
        view = self._views.get(name)
        if view and hasattr(view, "load"):
            view.load()
        if view and hasattr(view, "refresh"):
            view.refresh()

    def _on_search_activate(self, entry: Gtk.SearchEntry) -> None:
        query = entry.get_text().strip()
        if not query:
            return
        self._previous_page = self._view_stack.get_visible_child_name()
        self._view_stack.set_visible_child_name("search")
        search_view = self._views.get("search")
        if search_view:
            search_view.search(query)

    def show_settings(self) -> None:
        """Navigate to settings view (used on first run)."""
        self._navigate_to("settings")

    def set_status(self, text: str) -> None:
        """Update the bottom status bar text."""
        self._status_label.set_text(text)

    def _update_dl_badge(self, count: int) -> None:
        self._active_dl_count = count
        if count > 0:
            self._dl_badge.set_text(str(count))
            self._dl_badge.set_visible(True)
        else:
            self._dl_badge.set_visible(False)

    # --- Window lifecycle ---

    def _on_close_request(self, window) -> bool:
        """Always hide to tray instead of quitting."""
        self.set_visible(False)
        self._is_background = True
        app = self.get_application()
        if app:
            app.hold()
        if self._has_active_downloads():
            self._send_notification(
                "Downloads Running",
                "7-Seas is running in the background. Downloads will continue.",
                "background-running",
            )
        return True

    def _has_active_downloads(self) -> bool:
        if not hasattr(self, "_download_manager") or not self._download_manager:
            return False
        return self._download_manager.active_download is not None or bool(self._download_manager.queue)

    def _send_notification(self, title: str, body: str, notification_id: str) -> None:
        app = self.get_application()
        if not app:
            return
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        app.send_notification(notification_id, notification)

    def _start_tray(self) -> None:
        if self._tray_proc and self._tray_proc.poll() is None:
            return
        tray_script = os.path.join(os.path.dirname(__file__), "tray.py")
        try:
            self._tray_proc = subprocess.Popen(
                [sys.executable, tray_script, str(os.getpid())],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log.info("Tray icon started (pid=%d)", self._tray_proc.pid)
        except Exception as e:
            log.warning("Failed to start tray icon: %s", e)

    def _stop_tray(self) -> None:
        if self._tray_proc and self._tray_proc.poll() is None:
            self._tray_proc.terminate()
            self._tray_proc = None

    def _on_tray_show(self) -> bool:
        self._restore_from_background()
        return True

    def _restore_from_background(self) -> None:
        if not self._is_background:
            return
        self._is_background = False
        self.set_visible(True)
        self.present()
        app = self.get_application()
        if app:
            app.release()

    def _check_background_state(self) -> None:
        if self._is_background and not self._has_active_downloads():
            self._restore_from_background()

    # --- Background update checker ---

    def _schedule_update_check(self) -> bool:
        """GLib timer callback — spawns background thread for update check."""
        threading.Thread(target=self._check_for_updates, daemon=True).start()
        return True

    def _check_for_updates(self) -> None:
        """Background thread: fetch latest repacks and compare against known set."""
        try:
            results = self._scraper.get_latest(page=1)
            if not results:
                return
            current_urls = {r.url for r in results}
            if self._update_check_first:
                self._known_repack_urls = current_urls
                self._update_check_first = False
                return
            new_urls = current_urls - self._known_repack_urls
            if new_urls:
                new_titles = [r.title for r in results if r.url in new_urls]
                self._known_repack_urls = current_urls
                GLib.idle_add(self._notify_new_repacks, new_titles)
        except Exception:
            pass

    def _notify_new_repacks(self, titles: list[str]) -> None:
        """Send desktop notification for newly discovered repacks."""
        count = len(titles)
        if count == 1:
            body = titles[0]
        elif count <= 3:
            body = "\n".join(titles)
        else:
            body = "\n".join(titles[:3]) + f"\n+ {count - 3} more"
        self._send_notification(
            f"{count} New Repack{'s' if count != 1 else ''} Available",
            body,
            "new-repacks",
        )

    # --- Service/view wiring ---

    def _init_views(self, services, db):
        """Create all view instances and register them in the ViewStack."""
        from sevenseas.ui.views.search import SearchView
        from sevenseas.ui.views.browse_container import BrowseContainerView
        from sevenseas.ui.views.discover import DiscoverView
        from sevenseas.ui.views.detail import GameDetailView
        from sevenseas.ui.views.downloads import DownloadsView
        from sevenseas.ui.views.library import LibraryView
        from sevenseas.ui.views.settings import SettingsView

        scraper = services["scraper"]
        library = services["library"]
        config = services["config"]

        self._services = services
        self._db = db
        self._library = library
        self._config = config
        self._downloads_view = DownloadsView(
            on_cancel=self._on_cancel_download,
            on_retry=self._on_retry_download,
        )

        # --- Visible tabs (shown in ViewSwitcher) ---
        discover = DiscoverView(scraper, on_card_click=self._on_card_clicked, sgdb_api_key=config.steamgriddb_api_key)
        self._view_stack.add_titled_with_icon(discover, "discover", "Discover", "find-location-symbolic")
        self._views["discover"] = discover

        browse = BrowseContainerView(scraper, on_card_click=self._on_card_clicked, sgdb_api_key=config.steamgriddb_api_key)
        self._view_stack.add_titled_with_icon(browse, "browse", "Browse", "view-grid-symbolic")
        self._views["browse"] = browse

        library_view = LibraryView(library, steam=services["steam"], config=config, on_sync_steam=self._on_sync_steam)
        self._view_stack.add_titled_with_icon(library_view, "library", "Library", "application-x-executable-symbolic")
        self._views["library"] = library_view

        # --- Hidden pages (not in ViewSwitcher, navigated programmatically) ---
        search = SearchView(scraper, on_card_click=self._on_card_clicked)
        self._view_stack.add_named(search, "search")
        self._views["search"] = search

        detail = GameDetailView(on_install=self._on_install_requested, on_back=self._on_detail_back)
        self._view_stack.add_named(detail, "detail")
        self._views["detail"] = detail

        self._view_stack.add_named(self._downloads_view, "downloads")
        self._views["downloads"] = self._downloads_view

        settings = SettingsView(config, on_api_key_validated=self._on_api_key_validated, steam=services["steam"])
        self._view_stack.add_named(settings, "settings")
        self._views["settings"] = settings

        # Initialize download manager if API key is set
        self._download_manager = None
        if config.torbox_api_key:
            self._init_download_manager()

        # Background update checker
        self._scraper = scraper
        self._known_repack_urls: set[str] = set()
        self._update_check_first = True
        threading.Thread(target=self._check_for_updates, daemon=True).start()
        GLib.timeout_add_seconds(600, self._schedule_update_check)

    def _init_download_manager(self):
        from sevenseas.core.torbox import TorboxClient
        from sevenseas.core.downloader import DownloadManager

        torbox = TorboxClient(api_key=self._config.torbox_api_key)
        self._download_manager = DownloadManager(
            db=self._db,
            torbox=torbox,
            extractor=self._services["extractor"],
            installer=self._services["installer"],
            library=self._library,
            steam=self._services["steam"],
            config=self._config,
        )

        def on_progress(item):
            GLib.idle_add(self._on_download_progress, item)

        def on_complete(item):
            GLib.idle_add(self._on_download_complete, item)

        def on_error(item):
            GLib.idle_add(self._on_download_error, item)

        self._download_manager.on_progress(on_progress)
        self._download_manager.on_complete(on_complete)
        self._download_manager.on_error(on_error)

    def _on_card_clicked(self, game_result, source_card=None):
        self._previous_page = self._view_stack.get_visible_child_name()
        detail_view = self._views.get("detail")
        if not detail_view:
            return

        scraper = self._get_scraper_for_url(game_result.url)
        detail_view.show_game(game_result, scraper)

        # If no source card or widget not mapped, just switch instantly
        if source_card is None or not source_card.get_mapped():
            self._view_stack.set_visible_child_name("detail")
            return

        # Cancel any in-progress animation
        if self._active_hero_anim:
            self._active_hero_anim.skip()
            self._active_hero_anim = None

        # 1. Capture source geometry (card's _image widget)
        source_widget = source_card._image
        src_rect = self._get_widget_rect(source_widget)
        if src_rect is None:
            self._view_stack.set_visible_child_name("detail")
            return

        # 2. Freeze the source image as a paintable snapshot
        frozen = Gtk.WidgetPaintable.new(source_widget).get_current_image()

        # 3. Create floating clone at source position
        fly = Gtk.Picture()
        fly.set_paintable(frozen)
        fly.set_can_shrink(True)
        fly.set_content_fit(Gtk.ContentFit.COVER)
        fly.set_overflow(Gtk.Overflow.HIDDEN)
        fly.add_css_class("hero-fly-image")
        fly.set_size_request(int(src_rect[2]), int(src_rect[3]))
        self._anim_fixed.put(fly, src_rect[0], src_rect[1])

        # 4. Switch to detail page but keep it invisible
        self._view_stack.set_visible_child_name("detail")
        detail_view.set_opacity(0.0)

        # 5. Wait for GTK to fully lay out the detail page (2 frames),
        #    then query the destination and start the animation
        self._hero_retries = 0
        self._begin_hero_animation(fly, src_rect, detail_view)

    def _begin_hero_animation(self, fly, src_rect, detail_view):
        """Deferred animation start — retries until destination is laid out."""

        def try_start():
            dst_rect = self._get_widget_rect(detail_view._cover_image)

            # Destination widget might not be allocated yet; retry a few times
            if dst_rect is None or dst_rect[2] < 1 or dst_rect[3] < 1:
                self._hero_retries += 1
                if self._hero_retries < 6:
                    GLib.timeout_add(16, try_start)  # retry next frame
                    return False
                # Final fallback: estimate destination from window geometry
                dst_rect = self._estimate_cover_rect()

            if dst_rect is None:
                detail_view.set_opacity(1.0)
                self._anim_fixed.remove(fly)
                return False

            sx, sy, sw, sh = src_rect
            dx, dy, dw, dh = dst_rect

            def on_frame(t):
                x = sx + (dx - sx) * t
                y = sy + (dy - sy) * t
                w = sw + (dw - sw) * t
                h = sh + (dh - sh) * t
                fly.set_size_request(max(1, int(w)), max(1, int(h)))
                self._anim_fixed.move(fly, x, y)
                # Fade in the detail page from t=0.35 to t=0.85
                if t < 0.35:
                    detail_view.set_opacity(0.0)
                elif t < 0.85:
                    detail_view.set_opacity((t - 0.35) / 0.5)
                else:
                    detail_view.set_opacity(1.0)
                # Fade out the shadow on the fly image in the last 30%
                if t > 0.7:
                    fly.set_opacity(1.0 - ((t - 0.7) / 0.3) * 0.6)

            def on_done(_anim):
                detail_view.set_opacity(1.0)
                if fly.get_parent() is not None:
                    self._anim_fixed.remove(fly)
                self._anim_fixed.set_can_target(False)
                self._active_hero_anim = None

            target = Adw.CallbackAnimationTarget.new(on_frame)
            anim = Adw.TimedAnimation.new(fly, 0.0, 1.0, 350, target)
            anim.set_easing(Adw.Easing.EASE_IN_OUT_CUBIC)
            anim.connect("done", on_done)
            self._active_hero_anim = anim
            self._anim_fixed.set_can_target(True)  # block clicks during animation
            anim.play()
            return False

        GLib.idle_add(try_start)

    def _get_widget_rect(self, widget):
        """Get widget's (x, y, w, h) in window-local coordinates."""
        if not widget.get_mapped() or not widget.get_visible():
            return None
        w = widget.get_width()
        h = widget.get_height()
        if w < 1 or h < 1:
            return None
        ok, pt = widget.compute_point(self, Graphene.Point.zero())
        if not ok:
            return None
        return (pt.x, pt.y, float(w), float(h))

    def _estimate_cover_rect(self):
        """Fallback destination when cover image isn't laid out yet."""
        win_w = self.get_width()
        win_h = self.get_height()
        if win_w < 1 or win_h < 1:
            return None
        # Approximate: right side of detail hero area, with some padding
        cover_w = 280.0
        cover_h = 380.0
        x = win_w - cover_w - 40.0
        y = 100.0  # below header bar
        return (x, y, cover_w, cover_h)

    def _on_detail_back(self):
        target = self._previous_page or "discover"
        self._previous_page = None
        self._view_stack.set_visible_child_name(target)

    def _get_scraper_for_url(self, url: str):
        return self._services["scraper"]

    def _on_install_requested(self, title, url, thumbnail=None):
        if not self._download_manager:
            self.set_status("Set your Torbox API key in Settings first")
            self._navigate_to("settings")
            return

        def do_install():
            try:
                scraper = self._get_scraper_for_url(url)
                detail = scraper.get_detail(url)

                if not detail.magnet_uri:
                    GLib.idle_add(self.set_status, f"No magnet link found for {title}")
                    return

                slug = scraper.slug_from_url(url)
                cover_url = thumbnail or (detail.screenshots[0] if detail.screenshots else None)
                game = self._library.add_game(
                    title=title, slug=slug, source_url=url,
                    cover_url=cover_url,
                    size_bytes=None,
                )

                GLib.idle_add(self._downloads_view.add_download, game.id, title, cover_url)
                GLib.idle_add(self.set_status, f"Starting download: {title}")
                GLib.idle_add(self._navigate_to, "downloads")
                GLib.idle_add(self._update_dl_badge, self._active_dl_count + 1)

                self._download_manager.enqueue(
                    game_id=game.id, magnet=detail.magnet_uri,
                )
            except Exception as e:
                log.exception("Install failed for %s: %s", title, e)
                GLib.idle_add(self.set_status, f"Error: {e}")

        thread = threading.Thread(target=do_install, daemon=True)
        thread.start()

    def _on_api_key_validated(self, api_key):
        def validate():
            from sevenseas.core.torbox import TorboxClient
            client = TorboxClient(api_key=api_key)
            valid = client.validate_api_key()
            if valid:
                GLib.idle_add(self._on_api_key_valid, api_key)
            else:
                settings_view = self._views.get("settings")
                if settings_view:
                    GLib.idle_add(settings_view.set_api_status, "Invalid API key")

        thread = threading.Thread(target=validate, daemon=True)
        thread.start()

    def _on_api_key_valid(self, api_key):
        settings_view = self._views.get("settings")
        if settings_view:
            settings_view.set_api_status("API key validated successfully!")
        self._init_download_manager()

    def _on_download_progress(self, item):
        self._downloads_view.update_download(item.game_id, item.state.value, item.progress, item.speed_bps)
        game = self._library.get_by_id(item.game_id)
        title = game.title if game else "Unknown"
        self.set_status(f"Downloading: {title} — {item.progress * 100:.0f}%")

    def _on_download_complete(self, item):
        self._downloads_view.update_download(item.game_id, "complete", 1.0, 0)
        game = self._library.get_by_id(item.game_id)
        title = game.title if game else "Unknown"
        self.set_status(f"Installed: {title}")
        self._update_dl_badge(max(0, self._active_dl_count - 1))
        self._send_notification(
            "Game Installed",
            f"{title} has been installed successfully.",
            f"install-complete-{item.game_id}",
        )
        library_view = self._views.get("library")
        if library_view and hasattr(library_view, "refresh"):
            library_view.refresh()
        self._check_background_state()

    def _on_download_error(self, item):
        self._downloads_view.update_download(item.game_id, "failed", item.progress, 0)
        self.set_status(f"Failed: {item.error}")
        self._update_dl_badge(max(0, self._active_dl_count - 1))
        self._send_notification(
            "Download Failed",
            f"Error: {item.error}",
            f"install-failed-{item.game_id}",
        )
        self._check_background_state()

    def _on_retry_download(self, game_id):
        if self._download_manager:
            self._download_manager.request_reinstall(game_id)
            self.set_status("Installer will re-run after current finishes")

    def _on_cancel_download(self, game_id):
        if self._download_manager:
            self._download_manager.cancel(game_id)
            self._downloads_view.update_download(game_id, "failed", 0, 0)
            self._update_dl_badge(max(0, self._active_dl_count - 1))
            self.set_status("Download cancelled")

    def _on_sync_steam(self):
        if not self._download_manager:
            self.set_status("Set your Torbox API key in Settings first")
            self._navigate_to("settings")
            return

        self.set_status("Syncing installed games to Steam...")
        library_view = self._views.get("library")
        if library_view:
            library_view._sync_btn.set_sensitive(False)

        def on_progress(i, total, title):
            GLib.idle_add(self.set_status, f"Adding to Steam ({i + 1}/{total}): {title}")

        def on_done(count):
            def finish():
                if library_view:
                    library_view._sync_btn.set_sensitive(True)
                    library_view.refresh()
                if count:
                    self.set_status(f"Added {count} game{'s' if count != 1 else ''} to Steam")
                    self._send_notification(
                        "Steam Sync Complete",
                        f"Added {count} game{'s' if count != 1 else ''} to Steam.",
                        "steam-sync",
                    )
                else:
                    self.set_status("All games already in Steam")
            GLib.idle_add(finish)

        threading.Thread(
            target=self._download_manager.add_all_to_steam,
            kwargs={"on_progress": on_progress, "on_done": on_done},
            daemon=True,
        ).start()
