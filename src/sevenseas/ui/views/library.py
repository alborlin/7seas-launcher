"""Library view — shows installed games."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from sevenseas.ui.widgets.game_card import GameCard


class LibraryView(Gtk.Box):
    """Grid of installed games with launch/manage actions."""

    def __init__(self, library_service, on_launch=None, on_uninstall=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._library = library_service
        self._on_launch = on_launch
        self._on_uninstall = on_uninstall

        title = Gtk.Label(label="Library")
        title.add_css_class("title-1")
        title.set_margin_top(16)
        title.set_margin_bottom(12)
        self.append(title)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.append(scroll)

        self._flow = Gtk.FlowBox()
        self._flow.set_valign(Gtk.Align.START)
        self._flow.set_max_children_per_line(6)
        self._flow.set_min_children_per_line(2)
        self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow.set_homogeneous(True)
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
            card = GameCard(
                title=game.title,
                status="installed",
                on_action=lambda title, g=game: self._on_game_action(g),
            )
            self._flow.append(card)

    def _on_game_action(self, game) -> None:
        if self._on_launch:
            self._on_launch(game)
