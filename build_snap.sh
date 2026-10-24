#!/usr/bin/env bash
# Builds export/snap/snapcraft.yaml into
# export/snap/<name>_<version>_<arch>.snap, for testing/sharing, or
# publishes it to the Snap Store.
#
# snapcraft only finds its recipe at the project root, in snap/ or in
# build-aux/snap/ (and in LXD mode sees nothing outside the project): the
# recipe is copied to ./.snapcraft.yaml for the build, then removed.
#
# snapcraft builds inside an LXD container (Ubuntu 26.04 for core26),
# so the host only needs snapd + LXD.
#
# Usage: ./build_snap.sh [--install | --publish [channel]]
#   --install            also install the built snap locally (unsigned,
#                        --dangerous) and connect the Trash and color-tags
#                        interfaces
#   --publish [channel]  upload it to the Snap Store and release it on
#                        `channel` (default: edge); needs `snapcraft login`
#                        and the `dupot-file-browser` name registered
#                        (`snapcraft register dupot-file-browser`)

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

snap_name="dupot-file-browser"
# Passed to the app at launch (--packaging) by export/snap/launcher.sh:
# snapcraft builds in LXD and gets no variable from this script, so the
# launcher holds the value; checked here so that both stay in sync.
packaging="snap"
output_dir="export/snap"
recipe="$output_dir/snapcraft.yaml"
launcher="$output_dir/launcher.sh"
build_recipe=".snapcraft.yaml"

if ! command -v snapcraft >/dev/null 2>&1; then
    echo "error: snapcraft is not installed (sudo snap install snapcraft --classic)" >&2
    exit 2
fi

if ! command -v lxd >/dev/null 2>&1; then
    echo "error: LXD is not installed (sudo snap install lxd && sudo lxd init --auto)" >&2
    exit 2
fi

if [[ ! -f Cargo.lock ]]; then
    echo "error: Cargo.lock missing (the build runs cargo --locked)" >&2
    exit 2
fi

if ! grep -q -- "--packaging=$packaging" "$launcher"; then
    echo "error: $launcher must start the app with --packaging=$packaging" >&2
    exit 2
fi

if [[ -e snap/snapcraft.yaml || -e snapcraft.yaml ]]; then
    echo "error: another snapcraft.yaml exists (snap/ or project root); the recipe lives in $recipe" >&2
    exit 2
fi

echo "=== Building $snap_name ==="
cp "$recipe" "$build_recipe"
trap 'rm -f "$build_recipe"' EXIT
# snapcraft writes the .snap in the project root: moved next to the
# Flatpak bundle's export/flatpak/ afterwards.
snapcraft pack --use-lxd

version="$(grep -m1 -oP '^version = "\K[^"]+' Cargo.toml)"
built="$(ls -t "${snap_name}_${version}"_*.snap | head -n1)"
mkdir -p "$output_dir"
snap_file="$output_dir/$built"
mv -f "$built" "$snap_file"
echo "Done: $snap_file"

case "${1:-}" in
    --install)
        echo "=== Installing $snap_file ==="
        sudo snap install --dangerous "$snap_file"
        sudo snap connect "$snap_name:trash" || true
        sudo snap connect "$snap_name:color-tags" || true
        echo "Run it with: $snap_name"
        ;;
    --publish)
        channel="${2:-edge}"
        echo "=== Publishing $snap_file to $channel ==="
        snapcraft upload --release="$channel" "$snap_file"
        ;;
    "") ;;
    *)
        echo "error: unknown option $1" >&2
        exit 2
        ;;
esac
