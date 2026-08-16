#!/usr/bin/env python3

import gettext
import os
import sys

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
