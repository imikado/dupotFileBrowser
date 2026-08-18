import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, GLib, Gtk

from domain.entity.user_settings_entity import UserSettingsEntity
from domain.UseCase.list_directory_uc import ListDirectoryUc
from infrastructure.api.system_api import SystemApi
from infrastructure.api.user_settings_api import UserSettingsApi
from infrastructure.ui.shared.color_picker_popup import show_color_picker_popup
from infrastructure.ui.shared.confirm_dialog import show_confirm_dialog
from infrastructure.ui.shared.context_menu_shared import ContextMenuItem, show_context_menu
from infrastructure.ui.shared.file_icons import build_icon_image, build_folder_icon_image
from infrastructure.ui.shared.open_with_popup import show_open_with_popup
from infrastructure.ui.shared.properties_dialog import show_properties_dialog
from infrastructure.ui.shared.rename_dialog import show_rename_dialog

COLUMN_WIDTH = 260
_COLOR_DOT_SIZE = 10

# Right-clicking the row that *just* opened a new column (single-click
# navigation) can catch that column's own layout/render work still in
# flight — the context menu popover then has to compete for the same
# render pipeline to become interactive, and can show too late to catch
# the very next click (measured: reliable past ~150ms of real settle
# time, well under half of that and it's a coin flip). Rather than delay
# every right-click by that much, only the ones landing on a
# just-activated row within this window get it — see _on_row_right_click.
_RECENT_ACTIVATION_WINDOW_US = 300_000
_CONTEXT_MENU_SETTLE_DELAY_MS = 150


