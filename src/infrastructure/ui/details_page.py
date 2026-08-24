import threading
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GObject", "2.0")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Gdk, GLib, GObject, Gio, Gtk, Pango

from domain.entity.user_settings_entity import UserSettingsEntity
from domain.UseCase.list_directory_uc import ListDirectoryUc
from infrastructure.api.system_api import SystemApi
from infrastructure.api.user_settings_api import UserSettingsApi
from infrastructure.ui.shared.color_picker_popup import show_color_picker_popup
from infrastructure.ui.shared.compress_dialog import show_compress_dialog
from infrastructure.ui.shared.confirm_dialog import show_confirm_dialog
from infrastructure.ui.shared.context_menu_shared import ContextMenuItem, show_context_menu
from infrastructure.ui.shared.file_icons import ICON_DISPLAY_SIZE, build_icon_image, build_folder_icon_image
from infrastructure.ui.shared.open_with_popup import show_open_with_popup
from infrastructure.ui.shared.properties_dialog import show_properties_dialog
from infrastructure.ui.shared.rename_dialog import show_rename_dialog

# Displayed for a directory's Size cell — folder sizes aren't computed
# here (that's a full recursive tree walk, see SystemApi.get_dir_size and
# properties_dialog.py's background job for it), same "don't block a
# plain folder listing on it" choice GridPage makes for thumbnails.
_UNKNOWN_SIZE_DISPLAY = ""


class _FileRowObject(GObject.Object):
    """Gio.ListStore item wrapping one FileEntryEntity — GListModel needs
    a real GObject per row; the plain domain entity isn't one. `color` is
    stashed alongside it for the same reason GridPage's tile.color is:
    the "Add Color" popup highlights the entry's current color without
    re-querying it."""

    def __init__(self, entry, color: str | None):
        super().__init__()
        self.entry = entry
        self.color = color


