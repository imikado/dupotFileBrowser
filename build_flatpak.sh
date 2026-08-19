#!/usr/bin/env bash
# Builds this repo's own manifest (org.dupot.filebrowser.yml — sources:
# type: dir, path: ., i.e. the local working tree) into a standalone
# .flatpak bundle, for local testing/sharing without needing the local
# "filebrowser-origin" repo/remote set up on the target machine.
#
# NOT the Flathub submission — that manifest (sources: type: git, a
# tagged commit) lives in the separate imikado/flathub repo and is built
# by Flathub's own CI, not from here.
#
# flatpak-builder isn't installed natively on this machine (same as
# flathub-lint.sh's flatpak-builder-lint) — org.flatpak.Builder (the
# Flathub-maintained flatpak bundling it) is used instead.
#
# Usage: ./build_flatpak.sh [output.flatpak]

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

manifest="org.dupot.filebrowser.yml"
app_id="org.dupot.filebrowser"
build_dir="build-dir"
local_repo="repo"
output="${1:-${app_id}.flatpak}"

if ! command -v flatpak >/dev/null 2>&1; then
    echo "error: flatpak is not installed" >&2
    exit 2
fi

if [[ ! -f "$manifest" ]]; then
    echo "error: manifest not found: $manifest" >&2
    exit 2
fi

if ! flatpak info org.flatpak.Builder >/dev/null 2>&1; then
    echo "org.flatpak.Builder (flatpak-builder) not installed — installing from flathub..." >&2
    flatpak install -y flathub org.flatpak.Builder
fi

echo "=== Building $app_id from $manifest ==="
flatpak run --command=flatpak-builder org.flatpak.Builder \
    --force-clean --repo="$local_repo" "$build_dir" "$manifest"

echo "=== Bundling -> $output ==="
# --runtime-repo points the bundle at Flathub for org.gnome.Platform, so
# installing it on a machine that doesn't already have that runtime pulls
# it automatically instead of failing.
flatpak build-bundle \
    --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo \
    "$local_repo" "$output" "$app_id"

echo "Done: $output"