def _build_color_dot(color: str) -> Gtk.Widget:
    """Small round swatch shown next to a *file* row tagged via the "Add
    Color" context menu entry (see PathPage._set_color). Folders instead
    get their icon itself tinted — see build_folder_icon_image — matching
    how Nemo's "Folder Color" shows up."""
    dot = Gtk.Box()
    dot.set_size_request(_COLOR_DOT_SIZE, _COLOR_DOT_SIZE)
    dot.set_valign(Gtk.Align.CENTER)

    provider = Gtk.CssProvider()
    provider.load_from_data(
        f"box {{ background: {color}; border-radius: 999px; }}".encode()
    )
    dot.get_style_context().add_provider(
        provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    return dot


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

        # (row, GLib.get_monotonic_time()) of the last single-click
        # navigation — see _on_row_right_click.
        self._last_activated_row = None
        self._last_activated_at = 0

        self._list_box = Gtk.ListBox()
        self._list_box.add_css_class("navigation-sidebar")
        self._list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list_box.set_margin_top(6)
        self._list_box.set_margin_bottom(6)
        self._list_box.connect("row-activated", self._on_list_box_row_activated)
        self._on_row_activated = on_row_activated

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

    def set_entries(self, entry_list, color_map: dict | None = None):
        color_map = color_map or {}

        child = self._list_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._list_box.remove(child)
            child = next_child

        for entry in entry_list:
            row = Adw.ActionRow()
            row.set_title(GLib.markup_escape_text(entry.get_display_name()))
            row.set_title_lines(1)
            # Titles are truncated to one line (COLUMN_WIDTH is narrow) —
            # the tooltip is the only way to read a long name in full.
            row.set_tooltip_text(entry.get_display_name())
            row.set_activatable(True)
            color = color_map.get(entry.name)
            if entry.is_dir:
                row.add_prefix(build_folder_icon_image(color))
            else:
                row.add_prefix(build_icon_image(entry.get_icon_key()))
                if color:
                    row.add_suffix(_build_color_dot(color))
            if entry.is_dir:
                row.add_suffix(build_icon_image("go-next"))
            row.entry = entry
            # Stashed so the "Add Color" popup (_on_row_context_menu) can
            # highlight this entry's current color without re-querying it.
            row.color = color

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

    def _on_list_box_row_activated(self, _box, row):
        self._last_activated_row = row
        self._last_activated_at = GLib.get_monotonic_time()
        self._on_row_activated(self, row)

    def _on_row_left_click(self, _gesture, n_press, _x, _y, row):
        if n_press == 2:
            self._on_row_double_clicked(self, row)

    def _on_row_right_click(self, gesture, _n_press, x, y, row):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        just_activated = (
            row is self._last_activated_row
            and GLib.get_monotonic_time() - self._last_activated_at
            < _RECENT_ACTIVATION_WINDOW_US
        )
        show = lambda: self._on_row_context_menu(self, row, x, y) or False
        if just_activated:
            # This row's own single-click navigation (opening a new
            # column) may still be settling — see the constants above.
            GLib.timeout_add(_CONTEXT_MENU_SETTLE_DELAY_MS, show)
        else:
            # Never build the new popover synchronously from inside this
            # gesture's own "pressed" handling (see popup_deferred: "...or
            # the right-click gesture itself"). A previous context menu
            # can still be open — same row re-right-clicked, or a stray
            # click elsewhere reopening one — and its autohide-driven
            # dismissal runs as part of delivering *this* click; building
            # a new Gtk.Popover in that same call stack, while the old
            # one's grab teardown is mid-flight, corrupted GTK's active-
            # state accounting for it ("Gtk-WARNING: Broken accounting of
            # active state for widget", seen in the Flatpak build).
            # PRIORITY_HIGH_IDLE for the same reason show_context_menu's
            # own popup_deferred call uses it.
            GLib.idle_add(show, priority=GLib.PRIORITY_HIGH_IDLE)

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

        # File-type icons are baked light/dark PNGs (see file_icons.py),
        # not auto-recoloring symbolic icons — rows built under the old
        # style need rebuilding when it flips, whether from the in-app
        # toggle or the desktop's own scheme changing underneath it.
        Adw.StyleManager.get_default().connect(
            "notify::dark", self._on_style_dark_changed
        )

    def _on_style_dark_changed(self, _style_manager, _pspec):
        for column in self._columns:
            self._set_column_entries(column, column.path)

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
                self._set_column_entries(column, path)

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
        self._set_column_entries(column, parent_path)
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
        self._set_column_entries(column, path)
        self._columns.append(column)
        self._columns_box.append(column)

    def _set_column_entries(self, column: _Column, path: str):
        entry_list = self._list_directory_uc.get_entry_list(path)
        # Files: one batched read of the parent's .dupotFileBrowser
        # sidecar. Folders: each one owns its color on itself (Nemo
        # convention — see SystemApi.get_folder_color), so it's one query
        # per subfolder, same as Nemo/Nautilus themselves do.
        color_map = self._system_api.get_colored_path_map(path)
        for entry in entry_list:
            if entry.is_dir:
                folder_color = self._system_api.get_folder_color(entry.path)
                if folder_color:
                    color_map[entry.name] = folder_color
        column.set_entries(entry_list, color_map)

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

        self._drop_stale_columns(column)

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
        item_list.append(
            ContextMenuItem(
                _("Add Color"),
                lambda: show_color_picker_popup(
                    row,
                    lambda color: self._set_color(entry, color),
                    selected_color=getattr(row, "color", None),
                ),
            )
        )
        item_list.append(
            ContextMenuItem(
                _("Properties"),
                lambda: show_properties_dialog(
                    row.get_root(), self._system_api, entry.name, entry.path, entry.is_dir
                ),
            )
        )
        item_list.append(
            ContextMenuItem(
                _("Move to Trash"),
                lambda: show_confirm_dialog(
                    row.get_root(),
                    _("Move to Trash?"),
                    _('"{name}" will be moved to the Trash.').format(name=entry.name),
                    _("Move to Trash"),
                    lambda: self._trash_entry(column, entry, row),
                ),
                css_classes=("destructive-action",),
            )
        )

        show_context_menu(row, x, y, item_list)

    def _set_color(self, entry, color: str | None):
        """Tags `entry` with `color`, or untags it if color is None (the
        "Remove Color" entry).

        Folders go through SystemApi.set_folder_color — the same GVFS
        "metadata::custom-icon" attribute Nemo's "Folder Color" writes,
        so it's read back identically by Nemo (and vice versa). Files
        have no Nemo equivalent, so they keep the .dupotFileBrowser
        sidecar (add_colored_path/remove_colored_path)."""
        parent = self._system_api.get_parent_dir(entry.path)
        if entry.is_dir:
            self._system_api.set_folder_color(entry.path, color)
        elif color is None:
            self._system_api.remove_colored_path(parent, entry.name)
        else:
            self._system_api.add_colored_path(parent, entry.name, color)
        self.refresh_path(parent)

    def _on_renamed(self, column: _Column, destination: str):
        """Called by rename_dialog once the rename actually happened on
        disk. The renamed entry's own path is now stale for any column
        already open on it — drop those, same as _open_entry does when a
        row's underlying folder changes — then refresh the parent column
        and reselect the entry under its new name."""
        self._drop_stale_columns(column)
        self.refresh_path(column.path)
        column.select_path(destination)

    def _trash_entry(self, column: _Column, entry, row):
        if not self._system_api.trash_path(entry.path):
            self._show_trash_error(entry.name, row.get_root())
            return

        # Same reasoning as _on_renamed: the entry is gone, so any column
        # already open on it (if it was a directory) is now stale.
        self._drop_stale_columns(column)
        self.refresh_path(column.path)

    def _show_trash_error(self, name: str, root):
        dialog = Adw.AlertDialog(
            heading=_("Could not move to Trash"),
            body=_('"{name}" could not be moved to the Trash.').format(name=name),
        )
        dialog.add_response("ok", _("OK"))
        dialog.present(root)

    def _drop_stale_columns(self, column: _Column):
        """Removes every column to the right of `column` — used whenever
        the entry a column's row pointed at has just been renamed, moved,
        or trashed, so a stale further column can't stay open on it."""
        index = self._columns.index(column)
        for stale in self._columns[index + 1 :]:
            self._columns_box.remove(stale)
        self._columns = self._columns[: index + 1]

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
