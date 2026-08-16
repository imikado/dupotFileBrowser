import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib, Gtk


class SideMenuItem:
    def __init__(self, icon_name: str, label: str, path: str, on_activate, on_remove=None):
        self.icon_name = icon_name
        self.label = label
        self.path = path
        self.on_activate = on_activate
        # When set, right-clicking this item's row offers a "Remove" entry
        # that calls on_remove(path) — used for favorites, not for the
        # fixed entries like Home.
        self.on_remove = on_remove


class SideMenuShared(Gtk.ListBox):
    """Left navigation sidebar, mirrors the Flutter app's SideMenu widget."""

    def __init__(self):
        super().__init__()
        self.add_css_class("navigation-sidebar")
        self.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.set_vexpand(True)
        self._items: list[SideMenuItem] = []
        self.connect("row-activated", self._on_row_activated)

    def set_items(self, item_list: list):
        """`item_list` entries are SideMenuItem, or None for a visual
        separator (e.g. between Home and the favorites list)."""
        self._items = [item for item in item_list if item is not None]
        self._clear()
        for item in item_list:
            self.append(self._build_separator_row() if item is None else self._build_item_row(item))

    def _build_separator_row(self) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.set_activatable(False)
        row.set_can_focus(False)

        # Réduction de la hauteur minimale et réinitialisation complète des styles du nœud row
        provider = Gtk.CssProvider()
        provider.load_from_data(
            b"""
            row.separating-row {
                background: none;
                border: none;
                box-shadow: none;
                padding: 0px;
                margin: 0px;
                min-height: 0px;
            }
            """
        )
        row.get_style_context().add_provider(
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        row.add_css_class("separating-row")

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(6)
        separator.set_margin_bottom(6)
        separator.set_margin_start(12)
        separator.set_margin_end(12)

        row.set_child(separator)
        return row

    def _build_item_row(self, item: SideMenuItem) -> Gtk.ListBoxRow:

        row = Gtk.ListBoxRow()
        row.item = item

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.append(Gtk.Image.new_from_icon_name(item.icon_name))

        label = Gtk.Label(label=item.label)
        label.set_halign(Gtk.Align.START)
        box.append(label)

        
        row.set_child(box)

        if item.on_remove is not None:
            right_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
            right_click.connect("pressed", self._on_row_right_click, row)
            row.add_controller(right_click)

        return row

    def set_selected_path(self, path: str):
        row = self.get_first_child()
        while row is not None:
            item = getattr(row, "item", None)
            if item is not None and item.path == path:
                self.select_row(row)
                return
            row = row.get_next_sibling()
        self.unselect_all()

    def _clear(self):
        child = self.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.remove(child)
            child = next_child

    def _on_row_activated(self, _list_box, row):
        item = getattr(row, "item", None)
        if item is not None:
            item.on_activate(item.path)

    def _on_row_right_click(self, gesture, _n_press, x, y, row):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        item = getattr(row, "item", None)
        if item is None or item.on_remove is None:
            return
        self._show_remove_popover(row, item, x, y)

    def _show_remove_popover(self, row, item: SideMenuItem, x: float, y: float):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.add_css_class("menu")

        popover = Gtk.Popover()
        popover.set_child(box)
        popover.set_parent(row)
        popover.set_pointing_to(Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1))
        popover.set_autohide(True)
        popover.connect("closed", lambda p: p.unparent())

        remove_button = Gtk.Button(label=_("Remove from favorites"))
        remove_button.add_css_class("flat")
        remove_button.add_css_class("destructive-action")
        remove_button.get_child().set_xalign(0.0)

        def _on_remove_clicked(_button):
            popover.popdown()
            # Deferred to the next idle iteration, same reasoning as
            # PathPage's context menu: dropping the row's item here while
            # the popover is still closing races its pointer grab.
            GLib.idle_add(item.on_remove, item.path)

        remove_button.connect("clicked", _on_remove_clicked)
        box.append(remove_button)

        # See PathPage._popup_deferred: popping up synchronously from
        # inside the right-click's own "pressed" handler races the pointer
        # grab that same click still holds.
        GLib.idle_add(popover.popup)
