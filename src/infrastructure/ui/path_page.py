import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk

from domain.UseCase.list_directory_uc import ListDirectoryUc
from infrastructure.api.system_api import SystemApi

COLUMN_WIDTH = 260


class _Column(Gtk.Frame):
    """A single Miller-style column: the content of one directory."""

    def __init__(self, path: str, on_row_activated):
        super().__init__()
        self.path = path
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
            self._list_box.append(row)

        self._stack.set_visible_child_name("list" if entry_list else "empty")

    def clear_selection(self):
        self._list_box.unselect_all()


class PathPage(Gtk.Box):
    """Miller-column (macOS Finder-style) directory browser: clicking a
    folder keeps the column it was clicked in and opens a new column to its
    right with that folder's content. Clicking a folder in an earlier
    column drops every column to its right first."""

    def __init__(self, on_path_changed):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self._on_path_changed = on_path_changed
        self._system_api = SystemApi()
        self._list_directory_uc = ListDirectoryUc(self._system_api)
        self._columns: list[_Column] = []

        self._columns_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_hexpand(True)
        self._scroll.set_vexpand(True)
        self._scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self._scroll.set_child(self._columns_box)

        self.append(self._scroll)

    def load_path(self, path: str):
        """Reset the whole view to a single column showing `path`."""
        for column in self._columns:
            self._columns_box.remove(column)
        self._columns = []
        self._push_column(path)

    def pop_column(self):
        """Drop the rightmost column, if more than one is open.

        Returns the path now at the deepest (rightmost) level, or None if
        there was only one column left to begin with.
        """
        if len(self._columns) <= 1:
            return None
        removed = self._columns.pop()
        self._columns_box.remove(removed)
        self._columns[-1].clear_selection()
        deepest_path = self._columns[-1].path
        self._on_path_changed(deepest_path)
        return deepest_path

    def _push_column(self, path: str):
        column = _Column(path, self._on_row_activated)
        column.set_entries(self._list_directory_uc.get_entry_list(path))
        self._columns.append(column)
        self._columns_box.append(column)

    def _on_row_activated(self, column: _Column, row):
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
