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

    _instance: "UserSettingsEntity | None" = None

    DEFAULT_VERSION = 1
    DEFAULT_THEME = THEME_SYSTEM
    DEFAULT_LANGUAGE = LANGUAGE_SYSTEM

    version: int = DEFAULT_VERSION
    theme: str = DEFAULT_THEME
    language: str = DEFAULT_LANGUAGE

    # Resolved by the app at startup from the real system locale (see
    # main.py, which uses GLib.get_language_names() — the reliable locale
    # source inside a Flatpak sandbox). Used whenever `language` is
    # LANGUAGE_SYSTEM. Defaults to English until resolved.
    _system_language_code: str = LANGUAGE_EN_CODE

    def __new__(cls, *_args, **_kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def reset_to_defaults(self) -> None:
        self.version = self.DEFAULT_VERSION
        self.theme = self.DEFAULT_THEME
        self.language = self.DEFAULT_LANGUAGE

    def load(self, raw_obj: object) -> None:
        self.version = raw_obj.get(self.FIELD_VERSION, self.DEFAULT_VERSION)
        self.theme = raw_obj.get(self.FIELD_THEME, self.DEFAULT_THEME)
        self.language = raw_obj.get(self.FIELD_LANGUAGE, self.DEFAULT_LANGUAGE)

    def get_json_string(self) -> str:
        return json.dumps(
            {
                self.FIELD_VERSION: self.version,
                self.FIELD_THEME: self.theme,
                self.FIELD_LANGUAGE: self.language,
            }
        )

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
