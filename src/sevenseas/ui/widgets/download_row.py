"""Download progress row widget."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw


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
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(12)
        self.set_margin_end(12)

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(top_row)

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

        if on_cancel:
            cancel_btn = Gtk.Button.new_from_icon_name("process-stop-symbolic")
            cancel_btn.add_css_class("flat")
            cancel_btn.connect("clicked", lambda _: on_cancel())
            top_row.append(cancel_btn)

        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_fraction(progress)
        self._progress_bar.set_show_text(True)
        self._progress_bar.set_text(f"{progress * 100:.0f}%")
        self.append(self._progress_bar)

    def update(self, stage: str, progress: float, speed_bps: int) -> None:
        self._stage_label.set_text(stage)
        self._progress_bar.set_fraction(min(progress, 1.0))
        self._progress_bar.set_text(f"{progress * 100:.0f}%")
        self._speed_label.set_text(_format_speed(speed_bps))
