"""Browse container — wraps multiple BrowseView instances with sub-navigation pills."""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from sevenseas.ui.views.browse import BrowseView


class BrowseContainerView(Gtk.Box):
    """Container with toggle-button sub-nav for New Releases, Top 50, Top 150."""

    def __init__(self, scraper, on_card_click=None, sgdb_api_key: str | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        # Filter row with toggle buttons
        filter_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filter_row.set_margin_top(16)
        filter_row.set_margin_bottom(8)
        filter_row.set_margin_start(16)
        filter_row.set_margin_end(16)
        self.append(filter_row)

        self._buttons: list[Gtk.ToggleButton] = []
        self._toggling = False
        self._stack = Gtk.Stack()
        self._stack.set_vexpand(True)
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(200)

        # Create views
        views = [
            ("new", "New Releases", scraper.get_latest, True),
            ("top50", "Top 50", scraper.get_top_monthly, False),
            ("top150", "Top 150", scraper.get_top_yearly, False),
        ]

        for name, label, fetch_func, paginated in views:
            btn = Gtk.ToggleButton(label=label)
            btn.add_css_class("browse-filter-btn")
            btn._view_name = name
            btn.connect("toggled", self._on_filter_toggled)
            filter_row.append(btn)
            self._buttons.append(btn)

            view = BrowseView(label, fetch_func, on_card_click=on_card_click, paginated=paginated)
            self._stack.add_named(view, name)

        self.append(self._stack)

        # Activate first button
        self._buttons[0].set_active(True)

    def _on_filter_toggled(self, button: Gtk.ToggleButton) -> None:
        if self._toggling:
            return
        if not button.get_active():
            # If user clicks the active button, re-activate it (don't allow deselect)
            if self._stack.get_visible_child_name() == button._view_name:
                button.set_active(True)
            return

        # Guard against re-entrant toggling from set_active(False) below
        self._toggling = True
        for btn in self._buttons:
            if btn is not button:
                btn.set_active(False)
        self._toggling = False

        # Switch stack and load
        name = button._view_name
        self._stack.set_visible_child_name(name)
        view = self._stack.get_child_by_name(name)
        if view and hasattr(view, "load"):
            view.load()

    def load(self) -> None:
        """Load the currently active view."""
        name = self._stack.get_visible_child_name()
        view = self._stack.get_child_by_name(name)
        if view and hasattr(view, "load"):
            view.load()
