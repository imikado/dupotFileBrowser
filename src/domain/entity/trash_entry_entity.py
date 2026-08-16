class TrashEntryEntity:
    """One item currently in the Trash, read straight from Trash/files +
    Trash/info/*.trashinfo (see SystemApi.list_trash) — carries what a
    plain directory listing of ~/.local/share/Trash/files alone can't:
    the original location and the deletion date."""

    def __init__(
        self,
        trashed_path: str,
        display_name: str,
        original_path: str,
        deletion_date: str,
        is_dir: bool,
    ):
        self.trashed_path = trashed_path
        self.display_name = display_name
        self.original_path = original_path
        self.deletion_date = deletion_date
        self.is_dir = is_dir

    def get_icon_key(self) -> str:
        return "folder" if self.is_dir else "generic"
