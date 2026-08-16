import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk

from domain.entity.user_settings_entity import UserSettingsEntity
from infrastructure.api.system_api import SystemApi
from infrastructure.api.user_settings_api import UserSettingsApi
from infrastructure.ui.menu.parameters_dialog import ParametersDialog
from infrastructure.ui.path_page import PathPage
from infrastructure.ui.shared.sidemenu_shared import SideMenuItem, SideMenuShared

APP_ID = "org.dupot.filebrowser"
APP_VERSION = "1.0.0"


class MainWindow(Adw.ApplicationWindow):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.set_title(_("File browser"))
        self.set_default_size(1000, 700)

        self._system_api = SystemApi()
        self._settings = UserSettingsEntity()
        self._home_path = self._system_api.get_home_dir()
        self._current_path = self._home_path

        toolbar_view = Adw.ToolbarView()

        header_bar = Adw.HeaderBar()
        toolbar_view.add_top_bar(header_bar)

        self._up_button = Gtk.Button()
        self._up_button.set_icon_name("go-up-symbolic")
        self._up_button.set_tooltip_text(_("Parent folder"))
        self._up_button.connect("clicked", self._on_up_clicked)
        header_bar.pack_start(self._up_button)

        self._path_entry = Gtk.Entry()
        self._path_entry.set_hexpand(True)
        self._path_entry.add_css_class("flat")
        self._path_entry.set_tooltip_text(_("Type a path and press Enter to go there"))
        self._path_entry.connect("activate", self._on_path_entry_activate)
        self._path_entry.connect("changed", self._on_path_entry_changed)
        header_bar.set_title_widget(self._path_entry)

        self._dark_mode_button = Gtk.Button()
        self._dark_mode_button.connect("clicked", self._on_toggle_dark_mode)
        header_bar.pack_end(self._dark_mode_button)

        menu = Gio.Menu()
        menu.append(_("Parameters"), "win.parameters")
        menu.append(_("About"), "win.about")
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_menu_model(menu)
        header_bar.pack_end(menu_button)

        for name, callback in [
            ("parameters", self._on_menu_parameters),
            ("about", self._on_menu_about),
        ]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        body.set_vexpand(True)
        body.set_hexpand(True)

        self._side_menu = SideMenuShared()
        self._refresh_side_menu()

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_child(self._side_menu)
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_size_request(220, -1)
        sidebar_scroll.add_css_class("background")

        self._path_page = PathPage(self._on_path_changed)
        self._path_page.set_hexpand(True)

        body.append(sidebar_scroll)
        body.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        body.append(self._path_page)

        toolbar_view.set_content(body)
        self.set_content(toolbar_view)

        self._apply_theme()
        self._update_dark_mode_icon()
        self._go_to_path(self._current_path)

    def _refresh_side_menu(self):
        self._side_menu.set_items(
            [
                SideMenuItem(
                    "user-home-symbolic", _("Home"), self._home_path, self._go_to_path
                ),
            ]
        )

    def _go_to_path(self, path: str):
        """Full reset: used for sidebar navigation and the initial load,
        collapses back down to a single Miller column showing `path`."""
        self._update_path_state(path)
        self._path_page.load_path(path)

    def _on_path_changed(self, path: str):
        """Called by PathPage when the deepest open column changes because
        the user clicked into/around the Miller columns, without resetting
        the columns themselves."""
        self._update_path_state(path)

    def _update_path_state(self, path: str):
        self._current_path = path
        self._path_entry.set_text(path)
        self._path_entry.remove_css_class("error")
        self._up_button.set_sensitive(path not in ("/", ""))
        self._side_menu.set_selected_path(path)

    def _on_up_clicked(self, _button):
        # Reveals the enclosing folder as a new leftmost column; never
        # drops any column that's already open (see PathPage.prepend_parent).
        self._path_page.prepend_parent()

    def _on_path_entry_activate(self, entry):
        path = entry.get_text().strip()
        if path and self._system_api.is_dir(path):
            self._update_path_state(path)
            self._path_page.load_path_chain(path)
        else:
            entry.add_css_class("error")

    def _on_path_entry_changed(self, entry):
        entry.remove_css_class("error")

    def _on_toggle_dark_mode(self, _button):
        if self._settings.use_theme_dark():
            self._settings.theme = UserSettingsEntity.THEME_LIGHT
        else:
            self._settings.theme = UserSettingsEntity.THEME_DARK
        UserSettingsApi(self._system_api).save()
        self._apply_theme()
        self._update_dark_mode_icon()

    def _apply_theme(self):
        style_manager = Adw.StyleManager.get_default()
        if self._settings.use_theme_dark():
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        elif self._settings.use_theme_light():
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

    def _update_dark_mode_icon(self):
        is_dark = Adw.StyleManager.get_default().get_dark()
        self._dark_mode_button.set_icon_name(
            "weather-clear-symbolic" if is_dark else "weather-clear-night-symbolic"
        )
        self._dark_mode_button.set_tooltip_text(
            _("Switch to light mode") if is_dark else _("Switch to dark mode")
        )

    def _on_menu_parameters(self, _action, _param):
        ParametersDialog(self._on_settings_saved).present(self)

    def _on_settings_saved(self):
        self._apply_theme()
        self._update_dark_mode_icon()

    def _on_menu_about(self, _action, _param):
        about = Adw.AboutDialog.new()
        about.set_application_name(_("File browser"))
        about.set_version(APP_VERSION)
        about.set_developer_name("Michael Bertocchi")
        about.set_license_type(Gtk.License.LGPL_2_1)
        about.set_website("https://dupot.org")
        about.present(self)


class AppWindow(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE
        )

    def do_activate(self):
        win = self.get_active_window()
        if not win:
            win = MainWindow(application=self)
        win.present()
