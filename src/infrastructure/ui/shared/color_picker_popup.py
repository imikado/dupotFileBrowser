import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from infrastructure.ui.shared.popup_shared import close_then_run, popup_deferred

SWATCH_SIZE = 28
_COLUMNS = 4

# (label, hex) — Nemo's own "Folder Color" palette (Cinnamon's Mint-Y
# icon theme variants; see SystemApi.NEMO_FOLDER_COLOR_THEMES), so a
# color picked here matches exactly what Nemo would use — same hex, same
# name — keeping folders colored from here compatible with Nemo. Labels
# stay untranslated here and only go through _() at call time in
# show_color_picker_popup: this list is built at *module import* time,
# which happens before main() installs gettext's _() as a builtin —
# translating eagerly here would raise NameError on startup.
_PALETTE = [
    ("Blue", "#5294e2"),
    ("Navy", "#004988"),
    ("Aqua", "#57b8ec"),
    ("Teal", "#45abb7"),
    ("Cyan", "#00bcd4"),
    ("Green", "#50c16f"),
    ("Sand", "#f9c470"),
    ("Grey", "#aaaaaa"),
    ("Orange", "#ff804f"),
    ("Yaru", "#ff7446"),
    ("Red", "#f54f54"),
    ("Pink", "#f26a9a"),
    ("Purple", "#a27ae4"),
]


def show_color_picker_popup(parent_widget, on_color_selected, selected_color=None):
    """A small grid popover of color swatches, with a full-width "Remove
    Color" button below it. on_color_selected(hex) is called once, right
    after the popover starts closing — with None for "Remove Color".
    selected_color, if given, is the entry's current color (its own hex
    from _PALETTE) — that swatch is drawn with a ring around it."""
    container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    container.set_margin_top(10)
    container.set_margin_bottom(10)
    container.set_margin_start(10)
    container.set_margin_end(10)

    grid = Gtk.Grid()
    grid.set_row_spacing(6)
    grid.set_column_spacing(6)
    container.append(grid)

    popover = Gtk.Popover()
    popover.set_child(container)
    popover.set_parent(parent_widget)
    popover.set_autohide(True)
    popover.connect("closed", lambda p: p.unparent())

    def _select(color):
        # See close_then_run: don't popdown() synchronously from inside
        # this swatch's own "clicked" handler (Flatpak-observed GTK
        # bookkeeping corruption that can silently drop the click).
        close_then_run(popover, lambda: on_color_selected(color))

    for index, (label, hex_color) in enumerate(_PALETTE):
        selected = bool(selected_color) and selected_color.lower() == hex_color.lower()
        swatch = _build_swatch(_(label), hex_color, selected)
        swatch.connect("clicked", lambda _b, color=hex_color: _select(color))
        grid.attach(swatch, index % _COLUMNS, index // _COLUMNS, 1, 1)

    none_button = _build_none_button()
    none_button.connect("clicked", lambda _b: _select(None))
    container.append(none_button)

    # See popup_deferred: this popover is opened from inside the
    # right-click menu's own "Add Color" item activation, so it must not
    # popup() synchronously either.
    GLib.idle_add(popup_deferred, popover, priority=GLib.PRIORITY_HIGH_IDLE)


def _build_swatch(label: str, hex_color: str, selected: bool = False) -> Gtk.Button:
    swatch = Gtk.Button()
    swatch.set_tooltip_text(label)
    swatch.add_css_class("circular")
    swatch.set_size_request(SWATCH_SIZE, SWATCH_SIZE)

    # The currently-applied color gets a ring around it: a theme-bg halo
    # so it reads against the swatch's own hue, then an accent-colored
    # outer ring so it reads against the popover background too.
    ring_css = (
        "box-shadow: 0 0 0 2px @theme_bg_color, 0 0 0 4px @accent_bg_color;"
        if selected
        else ""
    )
    provider = Gtk.CssProvider()
    provider.load_from_data(
        f"""
        button {{
            background: {hex_color};
            min-width: {SWATCH_SIZE}px;
            min-height: {SWATCH_SIZE}px;
            {ring_css}
        }}
        """.encode()
    )
    swatch.get_style_context().add_provider(
        provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    return swatch


def _build_none_button() -> Gtk.Button:
    button = Gtk.Button(label=_("Remove Color"))
    button.add_css_class("flat")
    return button