class DetailsPage(Gtk.Box):
    """Single-folder sortable table — the third alternative to PathPage's
    Miller columns and GridPage's icon grid (see UserSettingsEntity.view_mode),
    for skimming a folder by name/type/size the way Dolphin's Details view
    does: click a column header to sort by it, click again to reverse.

    Same single-folder-in-place navigation as GridPage (not PathPage's
    Miller-column chain), and the same single-click-selects/double-click-
    opens activation by default — also flippable to single-click-opens
    via Parameters > "Open with a single click", same as GridPage (see
    apply_click_to_open_setting)."""

    def __init__(
        self,
        on_path_changed,
        on_favorites_changed=lambda: None,
        on_file_copied=lambda name, path: None,
        on_file_cut=lambda name, path: None,
        on_compress_requested=lambda path, destination, archive_format: None,
        on_extract_requested=lambda path: None,
    ):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._on_path_changed = on_path_changed
        self._on_favorites_changed = on_favorites_changed
        self._on_file_copied = on_file_copied
        self._on_file_cut = on_file_cut
        self._on_compress_requested = on_compress_requested
        self._on_extract_requested = on_extract_requested
        self._system_api = SystemApi()
        self._list_directory_uc = ListDirectoryUc(self._system_api)
        self._current_path: str | None = None

        self._list_store = Gio.ListStore(item_type=_FileRowObject)
        self._sort_model = Gtk.SortListModel(model=self._list_store)
        self._selection = Gtk.SingleSelection(model=self._sort_model)
        self._selection.set_autoselect(False)
        self._selection.set_can_unselect(True)

        self._column_view = Gtk.ColumnView(model=self._selection)
        self._column_view.set_show_row_separators(True)
        self._column_view.set_show_column_separators(False)
        # False (the default) is what gives us "single click selects,
        # double click/Enter activates" — see the class docstring. True
        # (Parameters > "Open with a single click") instead activates on
        # the first click.
        self._column_view.set_single_click_activate(
            UserSettingsEntity().should_open_on_single_click()
        )
        self._column_view.connect("activate", self._on_row_activated)
        # Feeds the header-click ascending/descending state back into the
        # model doing the actual sorting — standard GtkColumnView wiring.
        self._sort_model.set_sorter(self._column_view.get_sorter())

        name_column = self._build_column(
            _("Name"), self._setup_name_cell, self._bind_name_cell,
            key_func=lambda entry: entry.name.lower(),
        )
        name_column.set_expand(True)
        self._column_view.append_column(name_column)

        type_column = self._build_column(
            _("Type"), self._setup_label_cell, self._bind_type_cell,
            key_func=lambda entry: entry.get_type_label().lower(),
        )
        self._column_view.append_column(type_column)

        size_column = self._build_column(
            _("Size"), self._setup_label_cell, self._bind_size_cell,
            key_func=lambda entry: entry.size if entry.size is not None else -1,
        )
        self._column_view.append_column(size_column)

        modified_column = self._build_column(
            _("Modified"), self._setup_label_cell, self._bind_modified_cell,
            key_func=lambda entry: entry.mtime if entry.mtime is not None else -1,
        )
        self._column_view.append_column(modified_column)

        # Matches ListDirectoryUc's own default order (folders first, then
        # name) rather than leaving the table unsorted until the user
        # clicks a header.
        self._column_view.sort_by_column(name_column, Gtk.SortType.ASCENDING)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_child(self._column_view)

        self._empty_label = Gtk.Label(label=_("Empty folder"))
        self._empty_label.add_css_class("dim-label")
        self._empty_label.set_valign(Gtk.Align.START)
        self._empty_label.set_margin_top(24)

        self._stack = Gtk.Stack()
        self._stack.set_vexpand(True)
        self._stack.add_named(scroll, "details")
        self._stack.add_named(self._empty_label, "empty")
        self.append(self._stack)

        # Same reasoning as GridPage/PathPage: baked file-type icons are
        # light/dark PNGs, not auto-recoloring symbolic icons, so rows
        # built under the old style need rebuilding when it flips.
        Adw.StyleManager.get_default().connect("notify::dark", self._on_style_dark_changed)

    # --- Column plumbing ----------------------------------------------

    def _build_column(self, title, setup_cell, bind_cell, key_func) -> Gtk.ColumnViewColumn:
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", setup_cell)
        factory.connect("bind", bind_cell)
        column = Gtk.ColumnViewColumn(title=title, factory=factory)
        column.set_resizable(True)
        column.set_sorter(self._make_sorter(key_func))
        return column

    def _make_sorter(self, key_func) -> Gtk.CustomSorter:
        """Folders sort before files regardless of which column is
        clicked (same convention as ListDirectoryUc's own default sort),
        then by `key_func`'s value for that column, then by name as a
        stable tie-breaker."""

        def compare(row_a, row_b, *_args):
            entry_a, entry_b = row_a.entry, row_b.entry
            key_a = (not entry_a.is_dir, key_func(entry_a), entry_a.name.lower())
            key_b = (not entry_b.is_dir, key_func(entry_b), entry_b.name.lower())
            if key_a < key_b:
                return Gtk.Ordering.SMALLER
            if key_a > key_b:
                return Gtk.Ordering.LARGER
            return Gtk.Ordering.EQUAL

        return Gtk.CustomSorter.new(compare)

    # --- Name column (icon + label + right-click) ----------------------

    def _setup_name_cell(self, _factory, list_item):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(6)
        box.set_margin_end(6)
        icon_slot = Gtk.Box()
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(icon_slot)
        box.append(label)
        list_item.icon_slot = icon_slot
        list_item.label = label
        self._attach_context_menu(box, list_item)
        list_item.set_child(box)

    def _bind_name_cell(self, _factory, list_item):
        row = list_item.get_item()
        entry = row.entry
        child = list_item.icon_slot.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            list_item.icon_slot.remove(child)
            child = next_child
        list_item.icon_slot.append(self._build_row_icon(entry, row.color))
        list_item.label.set_label(entry.get_display_name())
        list_item.label.set_tooltip_text(entry.get_display_name())

    def _build_row_icon(self, entry, color: str | None) -> Gtk.Widget:
        if entry.is_dir:
            return build_folder_icon_image(color, size=ICON_DISPLAY_SIZE)
        return build_icon_image(entry.get_icon_key(), size=ICON_DISPLAY_SIZE)

    # --- Type / Size / Modified columns (plain label + right-click) ----

    def _setup_label_cell(self, _factory, list_item):
        label = Gtk.Label()
        label.set_xalign(0)
        label.set_margin_top(4)
        label.set_margin_bottom(4)
        label.set_margin_start(6)
        label.set_margin_end(6)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        list_item.label = label
        self._attach_context_menu(label, list_item)
        list_item.set_child(label)

    def _bind_type_cell(self, _factory, list_item):
        list_item.label.set_label(list_item.get_item().entry.get_type_label())

    def _bind_size_cell(self, _factory, list_item):
        entry = list_item.get_item().entry
        if entry.is_dir or entry.size is None:
            list_item.label.set_label(_UNKNOWN_SIZE_DISPLAY)
        else:
            list_item.label.set_label(GLib.format_size(entry.size))

    def _bind_modified_cell(self, _factory, list_item):
        entry = list_item.get_item().entry
        if entry.mtime is None:
            list_item.label.set_label(_UNKNOWN_SIZE_DISPLAY)
        else:
            list_item.label.set_label(
                datetime.fromtimestamp(entry.mtime).strftime("%Y-%m-%d %H:%M")
            )

    # --- Right-click, same context menu on every column's cell ---------

    def _attach_context_menu(self, widget: Gtk.Widget, list_item):
        right_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        right_click.connect("pressed", self._on_row_right_click, list_item)
        widget.add_controller(right_click)

    def _on_row_right_click(self, gesture, _n_press, x, y, list_item):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        row = list_item.get_item()
        if row is None:
            return
        widget = list_item.get_child()
        # Deferred for the same reason as GridPage/PathPage's own
        # right-click handling: never build a new Gtk.Popover
        # synchronously from inside this gesture's own "pressed" handler.
        show = lambda: self._show_context_menu(widget, row.entry, row.color, x, y) or False
        GLib.idle_add(show, priority=GLib.PRIORITY_HIGH_IDLE)

    # --- Public API, mirrors GridPage ----------------------------------

    def load_path(self, path: str):
        self._current_path = path
        self._reload()

    def refresh_path(self, path: str):
        """Reloads in place if `path` is the folder currently shown —
        used after a background paste job writes a new file into it,
        same contract as GridPage/PathPage.refresh_path."""
        if path == self._current_path:
            self._reload()

    def refresh_hidden_files(self):
        self._reload()

    def apply_click_to_open_setting(self):
        """Re-reads UserSettingsEntity.single_click_open and applies it to
        the column view live — called after Parameters is saved, no
        reload needed since it's just a widget property, not entry data."""
        self._column_view.set_single_click_activate(
            UserSettingsEntity().should_open_on_single_click()
        )

    def _on_style_dark_changed(self, _style_manager, _pspec):
        self._reload()

    def _reload(self):
        if self._current_path is None:
            return
        entry_list = self._list_directory_uc.get_entry_list(
            self._current_path, UserSettingsEntity().should_display_hidden()
        )
        # Same batched-sidecar-plus-per-folder-attribute approach as
        # GridPage._reload — see its comment for why.
        color_map = self._system_api.get_colored_path_map(self._current_path)
        for entry in entry_list:
            if entry.is_dir:
                folder_color = self._system_api.get_folder_color(entry.path)
                if folder_color:
                    color_map[entry.name] = folder_color

        self._list_store.remove_all()
        for entry in entry_list:
            self._list_store.append(_FileRowObject(entry, color_map.get(entry.name)))

        self._stack.set_visible_child_name("details" if entry_list else "empty")

    def _on_row_activated(self, _column_view, position: int):
        row = self._selection.get_item(position)
        if row is not None:
            self._open_entry(row.entry)

    def _open_entry(self, entry):
        if entry.is_dir:
            self.load_path(entry.path)
            self._on_path_changed(entry.path)
        else:
            self._system_api.open_path(entry.path)

    # --- Context menu, same item set as GridPage's -----------------------

    def _show_context_menu(self, anchor: Gtk.Widget, entry, color: str | None, x: float, y: float):
        item_list = [ContextMenuItem(_("Open"), lambda: self._open_entry(entry))]

        if not entry.is_dir:
            item_list.append(
                ContextMenuItem(
                    _("Open With…"),
                    lambda: show_open_with_popup(anchor, entry.path, self._system_api),
                )
            )

        if not entry.is_dir and entry.get_icon_key() == "image":
            item_list.append(
                ContextMenuItem(
                    _("Use as Wallpaper"),
                    lambda: self._set_wallpaper(entry.path, anchor.get_root()),
                )
            )

        if not entry.is_dir and entry.is_extractable_archive():
            item_list.append(
                ContextMenuItem(
                    _("Extract"),
                    lambda: self._on_extract_requested(entry.path),
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
                    _("Compress…"),
                    lambda: show_compress_dialog(
                        anchor.get_root(),
                        self._system_api,
                        entry.name,
                        entry.path,
                        self._on_compress_requested,
                    ),
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
            ContextMenuItem(_("Copy Path"), lambda: self._copy_path_to_clipboard(entry.path))
        )
        item_list.append(
            ContextMenuItem(
                _("Open Terminal Here"),
                lambda: self._open_terminal(entry.path, anchor.get_root()),
            )
        )
        item_list.append(
            ContextMenuItem(
                _("Rename"),
                lambda: show_rename_dialog(
                    anchor.get_root(),
                    self._system_api,
                    entry.name,
                    entry.path,
                    lambda _destination: self._reload(),
                ),
            )
        )
        item_list.append(
            ContextMenuItem(
                _("Add Color"),
                lambda: show_color_picker_popup(
                    anchor,
                    lambda picked_color: self._set_color(entry, picked_color),
                    selected_color=color,
                ),
            )
        )
        item_list.append(
            ContextMenuItem(
                _("Properties"),
                lambda: show_properties_dialog(
                    anchor.get_root(), self._system_api, entry.name, entry.path, entry.is_dir
                ),
            )
        )
        item_list.append(
            ContextMenuItem(
                _("Move to Trash"),
                lambda: show_confirm_dialog(
                    anchor.get_root(),
                    _("Move to Trash?"),
                    _('"{name}" will be moved to the Trash.').format(name=entry.name),
                    _("Move to Trash"),
                    lambda: self._trash_entry(entry, anchor.get_root()),
                ),
                css_classes=("destructive-action",),
            )
        )

        show_context_menu(anchor, x, y, item_list)

    def _set_color(self, entry, color: str | None):
        parent = self._system_api.get_parent_dir(entry.path)
        if entry.is_dir:
            self._system_api.set_folder_color(entry.path, color)
        elif color is None:
            self._system_api.remove_colored_path(parent, entry.name)
        else:
            self._system_api.add_colored_path(parent, entry.name, color)
        self.refresh_path(parent)

    def _trash_entry(self, entry, root):
        if not self._system_api.trash_path(entry.path):
            self._show_trash_error(entry.name, root)
            return
        self._reload()

    def _show_trash_error(self, name: str, root):
        dialog = Adw.AlertDialog(
            heading=_("Could not move to Trash"),
            body=_('"{name}" could not be moved to the Trash.').format(name=name),
        )
        dialog.add_response("ok", _("OK"))
        dialog.present(root)

    def _copy_to_clipboard(self, path: str, cut: bool, name: str | None = None):
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
            self._on_file_copied(name or path, path)

    def _copy_path_to_clipboard(self, path: str):
        self.get_clipboard().set_content(
            Gdk.ContentProvider.new_for_bytes(
                "text/plain;charset=utf-8", GLib.Bytes.new(path.encode("utf-8"))
            )
        )

    def _open_terminal(self, path: str, root):
        if not self._system_api.open_terminal(path):
            self._show_no_terminal_error(root)

    def _show_no_terminal_error(self, root):
        dialog = Adw.AlertDialog(
            heading=_("No terminal found"),
            body=_("No terminal emulator could be found on this system."),
        )
        dialog.add_response("ok", _("OK"))
        dialog.present(root)

    def _set_wallpaper(self, path: str, root):
        def run():
            success = self._system_api.set_wallpaper(path)
            GLib.idle_add(self._on_wallpaper_set, success, root)

        threading.Thread(target=run, daemon=True).start()

    def _on_wallpaper_set(self, success: bool, root):
        if not success:
            self._show_wallpaper_error(root)
        return GLib.SOURCE_REMOVE

    def _show_wallpaper_error(self, root):
        dialog = Adw.AlertDialog(
            heading=_("Could not set wallpaper"),
            body=_("No supported desktop environment setting could be found."),
        )
        dialog.add_response("ok", _("OK"))
        dialog.present(root)

    def _add_to_favorites(self, label: str, path: str):
        UserSettingsEntity().add_favorite(label, path)
        UserSettingsApi(self._system_api).save()
        self._on_favorites_changed()
