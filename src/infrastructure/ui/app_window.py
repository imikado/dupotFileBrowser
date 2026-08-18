import os
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk

from domain.entity.user_settings_entity import UserSettingsEntity
from infrastructure.api.system_api import SystemApi
from infrastructure.api.user_settings_api import UserSettingsApi
from infrastructure.ui.menu.parameters_dialog import ParametersDialog
from infrastructure.ui.path_page import PathPage
from infrastructure.ui.shared.file_icons import build_icon_image
from infrastructure.ui.shared.sidemenu_shared import SideMenuItem, SideMenuShared
from infrastructure.ui.trash_page import TrashPage

APP_ID = "org.dupot.filebrowser"
APP_VERSION = "1.0.5"


class MainWindow(Adw.ApplicationWindow):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.set_title(_("File browser"))

        self._system_api = SystemApi()
        self._settings = UserSettingsEntity()
        self.set_default_size(self._settings.window_width, self._settings.window_height)
        # Debounce id for _on_window_size_changed — GTK fires
        # notify::default-width/height continuously while the user drags
        # an edge, so saving on every one of those would hammer disk I/O;
        # this coalesces a burst of resize events into one write, a
        # moment after the user stops moving the pointer.
        self._save_window_size_source_id: int | None = None
        self.connect("notify::default-width", self._on_window_size_changed)
        self.connect("notify::default-height", self._on_window_size_changed)
        self.connect("close-request", self._on_close_request)
        self._home_path = self._system_api.get_home_dir()
        self._trash_path = self._system_api.get_trash_dir()
        self._current_path = self._home_path

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

        # Path + mode ("copy"/"cut") last sent to the clipboard via the
        # "Copy"/"Cut" context menu entries (see PathPage's on_file_copied
        # /on_file_cut), and the queue of paste jobs started from the
        # button _update_paste_button() builds below. Each queue entry is
        # (source, destination, is_cut) — is_cut picks mv vs cp for that
        # one job, since jobs already queued keep whatever mode they were
        # enqueued with even if the clipboard changes afterward.
        self._clipboard_path: str | None = None
        self._clipboard_is_cut: bool = False
        self._paste_queue: list[tuple[str, str, bool]] = []
        # Fixed-position, permanently packed placeholder — its content is
        # destroyed and rebuilt by _update_paste_button() (plain "Paste the
        # file" button, or the pending/badge button), but the slot itself
        # never moves, so it always stays right of the path entry.
        self._paste_slot = Gtk.Box()
        header_bar.pack_end(self._paste_slot)
        self._paste_badge_css = self._build_paste_badge_css_provider()

        #self._dark_mode_button = Gtk.Button()
        #self._dark_mode_button.connect("clicked", self._on_toggle_dark_mode)
        #header_bar.pack_end(self._dark_mode_button)

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
        )
        self._path_page.set_hexpand(True)

        self._trash_page = TrashPage(self._system_api)
        self._trash_page.set_hexpand(True)

        # Switched between the Miller-column browser and the flat Trash
        # list — they're different enough UI paradigms (see TrashPage)
        # that reusing PathPage's columns for the Trash wouldn't work.
        self._main_stack = Gtk.Stack()
        self._main_stack.set_hexpand(True)
        self._main_stack.add_named(self._path_page, "browser")
        self._main_stack.add_named(self._trash_page, "trash")

        body.append(sidebar_scroll)
        body.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        body.append(self._main_stack)

        toolbar_view.set_content(body)
        self.set_content(toolbar_view)

        # Header/sidebar/trash icons are baked light/dark PNGs (see
        # file_icons.py), not auto-recoloring symbolic icons — every place
        # one was built has to be rebuilt when the style flips, whether
        # from _apply_theme() below (the very first application, before
        # any of them have seen the *real* starting scheme) or later, from
        # the in-app toggle or the desktop's own scheme changing
        # underneath it. PathPage/TrashPage handle their own rows; this
        # covers what MainWindow builds directly.
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
        # Catches a resize immediately followed by closing the window —
        # otherwise that last size could still be sitting in the debounce
        # above, never written to disk.
        if self._save_window_size_source_id is not None:
            GLib.source_remove(self._save_window_size_source_id)
            self._save_window_size()
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
        """Empties _paste_slot and rebuilds a fresh button for the current
        state — a real remove-and-recreate rather than a hidden/shown
        widget, so a stale button never lingers on screen."""
        self._clear_paste_slot()

        pending_count = len(self._paste_queue)
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
        # Cleared and removed as soon as clicked — passed along explicitly
        # from here on, so self._clipboard_path can't make the button
        # reappear later (e.g. from _update_paste_button once the job
        # finishes) and can't leak into a second, unrelated paste.
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
            self._enqueue_paste(source_path, destination, is_cut)

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
            self._enqueue_paste(source_path, destination, is_cut)

        dialog.connect("response", on_response)
        dialog.present(self)

    def _enqueue_paste(self, source_path: str, destination: str, is_cut: bool):
        was_idle = not self._paste_queue
        self._paste_queue.append((source_path, destination, is_cut))
        self._update_paste_button()
        if was_idle:
            self._process_next_paste_job()

    def _process_next_paste_job(self):
        """Runs the head-of-queue copy/move in a background thread (never
        blocks the UI), same threading.Thread + GLib.idle_add handoff
        pattern as dupotEasyFlatpak's install/update jobs."""
        if not self._paste_queue:
            return
        source, destination, is_cut = self._paste_queue[0]
        threading.Thread(
            target=self._run_copy_job, args=(source, destination, is_cut), daemon=True
        ).start()

    def _run_copy_job(self, source: str, destination: str, is_cut: bool):
        # get_copy_call()/get_move_call() already go through flatpak-spawn
        # --host when running sandboxed (see SystemApi._cmd), so this
        # "mv"/"cp" runs on the host either way. communicate() (not
        # wait()) so an error message can't fill the stdout pipe buffer
        # and deadlock the job.
        call = (
            self._system_api.get_move_call(source, destination)
            if is_cut
            else self._system_api.get_copy_call(source, destination)
        )
        process = subprocess.Popen(
            call, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        output, _stdin = process.communicate()
        GLib.idle_add(
            self._on_copy_job_done,
            process.returncode,
            output.strip(),
            source,
            destination,
            is_cut,
        )

    def _on_copy_job_done(
        self, returncode: int, output: str, source: str, destination: str, is_cut: bool
    ):
        if self._paste_queue:
            self._paste_queue.pop(0)
        self._update_paste_button()
        if returncode == 0:
            self._path_page.refresh_path(os.path.dirname(destination))
            if is_cut:
                self._path_page.refresh_path(os.path.dirname(source))
        else:
            self._show_copy_error(source, output, is_cut)
        self._process_next_paste_job()
        return False

    def _show_copy_error(self, source: str, output: str, is_cut: bool):
        name = os.path.basename(source.rstrip("/"))
        body = (
            _('Could not move "{name}" to this folder.').format(name=name)
            if is_cut
            else _('Could not copy "{name}" to this folder.').format(name=name)
        )
        if output:
            body += "\n\n" + output
        heading = _("Move failed") if is_cut else _("Copy failed")
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("ok", _("OK"))
        dialog.present(self)

    def _go_to_path(self, path: str):
        """Full reset: used for sidebar navigation and the initial load,
        collapses back down to a single Miller column showing `path`."""
        self._main_stack.set_visible_child_name("browser")
        self._path_entry.set_sensitive(True)
        self._update_path_state(path)
        self._path_page.load_path(path)

    def _go_to_trash(self, _path: str):
        """Sidebar "Trash" entry: swaps the browser out for TrashPage
        instead of navigating PathPage anywhere — the Trash isn't a real,
        Miller-column-navigable folder (see TrashPage)."""
        self._main_stack.set_visible_child_name("trash")
        self._trash_page.refresh()
        self._path_entry.set_text(_("Trash"))
        self._path_entry.set_sensitive(False)
        self._up_button.set_sensitive(False)
        self._side_menu.set_selected_path(self._trash_path)

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
        #self._update_dark_mode_icon()

    def _apply_theme(self):
        style_manager = Adw.StyleManager.get_default()
        if self._settings.use_theme_dark():
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        elif self._settings.use_theme_light():
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

    #def _update_dark_mode_icon(self):
    #    is_dark = Adw.StyleManager.get_default().get_dark()
    #    self._dark_mode_button.set_child(
    #        build_icon_image("weather-clear" if is_dark else "weather-clear-night")
    #    )
    #    self._dark_mode_button.set_tooltip_text(
    #        _("Switch to light mode") if is_dark else _("Switch to dark mode")
    #    )

    def _on_menu_parameters(self, _action, _param):
        ParametersDialog(self._on_settings_saved).present(self)

    def _on_settings_saved(self):
        self._apply_theme()

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
