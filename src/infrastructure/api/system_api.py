import configparser
import json
import os
import shutil
import urllib.parse

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib

from domain.contract.system_api_contract import SystemApiContract
from domain.entity.file_entry_entity import FileEntryEntity
from domain.entity.trash_entry_entity import TrashEntryEntity

METADATA_FILENAME = ".dupotFileBrowser"
FIELD_COLORED_PATH_LIST = "coloredPathList"
FIELD_COLORED_PATH_NAME = "name"
FIELD_COLORED_PATH_COLOR = "color"


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

    def get_trash_dir(self) -> str:
        # Where trash_path() actually puts things — the XDG trash spec's
        # "files" subfolder for the home data dir (GLib.get_user_data_dir
        # already resolves $XDG_DATA_HOME with the right fallback).
        return os.path.join(GLib.get_user_data_dir(), "Trash", "files")

    def trash_path(self, path: str) -> bool:
        # Gio.File.trash() follows the XDG trash spec (moves into
        # ~/.local/share/Trash or the target filesystem's top-level
        # .Trash, recoverable from any Files app) rather than deleting
        # outright — no flatpak-spawn needed, it's plain GIO I/O within
        # --filesystem=home.
        try:
            return Gio.File.new_for_path(path).trash(None)
        except GLib.Error:
            return False

    def _get_trash_info_dir(self) -> str:
        return os.path.join(GLib.get_user_data_dir(), "Trash", "info")

    def list_trash(self) -> list[TrashEntryEntity]:
        # Reads Trash/files + Trash/info/*.trashinfo directly (the same
        # files trash_path() writes) rather than going through the
        # trash:// GIO URI scheme — that scheme is backed by the gvfsd
        # -trash daemon, which isn't guaranteed to be installed/running
        # (e.g. minimal distros, some sandboxes), and silently returning
        # nothing there made this page look empty even with items in it.
        entry_list = []
        try:
            with os.scandir(self.get_trash_dir()) as iterator:
                for entry in iterator:
                    original_path, deletion_date = self._read_trashinfo(entry.name)
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        is_dir = False
                    entry_list.append(
                        TrashEntryEntity(
                            trashed_path=entry.path,
                            display_name=entry.name,
                            original_path=original_path,
                            deletion_date=deletion_date,
                            is_dir=is_dir,
                        )
                    )
        except OSError:
            pass
        entry_list.sort(key=lambda entry: entry.deletion_date, reverse=True)
        return entry_list

    def _read_trashinfo(self, trashed_name: str) -> tuple[str, str]:
        info_path = os.path.join(self._get_trash_info_dir(), trashed_name + ".trashinfo")
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(info_path, encoding="utf-8")
            section = parser["Trash Info"]
            original_path = urllib.parse.unquote(section.get("Path", ""))
            deletion_date = section.get("DeletionDate", "")
        except (OSError, configparser.Error, KeyError):
            original_path, deletion_date = "", ""
        return original_path, deletion_date

    def _remove_trashinfo(self, trashed_path: str):
        name = os.path.basename(trashed_path)
        try:
            os.remove(os.path.join(self._get_trash_info_dir(), name + ".trashinfo"))
        except OSError:
            pass

    def restore_trash_entry(self, trashed_path: str, original_path: str) -> bool:
        try:
            os.makedirs(os.path.dirname(original_path), exist_ok=True)
            shutil.move(trashed_path, original_path)
        except (OSError, shutil.Error):
            return False
        self._remove_trashinfo(trashed_path)
        return True

    def delete_trash_entry(self, trashed_path: str) -> bool:
        try:
            if os.path.isdir(trashed_path) and not os.path.islink(trashed_path):
                shutil.rmtree(trashed_path)
            else:
                os.remove(trashed_path)
        except OSError:
            return False
        self._remove_trashinfo(trashed_path)
        return True

    def empty_trash(self) -> bool:
        all_deleted = True
        for entry in self.list_trash():
            if not self.delete_trash_entry(entry.trashed_path):
                all_deleted = False
        return all_deleted

    def _read_metadata(self, directory: str) -> dict:
        metadata_path = os.path.join(directory, METADATA_FILENAME)
        try:
            data = self.read_json_file_obj(metadata_path)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _without_colored_path(self, colored_path_list, name: str) -> list:
        if not isinstance(colored_path_list, list):
            return []
        return [
            item
            for item in colored_path_list
            if not isinstance(item, dict) or item.get(FIELD_COLORED_PATH_NAME) != name
        ]

    def add_colored_path(self, directory: str, name: str, color: str):
        """Tags `name` (a file/folder living in `directory`) with `color`
        by upserting it into directory/.dupotFileBrowser's
        "coloredPathList" — a small sidecar JSON file, one per directory,
        the same idea as Nautilus's per-folder metadata but private to
        this app."""
        data = self._read_metadata(directory)
        colored_path_list = self._without_colored_path(
            data.get(FIELD_COLORED_PATH_LIST, []), name
        )
        colored_path_list.append(
            {FIELD_COLORED_PATH_NAME: name, FIELD_COLORED_PATH_COLOR: color}
        )
        data[FIELD_COLORED_PATH_LIST] = colored_path_list

        metadata_path = os.path.join(directory, METADATA_FILENAME)
        self.write_file(metadata_path, json.dumps(data))

    def remove_colored_path(self, directory: str, name: str):
        """Undoes add_colored_path(directory, name, ...) — drops `name`
        from directory/.dupotFileBrowser's "coloredPathList", if present."""
        data = self._read_metadata(directory)
        original_list = data.get(FIELD_COLORED_PATH_LIST, [])
        colored_path_list = self._without_colored_path(original_list, name)
        if colored_path_list == original_list:
            return  # nothing tagged for `name`: no need to touch the file

        data[FIELD_COLORED_PATH_LIST] = colored_path_list
        metadata_path = os.path.join(directory, METADATA_FILENAME)
        self.write_file(metadata_path, json.dumps(data))

    def get_colored_path_map(self, directory: str) -> dict:
        """{entry name -> color} for every tagged entry directly inside
        `directory`, read from its .dupotFileBrowser sidecar file (see
        add_colored_path). Empty dict if there's no tag, or no such file."""
        colored_path_list = self._read_metadata(directory).get(FIELD_COLORED_PATH_LIST, [])
        if not isinstance(colored_path_list, list):
            return {}
        color_map = {}
        for item in colored_path_list:
            if not isinstance(item, dict):
                continue
            name = item.get(FIELD_COLORED_PATH_NAME)
            color = item.get(FIELD_COLORED_PATH_COLOR)
            if name and color:
                color_map[name] = color
        return color_map
