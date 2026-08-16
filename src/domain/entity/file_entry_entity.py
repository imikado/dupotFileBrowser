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


class FileEntryEntity:
    """A single file or directory entry, mirroring the Flutter app's use
    of dart:io's FileSystemEntity in PathView."""

    def __init__(self, name: str, path: str, is_dir: bool):
        self.name = name
        self.path = path
        self.is_dir = is_dir

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
