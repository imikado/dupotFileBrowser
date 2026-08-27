import os
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk

from domain.conf.app_version_conf import APP_VERSION
from domain.entity.user_settings_entity import UserSettingsEntity
from infrastructure.api.system_api import SystemApi
from infrastructure.api.user_settings_api import UserSettingsApi
from infrastructure.ui.details_page import DetailsPage
from infrastructure.ui.grid_page import GridPage
from infrastructure.ui.menu.parameters_dialog import ParametersDialog
from infrastructure.ui.path_page import PathPage
from infrastructure.ui.shared.file_icons import build_icon_image
from infrastructure.ui.shared.sidemenu_shared import SideMenuItem, SideMenuShared
from infrastructure.ui.shared.view_mode_switcher import ViewModeSwitcher
from infrastructure.ui.trash_page import TrashPage

APP_ID = "org.dupot.filebrowser"


class _FileOpJob:
   
    def __init__(self, kind: str, source: str, destination: str, archive_format: str | None = None):
        self.kind = kind  # "copy" | "move" | "compress" | "extract"
        self.source = source
        self.destination = destination
        self.archive_format = archive_format  # only set for kind == "compress"


class MainWindow(Adw.ApplicationWindow):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.set_title(_("File browser"))

        self._system_api = SystemApi()
        self._settings = UserSettingsEntity()
        self.set_default_size(self._settings.window_width, self._settings.window_height)

        self._save_window_size_source_id: int | None = None

        self._grid_icon_size_source_id: int | None = None
        self.connect("notify::default-width", self._on_window_size_changed)
        self.connect("notify::default-height", self._on_window_size_changed)
        self.connect("close-request", self._on_close_request)
        self._home_path = self._system_api.get_home_dir()
        self._trash_path = self._system_api.get_trash_dir()
        self._current_path = self._home_path

        self._host_etc_path = (
            "/run/host/etc"
            if self._system_api.is_running_flatpak()
            and self._system_api.is_dir("/run/host/etc")
            else None
        )

        toolbar_view = Adw.ToolbarView()

        header_bar = Adw.HeaderBar()
        toolbar_view.add_top_bar(header_bar)

        self._up_button = Gtk.Button()
        self._up_button.set_child(build_icon_image("go-up"))
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

        self._clipboard_path: str | None = None
        self._clipboard_is_cut: bool = False

        self._job_queue: list[_FileOpJob] = []

        self._paste_slot = Gtk.Box()
        header_bar.pack_end(self._paste_slot)
        self._paste_badge_css = self._build_paste_badge_css_provider()

        self._view_mode_switcher = ViewModeSwitcher(
            self._settings, self._on_view_mode_changed, self._on_grid_icon_size_changed
        )
        header_bar.pack_end(self._view_mode_switcher)

        menu = Gio.Menu()
        menu.append(_("Parameters"), "win.parameters")
        menu.append(_("About"), "win.about")
        self._menu_button = Gtk.MenuButton()
        self._menu_button.set_child(build_icon_image("open-menu"))
        self._menu_button.set_menu_model(menu)
        header_bar.pack_end(self._menu_button)

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

        self._path_page = PathPage(
            self._on_path_changed,
            self._refresh_side_menu,
            self._on_file_copied,
            self._on_file_cut,
            self._on_compress_requested,
            self._on_extract_requested,
        )
        self._path_page.set_hexpand(True)

        self._grid_page = GridPage(
            self._on_path_changed,
            self._refresh_side_menu,
            self._on_file_copied,
            self._on_file_cut,
            self._on_compress_requested,
            self._on_extract_requested,
        )
        self._grid_page.set_hexpand(True)

        self._details_page = DetailsPage(
            self._on_path_changed,
            self._refresh_side_menu,
            self._on_file_copied,
            self._on_file_cut,
            self._on_compress_requested,
            self._on_extract_requested,
        )
        self._details_page.set_hexpand(True)

        self._trash_page = TrashPage(self._system_api)
        self._trash_page.set_hexpand(True)

        self._main_stack = Gtk.Stack()
        self._main_stack.set_hexpand(True)
        self._main_stack.add_named(self._path_page, "browser")
        self._main_stack.add_named(self._grid_page, "grid")
        self._main_stack.add_named(self._details_page, "details")
        self._main_stack.add_named(self._trash_page, "trash")

        body.append(sidebar_scroll)
        body.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        body.append(self._main_stack)

        toolbar_view.set_content(body)
        self.set_content(toolbar_view)

        Adw.StyleManager.get_default().connect(
            "notify::dark", self._on_style_dark_changed
        )

        self._apply_theme()
        #self._update_dark_mode_icon()
        self._go_to_path(self._current_path)

    def _on_window_size_changed(self, _window, _pspec):
        if self._save_window_size_source_id is not None:
            GLib.source_remove(self._save_window_size_source_id)
        self._save_window_size_source_id = GLib.timeout_add(
            500, self._save_window_size
        )

    def _save_window_size(self) -> bool:
        self._save_window_size_source_id = None
        width, height = self.get_default_size()
        self._settings.set_window_size(width, height)
        UserSettingsApi(self._system_api).save()
        return GLib.SOURCE_REMOVE

    def _on_close_request(self, _window) -> bool:
        if self._save_window_size_source_id is not None:
            GLib.source_remove(self._save_window_size_source_id)
            self._save_window_size()
        if self._grid_icon_size_source_id is not None:
            GLib.source_remove(self._grid_icon_size_source_id)
            UserSettingsApi(self._system_api).save()
        return False  # don't block the close

    def _on_style_dark_changed(self, _style_manager, _pspec):
        self._up_button.set_child(build_icon_image("go-up"))
        self._menu_button.set_child(build_icon_image("open-menu"))
        #self._update_dark_mode_icon()
        self._update_paste_button()
        self._refresh_side_menu()
        self._trash_page.refresh()

    def _refresh_side_menu(self):
        items = [
            SideMenuItem(
                "user-home", _("Home"), self._home_path, self._go_to_path
            ),
            SideMenuItem(
                "user-trash", _("Trash"), self._trash_path, self._go_to_trash
            ),
        ]
        if self._host_etc_path is not None:
            items.append(
                SideMenuItem("folder", _("Host /etc"), self._host_etc_path, self._go_to_path)
            )
        if self._settings.favorite_list:
            items.append(None)  # separator between Home and the favorites
            for favorite in self._settings.favorite_list:
                items.append(
                    SideMenuItem(
                        "folder",
                        favorite.get(UserSettingsEntity.FIELD_FAVORITE_LABEL, ""),
                        favorite.get(UserSettingsEntity.FIELD_FAVORITE_PATH, ""),
                        self._go_to_path,
                        on_remove=self._on_remove_favorite,
                    )
                )
        self._side_menu.set_items(items)
        self._side_menu.set_selected_path(self._current_path)

    def _on_remove_favorite(self, path: str):
        self._settings.remove_favorite(path)
        UserSettingsApi(self._system_api).save()
        self._refresh_side_menu()

    # --- Paste button (Copy -> Paste the file, with a pending-jobs badge) -
    # Also drives the "Compress…" context menu entry (see
    # _on_compress_requested) — same badge, same one-at-a-time queue.

    def _build_paste_badge_css_provider(self) -> Gtk.CssProvider:
        provider = Gtk.CssProvider()
        provider.load_from_data(
            b"""
            label.paste-badge {
                background: @accent_bg_color;
                color: @accent_fg_color;
                font-size: 0.7em;
                min-width: 14px;
                padding: 1px 4px;
                border-radius: 999px;
            }
            """
        )
        return provider

    def _on_file_copied(self, _name: str, path: str):
        """Called by PathPage after the "Copy" context menu entry."""
        self._clipboard_path = path
        self._clipboard_is_cut = False
        self._update_paste_button()

    def _on_file_cut(self, _name: str, path: str):
        """Called by PathPage after the "Cut" context menu entry."""
        self._clipboard_path = path
        self._clipboard_is_cut = True
        self._update_paste_button()

    def _update_paste_button(self):
        self._clear_paste_slot()

        pending_count = len(self._job_queue)
        if pending_count > 0:
            self._paste_slot.append(self._build_pending_button(pending_count))
        elif self._clipboard_path:
            self._paste_slot.append(self._build_ready_button())

    def _clear_paste_slot(self):
        child = self._paste_slot.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._paste_slot.remove(child)
            child = next_child

    def _build_ready_button(self) -> Gtk.Button:
        label = _("Move file") if self._clipboard_is_cut else _("Paste the file")
        button = Gtk.Button(label=label)
        button.add_css_class("flat")
        # Absolute path of the copied/cut file/folder, on hover.
        button.set_tooltip_text(self._clipboard_path)
        button.connect("clicked", self._on_paste_clicked)
        return button

    def _build_pending_button(self, count: int) -> Gtk.Button:
        badge = Gtk.Label(label=str(count))
        badge.add_css_class("paste-badge")
        badge.set_halign(Gtk.Align.END)
        badge.set_valign(Gtk.Align.START)
        badge.get_style_context().add_provider(
            self._paste_badge_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        overlay = Gtk.Overlay()
        overlay.set_child(build_icon_image("edit-paste"))
        overlay.add_overlay(badge)

        button = Gtk.Button()
        button.add_css_class("flat")
        button.set_child(overlay)
        button.set_sensitive(False)
        button.set_tooltip_text(_("{count} pending").format(count=count))
        return button

    def _on_paste_clicked(self, _button):
        source_path = self._clipboard_path
        is_cut = self._clipboard_is_cut
        if not source_path:
            return
        self._clipboard_path = None
        self._clipboard_is_cut = False
        self._clear_paste_slot()
        self._try_paste(source_path, is_cut)

    def _try_paste(self, source_path: str, is_cut: bool):
        name = os.path.basename(source_path.rstrip("/"))
        destination = os.path.join(self._current_path, name)
        if self._system_api.file_exists(destination):
            self._ask_new_name(source_path, name, is_cut)
        else:
            self._enqueue_job(_FileOpJob("move" if is_cut else "copy", source_path, destination))

    def _ask_new_name(self, source_path: str, taken_name: str, is_cut: bool):
        entry = Gtk.Entry()
        entry.set_text(taken_name)
        entry.set_activates_default(True)

        dialog = Adw.AlertDialog(
            heading=_("File already exists"),
            body=_(
                '"{name}" already exists in this folder. Choose a new name.'
            ).format(name=taken_name),
        )
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", _("Cancel"))
        action_label = _("Move") if is_cut else _("Paste")
        dialog.add_response("paste", action_label)
        dialog.set_default_response("paste")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("paste", Adw.ResponseAppearance.SUGGESTED)

        def on_response(_dialog, response):
            if response != "paste":
                return
            new_name = entry.get_text().strip()
            if not new_name:
                return
            destination = os.path.join(self._current_path, new_name)
            if self._system_api.file_exists(destination):
                # Still taken: ask again instead of silently overwriting.
                GLib.idle_add(self._ask_new_name, source_path, new_name, is_cut)
                return
            self._enqueue_job(_FileOpJob("move" if is_cut else "copy", source_path, destination))

        dialog.connect("response", on_response)
        dialog.present(self)

    def _on_compress_requested(self, path: str, destination: str, archive_format: str):
        self._enqueue_job(_FileOpJob("compress", path, destination, archive_format))

    def _on_extract_requested(self, path: str):
        parent = self._system_api.get_parent_dir(path)
        base_name = self._system_api.get_archive_base_name(path)
        destination = os.path.join(parent, base_name)
        if self._system_api.file_exists(destination):
            self._ask_extract_name(path, base_name, parent)
        else:
            self._enqueue_job(_FileOpJob("extract", path, destination))

    def _ask_extract_name(self, path: str, taken_name: str, parent: str):
        entry = Gtk.Entry()
        entry.set_text(taken_name)
        entry.set_activates_default(True)

        dialog = Adw.AlertDialog(
            heading=_("Folder already exists"),
            body=_(
                '"{name}" already exists in this folder. Choose a name for the '
                "extracted folder."
            ).format(name=taken_name),
        )
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("extract", _("Extract"))
        dialog.set_default_response("extract")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("extract", Adw.ResponseAppearance.SUGGESTED)

        def on_response(_dialog, response):
            if response != "extract":
                return
            new_name = entry.get_text().strip()
            if not new_name:
                return
            destination = os.path.join(parent, new_name)
            if self._system_api.file_exists(destination):
                # Still taken: ask again instead of silently overwriting.
                GLib.idle_add(self._ask_extract_name, path, new_name, parent)
                return
            self._enqueue_job(_FileOpJob("extract", path, destination))

        dialog.connect("response", on_response)
        dialog.present(self)

    def _enqueue_job(self, job: _FileOpJob):
        was_idle = not self._job_queue
        self._job_queue.append(job)
        self._update_paste_button()
        if was_idle:
            self._process_next_job()

    def _process_next_job(self):
        if not self._job_queue:
            return
        threading.Thread(target=self._run_job, args=(self._job_queue[0],), daemon=True).start()

    def _run_job(self, job: _FileOpJob):
        if job.kind == "move":
            error = self._system_api.move_path(job.source, job.destination)
        elif job.kind == "compress":
            error = self._system_api.compress_path(job.source, job.destination, job.archive_format)
        elif job.kind == "extract":
            error = self._system_api.extract_path(job.source, job.destination)
        else:
            error = self._system_api.copy_path(job.source, job.destination)
        GLib.idle_add(self._on_job_done, job, error)

    def _on_job_done(self, job: _FileOpJob, error: str | None):
        if self._job_queue:
            self._job_queue.pop(0)
        self._update_paste_button()
        if error is None:
            refresh_target = (
                job.destination if job.kind == "extract" else os.path.dirname(job.destination)
            )
            self._active_browser_page().refresh_path(refresh_target)
            if job.kind == "move":
                self._active_browser_page().refresh_path(os.path.dirname(job.source))
        else:
            self._show_job_error(job, error)
        self._process_next_job()
        return False

    def _show_job_error(self, job: _FileOpJob, output: str):
        name = os.path.basename(job.source.rstrip("/"))
        if job.kind == "move":
            heading = _("Move failed")
            body = _('Could not move "{name}" to this folder.').format(name=name)
        elif job.kind == "compress":
            heading = _("Compression failed")
            body = _('Could not compress "{name}".').format(name=name)
        elif job.kind == "extract":
            heading = _("Extraction failed")
            body = _('Could not extract "{name}".').format(name=name)
        else:
            heading = _("Copy failed")
            body = _('Could not copy "{name}" to this folder.').format(name=name)
        if output:
            body += "\n\n" + output
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("ok", _("OK"))
        dialog.present(self)

    def _browser_view_name(self) -> str:
        if self._settings.use_grid_view():
            return "grid"
        if self._settings.use_details_view():
            return "details"
        return "browser"

    def _active_browser_page(self):
        if self._settings.use_grid_view():
            return self._grid_page
        if self._settings.use_details_view():
            return self._details_page
        return self._path_page

    def _uses_single_folder_view(self) -> bool:
        return self._settings.use_grid_view() or self._settings.use_details_view()

    def _go_to_path(self, path: str):
        self._main_stack.set_visible_child_name(self._browser_view_name())
        self._path_entry.set_sensitive(True)
        self._update_path_state(path)
        self._active_browser_page().load_path(path)

    def _go_to_trash(self, _path: str):
        self._main_stack.set_visible_child_name("trash")
        self._trash_page.refresh()
        self._path_entry.set_text(_("Trash"))
        self._path_entry.set_sensitive(False)
        self._up_button.set_sensitive(False)
        self._side_menu.set_selected_path(self._trash_path)

    def _on_path_changed(self, path: str):
        self._update_path_state(path)

    def _update_path_state(self, path: str):
        self._current_path = path
        self._path_entry.set_text(path)
        self._path_entry.remove_css_class("error")
        self._up_button.set_sensitive(path not in ("/", ""))
        self._side_menu.set_selected_path(path)

    def _on_up_clicked(self, _button):
        if self._uses_single_folder_view():
            parent_path = self._system_api.get_parent_dir(self._current_path)
            if parent_path != self._current_path:
                self._update_path_state(parent_path)
                self._active_browser_page().load_path(parent_path)
        else:
            self._path_page.prepend_parent()

    def _on_path_entry_activate(self, entry):
        path = entry.get_text().strip()
        if path and self._system_api.is_dir(path):
            self._update_path_state(path)
            if self._uses_single_folder_view():
                self._active_browser_page().load_path(path)
            else:
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

    def _apply_theme(self):
        style_manager = Adw.StyleManager.get_default()
        if self._settings.use_theme_dark():
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        elif self._settings.use_theme_light():
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

    def _on_menu_parameters(self, _action, _param):
        ParametersDialog(self._on_settings_saved).present(self)

    def _on_settings_saved(self, hidden_files_changed=False, single_click_open_changed=False):
        self._apply_theme()
        if hidden_files_changed:
            self._active_browser_page().refresh_hidden_files()
        if single_click_open_changed:
            self._grid_page.apply_click_to_open_setting()
            self._details_page.apply_click_to_open_setting()

    def _on_view_mode_changed(self, mode: str):
        UserSettingsApi(self._system_api).save()
        self._main_stack.set_visible_child_name(self._browser_view_name())
        if mode in (UserSettingsEntity.VIEW_MODE_GRID, UserSettingsEntity.VIEW_MODE_DETAILS):
            self._active_browser_page().load_path(self._current_path)
        else:
            self._path_page.load_path_chain(self._current_path)

    def _on_grid_icon_size_changed(self, size: int):
        if self._grid_icon_size_source_id is not None:
            GLib.source_remove(self._grid_icon_size_source_id)
        self._grid_icon_size_source_id = GLib.timeout_add(
            150, self._apply_grid_icon_size, size
        )

    def _apply_grid_icon_size(self, size: int) -> bool:
        self._grid_icon_size_source_id = None
        self._grid_page.set_icon_size(size)
        UserSettingsApi(self._system_api).save()
        return GLib.SOURCE_REMOVE

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
