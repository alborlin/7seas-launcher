"""Settings view — download method, API keys, paths, preferences."""

import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

_DOWNLOAD_METHODS = ["torbox", "qbittorrent", "transmission"]
_DOWNLOAD_METHOD_LABELS = [
    "Torbox (Recommended)",
    "qBittorrent (Local)",
    "Transmission (Local)",
]
_DEFAULT_PORTS = {
    "qbittorrent": "8080",
    "transmission": "9091",
}


class SettingsView(Gtk.Box):
    """Settings page with download method, API keys, game directory, and preferences."""

    def __init__(self, config, on_api_key_validated=None, on_backend_validated=None, steam=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._config = config
        self._on_api_key_validated = on_api_key_validated
        self._on_backend_validated = on_backend_validated
        self._steam = steam

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

        # --- Download Method section ---
        method_group = Adw.PreferencesGroup()
        method_group.set_title("Download Method")
        method_group.set_description("Choose how games are downloaded")
        content.append(method_group)

        self._method_row = Adw.ComboRow()
        self._method_row.set_title("Download Method")
        self._method_row.set_subtitle("Torbox is the fastest and most reliable option")
        method_model = Gtk.StringList()
        for label in _DOWNLOAD_METHOD_LABELS:
            method_model.append(label)
        self._method_row.set_model(method_model)

        current_method = config.download_method
        try:
            active_idx = _DOWNLOAD_METHODS.index(current_method)
        except ValueError:
            active_idx = 0
        self._method_row.set_selected(active_idx)
        self._method_row.connect("notify::selected", self._on_method_changed)
        method_group.add(self._method_row)

        # --- Torbox section ---
        self._torbox_group = Adw.PreferencesGroup()
        self._torbox_group.set_title("Torbox")
        self._torbox_group.set_description("Configure your Torbox debrid service connection")
        content.append(self._torbox_group)

        torbox_link = Gtk.LinkButton(
            uri="https://torbox.app/subscription?referral=ac555d57-5be1-4f54-8b4c-7dcb6ecf213b",
            label="Get a Torbox subscription",
        )
        torbox_link.set_halign(Gtk.Align.START)
        self._torbox_group.add(torbox_link)

        self._api_key_row = Adw.PasswordEntryRow()
        self._api_key_row.set_title("API Key")
        current_key = config.torbox_api_key or ""
        self._api_key_row.set_text(current_key)
        self._torbox_group.add(self._api_key_row)

        self._torbox_validate_btn = Gtk.Button(label="Validate & Save")
        self._torbox_validate_btn.add_css_class("suggested-action")
        self._torbox_validate_btn.connect("clicked", self._on_validate_clicked)
        content.append(self._torbox_validate_btn)

        self._api_status = Gtk.Label()
        self._api_status.set_halign(Gtk.Align.START)
        content.append(self._api_status)

        # --- BT Connection section ---
        self._bt_group = Adw.PreferencesGroup()
        self._bt_group.set_title("BitTorrent Client Connection")
        self._bt_group.set_description("Connect to your local BitTorrent client. For faster downloads and cached torrents, consider using Torbox instead.")
        content.append(self._bt_group)

        self._bt_host_row = Adw.EntryRow()
        self._bt_host_row.set_title("Host")
        self._bt_host_row.set_text(config.bt_host or "localhost")
        self._bt_host_row.connect("changed", self._on_bt_setting_changed)
        self._bt_group.add(self._bt_host_row)

        self._bt_port_row = Adw.EntryRow()
        self._bt_port_row.set_title("Port")
        self._bt_port_row.set_text(config.bt_port or _DEFAULT_PORTS.get(current_method, ""))
        self._bt_port_row.connect("changed", self._on_bt_setting_changed)
        self._bt_group.add(self._bt_port_row)

        self._bt_username_row = Adw.EntryRow()
        self._bt_username_row.set_title("Username (optional)")
        self._bt_username_row.set_text(config.bt_username or "")
        self._bt_username_row.connect("changed", self._on_bt_setting_changed)
        self._bt_group.add(self._bt_username_row)

        self._bt_password_row = Adw.PasswordEntryRow()
        self._bt_password_row.set_title("Password (optional)")
        self._bt_password_row.set_text(config.bt_password or "")
        self._bt_password_row.connect("changed", self._on_bt_setting_changed)
        self._bt_group.add(self._bt_password_row)

        bt_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content.append(bt_btn_box)

        self._bt_test_btn = Gtk.Button(label="Test Connection")
        self._bt_test_btn.add_css_class("suggested-action")
        self._bt_test_btn.connect("clicked", self._on_test_bt_clicked)
        bt_btn_box.append(self._bt_test_btn)

        self._bt_status = Gtk.Label()
        self._bt_status.set_halign(Gtk.Align.START)
        bt_btn_box.append(self._bt_status)

        # --- Paths section ---
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

        self._sgdb_key_row = Adw.PasswordEntryRow()
        self._sgdb_key_row.set_title("SteamGridDB API Key")
        self._sgdb_key_row.set_text(config.steamgriddb_api_key or "")
        self._sgdb_key_row.connect("changed", self._on_sgdb_key_changed)
        steam_group.add(self._sgdb_key_row)

        # Proton version picker
        self._proton_row = Adw.ComboRow()
        self._proton_row.set_title("Proton Version")
        self._proton_row.set_subtitle("Compat tool for imported games (all games need Proton)")
        self._proton_tools: list[dict] = []
        self._proton_model = Gtk.StringList()
        self._proton_model.append("Proton Experimental (default)")
        proton_active_idx = 0
        if steam:
            self._proton_tools = steam.get_compat_tools()
            current = config.proton_version
            for i, tool in enumerate(self._proton_tools):
                self._proton_model.append(tool["display_name"])
                if tool["name"] == current:
                    proton_active_idx = i + 1
        self._proton_row.set_model(self._proton_model)
        self._proton_row.set_selected(proton_active_idx)
        self._proton_row.connect("notify::selected", self._on_proton_changed)
        steam_group.add(self._proton_row)

        # Apply initial visibility
        self._update_method_visibility()

    def _update_method_visibility(self) -> None:
        """Show/hide sections based on selected download method."""
        idx = self._method_row.get_selected()
        method = _DOWNLOAD_METHODS[idx] if idx < len(_DOWNLOAD_METHODS) else "torbox"
        is_torbox = method == "torbox"
        self._torbox_group.set_visible(is_torbox)
        self._torbox_validate_btn.set_visible(is_torbox)
        self._api_status.set_visible(is_torbox)
        self._bt_group.set_visible(not is_torbox)
        self._bt_test_btn.set_visible(not is_torbox)
        self._bt_status.set_visible(not is_torbox)

    def _on_method_changed(self, row: Adw.ComboRow, _param) -> None:
        idx = row.get_selected()
        if idx >= len(_DOWNLOAD_METHODS):
            return
        method = _DOWNLOAD_METHODS[idx]
        self._config.set("download_method", method)
        # Update default port for the selected BT client
        if method in _DEFAULT_PORTS and not self._config.bt_port:
            self._bt_port_row.set_text(_DEFAULT_PORTS[method])
        self._update_method_visibility()
        # Clear status labels
        self._api_status.set_text("")
        self._bt_status.set_text("")

    def _on_validate_clicked(self, button: Gtk.Button) -> None:
        api_key = self._api_key_row.get_text().strip()
        if not api_key:
            self._api_status.set_text("Please enter an API key")
            return
        self._api_status.set_text("Validating...")
        self._config.set("torbox_api_key", api_key)
        if self._on_api_key_validated:
            self._on_api_key_validated(api_key)

    def _on_bt_setting_changed(self, row: Adw.EntryRow) -> None:
        """Persist BT connection settings on change."""
        self._config.set("bt_host", self._bt_host_row.get_text().strip())
        self._config.set("bt_port", self._bt_port_row.get_text().strip())
        self._config.set("bt_username", self._bt_username_row.get_text().strip())
        self._config.set("bt_password", self._bt_password_row.get_text())

    def _on_test_bt_clicked(self, button: Gtk.Button) -> None:
        """Test connection to the configured BT client."""
        self._bt_status.set_text("Testing...")
        self._bt_test_btn.set_sensitive(False)

        def do_test():
            from sevenseas.core.backends import create_backend
            try:
                backend = create_backend(self._config)
                if backend is None:
                    GLib.idle_add(self._bt_test_done, False, "Backend not configured")
                    return
                ok = backend.validate_connection()
                if ok:
                    GLib.idle_add(self._bt_test_done, True, "Connection successful!")
                    if self._on_backend_validated:
                        GLib.idle_add(self._on_backend_validated)
                else:
                    GLib.idle_add(self._bt_test_done, False, "Connection failed")
            except Exception as e:
                GLib.idle_add(self._bt_test_done, False, str(e))

        threading.Thread(target=do_test, daemon=True).start()

    def _bt_test_done(self, success: bool, message: str) -> None:
        self._bt_test_btn.set_sensitive(True)
        self._bt_status.set_text(message)

    def _on_games_dir_changed(self, row: Adw.EntryRow) -> None:
        self._config.set("games_dir", row.get_text())

    def _on_bottles_changed(self, row: Adw.EntryRow) -> None:
        self._config.set("bottles_name", row.get_text())

    def _on_steam_toggle(self, switch: Adw.SwitchRow, _param) -> None:
        self._config.set("auto_add_steam", str(switch.get_active()).lower())

    def _on_sgdb_key_changed(self, row: Adw.EntryRow) -> None:
        self._config.set("steamgriddb_api_key", row.get_text().strip())

    def _on_proton_changed(self, row: Adw.ComboRow, _param) -> None:
        idx = row.get_selected()
        if idx == 0:
            self._config.set("proton_version", "")
        elif idx - 1 < len(self._proton_tools):
            tool = self._proton_tools[idx - 1]
            self._config.set("proton_version", tool["name"])

    def set_api_status(self, text: str) -> None:
        self._api_status.set_text(text)
