import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk, Pango

from domain.entity.user_settings_entity import UserSettingsEntity
from domain.UseCase.list_directory_uc import ListDirectoryUc
from infrastructure.api.system_api import SystemApi
from infrastructure.api.user_settings_api import UserSettingsApi
from infrastructure.ui.shared.color_picker_popup import show_color_picker_popup
from infrastructure.ui.shared.compress_dialog import show_compress_dialog
from infrastructure.ui.shared.confirm_dialog import show_confirm_dialog
from infrastructure.ui.shared.context_menu_shared import ContextMenuItem, show_context_menu
from infrastructure.ui.shared.file_icons import build_icon_image, build_folder_icon_image
from infrastructure.ui.shared.open_with_popup import show_open_with_popup
from infrastructure.ui.shared.properties_dialog import show_properties_dialog
from infrastructure.ui.shared.rename_dialog import show_rename_dialog

_TILE_PADDING = 24
_LABEL_LINES = 2


class GridPage(Gtk.Box):
    """Single-folder icon/thumbnail grid — the alternative to PathPage's
    Miller columns (see UserSettingsEntity.view_mode), better suited to
    skimming a folder of images than a narrow column of names. Unlike
    PathPage there's only ever one folder on screen at a time: opening a
    subfolder replaces the grid in place rather than pushing a new
    column, closer to Nautilus/Files' icon view than macOS Finder's
    column view.

    Both single-click-selects/double-click-opens for every entry
    (Gtk.FlowBox's own activation) by default, not PathPage's single-
    click-opens-folders convention — that asymmetry exists there
    specifically to make Miller-column chains feel fluid, which doesn't
    apply to a plain grid replacing itself in place. Parameters >
    "Open with a single click" (UserSettingsEntity.single_click_open)
    can flip this to single-click-opens instead — see
    apply_click_to_open_setting."""

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
        self._icon_size = UserSettingsEntity().get_grid_icon_size()

        self._flow_box = Gtk.FlowBox()
        self._flow_box.set_valign(Gtk.Align.START)
        self._flow_box.set_homogeneous(True)
        self._flow_box.set_min_children_per_line(1)
        self._flow_box.set_max_children_per_line(1000)  # wrap purely by available width
        self._flow_box.set_row_spacing(12)
        self._flow_box.set_column_spacing(12)
        self._flow_box.set_margin_top(12)
        self._flow_box.set_margin_bottom(12)
        self._flow_box.set_margin_start(12)
        self._flow_box.set_margin_end(12)
        self._flow_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        # False (the default) is what gives us "single click selects,
        # double click/Enter activates" — see the class docstring. True
        # (Parameters > "Open with a single click") instead activates
        # (and, per GtkFlowBox, also selects) on the first click.
        self._flow_box.set_activate_on_single_click(
            UserSettingsEntity().should_open_on_single_click()
        )
        self._flow_box.connect("child-activated", self._on_child_activated)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self._flow_box)

        self._empty_label = Gtk.Label(label=_("Empty folder"))
        self._empty_label.add_css_class("dim-label")
        self._empty_label.set_valign(Gtk.Align.START)
        self._empty_label.set_margin_top(24)

        self._stack = Gtk.Stack()
        self._stack.set_vexpand(True)
        self._stack.add_named(scroll, "grid")
        self._stack.add_named(self._empty_label, "empty")
        self.append(self._stack)

        # Same reasoning as PathPage: baked file-type icons are light/dark
        # PNGs, not auto-recoloring symbolic icons, so tiles built under
        # the old style need rebuilding when it flips.
        Adw.StyleManager.get_default().connect("notify::dark", self._on_style_dark_changed)

    def _on_style_dark_changed(self, _style_manager, _pspec):
        self._reload()

    def load_path(self, path: str):
        self._current_path = path
        self._reload()

    def refresh_path(self, path: str):
        """Reloads in place if `path` is the folder currently shown —
        used after a background paste job writes a new file into it,
        same contract as PathPage.refresh_path."""
        if path == self._current_path:
            self._reload()

    def refresh_hidden_files(self):
        self._reload()

    def set_icon_size(self, size: int):
        self._icon_size = size
        self._reload()

    def apply_click_to_open_setting(self):
        """Re-reads UserSettingsEntity.single_click_open and applies it to
        the flow box live — called after Parameters is saved, no reload
        needed since it's just a widget property, not entry data."""
        self._flow_box.set_activate_on_single_click(
            UserSettingsEntity().should_open_on_single_click()
        )

    def _reload(self):
        if self._current_path is None:
            return
        entry_list = self._list_directory_uc.get_entry_list(
            self._current_path, UserSettingsEntity().should_display_hidden()
        )
        # Same batched-sidecar-plus-per-folder-attribute approach as
        # PathPage._set_column_entries — see its comment for why.
        color_map = self._system_api.get_colored_path_map(self._current_path)
        for entry in entry_list:
            if entry.is_dir:
                folder_color = self._system_api.get_folder_color(entry.path)
                if folder_color:
                    color_map[entry.name] = folder_color

        child = self._flow_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._flow_box.remove(child)
            child = next_child

        for entry in entry_list:
            self._flow_box.append(self._build_tile(entry, color_map.get(entry.name)))

        self._stack.set_visible_child_name("grid" if entry_list else "empty")

    def _build_tile(self, entry, color: str | None) -> Gtk.FlowBoxChild:
        tile = Gtk.FlowBoxChild()
        tile.entry = entry
        # Stashed so the "Add Color" popup can highlight this entry's
        # current color without re-querying it — same idea as PathPage's
        # row.color.
        tile.color = color

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_size_request(self._icon_size + _TILE_PADDING, -1)

        icon_widget = self._build_tile_icon(entry, color)
        icon_widget.set_halign(Gtk.Align.CENTER)
        box.append(icon_widget)

        label = Gtk.Label(label=entry.get_display_name())
        label.set_justify(Gtk.Justification.CENTER)
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_lines(_LABEL_LINES)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(1)  # forces wrapping to box width instead of natural text width
        label.set_tooltip_text(entry.get_display_name())
        box.append(label)

        tile.set_child(box)

        right_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        right_click.connect("pressed", self._on_tile_right_click, tile)
        tile.add_controller(right_click)

        return tile

    def _build_tile_icon(self, entry, color: str | None) -> Gtk.Widget:
        if entry.is_dir:
            return build_folder_icon_image(color, size=self._icon_size)
        # get_icon_key()'s extension map is the app's one existing notion
        # of "this file is an image" (see PathPage's wallpaper entry) —
        # reused here to decide when a real thumbnail is worth decoding.
        if entry.get_icon_key() == "image":
            thumbnail = self._build_thumbnail(entry.path)
            if thumbnail is not None:
                return thumbnail
        return build_icon_image(entry.get_icon_key(), size=self._icon_size)

    def _build_thumbnail(self, path: str) -> Gtk.Widget | None:
        """A real preview of the image file, scaled to the current icon
        size — decoded straight from disk at that target size (not full
        resolution then downscaled), so a large photo doesn't cost more
        than the grid actually needs. None on any decode failure (a
        corrupt file, or a format GdkPixbuf doesn't support), so the
        caller can fall back to the generic "image" icon instead of
        leaving the tile blank."""
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                path, self._icon_size, self._icon_size, True
            )
        except GLib.Error:
            return None
        image = Gtk.Image.new_from_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
        image.set_size_request(self._icon_size, self._icon_size)
        # set_pixel_size is what actually makes Gtk.Image render the
        # texture at this size — size_request alone is just a layout
        # minimum (see file_icons.py's _build_image for the same fix,
        # confirmed empirically both places).
        image.set_pixel_size(self._icon_size)
        return image

    def _on_child_activated(self, _flow_box, child):
        entry = getattr(child, "entry", None)
        if entry is not None:
            self._open_entry(entry)

    def _open_entry(self, entry):
        if entry.is_dir:
            self.load_path(entry.path)
            self._on_path_changed(entry.path)
        else:
            self._system_api.open_path(entry.path)

    def _on_tile_right_click(self, gesture, _n_press, x, y, tile):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        entry = getattr(tile, "entry", None)
        if entry is None:
            return
        # Deferred for the same reason as PathPage's own right-click
        # handling (see popup_deferred): never build a new Gtk.Popover
        # synchronously from inside this gesture's own "pressed" handler.
        show = lambda: self._show_context_menu(tile, entry, x, y) or False
        GLib.idle_add(show, priority=GLib.PRIORITY_HIGH_IDLE)

    def _show_context_menu(self, tile: Gtk.FlowBoxChild, entry, x: float, y: float):
        item_list = [ContextMenuItem(_("Open"), lambda: self._open_entry(entry))]

        if not entry.is_dir:
            item_list.append(
                ContextMenuItem(
                    _("Open With…"),
                    lambda: show_open_with_popup(tile, entry.path, self._system_api),
                )
            )

        if not entry.is_dir and entry.get_icon_key() == "image":
            item_list.append(
                ContextMenuItem(
                    _("Use as Wallpaper"),
                    lambda: self._set_wallpaper(entry.path, tile.get_root()),
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
                        tile.get_root(),
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
                lambda: self._open_terminal(entry.path, tile.get_root()),
            )
        )
        item_list.append(
            ContextMenuItem(
                _("Rename"),
                lambda: show_rename_dialog(
                    tile.get_root(),
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
                    tile,
                    lambda color: self._set_color(entry, color),
                    selected_color=getattr(tile, "color", None),
                ),
            )
        )
        item_list.append(
            ContextMenuItem(
                _("Properties"),
                lambda: show_properties_dialog(
                    tile.get_root(), self._system_api, entry.name, entry.path, entry.is_dir
                ),
            )
        )
        item_list.append(
            ContextMenuItem(
                _("Move to Trash"),
                lambda: show_confirm_dialog(
                    tile.get_root(),
                    _("Move to Trash?"),
                    _('"{name}" will be moved to the Trash.').format(name=entry.name),
                    _("Move to Trash"),
                    lambda: self._trash_entry(entry, tile.get_root()),
                ),
                css_classes=("destructive-action",),
            )
        )

        show_context_menu(tile, x, y, item_list)

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
