"""Main application window with sidebar navigation."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw


class MainWindow(Adw.ApplicationWindow):
    """Main window with sidebar navigation and content area."""

    def __init__(self, services=None, db=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_title("7-Seas Launcher")
        self.set_default_size(1200, 800)

        # Main layout: overlay with bottom status bar
        overlay_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(overlay_box)

        # Split view with sidebar
        self._split_view = Adw.NavigationSplitView()
        self._split_view.set_vexpand(True)
        overlay_box.append(self._split_view)

        # Sidebar
        sidebar_page = Adw.NavigationPage(title="7-Seas")
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_page.set_child(sidebar_box)

        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_title_widget(Gtk.Label(label="7-Seas"))
        sidebar_box.append(sidebar_header)

        # Browse section nav list
        nav_list = Gtk.ListBox()
        nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        nav_list.add_css_class("navigation-sidebar")
        nav_list.connect("row-activated", self._on_nav_row_activated)
        sidebar_box.append(nav_list)

        self._nav_items = []
        for label, icon, view_name in [
            ("Search", "system-search-symbolic", "search"),
            ("New Releases", "document-new-symbolic", "new"),
            ("Top 50", "starred-symbolic", "top50"),
            ("Top 150", "trophy-symbolic", "top150"),
        ]:
            row = self._make_nav_row(label, icon, view_name)
            nav_list.append(row)
            self._nav_items.append((row, view_name))

        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(12)
        sep.set_margin_bottom(12)
        sidebar_box.append(sep)

        # Management section nav list
        nav_list2 = Gtk.ListBox()
        nav_list2.set_selection_mode(Gtk.SelectionMode.SINGLE)
        nav_list2.add_css_class("navigation-sidebar")
        nav_list2.connect("row-activated", self._on_nav_row_activated)
        sidebar_box.append(nav_list2)

        for label, icon, view_name in [
            ("Downloads", "folder-download-symbolic", "downloads"),
            ("Library", "application-x-executable-symbolic", "library"),
            ("Settings", "emblem-system-symbolic", "settings"),
        ]:
            row = self._make_nav_row(label, icon, view_name)
            nav_list2.append(row)
            self._nav_items.append((row, view_name))

        self._split_view.set_sidebar(sidebar_page)

        # Content area
        self._content_page = Adw.NavigationPage(title="Search")
        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._content_page.set_child(self._content_box)

        content_header = Adw.HeaderBar()
        self._content_box.append(content_header)

        # Placeholder
        self._placeholder = Gtk.Label(label="Welcome to 7-Seas Launcher")
        self._placeholder.set_vexpand(True)
        self._content_box.append(self._placeholder)

        self._split_view.set_content(self._content_page)

        # Bottom status bar
        self._status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._status_bar.add_css_class("toolbar")
        self._status_bar.set_margin_start(12)
        self._status_bar.set_margin_end(12)
        self._status_label = Gtk.Label(label="No active downloads")
        self._status_bar.append(self._status_label)
        overlay_box.append(self._status_bar)

        # View management
        self._views: dict[str, Gtk.Widget] = {}
        self._current_view: str | None = None

        # Wire services and views if provided
        if services is not None:
            self._init_views(services, db)

    def _make_nav_row(self, label: str, icon_name: str, view_name: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        box.append(icon)
        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        box.append(lbl)
        row.set_child(box)
        row._view_name = view_name
        return row

    def _on_nav_row_activated(self, listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        view_name = getattr(row, "_view_name", None)
        if view_name:
            self._switch_view(view_name)

    def _switch_view(self, view_name: str) -> None:
        """Switch the content area to the named view."""
        self._current_view = view_name
        # Remove current content (except header)
        children = []
        child = self._content_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            children.append(child)
            child = next_child
        # Keep header (first child), remove rest
        for child in children[1:]:
            self._content_box.remove(child)
        # Add the view widget if registered
        view = self._views.get(view_name)
        if view:
            view.set_vexpand(True)
            self._content_box.append(view)
            # Trigger load on browse views
            if hasattr(view, "load"):
                view.load()
            if hasattr(view, "refresh"):
                view.refresh()
        else:
            label = Gtk.Label(label=f"View: {view_name}")
            label.set_vexpand(True)
            self._content_box.append(label)

    def register_view(self, name: str, widget: Gtk.Widget) -> None:
        """Register a view widget that can be shown via sidebar navigation."""
        self._views[name] = widget

    def show_settings(self) -> None:
        """Navigate to settings view (used on first run)."""
        self._switch_view("settings")

    def set_status(self, text: str) -> None:
        """Update the bottom status bar text."""
        self._status_label.set_text(text)

    # --- Service/view wiring ---

    def _init_views(self, services, db):
        """Create all view instances and register them."""
        from sevenseas.ui.views.search import SearchView
        from sevenseas.ui.views.browse import BrowseView
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
        self._downloads_view = DownloadsView()

        # Register views
        self.register_view("search", SearchView(scraper, on_install=self._on_install_requested))
        self.register_view("new", BrowseView("New Releases", scraper.get_latest, on_install=self._on_install_requested))
        self.register_view("top50", BrowseView("Top 50 This Month", scraper.get_top_monthly, on_install=self._on_install_requested))
        self.register_view("top150", BrowseView("Top 150 This Year", scraper.get_top_yearly, on_install=self._on_install_requested))
        self.register_view("downloads", self._downloads_view)
        self.register_view("library", LibraryView(library))
        self.register_view("settings", SettingsView(config, on_api_key_validated=self._on_api_key_validated))

        # Initialize download manager if API key is set
        self._download_manager = None
        if config.torbox_api_key:
            self._init_download_manager()

    def _init_download_manager(self):
        """Create the download manager with all services wired up."""
        from sevenseas.core.torbox import TorboxClient
        from sevenseas.core.downloader import DownloadManager
        from gi.repository import GLib

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

    def _on_install_requested(self, title, url):
        """Handle install button click -- fetch detail, extract magnet, start download."""
        import threading
        from gi.repository import GLib

        if not self._download_manager:
            self.set_status("Set your Torbox API key in Settings first")
            self._switch_view("settings")
            return

        def do_install():
            try:
                scraper = self._services["scraper"]
                detail = scraper.get_detail(url)
                if not detail.magnet_uri:
                    GLib.idle_add(self.set_status, f"No magnet link found for {title}")
                    return

                slug = scraper.slug_from_url(url)
                game = self._library.add_game(
                    title=title, slug=slug, source_url=url,
                    cover_url=detail.screenshots[0] if detail.screenshots else None,
                    size_bytes=None,
                )

                GLib.idle_add(self._downloads_view.add_download, game.id, title)
                GLib.idle_add(self.set_status, f"Starting download: {title}")
                GLib.idle_add(self._switch_view, "downloads")

                self._download_manager.enqueue(game_id=game.id, magnet=detail.magnet_uri)
            except Exception as e:
                GLib.idle_add(self.set_status, f"Error: {e}")

        thread = threading.Thread(target=do_install, daemon=True)
        thread.start()

    def _on_api_key_validated(self, api_key):
        """Handle API key validation from settings."""
        from gi.repository import GLib
        import threading

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
        """Called when API key is confirmed valid."""
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
        # Refresh library view
        library_view = self._views.get("library")
        if library_view and hasattr(library_view, "refresh"):
            library_view.refresh()

    def _on_download_error(self, item):
        self._downloads_view.update_download(item.game_id, "failed", item.progress, 0)
        self.set_status(f"Failed: {item.error}")
