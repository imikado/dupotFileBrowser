import os


class PathConf:
    """Resolves the asset paths (shipped with the app) and the user data
    paths (XDG data dir), mirroring dupotEasyFlatpak's PathConf."""

    _instance = None

    ID_PATH = "org.dupot.filebrowser"

    USER_SETTINGS_FILENAME = "user_settings.json"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_path_list_join(self, path_list: list) -> str:
        return "/".join(path_list)

    # assets
    def get_asset_path(self) -> str:
        return self.get_path_list_join(
            [os.path.dirname(__file__), "..", "..", "..", "assets"]
        )

    def get_asset_logo_path(self) -> str:
        return self.get_path_list_join([self.get_asset_path(), "logos", "512x512.png"])

    def get_asset_file_icon_path(self, icon_key: str, dark: bool) -> str:
        variant = "dark" if dark else "light"
        return self.get_path_list_join(
            [self.get_asset_path(), "icons", variant, f"{icon_key}.png"]
        )

    # user
    def set_data_path(self, data_path: str):
        self._data_path = data_path

    def get_data_path(self) -> str:
        return self.get_path_list_join([self._data_path, self.ID_PATH])

    def get_user_settings_path(self) -> str:
        return self.get_path_list_join([self.get_data_path(), self.USER_SETTINGS_FILENAME])
