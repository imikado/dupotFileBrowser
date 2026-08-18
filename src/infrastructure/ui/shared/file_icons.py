import gi

gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "4.0")

import cairo
from gi.repository import Adw, Gdk, GdkPixbuf, Gtk

from domain.conf.path_conf import PathConf
from domain.entity.user_settings_entity import UserSettingsEntity

# Baked by default, not looked up: every icon in the app (file types,
# folders, and header-bar/sidebar/action icons alike) comes from our own
# assets/icons/{light,dark}/<key>.png instead of a GTK icon-theme name.
# A host's icon theme is exactly the "surprise depending on where it's
# installed" this replaced — a Flatpak's bundled Adwaita, or a distro
# with a slim/alternate theme, may not carry every name (mimetype ones
# like x-office-* especially), leaving the row/button with no icon at
# all. See FileEntryEntity.get_icon_key() for the extension -> key
# mapping; other keys (e.g. "go-up", "user-home") are just the old
# icon-theme name with the "-symbolic" suffix dropped.
#
# Parameters > Appearance has an opt-in "use system icon theme" switch
# (UserSettingsEntity.use_system_icon_theme) for people who want the same
# file-type icons their file manager (Nemo, Nautilus, ...) shows. It only
# applies to the keys in _SYSTEM_ICON_NAME_MAP below — chrome icons like
# "go-up" stay baked regardless — and only when the current icon theme
# actually has that name (see _lookup_system_icon); anything missing
# falls back to the baked PNG, so turning the switch on can never leave a
# row with no icon at all.
ICON_DISPLAY_SIZE = 16
_FOLDER_ICON_KEY = "folder"

# icon_key -> freedesktop icon-naming-spec name, tried when the "use
# system icon theme" switch is on. Deliberately a small, fixed set —
# every icon_key FileEntryEntity/TrashEntryEntity can hand to
# build_icon_image/build_folder_icon_image.
_SYSTEM_ICON_NAME_MAP = {
    "image": "image-x-generic",
    "audio": "audio-x-generic",
    "video": "video-x-generic",
    "archive": "package-x-generic",
    "document": "x-office-document",
    "spreadsheet": "x-office-spreadsheet",
    "presentation": "x-office-presentation",
    "font": "font-x-generic",
    "executable": "application-x-executable",
    "generic": "text-x-generic",
    _FOLDER_ICON_KEY: "folder",
}

# icon_key -> Gtk.IconPaintable, or None if the current icon theme doesn't
# have that name — remembered so a miss isn't re-probed on every row.
# Not keyed by theme name: a live theme switch is rare enough that a
# restart (see ParametersDialog) is an acceptable way to pick it up,
# same as the language setting.
_system_icon_cache: dict[str, Gtk.IconPaintable | None] = {}

# (icon_key, dark) -> Gdk.Texture, built once and reused across rows —
# Gdk.Texture is an immutable paintable, safe to share unlike Gtk.Widget.
_texture_cache: dict[tuple[str, bool], Gdk.Texture] = {}

# (icon_key, hex_color) -> Gdk.Texture, for Nemo-style colored folders —
# same silhouette, recolored at runtime (see _load_pixbuf/_tint_pixbuf)
# since a baked PNG can't take an arbitrary user-picked color the way a
# real symbolic icon-name image can via CSS "color".
_tinted_texture_cache: dict[tuple[str, str], Gdk.Texture] = {}


def _load_pixbuf(icon_key: str, dark: bool) -> GdkPixbuf.Pixbuf:
    path = PathConf().get_asset_file_icon_path(icon_key, dark)
    return GdkPixbuf.Pixbuf.new_from_file_at_size(
        path, ICON_DISPLAY_SIZE, ICON_DISPLAY_SIZE
    )


def _get_texture(icon_key: str, dark: bool) -> Gdk.Texture:
    cache_key = (icon_key, dark)
    texture = _texture_cache.get(cache_key)
    if texture is None:
        texture = Gdk.Texture.new_for_pixbuf(_load_pixbuf(icon_key, dark))
        _texture_cache[cache_key] = texture
    return texture


