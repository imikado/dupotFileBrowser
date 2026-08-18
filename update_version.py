#!/usr/bin/env python3
"""Sync app_window.py's APP_VERSION with appdata.xml's version of record,
and optionally cut the release for it.

appdata.xml (export/flatpak/org.dupot.filebrowser.appdata.xml) is what
Flatpak/appstream actually show the user, and each release() bump belongs
there first — see org.dupot.filebrowser.appdata.xml's <releases>, newest
first. APP_VERSION in app_window.py (shown in the "About" dialog) is a
separate hardcoded copy that has to be kept in sync by hand, and it's
already drifted from appdata.xml once. This script closes that loop:
read the first (= latest) <release version="..."> entry and write it
into APP_VERSION, instead of editing both by hand.

Usage:
    ./update_version.py             # sync APP_VERSION only
    ./update_version.py --release   # sync, then tag the current commit
                                     # with that version and push the tag
                                     # to origin (the release itself — no
                                     # separate GitHub Release step, this
                                     # env has no `gh`)
"""

import argparse
import pathlib
import re
import subprocess
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


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT_DIR, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def create_release(version: str) -> None:
    """Tags the current commit with `version` (bare, e.g. "1.0.12" — same
    convention as the existing "1.0.0" tag, no "v" prefix) and pushes the
    tag to origin."""
    if _git("status", "--porcelain"):
        raise SystemExit(
            "Working tree has uncommitted changes — commit them (including "
            "any APP_VERSION sync above) before tagging a release."
        )
    if _git("tag", "-l", version):
        raise SystemExit(f"Tag {version} already exists — nothing to do.")
    _git("tag", "-a", version, "-m", f"Release {version}")
    _git("push", "origin", version)
    print(f"Tagged and pushed release {version}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--release",
        action="store_true",
        help="Also tag the current commit with the version and push the tag to origin.",
    )
    args = parser.parse_args()

    version = get_latest_version(APPDATA_PATH)
    previous = set_app_version(APP_WINDOW_PATH, version)
    if previous is None:
        print(f"APP_VERSION already up to date ({version})")
    else:
        print(f"APP_VERSION: {previous} -> {version}")

    if args.release:
        create_release(version)

    return 0


if __name__ == "__main__":
    sys.exit(main())
