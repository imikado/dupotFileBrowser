import configparser
import grp
import json
import os
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import urllib.parse
from datetime import datetime

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib

from domain.contract.system_api_contract import SystemApiContract
from domain.entity.file_entry_entity import FileEntryEntity
from domain.entity.file_properties_entity import FilePropertiesEntity
from domain.entity.trash_entry_entity import TrashEntryEntity

METADATA_FILENAME = ".dupotFileBrowser"
FIELD_COLORED_PATH_LIST = "coloredPathList"
FIELD_COLORED_PATH_NAME = "name"
FIELD_COLORED_PATH_COLOR = "color"

# Mirrors /usr/share/folder-color-switcher/colors.d/Mint-Y.json — the
# exact palette Cinnamon/Nemo's "Folder Color" context menu entry uses on
# Linux Mint (the active icon theme is "Mint-Y" + a colored variant, e.g.
# "Mint-Y-Teal"). Folders colored here read back identically in Nemo (and
# vice versa) since both write the same GIO "metadata::custom-icon"
# attribute — see set_folder_color/get_folder_color.
NEMO_FOLDER_COLOR_THEMES = {
    "#5294e2": "Mint-Y-Blue",
    "#004988": "Mint-Y-Navy",
    "#57b8ec": "Mint-Y-Aqua",
    "#45abb7": "Mint-Y-Teal",
    "#00bcd4": "Mint-Y-Cyan",
    "#50c16f": "Mint-Y",  # "Green" is Mint-Y's own default, no suffix
    "#f9c470": "Mint-Y-Sand",
    "#aaaaaa": "Mint-Y-Grey",
    "#ff804f": "Mint-Y-Orange",
    "#ff7446": "Mint-Y-Yaru",
    "#f54f54": "Mint-Y-Red",
    "#f26a9a": "Mint-Y-Pink",
    "#a27ae4": "Mint-Y-Purple",
}
_NEMO_THEME_TO_COLOR = {theme: hex_color for hex_color, theme in NEMO_FOLDER_COLOR_THEMES.items()}
_NEMO_ICON_SIZE = 48
_NEMO_CUSTOM_ICON_ATTRIBUTE = "metadata::custom-icon"
_NEMO_ICON_URI_RE = re.compile(r"/(Mint-Y(?:-[A-Za-z]+)?)/places/\d+(?:@2x)?/folder[^/]*\.png$")

# Probed in order by open_terminal until one is found on the host — there
# is no portal/AppInfo API for "the user's terminal" the way OpenURI covers
# "the user's file handler" (see open_path). xdg-terminal-exec comes first:
# it's the freedesktop spec's own dispatcher to whatever terminal the
# desktop environment is actually configured to use, present on any
# reasonably current distro; the rest is a plain fallback list of specific
# emulators for systems that don't have it.
_TERMINAL_CANDIDATE_LIST = [
    "xdg-terminal-exec",
    "x-terminal-emulator",
    "gnome-terminal",
    "ptyxis",
    "kgx",
    "konsole",
    "xfce4-terminal",
    "mate-terminal",
    "tilix",
    "terminator",
    "alacritty",
    "kitty",
    "lxterminal",
    "deepin-terminal",
    "xterm",
]

