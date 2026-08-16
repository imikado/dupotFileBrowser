import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk


class SideMenuItem:
    def __init__(self, icon_name: str, label: str, path: str, on_activate):
        self.icon_name = icon_name
        self.label = label
        self.path = path
        self.on_activate = on_activate


class SideMenuShared(Gtk.ListBox):
    """Left navigation sidebar, mirrors the Flutter app's SideMenu widget."""

    def __init__(self):
        super().__init__()
        self.add_css_class("navigation-sidebar")
        self.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.set_vexpand(True)
        self._items: list[SideMenuItem] = []
        self.connect("row-activated", self._on_row_activated)

    def set_items(self, item_list: list[SideMenuItem]):
        self._items = item_list
        self._clear()
        for item in item_list:
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
            self.append(row)

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
