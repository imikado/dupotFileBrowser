import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib, Gtk

from infrastructure.ui.shared.popup_shared import popup_deferred

# Generous per-row padding so the *entire* row is clickable, not just the
# label text — a tight hit box is what made an imprecise click land on
# dead space around the word instead of the button, which Gtk.Popover's
# autohide then reads as "clicked outside" and closes without running
# anything (see show_context_menu). "menu-item-button" is scoped to just
# these buttons so it can't affect flat buttons elsewhere in the app.
_ROW_CSS = b"""
button.menu-item-button {
    padding: 8px 16px;
    min-width: 160px;
}
"""


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

    css_provider = Gtk.CssProvider()
    css_provider.load_from_data(_ROW_CSS)

    popover = Gtk.Popover()
    popover.set_child(box)
    popover.set_parent(parent_widget)
    popover.set_pointing_to(Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1))
    popover.set_autohide(True)
    popover.connect("closed", lambda p: p.unparent())

    def make_button(item: ContextMenuItem) -> Gtk.Button:
        btn = Gtk.Button(label=item.label)
        btn.add_css_class("flat")
        btn.add_css_class("menu-item-button")
        btn.get_style_context().add_provider(
            css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        for css_class in item.css_classes:
            btn.add_css_class(css_class)
        # Gtk.Button n'a plus de set_alignment() en GTK4 : le bouton
        # étire son Label enfant sur toute sa largeur (halign FILL par
        # défaut), donc c'est ce Label qu'il faut aligner à gauche.
        btn.get_child().set_xalign(0.0)
        # Belt-and-braces on top of the CSS padding above: without an
        # explicit hexpand, a themed button can end up only as wide as its
        # label, leaving a dead strip to its right inside the row — a
        # click there falls through to the popover's own background and,
        # once past the popover's edge, to autohide (closes, no action).
        btn.set_hexpand(True)

        def _on_click(_b):
            # Wait for the popover to actually finish closing — its real
            # "closed" signal, not just calling popdown() — before running
            # the action. on_click often opens its own follow-up popup
            # (Add Color, Open With…); firing it after a fixed one-tick
            # GLib.idle_add instead of this signal raced this popover's
            # own close animation/pointer-grab teardown, which could still
            # be in flight past that one tick — the new popup would then
            # open while the old grab hadn't been released yet and end up
            # not showing at all (see popup_deferred, same root cause).
            popover.connect("closed", lambda _p: item.on_click())
            popover.popdown()

        btn.connect("clicked", _on_click)
        return btn

    for item in item_list:
        box.append(make_button(item))

    GLib.idle_add(popup_deferred, popover, priority=GLib.PRIORITY_HIGH_IDLE)
    return popover
