#!/bin/sh
# Runtime environment for the self-contained GTK4/libadwaita stack staged
# in this snap (see snapcraft.yaml), then starts the app.
arch="$SNAP_LAUNCHER_ARCH_TRIPLET"
[ -n "$arch" ] || arch="$(ls "$SNAP/usr/lib" | grep -- '-linux-gnu$' | head -n1)"

export LD_LIBRARY_PATH="$SNAP/usr/lib/$arch:$SNAP/lib/$arch${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export XDG_DATA_DIRS="$SNAP/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
export GSETTINGS_SCHEMA_DIR="$SNAP/usr/share/glib-2.0/schemas"
export GDK_PIXBUF_MODULE_FILE="$SNAP/usr/lib/$arch/gdk-pixbuf-2.0/2.10.0/loaders.cache"
export FONTCONFIG_FILE="$SNAP/etc/fonts/fonts.conf"
export XDG_CACHE_HOME="$SNAP_USER_COMMON/.cache"
# No GPU drivers in the snap: software rendering, without probing GL first.
export GSK_RENDERER=cairo
mkdir -p "$XDG_CACHE_HOME"

# Tells the app it runs confined in a snap (portal for "Open With", …).
exec "$SNAP/bin/dupot-file-browser" --packaging=snap "$@"
