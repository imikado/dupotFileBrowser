import os
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from domain.entity.user_settings_entity import UserSettingsEntity
from domain.UseCase.list_directory_uc import ListDirectoryUc
from infrastructure.api.system_api import SystemApi
from infrastructure.api.user_settings_api import UserSettingsApi

COLUMN_WIDTH = 260


class _Column(Gtk.Frame):
    """A single Miller-style column: the content of one directory."""

    def __init__(self, path: str, on_row_activated, on_row_double_clicked, on_row_context_menu):
        super().__init__()
        self.path = path
        self._on_row_double_clicked = on_row_double_clicked
        self._on_row_context_menu = on_row_context_menu
        self.add_css_class("background")
        self.set_size_request(COLUMN_WIDTH, -1)
        self.set_vexpand(True)

        self._list_box = Gtk.ListBox()
        self._list_box.add_css_class("navigation-sidebar")
        self._list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list_box.set_margin_top(6)
        self._list_box.set_margin_bottom(6)
        self._list_box.connect(
            "row-activated", lambda _box, row: on_row_activated(self, row)
        )

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self._list_box)

        self._empty_label = Gtk.Label(label=_("Empty folder"))
        self._empty_label.add_css_class("dim-label")
        self._empty_label.set_valign(Gtk.Align.START)
        self._empty_label.set_margin_top(24)

        self._stack = Gtk.Stack()
        self._stack.set_vexpand(True)
        self._stack.add_named(scroll, "list")
        self._stack.add_named(self._empty_label, "empty")

        self.set_child(self._stack)

    def set_entries(self, entry_list):
        child = self._list_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._list_box.remove(child)
            child = next_child

        for entry in entry_list:
            row = Adw.ActionRow()
            row.set_title(GLib.markup_escape_text(entry.get_display_name()))
            row.set_title_lines(1)
            row.set_activatable(True)
            row.add_prefix(Gtk.Image.new_from_icon_name(entry.get_icon_name()))
            if entry.is_dir:
                row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
            row.entry = entry

            # Files only open on a double click (see PathPage._open_entry);
            # a single click just selects, like GtkListBox already does.
            left_click = Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY)
            left_click.connect("pressed", self._on_row_left_click, row)
            row.add_controller(left_click)

            right_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
            right_click.connect("pressed", self._on_row_right_click, row)
            row.add_controller(right_click)

            self._list_box.append(row)

        self._stack.set_visible_child_name("list" if entry_list else "empty")

    def _on_row_left_click(self, _gesture, n_press, _x, _y, row):
        if n_press == 2:
            self._on_row_double_clicked(self, row)

    def _on_row_right_click(self, gesture, _n_press, x, y, row):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self._on_row_context_menu(self, row, x, y)

    def select_path(self, path: str):
        row = self._list_box.get_first_child()
        while row is not None:
            entry = getattr(row, "entry", None)
            if entry is not None and entry.path == path:
                self._list_box.select_row(row)
                return
            row = row.get_next_sibling()


