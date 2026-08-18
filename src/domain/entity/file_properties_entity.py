class FilePropertiesEntity:
    """A single file/folder's filesystem metadata, read by
    SystemApi.get_file_properties() and shown by the "Properties" context
    menu entry (see properties_dialog.py) — the same kind of information
    Nemo/Nautilus/Files show in their own Properties window. Most fields
    are already display-ready strings (or None for "unknown"/"-"); `mode`
    is the exception — the raw rwx bits (stat.S_IMODE), kept numeric so
    the Permissions tab's checkbox grid can edit it (see
    SystemApi.set_file_permissions)."""

    def __init__(
        self,
        name: str,
        location: str,
        type_description: str,
        size_display: str,
        modified_display: str | None,
        owner: str | None,
        group: str | None,
        permissions_display: str | None,
        mode: int | None,
        is_dir: bool,
    ):
        self.name = name
        self.location = location
        self.type_description = type_description
        self.size_display = size_display
        self.modified_display = modified_display
        self.owner = owner
        self.group = group
        self.permissions_display = permissions_display
        self.mode = mode
        self.is_dir = is_dir
