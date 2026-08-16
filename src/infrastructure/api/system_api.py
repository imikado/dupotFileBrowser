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

    def is_dir(self, path: str) -> bool:
        return os.path.isdir(path)

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

    def get_uri(self, path: str) -> str:
        return Gio.File.new_for_path(path).get_uri()

    def get_content_type(self, path: str) -> str:
        try:
            info = Gio.File.new_for_path(path).query_info(
                "standard::content-type", Gio.FileQueryInfoFlags.NONE, None
            )
            return info.get_content_type() or "application/octet-stream"
        except GLib.Error:
            return "application/octet-stream"

    def is_running_flatpak(self) -> bool:
        return bool(os.environ.get("FLATPAK_ID"))

    def _cmd(self, *args) -> list:
        # Inside the Flatpak sandbox, host binaries aren't on PATH and
        # can't be exec'd directly — flatpak-spawn --host runs them on the
        # host instead (needs --talk-name=org.freedesktop.Flatpak in the
        # manifest). Same mechanism as dupotEasyFlatpak's FlatpakApi._cmd.
        prefix = ["flatpak-spawn", "--host"] if self.is_running_flatpak() else []
        return prefix + list(args)

    def get_copy_call(self, source: str, destination: str) -> list:
        # `cp -a` (not shutil) so it runs as a real subprocess we can
        # background via threading + flatpak-spawn, and preserves
        # timestamps/permissions like the host's file manager would.
        return self._cmd("cp", "-a", "--", source, destination)

    def get_move_call(self, source: str, destination: str) -> list:
        return self._cmd("mv", "--", source, destination)