class PathPage(Gtk.Box):
    """Miller-column (macOS Finder-style) directory browser: clicking a
    folder keeps the column it was clicked in and opens a new column to its
    right with that folder's content. Clicking a folder in an earlier
    column drops every column to its right first (there can only be one
    folder open per column). Nothing is ever dropped from the left; the
    view instead scrolls horizontally, and going "up" past the leftmost
    column prepends its parent rather than discarding anything."""

    def __init__(
        self,
        on_path_changed,
        on_favorites_changed=lambda: None,
        on_file_copied=lambda name, path: None,
        on_file_cut=lambda name, path: None,
    ):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self._on_path_changed = on_path_changed
        self._on_favorites_changed = on_favorites_changed
        self._on_file_copied = on_file_copied
        self._on_file_cut = on_file_cut
        # Absolute path of the last file/folder sent to the clipboard via
        # the "Copy" context menu entry (not "Cut" — see _copy_to_clipboard).
        self._last_copied_path: str | None = None
        self._system_api = SystemApi()
        self._list_directory_uc = ListDirectoryUc(self._system_api)
        self._columns: list[_Column] = []

        self._columns_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_hexpand(True)
        self._scroll.set_vexpand(True)
        self._scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        # Always-visible (not fade-in-on-hover) horizontal scrollbar, since
        # it's the main way back to columns scrolled out of view.
        self._scroll.set_overlay_scrolling(False)
        self._scroll.set_child(self._columns_box)

        self.append(self._scroll)

    def load_path(self, path: str):
        """Reset the whole view to a single column showing `path`."""
        self._reset_columns()
        self._push_column(path)

    def refresh_path(self, path: str):
        """Reloads the entries of any open column showing `path` in place
        (columns/selection untouched) — used after a background paste job
        writes a new file into it."""
        for column in self._columns:
            if column.path == path:
                column.set_entries(self._list_directory_uc.get_entry_list(path))

    def load_path_chain(self, path: str):
        """Reset the whole view, rebuilding one column per path segment
        from the filesystem root down to `path`, each ancestor column
        highlighting the segment leading into the next — as if the user
        had clicked into every directory along the way one by one."""
        self._reset_columns()
        for segment_path in self._ancestor_chain(path.rstrip("/") or "/"):
            if self._columns:
                self._columns[-1].select_path(segment_path)
            self._push_column(segment_path)
        GLib.idle_add(self._scroll_to_end)

    def _reset_columns(self):
        for column in self._columns:
            self._columns_box.remove(column)
        self._columns = []

    def _ancestor_chain(self, path: str) -> list[str]:
        """Every directory from the filesystem root down to `path`
        (inclusive), root first."""
        chain = [path]
        current = path
        while True:
            parent = self._system_api.get_parent_dir(current)
            if parent == current:
                break
            chain.append(parent)
            current = parent
        chain.reverse()
        return chain

    def prepend_parent(self):
        """Reveal the enclosing folder of the leftmost column, without
        dropping any column already open.

        Returns the new leftmost path, or None if the leftmost column is
        already the filesystem root.
        """
        if not self._columns:
            return None

        leftmost_path = self._columns[0].path
        parent_path = self._system_api.get_parent_dir(leftmost_path)
        if parent_path == leftmost_path:
            return None

        column = _Column(
            parent_path,
            self._on_row_activated,
            self._on_row_double_clicked,
            self._on_row_context_menu,
        )
        column.set_entries(self._list_directory_uc.get_entry_list(parent_path))
        column.select_path(leftmost_path)
        self._columns.insert(0, column)
        self._columns_box.insert_child_after(column, None)

        self._on_path_changed(parent_path)
        GLib.idle_add(self._scroll_to_start)
        return parent_path

    def _push_column(self, path: str):
        column = _Column(
            path, self._on_row_activated, self._on_row_double_clicked, self._on_row_context_menu
        )
        column.set_entries(self._list_directory_uc.get_entry_list(path))
        self._columns.append(column)
        self._columns_box.append(column)

    def _on_row_activated(self, column: _Column, row):
        """Fires on every single click (GtkListBox's own activation).
        Only directories act on a single click, matching a normal file
        manager; a file needs a double click (_on_row_double_clicked) so a
        single click can just select it without opening anything."""
        entry = getattr(row, "entry", None)
        if entry is None or not entry.is_dir:
            return
        self._open_entry(column, row)

    def _on_row_double_clicked(self, column: _Column, row):
        entry = getattr(row, "entry", None)
        if entry is None or entry.is_dir:
            return
        self._open_entry(column, row)

    def _open_entry(self, column: _Column, row):
        entry = getattr(row, "entry", None)
        if entry is None:
            return

        index = self._columns.index(column)
        for stale in self._columns[index + 1 :]:
            self._columns_box.remove(stale)
        self._columns = self._columns[: index + 1]

        if not entry.is_dir:
            self._system_api.open_path(entry.path)
            self._on_path_changed(column.path)
            return

        self._push_column(entry.path)
        self._on_path_changed(entry.path)
        GLib.idle_add(self._scroll_to_end)

    def _scroll_to_end(self):
        adjustment = self._scroll.get_hadjustment()
        if adjustment:
            adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
        return False

    def _scroll_to_start(self):
        adjustment = self._scroll.get_hadjustment()
        if adjustment:
            adjustment.set_value(0)
        return False

    def _on_row_context_menu(self, column: _Column, row, x: float, y: float):
        entry = getattr(row, "entry", None)
        if entry is None:
            return

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.add_css_class("menu")  # Donne le style visuel d'un menu GTK

        popover = Gtk.Popover()
        popover.set_child(box)
        popover.set_parent(row)
        popover.set_pointing_to(Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1))
        popover.set_autohide(True)
        popover.connect("closed", lambda p: p.unparent())

        def make_button(label_text, callback):
            btn = Gtk.Button(label=label_text)
            btn.add_css_class("flat")
            # Gtk.Button n'a plus de set_alignment() en GTK4 : le bouton
            # étire son Label enfant sur toute sa largeur (halign FILL par
            # défaut), donc c'est ce Label qu'il faut aligner à gauche.
            btn.get_child().set_xalign(0.0)

            def _on_click(_b):
                popover.popdown()
                # On exécute l'action au tour de boucle suivant
                GLib.idle_add(callback)

            btn.connect("clicked", _on_click)
            return btn

        # Bouton "Open"
        box.append(make_button(_("Open"), lambda: self._open_entry(column, row)))

        # Bouton "Open With…" (uniquement pour les fichiers)
        if not entry.is_dir:
            box.append(
                make_button(
                    _("Open With…"), lambda: self._open_with(entry.path, row)
                )
            )

        # Bouton "Add to favorites" (uniquement pour les répertoires)
        if entry.is_dir:
            box.append(
                make_button(
                    _("Add to favorites"),
                    lambda: self._add_to_favorites(entry.name, entry.path),
                )
            )

        # Boutons "Copy" et "Cut"
        box.append(
            make_button(
                _("Copy"),
                lambda: self._copy_to_clipboard(entry.path, cut=False, name=entry.name),
            )
        )
        box.append(
            make_button(
                _("Cut"),
                lambda: self._copy_to_clipboard(entry.path, cut=True, name=entry.name),
            )
        )

        # Bouton "Rename"
        box.append(
            make_button(
                _("Rename"), lambda: self._show_rename_dialog(column, entry, row)
            )
        )

        GLib.idle_add(self._popup_deferred, popover)

    def _popup_deferred(self, popover):
        """Shows a popover on the next idle iteration instead of straight
        away. Needed whenever popup() is called synchronously from inside
        another popover's own click/close handling (e.g. a right-click
        menu item opening a follow-up popover, or the right-click gesture
        itself) — doing it immediately races that other popover's pointer
        grab/teardown and the new one ends up unresponsive."""
        popover.popup()
        return False

    def _copy_to_clipboard(self, path: str, cut: bool, name: str | None = None):
        """Puts the file/folder on the system clipboard the same way
        Nautilus/Files do, so Cut/Copy here interoperate with Paste in any
        other GTK file manager."""
        uri = self._system_api.get_uri(path)
        gnome_format = f"{'cut' if cut else 'copy'}\n{uri}\n".encode("utf-8")
        uri_list_format = f"{uri}\r\n".encode("utf-8")
        provider = Gdk.ContentProvider.new_union(
            [
                Gdk.ContentProvider.new_for_bytes(
                    "x-special/gnome-copied-files", GLib.Bytes.new(gnome_format)
                ),
                Gdk.ContentProvider.new_for_bytes(
                    "text/uri-list", GLib.Bytes.new(uri_list_format)
                ),
            ]
        )
        self.get_clipboard().set_content(provider)

        if cut:
            self._on_file_cut(name or path, path)
        else:
            self._last_copied_path = path
            self._on_file_copied(name or path, path)

    def _show_rename_dialog(
        self, column: _Column, entry, row, initial_name: str | None = None
    ):
        name_entry = Gtk.Entry()
        name_entry.set_text(initial_name or entry.name)
        name_entry.set_activates_default(True)

        dialog = Adw.AlertDialog(
            heading=_("Rename"),
            body=_('Choose a new name for "{name}".').format(name=entry.name),
        )
        dialog.set_extra_child(name_entry)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("rename", _("Rename"))
        dialog.set_default_response("rename")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)

        def on_response(_dialog, response):
            if response != "rename":
                return
            new_name = name_entry.get_text().strip()
            if not new_name or new_name == entry.name:
                return
            parent = self._system_api.get_parent_dir(entry.path)
            destination = os.path.join(parent, new_name)
            if self._system_api.file_exists(destination):
                # Still taken: ask again, keeping the attempted name so
                # the user can tweak it instead of retyping from scratch.
                GLib.idle_add(self._show_rename_dialog, column, entry, row, new_name)
                return
            self._perform_rename(column, entry, destination)

        dialog.connect("response", on_response)
        dialog.present(row.get_root())

    def _perform_rename(self, column: _Column, entry, destination: str):
        # get_move_call() goes through flatpak-spawn --host when
        # sandboxed, same as the Cut/Paste "move" job (see SystemApi._cmd).
        # A rename is a same-directory move, so it runs synchronously —
        # it's a plain filesystem rename, not a data copy.
        result = subprocess.run(
            self._system_api.get_move_call(entry.path, destination),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            self._show_rename_error(entry.name, result.stdout + result.stderr, column.get_root())
            return

        # The renamed entry's own path is now stale for any column already
        # open on it — drop those, same as _open_entry does when a row's
        # underlying folder changes.
        index = self._columns.index(column)
        for stale in self._columns[index + 1 :]:
            self._columns_box.remove(stale)
        self._columns = self._columns[: index + 1]

        self.refresh_path(column.path)
        column.select_path(destination)

    def _show_rename_error(self, name: str, output: str, root):
        body = _('Could not rename "{name}".').format(name=name)
        if output.strip():
            body += "\n\n" + output.strip()
        dialog = Adw.AlertDialog(heading=_("Rename failed"), body=body)
        dialog.add_response("ok", _("OK"))
        dialog.present(root)

    def _add_to_favorites(self, label: str, path: str):
        """Adds {label, path} to UserSettingsEntity.favorite_list and
        persists it, so it survives an app restart."""
        UserSettingsEntity().add_favorite(label, path)
        UserSettingsApi(self._system_api).save()
        self._on_favorites_changed()

    def _open_with(self, path: str, row):
        """Popover with a dropdown of every application registered for
        this file's type, the system default pre-selected, plus a way to
        browse the full application list for anything not registered."""
        content_type = self._system_api.get_content_type(path)
        app_infos = Gio.AppInfo.get_all_for_type(content_type)
        default_app = Gio.AppInfo.get_default_for_type(content_type, False)

        other_label = _("Other application…")
        names = [app.get_display_name() or app.get_name() for app in app_infos]
        names.append(other_label)

        default_index = len(app_infos) - 1 if app_infos else 0
        if default_app is not None:
            for i, app in enumerate(app_infos):
                if app.get_id() == default_app.get_id():
                    default_index = i
                    break

        dropdown = Gtk.DropDown.new_from_strings(names)
        dropdown.set_selected(max(default_index, 0))

        open_button = Gtk.Button(label=_("Open"))
        open_button.add_css_class("suggested-action")

        cancel_button = Gtk.Button(label=_("Cancel"))

        buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons_box.set_halign(Gtk.Align.END)
        buttons_box.append(cancel_button)
        buttons_box.append(open_button)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.append(dropdown)
        box.append(buttons_box)

        popover = Gtk.Popover()
        popover.set_child(box)
        popover.set_parent(row)
        popover.set_autohide(True)
        popover.connect("closed", lambda p: p.unparent())

        def on_open_clicked(_button):
            popover.popdown()
            index = dropdown.get_selected()
            if 0 <= index < len(app_infos):
                app_infos[index].launch([Gio.File.new_for_path(path)], None)
            else:
                self._open_with_dialog(path, row, content_type)

        open_button.connect("clicked", on_open_clicked)
        # Filet de sécurité explicite : même si l'autohide/Escape est
        # perturbé par le popup() différé (voir _popup_deferred), un clic
        # sur Cancel referme toujours la popover.
        cancel_button.connect("clicked", lambda _b: popover.popdown())
        # See _popup_deferred: this popover is opened from inside the
        # right-click menu's own "Open With…" item activation, so it must
        # not popup() synchronously either.
        GLib.idle_add(self._popup_deferred, popover)

    def _open_with_dialog(self, path: str, row, content_type: str):
        """Fallback full app chooser, for content types with no app
        already registered (or when the user asks for "Other application")."""
        dialog = Gtk.AppChooserDialog.new_for_content_type(
            row.get_root(), Gtk.DialogFlags.MODAL, content_type
        )
        dialog.connect("response", self._on_open_with_dialog_response, path)
        dialog.present()

    def _on_open_with_dialog_response(self, dialog, response, path: str):
        if response == Gtk.ResponseType.OK:
            app_info = dialog.get_widget().get_app_info()
            if app_info is not None:
                app_info.launch([Gio.File.new_for_path(path)], None)
        dialog.destroy()
