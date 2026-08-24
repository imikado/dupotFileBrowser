# Extension (lowercase, no leading dot) -> icon key.
# Keys name a PNG shipped under assets/icons/{light,dark}/<key>.png (see
# infrastructure/ui/shared/file_icons.py) instead of a GTK/Adwaita icon
# theme name: relying on the host icon theme turned out to be exactly the
# "surprise depending on where it's installed" this was meant to avoid —
# a Flatpak's bundled Adwaita, or a distro with a slim/alternate theme,
# may simply not carry x-office-* or package-x-generic-symbolic, and the
# row would render with no icon at all.
_EXTENSION_ICON_MAP = {
    # Images
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "gif": "image",
    "bmp": "image",
    "svg": "image",
    "webp": "image",
    "tiff": "image",
    "tif": "image",
    "ico": "image",
    "heic": "image",
    # Audio
    "mp3": "audio",
    "wav": "audio",
    "flac": "audio",
    "ogg": "audio",
    "oga": "audio",
    "m4a": "audio",
    "aac": "audio",
    "wma": "audio",
    "opus": "audio",
    # Video
    "mp4": "video",
    "mkv": "video",
    "avi": "video",
    "mov": "video",
    "webm": "video",
    "flv": "video",
    "wmv": "video",
    "mpg": "video",
    "mpeg": "video",
    "m4v": "video",
    # Archives / packages
    "zip": "archive",
    "tar": "archive",
    "gz": "archive",
    "tgz": "archive",
    "bz2": "archive",
    "tbz2": "archive",
    "xz": "archive",
    "7z": "archive",
    "rar": "archive",
    "deb": "archive",
    "rpm": "archive",
    "flatpak": "archive",
    # Documents
    "pdf": "document",
    "doc": "document",
    "docx": "document",
    "odt": "document",
    "rtf": "document",
    # Spreadsheets
    "xls": "spreadsheet",
    "xlsx": "spreadsheet",
    "ods": "spreadsheet",
    "csv": "spreadsheet",
    # Presentations
    "ppt": "presentation",
    "pptx": "presentation",
    "odp": "presentation",
    # Code / scripts — deliberately not mapped to a per-language key: falls
    # through to _DEFAULT_ICON_KEY like any other unrecognized extension.
    # Fonts
    "ttf": "font",
    "otf": "font",
    "woff": "font",
    "woff2": "font",
    # Executables
    "exe": "executable",
    "appimage": "executable",
}

_DEFAULT_ICON_KEY = "generic"

# icon_key -> human-readable type label, for DetailsPage's "Type" column.
# Deliberately reuses the same coarse extension grouping as the icon
# lookup above rather than querying Gio's content-type machinery
# per-entry (see SystemApi.get_content_type) — that's precise enough for
# the Properties dialog's single file, but calling it once per row would
# add real I/O to every folder listing just to populate a column.
_ICON_KEY_TYPE_LABEL = {
    "image": lambda: _("Image"),
    "audio": lambda: _("Audio"),
    "video": lambda: _("Video"),
    "archive": lambda: _("Archive"),
    "document": lambda: _("Document"),
    "spreadsheet": lambda: _("Spreadsheet"),
    "presentation": lambda: _("Presentation"),
    "font": lambda: _("Font"),
    "executable": lambda: _("Executable"),
}

# Extensions SystemApi.extract_path can actually unpack (shutil's own
# registered formats: zip, tar, gztar, bztar, xztar) — a subset of
# _EXTENSION_ICON_MAP's broader "archive" category, which also covers
# formats we can't extract in-process (7z, rar, deb, rpm, flatpak).
# Deliberately kept in sync by hand with SystemApi.compress_path's own
# _ARCHIVE_EXTENSIONS rather than imported from there — this is domain
# code, infrastructure/api/system_api.py isn't something it should
# depend on. Longest first so ".tar.gz" matches whole instead of via a
# shorter suffix.
_EXTRACTABLE_ARCHIVE_EXTENSIONS = (".tar.gz", ".tar.bz2", ".tar.xz", ".tar", ".zip")


class FileEntryEntity:
    """A single file or directory entry, mirroring the Flutter app's use
    of dart:io's FileSystemEntity in PathView."""

    def __init__(
        self,
        name: str,
        path: str,
        is_dir: bool,
        size: int | None = None,
        mtime: float | None = None,
    ):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        # Populated by SystemApi.list_dir from the same os.scandir() stat
        # call that already resolves is_dir — free to grab there, unlike
        # a directory's total size (see SystemApi.get_dir_size), which
        # walks the whole tree and stays an explicit, on-demand-only call.
        # None for a directory (DetailsPage shows a blank Size cell) or
        # when the stat itself failed (a broken symlink, a race with
        # deletion).
        self.size = size
        self.mtime = mtime

    def get_display_name(self) -> str:
        return f"{self.name}/" if self.is_dir else self.name

    def get_icon_key(self) -> str:
        """Key into assets/icons/{light,dark}/ — see
        infrastructure/ui/shared/file_icons.py. Directories aren't covered
        here: PathPage renders those with the real folder-symbolic icon
        (needed for Nemo folder-color tinting)."""
        _, dot, extension = self.name.rpartition(".")
        if not dot:
            return _DEFAULT_ICON_KEY
        return _EXTENSION_ICON_MAP.get(extension.lower(), _DEFAULT_ICON_KEY)

    def is_extractable_archive(self) -> bool:
        """Whether this file's extension is one SystemApi.extract_path
        can actually unpack — gates the "Extract Here" context menu
        entry (see _EXTRACTABLE_ARCHIVE_EXTENSIONS)."""
        if self.is_dir:
            return False
        lowered_name = self.name.lower()
        return any(lowered_name.endswith(ext) for ext in _EXTRACTABLE_ARCHIVE_EXTENSIONS)

    def get_type_label(self) -> str:
        """Human-readable type, for DetailsPage's "Type" column — e.g.
        "Folder", "Image", "PDF File". Lazily translated (called at
        display time, not import time) so a language switch is picked up
        without restarting."""
        if self.is_dir:
            return _("Folder")
        key = self.get_icon_key()
        label_builder = _ICON_KEY_TYPE_LABEL.get(key)
        if label_builder is not None:
            return label_builder()
        # Not "_, dot, extension" — this function also calls the gettext
        # "_" above, and Python scopes an assigned name as local for the
        # whole function, so reusing "_" here would shadow gettext's and
        # crash the self.is_dir branch's return _("Folder") above with
        # UnboundLocalError.
        stem, dot, extension = self.name.rpartition(".")
        if dot:
            return _("{extension} File").format(extension=extension.upper())
        return _("File")
