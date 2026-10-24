#!/usr/bin/env bash
# Rebuilds the snap, installs it locally (with its Trash and color-tags
# interfaces connected) and starts it, for testing each change.
#
# Usage: ./test_snap.sh [--no-run]
#   --no-run  build and install only

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

snap_name="dupot-file-browser"

case "${1:-}" in
    --no-run | "") ;;
    *)
        echo "error: unknown option $1" >&2
        exit 2
        ;;
esac

./build_snap.sh --install

if [[ "${1:-}" != "--no-run" ]]; then
    echo "=== Running $snap_name ==="
    exec "/snap/bin/$snap_name"
fi
