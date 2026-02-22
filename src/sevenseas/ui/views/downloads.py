"""Downloads view — active and completed downloads."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from sevenseas.ui.widgets.download_row import DownloadRow


_STAGE_LABELS = {
    "pending": "Queued",
    "torbox_downloading": "Waiting on Torbox",
    "pulling": "Downloading",
    "extracting": "Extracting",
    "installing": "Running Installer",
    "moving": "Moving to Games",
    "adding_to_steam": "Adding to Steam",
    "installing_redists": "Installing Redistributables",
    "fetching_art": "Pulling Media",
    "restarting_steam": "Restarting Steam",
    "cleaning_up": "Cleaning Up",
    "complete": "Complete",
    "failed": "Failed",
}


class DownloadsView(Gtk.Box):
    """Shows active downloads and their progress."""

    def __init__(self, on_cancel=None, on_retry=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._on_cancel = on_cancel
        self._on_retry = on_retry

        title = Gtk.Label(label="Downloads")
        title.add_css_class("title-1")
        title.set_margin_top(16)
        title.set_margin_bottom(12)
        self.append(title)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.append(scroll)

        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list_box.add_css_class("boxed-list")
        self._list_box.set_margin_start(12)
        self._list_box.set_margin_end(12)
        scroll.set_child(self._list_box)

        self._rows: dict[int, DownloadRow] = {}

        self._empty = Gtk.Label(label="No downloads")
        self._empty.add_css_class("dim-label")
        self._empty.set_vexpand(True)
        self.append(self._empty)

    def add_download(self, game_id: int, title: str, cover_url: str | None = None) -> None:
        self._empty.set_visible(False)
        cancel_cb = (lambda gid=game_id: self._on_cancel(gid)) if self._on_cancel else None
        retry_cb = (lambda gid=game_id: self._on_retry(gid)) if self._on_retry else None
        row = DownloadRow(title=title, stage="Pending", on_cancel=cancel_cb,
                          on_retry=retry_cb, cover_url=cover_url)
        self._rows[game_id] = row
        self._list_box.append(row)

    def update_download(self, game_id: int, state: str, progress: float, speed_bps: int) -> None:
        row = self._rows.get(game_id)
        if row:
            stage = _STAGE_LABELS.get(state, state)
            row.update(stage, progress, speed_bps)

    def remove_download(self, game_id: int) -> None:
        row = self._rows.pop(game_id, None)
        if row:
            self._list_box.remove(row)
        if not self._rows:
            self._empty.set_visible(True)
