import json
import os

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib

from domain.contract.system_api_contract import SystemApiContract
from domain.entity.file_entry_entity import FileEntryEntity


class SystemApi(SystemApiContract):

    def file_exists(self, path: str) -> bool:
        return os.path.exists(path)

    def read_json_file_obj(self, path: str) -> object:
        with open(path, "r") as file:
            return json.load(file)

    def write_file(self, path: str, content: str):
        with open(path, "w") as file:
            file.write(content)

    def create_dir(self, path: str):
        os.makedirs(path, exist_ok=True)

    def list_dir(self, path: str) -> list[FileEntryEntity]:
        entry_list = []
        try:
            with os.scandir(path) as iterator:
                for entry in iterator:
                    try:
                        is_dir = entry.is_dir(follow_symlinks=True)
                    except OSError:
                        is_dir = False
                    entry_list.append(FileEntryEntity(entry.name, entry.path, is_dir))
        except OSError:
            pass
        return entry_list

    def get_home_dir(self) -> str:
        return os.environ.get("HOME") or os.path.expanduser("~")

    def get_parent_dir(self, path: str) -> str:
        parent = os.path.dirname(path.rstrip("/"))
        return parent or "/"

    def open_path(self, path: str) -> bool:
        # Goes through the xdg-desktop-portal (Gio.AppInfo) rather than
        # spawning `xdg-open` directly, so it also works from inside the
        # Flatpak sandbox where no host binaries are on PATH.
        try:
            uri = Gio.File.new_for_path(path).get_uri()
            return Gio.AppInfo.launch_default_for_uri(uri, None)
        except GLib.Error:
            return False
