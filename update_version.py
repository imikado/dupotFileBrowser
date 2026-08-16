#!/usr/bin/env python3
"""Sync app_window.py's APP_VERSION with appdata.xml's version of record.

appdata.xml (export/flatpak/org.dupot.filebrowser.appdata.xml) is what
Flatpak/appstream actually show the user, and each release() bump belongs
there first — see org.dupot.filebrowser.appdata.xml's <releases>, newest
first. APP_VERSION in app_window.py (shown in the "About" dialog) is a
separate hardcoded copy that has to be kept in sync by hand, and it's
already drifted from appdata.xml once. This script closes that loop:
read the first (= latest) <release version="..."> entry and write it
into APP_VERSION, instead of editing both by hand.

Usage: ./update_version.py
"""

import pathlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT_DIR = pathlib.Path(__file__).parent
APPDATA_PATH = ROOT_DIR / "export" / "flatpak" / "org.dupot.filebrowser.appdata.xml"
APP_WINDOW_PATH = ROOT_DIR / "src" / "infrastructure" / "ui" / "app_window.py"

_APP_VERSION_RE = re.compile(r'^(APP_VERSION\s*=\s*)"([^"]*)"', re.MULTILINE)


def get_latest_version(appdata_path: pathlib.Path) -> str:
    root = ET.parse(appdata_path).getroot()
    # <releases> lists newest first (AppStream convention) — the first
    # <release> child is "the" current version.
    release = root.find("releases/release")
    if release is None:
        raise SystemExit(f"No <release> entry found in {appdata_path}")
    version = release.get("version")
    if not version:
        raise SystemExit(f"<release> in {appdata_path} has no version attribute")
    return version


def set_app_version(app_window_path: pathlib.Path, version: str) -> str | None:
    """Rewrites APP_VERSION in app_window_path to `version`. Returns the
    previous value, or None if it was already up to date."""
    text = app_window_path.read_text(encoding="utf-8")
    match = _APP_VERSION_RE.search(text)
    if match is None:
        raise SystemExit(f"No APP_VERSION assignment found in {app_window_path}")

    previous = match.group(2)
    if previous == version:
        return None

    new_text = _APP_VERSION_RE.sub(rf'\g<1>"{version}"', text, count=1)
    app_window_path.write_text(new_text, encoding="utf-8")
    return previous


def main() -> int:
    version = get_latest_version(APPDATA_PATH)
    previous = set_app_version(APP_WINDOW_PATH, version)
    if previous is None:
        print(f"APP_VERSION already up to date ({version})")
    else:
        print(f"APP_VERSION: {previous} -> {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
