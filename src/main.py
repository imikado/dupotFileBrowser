#!/usr/bin/env python3

import gettext
import glob
import os
import sys


def _ensure_gvfs_metadata_discoverable():
    """Some environments (seen in at least one dev shell) don't export
    GIO_EXTRA_MODULES, so GIO's local libgio never finds the host's
    libgvfsdbus.so and silently behaves as if gvfsd-metadata doesn't
    exist — reads/writes of "metadata::*" attributes (SystemApi's
    set_folder_color/get_folder_color, for Nemo-compatible folder
    colors) then always miss, even though the daemon and its data are
    right there. Must run before the first "from gi.repository import
    Gio" anywhere (module scanning is lazy but only happens once)."""
    if os.environ.get("GIO_EXTRA_MODULES"):
        return  # already configured by the desktop session — don't override
    candidates = sorted(glob.glob("/usr/lib/*/gio/modules")) + [
        "/usr/lib64/gio/modules",
        "/usr/lib/gio/modules",
    ]
    for candidate in candidates:
        if glob.glob(os.path.join(candidate, "*gvfsdbus*")):
            os.environ["GIO_EXTRA_MODULES"] = candidate
            return


def _ensure_host_apps_discoverable():
    """Under Flatpak, GIO's app database (Gio.AppInfo.get_all_for_type,
    used by open_with_popup.py's "Open With" list) only scans
    $XDG_DATA_DIRS as the sandbox sets it up — /app/share:/usr/share,
    i.e. this Flatpak's own bundled share dir plus org.gnome.Platform's,
    neither of which has the host's actual applications/*.desktop files
    — so that list comes back near-empty even though the host has
    plenty of apps registered. "Open" itself (double-click / the
    context menu's "Open" entry) still works fine because
    Gio.AppInfo.launch_default_for_uri() (SystemApi.open_path) is
    routed through the xdg-desktop-portal instead, which isn't affected
    by this — only the *list* of choices is.

    --filesystem=host (already granted, for browsing the whole
    filesystem) bind-mounts the real host root at /run/host, so
    prepending its applications dirs to XDG_DATA_DIRS lets GIO's own
    already-correct MIME-association/default-app lookup see the host's
    apps too. Deliberately NOT touching XDG_DATA_HOME the same way:
    that's where PathConf/GLib.get_user_data_dir() stores this app's
    own settings, and Flatpak's redirect of it to the isolated
    ~/.var/app/<id>/data is the wanted behavior there (see
    SystemApi._get_real_trash_base_dir) — only the *system* dirs list
    needs widening. Must run before the first "from gi.repository
    import Gio" anywhere, same as _ensure_gvfs_metadata_discoverable
    above."""
    if not os.environ.get("FLATPAK_ID"):
        return
    host_dirs = [
        d
        for d in ("/run/host/usr/local/share", "/run/host/usr/share")
        if os.path.isdir(d)
    ]
    if not host_dirs:
        return
    existing = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    os.environ["XDG_DATA_DIRS"] = ":".join(host_dirs + [existing])


_ensure_gvfs_metadata_discoverable()
_ensure_host_apps_discoverable()

from gi.repository import GLib

from domain.conf.path_conf import PathConf
from domain.entity.user_settings_entity import UserSettingsEntity
from infrastructure.api.system_api import SystemApi
from infrastructure.ui.app_window import AppWindow

APPNAME = "dupot_file_browser"
SUPPORTED_LANGUAGE_CODES = {"en", "fr", "it"}


def main():
    localedir = os.path.join(os.path.dirname(__file__), "infrastructure", "locales")

    # GLib.get_language_names() is the reliable source for locale in
    # GTK/Flatpak apps, e.g. ['fr_FR.UTF-8', 'fr_FR', 'fr', 'C'] — gettext
    # handles the variants automatically.
    languages = [l for l in GLib.get_language_names() if l != "C"]

    # On some fresh installs the desktop session hasn't exported
    # LANG/LC_ALL into the sandbox yet, so GLib.get_language_names() comes
    # back empty/"C" even though the system is set to e.g. French. Fall
    # back to reading the raw locale env vars directly in that case.
    env_languages = [
        v
        for v in ":".join(
            os.environ.get(name, "")
            for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")
        ).split(":")
        if v and v != "C"
    ]

    system_language_code = UserSettingsEntity.LANGUAGE_EN_CODE
    for language_name in languages + env_languages:
        base = language_name.split(".")[0].split("_")[0].lower()
        if base in SUPPORTED_LANGUAGE_CODES:
            system_language_code = base
            break

    UserSettingsEntity().set_system_language_code(system_language_code)

    en_i18n = gettext.translation(
        APPNAME, localedir, languages=languages, fallback=True
    )
    en_i18n.install()

    system_api = SystemApi()
    path_conf = PathConf()
    path_conf.set_data_path(GLib.get_user_data_dir())
    system_api.create_dir(path_conf.get_data_path())

    settings = UserSettingsEntity()
    settings_path = path_conf.get_user_settings_path()

    print('load settings_path '+settings_path+' (if exist)')

    if system_api.file_exists(settings_path):
        settings.load(system_api.read_json_file_obj(settings_path))
        if settings.version != UserSettingsEntity.DEFAULT_VERSION:
            settings.reset_to_defaults()
            system_api.write_file(settings_path, settings.get_json_string())
    else:
        system_api.write_file(settings_path, settings.get_json_string())

    if settings.should_force_language():
        forced_i18n = gettext.translation(
            APPNAME, localedir, languages=[settings.get_language_code()], fallback=True
        )
        forced_i18n.install()

    app = AppWindow()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
