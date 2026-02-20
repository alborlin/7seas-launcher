"""Game card widget — shows cover art, title, size, and action button."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw


class GameCard(Gtk.Box):
    """A card displaying game info with an action button."""

    def __init__(
        self,
        title: str,
        size_info: str | None = None,
        thumbnail_path: str | None = None,
        status: str = "new",
        on_action=None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_size_request(200, 300)
        self.add_css_class("card")
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        self._title = title
        self._on_action = on_action

        # Cover image placeholder
        self._image = Gtk.Picture()
        self._image.set_size_request(200, 200)
        self._image.set_content_fit(Gtk.ContentFit.COVER)
        if thumbnail_path:
            self._image.set_filename(thumbnail_path)
        self.append(self._image)

        # Info box
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.set_margin_start(8)
        info_box.set_margin_end(8)
        info_box.set_margin_bottom(8)
        self.append(info_box)

        # Title
        title_label = Gtk.Label(label=title)
        title_label.set_halign(Gtk.Align.START)
        title_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        title_label.set_max_width_chars(25)
        title_label.add_css_class("heading")
        info_box.append(title_label)

        # Size
        if size_info:
            size_label = Gtk.Label(label=size_info)
            size_label.set_halign(Gtk.Align.START)
            size_label.add_css_class("dim-label")
            info_box.append(size_label)

        # Action button
        self._action_btn = Gtk.Button()
        self._action_btn.add_css_class("suggested-action")
        self._update_button_for_status(status)
        self._action_btn.connect("clicked", self._on_button_clicked)
        info_box.append(self._action_btn)

    def _update_button_for_status(self, status: str) -> None:
        labels = {
            "new": "Install",
            "downloading": "Downloading...",
            "extracting": "Extracting...",
            "installing": "Installing...",
            "installed": "Launch",
            "failed": "Retry",
        }
        self._action_btn.set_label(labels.get(status, "Install"))
        self._action_btn.set_sensitive(status in ("new", "installed", "failed"))

    def _on_button_clicked(self, button: Gtk.Button) -> None:
        if self._on_action:
            self._on_action(self._title)

    def set_thumbnail(self, path: str) -> None:
        try:
            self._image.set_filename(path)
        except Exception:
            pass
