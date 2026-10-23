#!/usr/bin/env bash
# Regenerates the screenshots of export/screenshots/ and a demo GIF.
# Usage: ./generate_screenshots.sh   (inside `nix develop`, in an X11 session)
#
#   1. Builds the release binary
#   2. Creates a demo home folder (and settings) in a temporary directory, so
#      no personal file shows up
#   3. Starts the app in that environment, drives it through its D-Bus
#      actions (view mode, new tab, Parameters…) and captures the window
#   4. Assembles the captured steps into export/screenshots/demo.gif
#
# Needs: xwd, xprop, wmctrl, gdbus, ffmpeg.
# Not regenerated (they need a right-click): folder_menu.png, add_color.png,
# file_properties.png.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
ROOT="$PWD"

APP_ID="org.dupot.filebrowser"
OBJECT_PATH="/org/dupot/filebrowser/window/1"
BIN="$ROOT/target/release/dupot-file-browser"
OUT="${OUT:-$ROOT/export/screenshots}"   # overridable, to try without overwriting
WINDOW_WIDTH=1100
WINDOW_HEIGHT=680
GIF_WIDTH=900
SETTLE=1.2   # seconds left to the window to redraw after each step

for tool in xwd xprop wmctrl gdbus ffmpeg; do
    command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }
done
if [[ "${XDG_SESSION_TYPE:-x11}" == "wayland" || -z "${DISPLAY:-}" ]]; then
    echo "An X11 session is needed (xwd captures X windows)." >&2
    exit 1
fi
# A running instance would receive our requests instead of the demo one.
if gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
    --method org.freedesktop.DBus.NameHasOwner "$APP_ID" | grep -q true; then
    echo "Close the running File browser first." >&2
    exit 1
fi

echo "=== Building ==="
cargo build --release --quiet

# Short, readable paths in the path bar: /tmp/dupot-XXXX/demo/…
WORK="$(mktemp -d /tmp/dupot-XXXX)"
APP_PID=""
cleanup() {
    [[ -n "$APP_PID" ]] && kill "$APP_PID" 2>/dev/null || true
    rm -rf "$WORK"
}
trap cleanup EXIT

DEMO_HOME="$WORK/demo"
export HOME="$DEMO_HOME"
export XDG_DATA_HOME="$WORK/data"
export XDG_CONFIG_HOME="$WORK/config"
export XDG_CACHE_HOME="$WORK/cache"
SETTINGS_FILE="$XDG_DATA_HOME/$APP_ID/user_settings.json"

# --- Demo content -------------------------------------------------------

image() { # image <path> <seed>
    ffmpeg -loglevel error -f lavfi -i "gradients=s=640x420:seed=$2" -frames:v 1 "$1" \
        || ffmpeg -loglevel error -f lavfi -i "testsrc2=s=640x420" -frames:v 1 "$1"
}

create_demo_home() {
    echo "=== Creating the demo home folder ==="
    local h="$DEMO_HOME"
    mkdir -p "$h"/{Desktop,Downloads,Music,Public,Templates,Videos} \
        "$h"/Documents/Invoices/{2025,2026} \
        "$h"/Pictures/{Holidays,Screenshots} \
        "$h"/Projects/website/{assets,css,js} "$h"/Projects/game/{levels,sprites}
    echo "Meeting notes" >"$h/Documents/notes.txt"
    for f in report.pdf budget.ods presentation.odp letter.odt; do echo demo >"$h/Documents/$f"; done
    for f in invoice-01.pdf invoice-02.pdf invoice-03.pdf; do echo demo >"$h/Documents/Invoices/2026/$f"; done
    echo demo >"$h/Documents/Invoices/2025/invoice-12.pdf"
    for f in setup.tar.gz photos.zip font.ttf; do echo demo >"$h/Downloads/$f"; done
    for f in 01-intro.mp3 02-theme.mp3 03-outro.ogg; do echo demo >"$h/Music/$f"; done
    echo demo >"$h/Videos/trailer.mp4"
    echo "<!doctype html>" >"$h/Projects/website/index.html"
    echo "body {}" >"$h/Projects/website/css/style.css"
    echo "console.log()" >"$h/Projects/website/js/app.js"
    echo "# Website" >"$h/Projects/website/README.md"
    echo "#!/bin/sh" >"$h/Projects/game/run.sh" && chmod +x "$h/Projects/game/run.sh"
    local seed=1
    for name in beach mountain sunset forest city lake; do
        image "$h/Pictures/Holidays/$name.png" "$seed"
        seed=$((seed + 1))
    done
    image "$h/Pictures/Screenshots/desktop.png" 9
    image "$h/Projects/website/assets/logo.png" 11
    image "$h/Projects/website/assets/banner.png" 12
    # Color tags, in the app's own sidecar file.
    echo '{"coloredPathList":[{"name":"Projects","color":"#50c16f"},{"name":"Pictures","color":"#ff804f"},{"name":"notes.txt","color":"#5294e2"}]}' \
        >"$h/.dupotFileBrowser"
}

