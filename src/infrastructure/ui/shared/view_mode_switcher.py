import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

from domain.entity.user_settings_entity import UserSettingsEntity

# GTK4 bundles these itself (confirmed present even with no host icon
# theme installed) — unlike the mimetype names in file_icons.py
# (x-office-document and friends), which is why every other icon in this
# app is a baked PNG instead of a system icon-theme lookup. Safe to use
# Gtk.Image.new_from_icon_name directly for this trio.
# Two side-by-side panes — reads as "columns" and stays visually
# distinct from Grid's 2x2 squares and Details' bulleted rows. Adwaita
# has no "view-columns-symbolic" to reach for instead (confirmed absent
# from the bundled runtime).
_COLUMNS_ICON_NAME = "view-dual-symbolic"
_GRID_ICON_NAME = "view-grid-symbolic"
_DETAILS_ICON_NAME = "view-list-bullet-symbolic"


class ViewModeSwitcher(Gtk.MenuButton):
    """Header-bar button opening a small popover to pick the browser's
    view mode (Miller columns, an icon/thumbnail grid, or a sortable
    details table — see UserSettingsEntity.view_mode) and, only relevant
    for the grid, the tile/preview size. The button's own icon always
    reflects the current mode, same idea as the paste button's icon in
    app_window.py.

    Deliberately only updates the in-memory UserSettingsEntity singleton
    and calls back into MainWindow — it doesn't touch disk or the
    browser stack itself, both of which need debouncing (a size drag
    fires many events) that belongs with the rest of app_window.py's
    debounce logic (see _on_window_size_changed)."""

    def __init__(self, settings: UserSettingsEntity, on_mode_changed, on_icon_size_changed):
        super().__init__()
        self._settings = settings
        self._on_mode_changed = on_mode_changed
        self._on_icon_size_changed = on_icon_size_changed
        self.set_tooltip_text(_("View"))
        self._update_icon()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        self._toggle_group = Adw.ToggleGroup()
        columns_toggle = Adw.Toggle()
        columns_toggle.set_name(UserSettingsEntity.VIEW_MODE_COLUMNS)
        columns_toggle.set_icon_name(_COLUMNS_ICON_NAME)
        columns_toggle.set_tooltip(_("Columns"))
        self._toggle_group.add(columns_toggle)
        grid_toggle = Adw.Toggle()
        grid_toggle.set_name(UserSettingsEntity.VIEW_MODE_GRID)
        grid_toggle.set_icon_name(_GRID_ICON_NAME)
        grid_toggle.set_tooltip(_("Grid"))
        self._toggle_group.add(grid_toggle)
        details_toggle = Adw.Toggle()
        details_toggle.set_name(UserSettingsEntity.VIEW_MODE_DETAILS)
        details_toggle.set_icon_name(_DETAILS_ICON_NAME)
        details_toggle.set_tooltip(_("Details"))
        self._toggle_group.add(details_toggle)
        self._toggle_group.set_active_name(settings.view_mode)
        self._toggle_group.connect("notify::active-name", self._on_toggle_changed)
        box.append(self._toggle_group)

        size_label = Gtk.Label(label=_("Icon size"))
        size_label.set_halign(Gtk.Align.START)
        size_label.add_css_class("dim-label")
        box.append(size_label)

        self._size_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            UserSettingsEntity.MIN_GRID_ICON_SIZE,
            UserSettingsEntity.MAX_GRID_ICON_SIZE,
            8,
        )
        self._size_scale.set_value(settings.get_grid_icon_size())
        self._size_scale.set_hexpand(True)
        self._size_scale.set_size_request(180, -1)
        self._size_scale.set_draw_value(False)
        # Only meaningful for the grid — greyed out on Columns rather
        # than hidden, so the popover's layout doesn't jump when toggling.
        self._size_scale.set_sensitive(settings.use_grid_view())
        self._size_scale.connect("value-changed", self._on_size_changed)
        box.append(self._size_scale)

        popover = Gtk.Popover()
        popover.set_child(box)
        self.set_popover(popover)

    def _update_icon(self):
        if self._settings.use_grid_view():
            icon_name = _GRID_ICON_NAME
        elif self._settings.use_details_view():
            icon_name = _DETAILS_ICON_NAME
        else:
            icon_name = _COLUMNS_ICON_NAME
        self.set_child(Gtk.Image.new_from_icon_name(icon_name))

    def _on_toggle_changed(self, toggle_group, _pspec):
        mode = toggle_group.get_active_name()
        if mode is None or mode == self._settings.view_mode:
            return
        self._settings.set_view_mode(mode)
        self._update_icon()
        self._size_scale.set_sensitive(self._settings.use_grid_view())
        self._on_mode_changed(mode)

    def _on_size_changed(self, scale):
        size = int(scale.get_value())
        self._settings.set_grid_icon_size(size)
        self._on_icon_size_changed(size)
