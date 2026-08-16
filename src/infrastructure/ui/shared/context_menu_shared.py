import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib, Gtk

from infrastructure.ui.shared.popup_shared import popup_deferred


class ContextMenuItem:
    """One row of show_context_menu(): a label, the action it runs, and
    optional extra CSS classes (e.g. "destructive-action" for a
    delete/remove entry)."""

    def __init__(self, label: str, on_click, css_classes: tuple = ()):
        self.label = label
        self.on_click = on_click
        self.css_classes = css_classes


def show_context_menu(parent_widget, x: float, y: float, item_list: list[ContextMenuItem]):
    """A small popover of flat, left-aligned buttons pointing at (x, y) on
    parent_widget — this app's stand-in for a Gio.Menu-based
    Gtk.PopoverMenu (see popup_deferred: clicks inside a GtkPopoverMenu
    built from a Gio.Menu don't reliably register right after the
    right-click that opens it)."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    box.add_css_class("menu")  # Donne le style visuel d'un menu GTK

    popover = Gtk.Popover()
    popover.set_child(box)
    popover.set_parent(parent_widget)
    popover.set_pointing_to(Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1))
    popover.set_autohide(True)
    popover.connect("closed", lambda p: p.unparent())

    def make_button(item: ContextMenuItem) -> Gtk.Button:
        btn = Gtk.Button(label=item.label)
        btn.add_css_class("flat")
        for css_class in item.css_classes:
            btn.add_css_class(css_class)
        # Gtk.Button n'a plus de set_alignment() en GTK4 : le bouton
        # étire son Label enfant sur toute sa largeur (halign FILL par
        # défaut), donc c'est ce Label qu'il faut aligner à gauche.
        btn.get_child().set_xalign(0.0)

        def _on_click(_b):
            popover.popdown()
            # On exécute l'action au tour de boucle suivant
            GLib.idle_add(item.on_click)

        btn.connect("clicked", _on_click)
        return btn

    for item in item_list:
        box.append(make_button(item))

    GLib.idle_add(popup_deferred, popover)
    return popover