write_settings() { # write_settings <view mode> <theme>
    mkdir -p "$(dirname "$SETTINGS_FILE")"
    cat >"$SETTINGS_FILE" <<EOF
{
  "version": 1,
  "theme": "$2",
  "language": "english",
  "useSystemIconTheme": true,
  "windowWidth": $WINDOW_WIDTH,
  "windowHeight": $WINDOW_HEIGHT,
  "favoriteList": [
    {"label": "Documents", "path": "$DEMO_HOME/Documents"},
    {"label": "website", "path": "$DEMO_HOME/Projects/website"},
    {"label": "Holidays", "path": "$DEMO_HOME/Pictures/Holidays"}
  ],
  "displayHidden": false,
  "viewMode": "$1",
  "gridIconSize": 128,
  "singleClickOpen": false
}
EOF
}

# --- Driving the app ----------------------------------------------------

WINDOW=""

start_app() { # start_app <view mode> <theme> [folder]
    write_settings "$1" "$2"
    "$BIN" ${3:+"$3"} >/dev/null 2>&1 &
    APP_PID=$!
    WINDOW=""
    for _ in $(seq 50); do
        WINDOW="$(wmctrl -lp | awk -v pid="$APP_PID" '$3 == pid { print $1; exit }')"
        [[ -n "$WINDOW" ]] && break
        sleep 0.2
    done
    [[ -n "$WINDOW" ]] || { echo "The app window did not show up." >&2; exit 1; }
    wmctrl -i -a "$WINDOW"
    sleep "$SETTLE"
}

stop_app() {
    kill "$APP_PID" 2>/dev/null || true
    wait "$APP_PID" 2>/dev/null || true
    APP_PID=""
}

action() { # action <name> [GVariant parameter]
    gdbus call --session --dest "$APP_ID" --object-path "$OBJECT_PATH" \
        --method org.gtk.Actions.Activate "$1" "[${2:-}]" "{}" >/dev/null
    sleep "$SETTLE"
}

open_folder() { # open_folder <path>: sent to the running instance
    "$BIN" "$1" >/dev/null 2>&1
    sleep "$SETTLE"
}

# Window capture without the client-side shadow around it.
capture() { # capture <output png>
    wmctrl -i -a "$WINDOW"
    sleep 0.3
    local extents left=0 right=0 top=0 bottom=0
    extents="$(xprop -id "$WINDOW" _GTK_FRAME_EXTENTS 2>/dev/null | grep -o '[0-9, ]*$' || true)"
    if [[ -n "$extents" ]]; then
        IFS=', ' read -r left right top bottom <<<"$extents"
    fi
    xwd -silent -id "$WINDOW" -out "$WORK/capture.xwd"
    ffmpeg -loglevel error -y -i "$WORK/capture.xwd" \
        -vf "crop=iw-$left-$right:ih-$top-$bottom:$left:$top" "$1"
}

FRAMES="$WORK/frames"
FRAME_LIST="$WORK/frames.txt"
FRAME_COUNT=0

frame() { # frame <seconds shown in the GIF>
    FRAME_COUNT=$((FRAME_COUNT + 1))
    local file="$FRAMES/$(printf '%03d' "$FRAME_COUNT").png"
    capture "$file"
    printf "file '%s'\nduration %s\n" "$file" "$1" >>"$FRAME_LIST"
}

# --- Screenshots --------------------------------------------------------

take_screenshots() {
    echo "=== Screenshots ==="
    mkdir -p "$OUT"

    start_app columns light
    capture "$OUT/homepage.png"
    # Three levels: a fourth column would scroll the first one out of view.
    open_folder "$DEMO_HOME/Projects/website"
    capture "$OUT/columns_navigation.png"
    open_folder "$DEMO_HOME/Documents/Invoices"
    action focus-path
    capture "$OUT/path_editable.png"
    action parameters
    capture "$OUT/parameters.png"
    stop_app

    start_app columns dark "$DEMO_HOME/Pictures/Holidays"
    capture "$OUT/display_mode_list.png"
    stop_app

    start_app grid light "$DEMO_HOME/Pictures/Holidays"
    capture "$OUT/display_mode_icons.png"
    stop_app

    start_app details light "$DEMO_HOME/Documents"
    capture "$OUT/display_mode_details.png"
    stop_app
}

# --- Demo GIF -----------------------------------------------------------

record_demo() {
    echo "=== Demo GIF ==="
    mkdir -p "$FRAMES"
    : >"$FRAME_LIST"

    start_app columns light
    frame 2
    open_folder "$DEMO_HOME/Projects"
    frame 1
    open_folder "$DEMO_HOME/Projects/website"
    frame 1
    open_folder "$DEMO_HOME/Projects/website/assets"
    frame 2
    action view-mode "<'grid'>"
    open_folder "$DEMO_HOME/Pictures/Holidays"
    frame 2.5
    action view-mode "<'details'>"
    open_folder "$DEMO_HOME/Documents"
    frame 2.5
    action new-tab
    action view-mode "<'columns'>"
    open_folder "$DEMO_HOME/Documents/Invoices/2026"
    frame 2
    action toggle-sidebar
    frame 1.5
    action toggle-sidebar
    action about
    frame 2.5
    stop_app

    # The concat demuxer ignores the last duration unless the file repeats.
    tail -n 2 "$FRAME_LIST" | head -n 1 >>"$FRAME_LIST"
    ffmpeg -loglevel error -y -f concat -safe 0 -i "$FRAME_LIST" \
        -vf "fps=2,scale=$GIF_WIDTH:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse=dither=none:diff_mode=rectangle" \
        -loop 0 "$OUT/demo.gif"
}

create_demo_home
take_screenshots
record_demo

echo "=== Done ==="
ls -1 "$OUT"
