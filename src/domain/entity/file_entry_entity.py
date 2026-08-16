class FileEntryEntity:
    """A single file or directory entry, mirroring the Flutter app's use
    of dart:io's FileSystemEntity in PathView."""

    def __init__(self, name: str, path: str, is_dir: bool):
        self.name = name
        self.path = path
        self.is_dir = is_dir

    def get_display_name(self) -> str:
        return f"{self.name}/" if self.is_dir else self.name

    def get_icon_name(self) -> str:
        return "folder-symbolic" if self.is_dir else "text-x-generic-symbolic"
