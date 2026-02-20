"""Settings view — Torbox API key, paths, preferences."""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw


class SettingsView(Gtk.Box):
    """Settings page with Torbox API key, game directory, and preferences."""

    def __init__(self, config, on_api_key_validated=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._config = config
        self._on_api_key_validated = on_api_key_validated

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self.append(scroll)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        scroll.set_child(clamp)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(12)
        content.set_margin_end(12)
        clamp.set_child(content)

        # Torbox section
        torbox_group = Adw.PreferencesGroup()
        torbox_group.set_title("Torbox")
        torbox_group.set_description("Configure your Torbox debrid service connection")
        content.append(torbox_group)

        self._api_key_row = Adw.PasswordEntryRow()
        self._api_key_row.set_title("API Key")
        current_key = config.torbox_api_key or ""
        self._api_key_row.set_text(current_key)
        torbox_group.add(self._api_key_row)

        validate_btn = Gtk.Button(label="Validate & Save")
        validate_btn.add_css_class("suggested-action")
        validate_btn.connect("clicked", self._on_validate_clicked)
        content.append(validate_btn)

        self._api_status = Gtk.Label()
        self._api_status.set_halign(Gtk.Align.START)
        content.append(self._api_status)

        # Paths section
        paths_group = Adw.PreferencesGroup()
        paths_group.set_title("Paths")
        content.append(paths_group)

        self._games_dir_row = Adw.EntryRow()
        self._games_dir_row.set_title("Games Directory")
        self._games_dir_row.set_text(config.games_dir)
        self._games_dir_row.connect("changed", self._on_games_dir_changed)
        paths_group.add(self._games_dir_row)

        # Bottles section
        bottles_group = Adw.PreferencesGroup()
        bottles_group.set_title("Bottles")
        content.append(bottles_group)

        self._bottles_row = Adw.EntryRow()
        self._bottles_row.set_title("Bottle Name")
        self._bottles_row.set_text(config.bottles_name)
        self._bottles_row.connect("changed", self._on_bottles_changed)
        bottles_group.add(self._bottles_row)

        # Steam section
        steam_group = Adw.PreferencesGroup()
        steam_group.set_title("Steam Integration")
        content.append(steam_group)

        self._steam_switch = Adw.SwitchRow()
        self._steam_switch.set_title("Auto-add to Steam")
        self._steam_switch.set_subtitle("Automatically add installed games as non-Steam shortcuts")
        self._steam_switch.set_active(config.auto_add_steam)
        self._steam_switch.connect("notify::active", self._on_steam_toggle)
        steam_group.add(self._steam_switch)

    def _on_validate_clicked(self, button: Gtk.Button) -> None:
        api_key = self._api_key_row.get_text().strip()
        if not api_key:
            self._api_status.set_text("Please enter an API key")
            return
        self._api_status.set_text("Validating...")
        self._config.set("torbox_api_key", api_key)
        if self._on_api_key_validated:
            self._on_api_key_validated(api_key)

    def _on_games_dir_changed(self, row: Adw.EntryRow) -> None:
        self._config.set("games_dir", row.get_text())

    def _on_bottles_changed(self, row: Adw.EntryRow) -> None:
        self._config.set("bottles_name", row.get_text())

    def _on_steam_toggle(self, switch: Adw.SwitchRow, _param) -> None:
        self._config.set("auto_add_steam", str(switch.get_active()).lower())

    def set_api_status(self, text: str) -> None:
        self._api_status.set_text(text)
