#!/usr/bin/env bash
# Refreshes the translation catalogs of dupot_file_browser.
# Usage: ./generate_translations.sh   (inside `nix develop`: needs gettext >= 0.24)
#
#   1. Extract every tr("…") / trf("…") string from the Rust sources → po/dupot_file_browser.pot
#   2. Add the strings the domain passes as values (po/dynamic_hints.pot)
#   3. Merge the template into each po/<lang>.po
#
# The .po files are embedded in the binary and read at startup: no .mo to compile.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

DOMAIN="dupot_file_browser"
POT_FILE="po/$DOMAIN.pot"
LANGUAGES=(en fr it)

echo "=== Extracting strings from Rust sources ==="
find src -name "*.rs" | sort | xgettext \
    --language=Rust \
    --keyword=tr \
    --keyword=trf \
    --from-code=UTF-8 \
    --output="$POT_FILE" \
    --package-name="$DOMAIN" \
    --files-from=-
msgcat --use-first "$POT_FILE" po/dynamic_hints.pot -o "$POT_FILE"
echo "  → $POT_FILE"

for LANG in "${LANGUAGES[@]}"; do
    PO_FILE="po/$LANG.po"
    echo "=== [$LANG] ==="
    if [ -f "$PO_FILE" ]; then
        msgmerge --update --no-fuzzy-matching --backup=none "$PO_FILE" "$POT_FILE"
    else
        msginit --input="$POT_FILE" --locale="$LANG" --output="$PO_FILE" --no-translator
    fi
done

echo "Done. Run 'cargo test' to check every string is translated."