# binary -> extra argv (after the binary itself) to make it start in a
# given directory, with "{directory}" filled in by _terminal_argv. Only
# covers emulators whose flag is actually documented; anything missing
# here (xdg-terminal-exec, xterm) falls back to a plain `cd && exec` in
# _terminal_argv, which for those two is not a guess but the correct way
# to do it — see open_terminal's docstring for why that fallback would be
# wrong for everything listed below.
#
# x-terminal-emulator is deliberately NOT here despite resolving to a
# real emulator: on Debian/Ubuntu it's an update-alternatives symlink to
# a *wrapper script* that only understands classic xterm-style options
# (-e, -T, -geometry...) and silently drops anything else — confirmed
# empirically: --working-directory reached the real gnome-terminal
# unchanged as a plain argv element the wrapper doesn't recognize, and
# gnome-terminal itself just as silently ignores an option it doesn't
# know, so the new window opened wherever gnome-terminal's already-
# running background server happened to start rather than `directory`.
# It gets the same "-e sh -c" treatment as xterm/xdg-terminal-exec in
# _terminal_argv instead — the one interface Debian Policy §11.8.3
# guarantees every x-terminal-emulator alternative implements.
_TERMINAL_FLAG_MAP = {
    "gnome-terminal": ["--working-directory={directory}"],
    "ptyxis": ["--working-directory={directory}"],
    "kgx": ["--working-directory={directory}"],
    "konsole": ["--workdir", "{directory}"],
    "xfce4-terminal": ["--working-directory={directory}"],
    "mate-terminal": ["--working-directory={directory}"],
    "tilix": ["--working-directory={directory}"],
    "terminator": ["--working-directory={directory}"],
    "alacritty": ["--working-directory", "{directory}"],
    "kitty": ["--directory", "{directory}"],
    "lxterminal": ["--working-directory={directory}"],
}


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
                    # Cheap here — os.scandir's DirEntry caches this stat
                    # call on most platforms — unlike a directory's total
                    # size, which needs a full tree walk (see
                    # get_dir_size) and stays an explicit, on-demand-only
                    # call instead of something every listing pays for.
                    size = None
                    mtime = None
                    try:
                        stat_result = entry.stat(follow_symlinks=True)
                        mtime = stat_result.st_mtime
                        if not is_dir:
                            size = stat_result.st_size
                    except OSError:
                        pass
                    entry_list.append(
                        FileEntryEntity(entry.name, entry.path, is_dir, size, mtime)
                    )
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

    def open_with_chooser(self, path: str) -> bool:
        """Asks the xdg-desktop-portal to show its native "Open With"
        chooser for `path`, listing whatever apps are registered for it
        — always asking, never silently launching the default.

        Only meaningful under Flatpak (see open_with_popup.py's use of
        this): natively, Gio.AppInfo.get_all_for_type() already lists
        every registered app directly, no portal needed. Under Flatpak
        that same call comes back with next to nothing — not an
        XDG_DATA_DIRS visibility problem (--filesystem=host does put
        the host's applications/*.desktop files within reach), but a
        deliberate GIO/Flatpak security boundary: confirmed empirically
        that Gio.DesktopAppInfo.new_from_filename() returns NULL for
        ~97% of a real host's *.desktop files when called from inside
        the sandbox, host system files included, so there's no local
        API that can list them. The portal is the sanctioned way
        around that — its chooser dialog runs outside the sandbox, with
        the host's real app list, and launches the pick itself.

        OpenFile (not OpenURI) takes an open fd rather than a path/URI:
        the portal reads the file itself to resolve its type, so this
        works even for a path the portal process couldn't otherwise
        resolve from inside our sandboxed view of the filesystem."""
        try:
            fd = os.open(path, os.O_RDONLY)
        except OSError:
            return False
        try:
            fd_list = Gio.UnixFDList.new()
            index = fd_list.append(fd)
        finally:
            os.close(fd)  # appended fd is dup()'d; our copy is done with

        parameters = GLib.Variant(
            "(sha{sv})", ("", index, {"ask": GLib.Variant("b", True)})
        )
        try:
            Gio.bus_get_sync(Gio.BusType.SESSION, None).call_with_unix_fd_list_sync(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.OpenURI",
                "OpenFile",
                parameters,
                GLib.VariantType.new("(o)"),
                Gio.DBusCallFlags.NONE,
                -1,
                fd_list,
                None,
            )
            return True
        except GLib.Error:
            return False

    def open_terminal(self, path: str) -> bool:
        """Opens a terminal emulator in `path` (its parent directory, if
        `path` is a file) — mirrors "Open Terminal Here" in Nemo/
        Nautilus/Files. Under Flatpak the terminal has to be launched on
        the host via flatpak-spawn (--talk-name=org.freedesktop.Flatpak,
        see org.dupot.filebrowser.yml) since none of _TERMINAL_CANDIDATE_
        LIST is inside the org.gnome.Platform runtime; natively it's run
        directly.

        Each candidate gets its own explicit "open in this directory"
        flag (see _terminal_argv) rather than a plain `cd DIR && exec
        binary` — most of these (gnome-terminal, xfce4-terminal,
        konsole...) are single-instance apps whose CLI invocation is just
        a client that asks an already-running background server to open
        a new window/tab; the server does that using *its own* working
        directory, not the short-lived client's, so `cd`-ing before exec
        silently opens the new terminal wherever the server happened to
        start (confirmed empirically: a plain exec'd gnome-terminal
        landed in the server's launch directory, not the one requested
        here)."""
        directory = path if self.is_dir(path) else self.get_parent_dir(path)
        if not self.is_dir(directory):
            return False

        for binary in _TERMINAL_CANDIDATE_LIST:
            if not self._host_command_exists(binary):
                continue
            try:
                Gio.Subprocess.new(
                    self._host_argv(self._terminal_argv(binary, directory)),
                    Gio.SubprocessFlags.NONE,
                )
                return True
            except GLib.Error:
                continue
        return False

    def _terminal_argv(self, binary: str, directory: str) -> list[str]:
        """Full argv to launch `binary` starting in `directory`, using
        that emulator's own flag for it where one is documented
        (_TERMINAL_FLAG_MAP).

        x-terminal-emulator instead gets the classic xterm `-e COMMAND`
        form (see _TERMINAL_FLAG_MAP's comment on why): the command run
        is its own `cd DIR && exec $SHELL`, so it's the freshly spawned
        shell doing the cd, not this wrapper's own — sidesteps needing
        the wrapper to understand any flag at all.

        Every other unlisted binary (xdg-terminal-exec, xterm,
        deepin-terminal...) gets a plain `cd DIR && exec binary`: none of
        these is a D-Bus-activated single-instance app reusing some
        already-running server's cwd (xdg-terminal-exec execs the
        resolved terminal directly per its own spec; xterm has no server
        to reuse), so inheriting cwd through the exec genuinely lands the
        new terminal in `directory` — and for xterm it's the only option
        anyway, since it has no such flag at all."""
        flag_args = _TERMINAL_FLAG_MAP.get(binary)
        if flag_args is not None:
            return [binary] + [arg.format(directory=directory) for arg in flag_args]
        if binary == "x-terminal-emulator":
            inner_shell_command = f"cd {shlex.quote(directory)} && exec ${{SHELL:-/bin/sh}}"
            return [binary, "-e", "sh", "-c", inner_shell_command]
        shell_command = f"cd {shlex.quote(directory)} && exec {shlex.quote(binary)}"
        return ["sh", "-c", shell_command]

    def _host_argv(self, argv: list[str]) -> list[str]:
        """Prefixes `argv` with `flatpak-spawn --host` when sandboxed, so
        it runs as a real host process (a terminal window has no business
        living inside our sandbox) — a no-op outside Flatpak."""
        return (["flatpak-spawn", "--host"] if self.is_running_flatpak() else []) + argv

    def _host_command_exists(self, binary: str) -> bool:
        """Whether `binary` resolves on the host $PATH. Checked with a
        quick, synchronous `command -v` (not a plain PATH scan in-process
        — under Flatpak our own $PATH is the sandboxed runtime's, which
        none of _TERMINAL_CANDIDATE_LIST lives on) rather than just
        trying to launch each candidate and seeing what fails: a failed
        exec happens *after* Gio.Subprocess.new returns (fire-and-forget,
        see open_terminal), so there'd be nothing to catch here."""
        return self._run_host_command(["sh", "-c", f"command -v {shlex.quote(binary)}"])

    def _run_host_command(self, argv: list[str]) -> bool:
        """Runs `argv` to completion (on the host if sandboxed — see
        _host_argv) and reports whether it exited successfully. Used for
        short-lived probes/setters (existence checks, gsettings/
        xfconf-query calls) — never for anything long-running like a
        terminal window, which needs the fire-and-forget
        Gio.Subprocess.new open_terminal uses instead."""
        try:
            result = subprocess.run(
                self._host_argv(argv),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def set_wallpaper(self, path: str) -> bool:
        """Sets `path` (an image) as the desktop background — "Use as
        Wallpaper" in the context menu. There's no portal for this
        (unlike open_path's OpenURI), so — same spirit as open_terminal —
        a handful of desktop-specific setters are tried in turn until one
        reports success; each runs on the host (flatpak-spawn --host,
        see _host_argv) since none of gsettings/xfconf-query/
        plasma-apply-wallpaperimage live in the sandboxed org.gnome.
        Platform runtime."""
        uri = self.get_uri(path)
        setter_list = [
            # GNOME/most distros' default desktop schema.
            lambda: self._set_gsettings_wallpaper("org.gnome.desktop.background", uri),
            # Cinnamon — Linux Mint's default desktop, and this app's
            # other primary target (see NEMO_FOLDER_COLOR_THEMES above).
            lambda: self._set_gsettings_wallpaper("org.cinnamon.desktop.background", uri),
            # MATE's schema takes a plain path, not a URI.
            lambda: self._run_host_command(
                ["gsettings", "set", "org.mate.background", "picture-filename", path]
            ),
            # KDE Plasma 5.19+ ships this dedicated one-shot command.
            lambda: self._host_command_exists("plasma-apply-wallpaperimage")
            and self._run_host_command(["plasma-apply-wallpaperimage", path]),
            # XFCE stores the backdrop per monitor/workspace under
            # xfce4-desktop's config channel — every property ending in
            # "last-image" needs setting, there's no single global key.
            lambda: self._set_xfce_wallpaper(path),
            # Last-resort fallback for minimal/tiling window managers with
            # no desktop-session settings of their own.
            lambda: self._host_command_exists("feh")
            and self._run_host_command(["feh", "--bg-fill", path]),
        ]
        return any(setter() for setter in setter_list)

    def _set_gsettings_wallpaper(self, schema: str, uri: str) -> bool:
        """Sets `schema`'s picture-uri key — the actual "did this desktop
        even have this schema" signal (gsettings exits non-zero on an
        unknown schema/key, letting set_wallpaper's `any()` fall through
        to the next desktop). picture-uri-dark is set too where it exists
        (GNOME 42+/Cinnamon 5.4+) but only best-effort: it's not present
        on older versions, and that alone shouldn't read as "this schema
        doesn't apply here" once the light variant already succeeded."""
        if not self._run_host_command(["gsettings", "set", schema, "picture-uri", uri]):
            return False
        self._run_host_command(["gsettings", "set", schema, "picture-uri-dark", uri])
        return True

    def _set_xfce_wallpaper(self, path: str) -> bool:
        if not self._host_command_exists("xfconf-query"):
            return False
        try:
            result = subprocess.run(
                self._host_argv(["xfconf-query", "-c", "xfce4-desktop", "-l"]),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        if result.returncode != 0:
            return False

        property_list = [
            line.strip() for line in result.stdout.splitlines() if line.strip().endswith("last-image")
        ]
        did_set_one = False
        for property_path in property_list:
            if self._run_host_command(
                ["xfconf-query", "-c", "xfce4-desktop", "-p", property_path, "-s", path]
            ):
                did_set_one = True
        return did_set_one

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

    def get_file_properties(self, path: str) -> FilePropertiesEntity:
        """Read straight off the filesystem with os.stat — no portal
        needed, --filesystem=host already gives full access (see
        org.dupot.filebrowser.yml). uid/gid resolve fine for the host's
        files too: Flatpak shares the host's user namespace, it doesn't
        remap ids."""
        name = os.path.basename(path.rstrip("/")) or path
        location = self.get_parent_dir(path)
        is_dir = self.is_dir(path)

        content_type = self.get_content_type(path)
        type_description = Gio.content_type_get_description(content_type) or content_type

        try:
            info = os.stat(path)
        except OSError:
            info = None

        if info is None:
            size_display = "—"
            modified_display = None
            owner = None
            group = None
            permissions_display = None
            mode = None
        else:
            if is_dir:
                try:
                    item_count = len(os.listdir(path))
                    size_display = _("{count} items").format(count=item_count)
                except OSError:
                    size_display = "—"
            else:
                size_display = GLib.format_size(info.st_size)

            modified_display = datetime.fromtimestamp(info.st_mtime).strftime(
                "%Y-%m-%d %H:%M"
            )

            try:
                owner = pwd.getpwuid(info.st_uid).pw_name
            except KeyError:
                owner = str(info.st_uid)
            try:
                group = grp.getgrgid(info.st_gid).gr_name
            except KeyError:
                group = str(info.st_gid)

            mode = stat.S_IMODE(info.st_mode)
            permissions_display = f"{stat.filemode(info.st_mode)} ({mode:03o})"

        return FilePropertiesEntity(
            name=name,
            location=location,
            type_description=type_description,
            size_display=size_display,
            modified_display=modified_display,
            owner=owner,
            group=group,
            permissions_display=permissions_display,
            mode=mode,
            is_dir=is_dir,
        )

    def get_dir_size(self, path: str) -> int:
        total = 0
        try:
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        # follow_symlinks=False évite de suivre les liens et de bloquer
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                        elif entry.is_dir(follow_symlinks=False):
                            total += self.get_dir_size(entry.path)
                    except OSError:
                        pass
        except OSError:
            pass
        return total

    def set_file_permissions(self, path: str, mode: int) -> bool:
        """chmod, straight on the host path — no flatpak-spawn needed,
        the sandbox already sees this file directly (--filesystem=host),
        same as get_file_properties' os.stat above. False (not raised) on
        failure — e.g. a root-owned file the sandboxed user can't chmod —
        so the Permissions tab can show that inline instead of crashing."""
        try:
            os.chmod(path, mode)
            return True
        except OSError:
            return False

    def is_running_flatpak(self) -> bool:
        return bool(os.environ.get("FLATPAK_ID"))

    def copy_path(self, source: str, destination: str) -> str | None:
        """Recursive copy preserving symlinks/timestamps/permissions, the
        same semantics as `cp -a` — but done in-process with shutil rather
        than shelling out to a host `cp` via flatpak-spawn. No sandbox
        escape needed for this: --filesystem=host already gives direct
        read/write access to both source and destination (see
        org.dupot.filebrowser.yml). Returns None on success, or an error
        message string on failure (caller displays it, mirrors the old
        subprocess stdout+stderr text)."""
        try:
            if os.path.isdir(source) and not os.path.islink(source):
                shutil.copytree(source, destination, symlinks=True, copy_function=shutil.copy2)
            else:
                shutil.copy2(source, destination, follow_symlinks=False)
            return None
        except (OSError, shutil.Error) as error:
            return str(error)

    def move_path(self, source: str, destination: str) -> str | None:
        """Same idea as copy_path — shutil.move in-process instead of a
        host `mv` via flatpak-spawn. None on success, error text on
        failure."""
        try:
            shutil.move(source, destination)
            return None
        except (OSError, shutil.Error) as error:
            return str(error)

    def _get_real_trash_base_dir(self) -> str:
        # Deliberately NOT GLib.get_user_data_dir(): under Flatpak that
        # resolves $XDG_DATA_HOME, which Flatpak always redirects to the
        # app's private ~/.var/app/<id>/data regardless of --filesystem
        # grants — so trash written/read there is invisible to (and
        # doesn't see) the host's real Trash used by Nautilus/Nemo/etc.
        # self.get_home_dir() returns the real $HOME untouched by that
        # redirection (verified: still /home/<user> inside the sandbox),
        # so anchor Trash off that instead, same as every other desktop
        # file manager's default XDG_DATA_HOME.
        return os.path.join(self.get_home_dir(), ".local", "share", "Trash")

    def get_trash_dir(self) -> str:
        # Where trash_path() actually puts things (the XDG trash spec's
        # "files" subfolder).
        return os.path.join(self._get_real_trash_base_dir(), "files")

    def _unique_trashed_name(self, files_dir: str, name: str) -> str:
        # freedesktop.org Trash spec: on a name collision, the
        # implementation must pick another unique name rather than
        # overwrite — mirrors the "name.2", "name.3", ... scheme other
        # file managers use.
        candidate = name
        base, ext = os.path.splitext(name)
        counter = 2
        while os.path.exists(os.path.join(files_dir, candidate)):
            candidate = f"{base}.{counter}{ext}"
            counter += 1
        return candidate

    def trash_path(self, path: str) -> bool:
        # Moves into the real ~/.local/share/Trash (files/ + a matching
        # info/*.trashinfo), by hand rather than via Gio.File.trash() —
        # GIO's trash() resolves the same sandboxed XDG_DATA_HOME as
        # GLib.get_user_data_dir() (see _get_real_trash_base_dir), so it
        # would write into the app's private Trash instead of the host's.
        try:
            files_dir = self.get_trash_dir()
            info_dir = self._get_trash_info_dir()
            os.makedirs(files_dir, exist_ok=True)
            os.makedirs(info_dir, exist_ok=True)

            name = self._unique_trashed_name(files_dir, os.path.basename(path.rstrip("/")))
            trashed_path = os.path.join(files_dir, name)
            shutil.move(path, trashed_path)

            parser = configparser.ConfigParser(interpolation=None)
            parser["Trash Info"] = {
                "Path": urllib.parse.quote(path),
                "DeletionDate": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            }
            with open(os.path.join(info_dir, name + ".trashinfo"), "w", encoding="utf-8") as info_file:
                parser.write(info_file)
            return True
        except (OSError, shutil.Error):
            return False

    def _get_trash_info_dir(self) -> str:
        return os.path.join(self._get_real_trash_base_dir(), "info")

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

    def set_folder_color(self, directory: str, color: str | None) -> bool:
        """Sets/unsets `directory`'s own icon color the way Nemo's
        "Folder Color" context menu entry does — via the GVFS
        "metadata::custom-icon" attribute — when that mechanism is
        available (needs gvfsd-metadata reachable; on a Flatpak build,
        --talk-name=org.gtk.vfs.Metadata). Otherwise falls back to the
        same .dupotFileBrowser sidecar files use (add_colored_path
        /remove_colored_path, keyed on this folder's own name in *its*
        parent), so coloring still works even without GVFS metadata —
        just without the Nemo cross-compatibility. Either way,
        get_folder_color finds it again."""
        parent = self.get_parent_dir(directory)
        name = os.path.basename(directory.rstrip("/"))

        if self._set_folder_color_metadata(directory, color):
            # Metadata is authoritative once available — drop any stale
            # fallback entry so the two can't disagree later.
            self.remove_colored_path(parent, name)
            return True

        if color is None:
            self.remove_colored_path(parent, name)
        else:
            self.add_colored_path(parent, name, color)
        return True

    def _set_folder_color_metadata(self, directory: str, color: str | None) -> bool:
        """The GVFS/Nemo-compatible half of set_folder_color. Returns
        False (triggering the .dupotFileBrowser fallback above) if the
        metadata mechanism isn't available, or `color` isn't one of
        NEMO_FOLDER_COLOR_THEMES (Nemo has no icon asset for it)."""
        gfile = Gio.File.new_for_path(directory)
        try:
            if color is None:
                return gfile.set_attribute(
                    _NEMO_CUSTOM_ICON_ATTRIBUTE,
                    Gio.FileAttributeType.INVALID,
                    0,
                    Gio.FileQueryInfoFlags.NONE,
                    None,
                )
            theme = NEMO_FOLDER_COLOR_THEMES.get(color.lower())
            if theme is None:
                return False
            icon_uri = f"file:///usr/share/icons/{theme}/places/{_NEMO_ICON_SIZE}/folder.png"
            return gfile.set_attribute_string(
                _NEMO_CUSTOM_ICON_ATTRIBUTE, icon_uri, Gio.FileQueryInfoFlags.NONE, None
            )
        except GLib.Error:
            return False

    def get_folder_color(self, directory: str) -> str | None:
        """The reverse of set_folder_color: tries the GVFS/Nemo metadata
        first, then falls back to the .dupotFileBrowser sidecar in the
        parent directory — whichever mechanism set_folder_color actually
        used to store it."""
        color = self._get_folder_color_metadata(directory)
        if color is not None:
            return color
        parent = self.get_parent_dir(directory)
        name = os.path.basename(directory.rstrip("/"))
        return self.get_colored_path_map(parent).get(name)

    def _get_folder_color_metadata(self, directory: str) -> str | None:
        """None if `directory` has no custom-icon, the metadata
        mechanism isn't available, or its custom-icon isn't one of ours
        (e.g. a Mint-L/Mint-X variant, or some unrelated custom icon)."""
        try:
            info = Gio.File.new_for_path(directory).query_info(
                _NEMO_CUSTOM_ICON_ATTRIBUTE, Gio.FileQueryInfoFlags.NONE, None
            )
        except GLib.Error:
            return None
        icon_uri = info.get_attribute_string(_NEMO_CUSTOM_ICON_ATTRIBUTE)
        if not icon_uri:
            return None
        match = _NEMO_ICON_URI_RE.search(icon_uri)
        if not match:
            return None
        return _NEMO_THEME_TO_COLOR.get(match.group(1))
