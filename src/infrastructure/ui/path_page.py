import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, GLib, Gtk

from domain.entity.user_settings_entity import UserSettingsEntity
from domain.UseCase.list_directory_uc import ListDirectoryUc
from infrastructure.api.system_api import SystemApi
from infrastructure.api.user_settings_api import UserSettingsApi
from infrastructure.ui.shared.context_menu_shared import ContextMenuItem, show_context_menu
from infrastructure.ui.shared.open_with_popup import show_open_with_popup
from infrastructure.ui.shared.rename_dialog import show_rename_dialog

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

        item_list = [ContextMenuItem(_("Open"), lambda: self._open_entry(column, row))]

        if not entry.is_dir:
            item_list.append(
                ContextMenuItem(
                    _("Open With…"),
                    lambda: show_open_with_popup(row, entry.path, self._system_api),
                )
            )

        if entry.is_dir:
            item_list.append(
                ContextMenuItem(
                    _("Add to favorites"),
                    lambda: self._add_to_favorites(entry.name, entry.path),
                )
            )

        item_list.append(
            ContextMenuItem(
                _("Copy"),
                lambda: self._copy_to_clipboard(entry.path, cut=False, name=entry.name),
            )
        )
        item_list.append(
            ContextMenuItem(
                _("Cut"),
                lambda: self._copy_to_clipboard(entry.path, cut=True, name=entry.name),
            )
        )
        item_list.append(
            ContextMenuItem(
                _("Rename"),
                lambda: show_rename_dialog(
                    row.get_root(),
                    self._system_api,
                    entry.name,
                    entry.path,
                    lambda destination: self._on_renamed(column, destination),
                ),
            )
        )

        show_context_menu(row, x, y, item_list)

    def _on_renamed(self, column: _Column, destination: str):
        """Called by rename_dialog once the rename actually happened on
        disk. The renamed entry's own path is now stale for any column
        already open on it — drop those, same as _open_entry does when a
        row's underlying folder changes — then refresh the parent column
        and reselect the entry under its new name."""
        index = self._columns.index(column)
        for stale in self._columns[index + 1 :]:
            self._columns_box.remove(stale)
        self._columns = self._columns[: index + 1]

        self.refresh_path(column.path)
        column.select_path(destination)

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

    def _add_to_favorites(self, label: str, path: str):
        """Adds {label, path} to UserSettingsEntity.favorite_list and
        persists it, so it survives an app restart."""
        UserSettingsEntity().add_favorite(label, path)
        UserSettingsApi(self._system_api).save()
        self._on_favorites_changed()