def _tint_pixbuf(pixbuf: GdkPixbuf.Pixbuf, hex_color: str) -> GdkPixbuf.Pixbuf:
    """Flat-fills `pixbuf`'s silhouette (its alpha channel) with
    `hex_color`, discarding whatever ink color it was baked with —
    Cairo's "in" operator keeps the destination's alpha but replaces its
    color with the new source, which is exactly a recolor here since the
    icon is a single opaque shape on a transparent background."""
    width, height = pixbuf.get_width(), pixbuf.get_height()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    ctx = cairo.Context(surface)
    Gdk.cairo_set_source_pixbuf(ctx, pixbuf, 0, 0)
    ctx.paint()
    ctx.set_operator(cairo.OPERATOR_IN)
    red, green, blue = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    ctx.set_source_rgba(red, green, blue, 1)
    ctx.rectangle(0, 0, width, height)
    ctx.fill()
    return Gdk.pixbuf_get_from_surface(surface, 0, 0, width, height)


def _get_tinted_texture(icon_key: str, hex_color: str) -> Gdk.Texture:
    cache_key = (icon_key, hex_color)
    texture = _tinted_texture_cache.get(cache_key)
    if texture is None:
        # Either variant's silhouette works as the tint source — light
        # and dark only differ in baked-in ink color, not shape.
        pixbuf = _tint_pixbuf(_load_pixbuf(icon_key, dark=False), hex_color)
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        _tinted_texture_cache[cache_key] = texture
    return texture


def _lookup_system_icon(icon_key: str) -> Gtk.IconPaintable | None:
    """The host icon theme's take on `icon_key`, or None if it doesn't
    have that name (or there's no display to ask). Only called when the
    "use system icon theme" switch is on."""
    if icon_key in _system_icon_cache:
        return _system_icon_cache[icon_key]
    icon_name = _SYSTEM_ICON_NAME_MAP.get(icon_key)
    paintable = None
    display = Gdk.Display.get_default()
    if icon_name is not None and display is not None:
        icon_theme = Gtk.IconTheme.get_for_display(display)
        if icon_theme.has_icon(icon_name):
            paintable = icon_theme.lookup_icon(
                icon_name,
                [],
                ICON_DISPLAY_SIZE,
                1,
                Gtk.TextDirection.NONE,
                Gtk.IconLookupFlags.FORCE_REGULAR,
            )
    _system_icon_cache[icon_key] = paintable
    return paintable


def _build_image(paintable: Gdk.Paintable) -> Gtk.Widget:
    image = Gtk.Image.new_from_paintable(paintable)
    image.set_size_request(ICON_DISPLAY_SIZE, ICON_DISPLAY_SIZE)
    return image


def build_icon_image(icon_key: str) -> Gtk.Widget:
    """A fixed-size Gtk.Image for `icon_key`. Uses the host icon theme's
    icon when the user opted into that (see module docstring) and it has
    one; otherwise whichever of the two shipped variants matches the
    app's current light/dark style. Used for plain single-tone icons —
    file types, and header-bar/sidebar/action icons alike; see
    build_folder_icon_image for the one icon that also needs an
    arbitrary runtime tint."""
    if UserSettingsEntity().use_system_icon_theme:
        system_paintable = _lookup_system_icon(icon_key)
        if system_paintable is not None:
            return _build_image(system_paintable)
    dark = Adw.StyleManager.get_default().get_dark()
    return _build_image(_get_texture(icon_key, dark))


def build_folder_icon_image(color: str | None) -> Gtk.Widget:
    """The folder icon, recolored to `color` if a Nemo "Folder Color" tag
    is set on it — otherwise the plain light/dark folder icon, same as
    build_file_icon_image. A colored tag always wins over the system
    theme: recoloring an arbitrary system folder icon isn't supported,
    only our own baked one (see _tint_pixbuf)."""
    if color:
        return _build_image(_get_tinted_texture(_FOLDER_ICON_KEY, color))
    if UserSettingsEntity().use_system_icon_theme:
        system_paintable = _lookup_system_icon(_FOLDER_ICON_KEY)
        if system_paintable is not None:
            return _build_image(system_paintable)
    dark = Adw.StyleManager.get_default().get_dark()
    return _build_image(_get_texture(_FOLDER_ICON_KEY, dark))
