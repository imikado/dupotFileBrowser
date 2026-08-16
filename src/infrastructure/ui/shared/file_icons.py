import gi

gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "4.0")

import cairo
from gi.repository import Adw, Gdk, GdkPixbuf, Gtk

from domain.conf.path_conf import PathConf

# Baked, not looked up: every icon in the app (file types, folders, and
# header-bar/sidebar/action icons alike) comes from our own
# assets/icons/{light,dark}/<key>.png instead of a GTK icon-theme name.
# A host's icon theme is exactly the "surprise depending on where it's
# installed" this replaced — a Flatpak's bundled Adwaita, or a distro
# with a slim/alternate theme, may not carry every name (mimetype ones
# like x-office-* especially), leaving the row/button with no icon at
# all. See FileEntryEntity.get_icon_key() for the extension -> key
# mapping; other keys (e.g. "go-up", "user-home") are just the old
# icon-theme name with the "-symbolic" suffix dropped.
ICON_DISPLAY_SIZE = 16
_FOLDER_ICON_KEY = "folder"

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


def _build_image(texture: Gdk.Texture) -> Gtk.Widget:
    image = Gtk.Image.new_from_paintable(texture)
    image.set_size_request(ICON_DISPLAY_SIZE, ICON_DISPLAY_SIZE)
    return image


def build_icon_image(icon_key: str) -> Gtk.Widget:
    """A fixed-size Gtk.Image for `icon_key`, using whichever of the two
    shipped variants matches the app's current light/dark style. Used for
    plain single-tone icons — file types, and header-bar/sidebar/action
    icons alike; see build_folder_icon_image for the one icon that also
    needs an arbitrary runtime tint."""
    dark = Adw.StyleManager.get_default().get_dark()
    return _build_image(_get_texture(icon_key, dark))


def build_folder_icon_image(color: str | None) -> Gtk.Widget:
    """The folder icon, recolored to `color` if a Nemo "Folder Color" tag
    is set on it — otherwise the plain light/dark folder icon, same as
    build_file_icon_image."""
    if color:
        return _build_image(_get_tinted_texture(_FOLDER_ICON_KEY, color))
    dark = Adw.StyleManager.get_default().get_dark()
    return _build_image(_get_texture(_FOLDER_ICON_KEY, dark))
