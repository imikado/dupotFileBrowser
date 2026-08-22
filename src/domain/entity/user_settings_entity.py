import json


class UserSettingsEntity:
    """Persisted user preferences (theme + language), mirroring the
    Flutter app's Parameters singleton and dupotEasyFlatpak's
    UserSettingsEntity."""

    THEME_DARK = "dark"
    THEME_LIGHT = "light"
    THEME_SYSTEM = "system"

    LANGUAGE_SYSTEM = "system"
    LANGUAGE_EN = "english"
    LANGUAGE_FR = "french"
    LANGUAGE_IT = "italian"

    LANGUAGE_EN_CODE = "en"

    FIELD_VERSION = "version"
    FIELD_THEME = "theme"
    FIELD_LANGUAGE = "language"
    FIELD_USE_SYSTEM_ICON_THEME = "useSystemIconTheme"
    FIELD_FAVORITE_LIST = "favoriteList"
    FIELD_FAVORITE_LABEL = "label"
    FIELD_FAVORITE_PATH = "path"
    FIELD_WINDOW_WIDTH = "windowWidth"
    FIELD_WINDOW_HEIGHT = "windowHeight"
    FIELD_DISPLAY_HIDDEN = "displayHidden"
    FIELD_VIEW_MODE = "viewMode"
    FIELD_GRID_ICON_SIZE = "gridIconSize"
    FIELD_SINGLE_CLICK_OPEN = "singleClickOpen"

    VIEW_MODE_COLUMNS = "columns"
    VIEW_MODE_GRID = "grid"
    VIEW_MODE_DETAILS = "details"

    # Clamp range for the grid view's icon-size slider (see
    # infrastructure/ui/shared/view_mode_switcher.py) — narrow enough
    # that a thumbnail is still recognizable, wide enough to actually
    # preview an image.
    MIN_GRID_ICON_SIZE = 48
    MAX_GRID_ICON_SIZE = 256

    _instance: "UserSettingsEntity | None" = None

    DEFAULT_VERSION = 1
    DEFAULT_THEME = THEME_SYSTEM
    DEFAULT_LANGUAGE = LANGUAGE_SYSTEM
    # Off by default: the host icon theme may not cover every file type
    # (see file_icons.py) — baked icons stay the safe out-of-the-box choice.
    DEFAULT_USE_SYSTEM_ICON_THEME = True
    # Matches MainWindow's previous hardcoded set_default_size(1000, 700).
    DEFAULT_WINDOW_WIDTH = 1000
    DEFAULT_WINDOW_HEIGHT = 700
    DEFAULT_DISPLAY_HIDDEN=False
    # The Miller-column browser stays the default view — it's the one
    # existing users already know; grid is opt-in.
    DEFAULT_VIEW_MODE = VIEW_MODE_COLUMNS
    DEFAULT_GRID_ICON_SIZE = 96
    # Only read by GridPage/DetailsPage — PathPage's Miller columns keep
    # their own fixed single-click-opens-folders convention regardless
    # of this setting (see its class docstring). Off by default: matches
    # the grid/details views' existing single-click-selects/double-
    # click-opens behavior, so this setting is purely opt-in.
    DEFAULT_SINGLE_CLICK_OPEN = False

    version: int = DEFAULT_VERSION
    theme: str = DEFAULT_THEME
    language: str = DEFAULT_LANGUAGE
    use_system_icon_theme: bool = DEFAULT_USE_SYSTEM_ICON_THEME
    window_width: int = DEFAULT_WINDOW_WIDTH
    window_height: int = DEFAULT_WINDOW_HEIGHT
    display_hidden_files: bool= DEFAULT_DISPLAY_HIDDEN
    view_mode: str = DEFAULT_VIEW_MODE
    grid_icon_size: int = DEFAULT_GRID_ICON_SIZE
    single_click_open: bool = DEFAULT_SINGLE_CLICK_OPEN
    # Each item is {"label": <dir name>, "path": <absolute path>}.
    favorite_list: list[dict]

    # Resolved by the app at startup from the real system locale (see
    # main.py, which uses GLib.get_language_names() — the reliable locale
    # source inside a Flatpak sandbox). Used whenever `language` is
    # LANGUAGE_SYSTEM. Defaults to English until resolved.
    _system_language_code: str = LANGUAGE_EN_CODE

    def __new__(cls, *_args, **_kwargs):
        if cls._instance is None:
            instance = super().__new__(cls)
            # Own mutable list per (singleton) instance, never a shared
            # class attribute — see reset_to_defaults/load.
            instance.favorite_list = []
            cls._instance = instance
        return cls._instance

    def reset_to_defaults(self) -> None:
        self.version = self.DEFAULT_VERSION
        self.theme = self.DEFAULT_THEME
        self.language = self.DEFAULT_LANGUAGE
        self.use_system_icon_theme = self.DEFAULT_USE_SYSTEM_ICON_THEME
        self.window_width = self.DEFAULT_WINDOW_WIDTH
        self.window_height = self.DEFAULT_WINDOW_HEIGHT
        self.display_hidden_files= self.DEFAULT_DISPLAY_HIDDEN
        self.view_mode = self.DEFAULT_VIEW_MODE
        self.grid_icon_size = self.DEFAULT_GRID_ICON_SIZE
        self.single_click_open = self.DEFAULT_SINGLE_CLICK_OPEN
        self.favorite_list = []

    def load(self, raw_obj: object) -> None:
        self.version = raw_obj.get(self.FIELD_VERSION, self.DEFAULT_VERSION)
        self.theme = raw_obj.get(self.FIELD_THEME, self.DEFAULT_THEME)
        self.language = raw_obj.get(self.FIELD_LANGUAGE, self.DEFAULT_LANGUAGE)
        self.use_system_icon_theme = raw_obj.get(
            self.FIELD_USE_SYSTEM_ICON_THEME, self.DEFAULT_USE_SYSTEM_ICON_THEME
        )
        self.window_width = raw_obj.get(self.FIELD_WINDOW_WIDTH, self.DEFAULT_WINDOW_WIDTH)
        self.window_height = raw_obj.get(self.FIELD_WINDOW_HEIGHT, self.DEFAULT_WINDOW_HEIGHT)
        self.display_hidden_files = raw_obj.get(self.FIELD_DISPLAY_HIDDEN, self.DEFAULT_DISPLAY_HIDDEN)
        self.view_mode = raw_obj.get(self.FIELD_VIEW_MODE, self.DEFAULT_VIEW_MODE)
        self.grid_icon_size = raw_obj.get(self.FIELD_GRID_ICON_SIZE, self.DEFAULT_GRID_ICON_SIZE)
        self.single_click_open = raw_obj.get(
            self.FIELD_SINGLE_CLICK_OPEN, self.DEFAULT_SINGLE_CLICK_OPEN
        )

        self.favorite_list = raw_obj.get(self.FIELD_FAVORITE_LIST, [])

    def get_json_string(self) -> str:
        return json.dumps(
            {
                self.FIELD_VERSION: self.version,
                self.FIELD_THEME: self.theme,
                self.FIELD_LANGUAGE: self.language,
                self.FIELD_USE_SYSTEM_ICON_THEME: self.use_system_icon_theme,
                self.FIELD_WINDOW_WIDTH: self.window_width,
                self.FIELD_WINDOW_HEIGHT: self.window_height,
                self.FIELD_FAVORITE_LIST: self.favorite_list,
                self.FIELD_DISPLAY_HIDDEN: self.display_hidden_files,
                self.FIELD_VIEW_MODE: self.view_mode,
                self.FIELD_GRID_ICON_SIZE: self.grid_icon_size,
                self.FIELD_SINGLE_CLICK_OPEN: self.single_click_open,
            }
        )

    def set_window_size(self, width: int, height: int) -> None:
        self.window_width = width
        self.window_height = height

    def add_favorite(self, label: str, path: str) -> None:
        """Adds {label, path} to favorite_list, unless that path is
        already favorited."""
        already_favorite = any(
            fav.get(self.FIELD_FAVORITE_PATH) == path for fav in self.favorite_list
        )
        if already_favorite:
            return
        self.favorite_list.append(
            {self.FIELD_FAVORITE_LABEL: label, self.FIELD_FAVORITE_PATH: path}
        )

    def remove_favorite(self, path: str) -> None:
        self.favorite_list = [
            fav for fav in self.favorite_list if fav.get(self.FIELD_FAVORITE_PATH) != path
        ]

    def use_theme_system(self) -> bool:
        return self.theme == self.THEME_SYSTEM

    def use_theme_dark(self) -> bool:
        return self.theme == self.THEME_DARK

    def use_theme_light(self) -> bool:
        return self.theme == self.THEME_LIGHT

    def get_theme_choice_list(self) -> list[str]:
        return [self.THEME_DARK, self.THEME_LIGHT, self.THEME_SYSTEM]

    def get_language_choice_list(self) -> list[str]:
        return [self.LANGUAGE_SYSTEM, self.LANGUAGE_EN, self.LANGUAGE_FR, self.LANGUAGE_IT]

    def should_force_language(self) -> bool:
        return self.language != self.LANGUAGE_SYSTEM

    def set_system_language_code(self, code: str) -> None:
        self._system_language_code = code

    def get_language_code(self) -> str:
        if self.language == self.LANGUAGE_SYSTEM:
            return self._system_language_code

        language_codes = {
            self.LANGUAGE_EN: self.LANGUAGE_EN_CODE,
            self.LANGUAGE_FR: "fr",
            self.LANGUAGE_IT: "it",
        }
        return language_codes.get(self.language, self.LANGUAGE_EN_CODE)

    def should_display_hidden(self)->bool:
        return self.display_hidden_files

    def set_should_display_hidden(self,display_hidden:bool):
        self.display_hidden_files=display_hidden

    def use_grid_view(self) -> bool:
        return self.view_mode == self.VIEW_MODE_GRID

    def use_details_view(self) -> bool:
        return self.view_mode == self.VIEW_MODE_DETAILS

    def set_view_mode(self, view_mode: str) -> None:
        self.view_mode = view_mode

    def get_grid_icon_size(self) -> int:
        return self.grid_icon_size

    def set_grid_icon_size(self, size: int) -> None:
        self.grid_icon_size = max(self.MIN_GRID_ICON_SIZE, min(self.MAX_GRID_ICON_SIZE, size))

    def should_open_on_single_click(self) -> bool:
        return self.single_click_open

    def set_should_open_on_single_click(self, single_click_open: bool) -> None:
        self.single_click_open = single_click_open
