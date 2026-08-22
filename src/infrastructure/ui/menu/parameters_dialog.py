import os
import sys
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk

from domain.entity.user_settings_entity import UserSettingsEntity
from infrastructure.api.system_api import SystemApi
from infrastructure.api.user_settings_api import UserSettingsApi


class ParametersDialog(Adw.PreferencesDialog):

    def __init__(self, on_saved=None):
        super().__init__()
        self.set_title(_("Parameters"))

        self._settings = UserSettingsEntity()
        self._user_settings_api = UserSettingsApi(SystemApi())
        self._on_saved = on_saved

        page = Adw.PreferencesPage()
        self.add(page)

        appearance_group = Adw.PreferencesGroup()
        appearance_group.set_title(_("Appearance"))
        page.add(appearance_group)

        theme_choices = self._settings.get_theme_choice_list()
        self._theme_row = Adw.ComboRow()
        self._theme_row.set_title(_("Theme"))
        self._theme_row.set_model(Gtk.StringList.new([_(c) for c in theme_choices]))
        current_theme = self._settings.theme
        self._theme_row.set_selected(
            theme_choices.index(current_theme) if current_theme in theme_choices else 0
        )
        self._theme_row.connect("notify::selected", lambda *_: self._on_change())
        appearance_group.add(self._theme_row)

        language_choices = self._settings.get_language_choice_list()
        self._language_row = Adw.ComboRow()
        self._language_row.set_title(_("Language"))
        self._language_row.set_model(Gtk.StringList.new([_(c) for c in language_choices]))
        current_language = self._settings.language
        self._language_row.set_selected(
            language_choices.index(current_language) if current_language in language_choices else 0
        )
        self._language_row.connect("notify::selected", lambda *_: self._on_change())
        appearance_group.add(self._language_row)

        self._system_icon_row = Adw.SwitchRow()
        self._system_icon_row.set_title(_("Use system icon theme"))
        self._system_icon_row.set_subtitle(
            _(
                "Show the same file icons as your file manager (Nemo, "
                "Nautilus...). Falls back to the built-in icons for any "
                "file type your theme doesn't cover."
            )
        )
        self._system_icon_row.set_active(self._settings.use_system_icon_theme)
        self._system_icon_row.connect("notify::active", lambda *_: self._on_change())
        appearance_group.add(self._system_icon_row)

        self._hidden_files_row = Adw.SwitchRow()
        self._hidden_files_row.set_title(_("Show hidden files"))
        self._hidden_files_row.set_subtitle(
            _("Display files and folders whose name starts with a dot.")
        )
        self._hidden_files_row.set_active(self._settings.should_display_hidden())
        self._hidden_files_row.connect("notify::active", lambda *_: self._on_change())
        appearance_group.add(self._hidden_files_row)

        self._single_click_open_row = Adw.SwitchRow()
        self._single_click_open_row.set_title(_("Open with a single click"))
        self._single_click_open_row.set_subtitle(
            _(
                "In Grid and Details view, open a file or folder with a "
                "single click instead of a double click. Doesn't affect "
                "Columns view."
            )
        )
        self._single_click_open_row.set_active(self._settings.should_open_on_single_click())
        self._single_click_open_row.connect("notify::active", lambda *_: self._on_change())
        appearance_group.add(self._single_click_open_row)

        save_group = Adw.PreferencesGroup()
        page.add(save_group)

        self._save_btn = Gtk.Button(label=_("Save"))
        self._save_btn.add_css_class("suggested-action")
        self._save_btn.add_css_class("pill")
        self._save_btn.set_halign(Gtk.Align.CENTER)
        self._save_btn.set_margin_top(8)
        self._save_btn.set_margin_bottom(8)
        self._save_btn.set_sensitive(False)
        self._save_btn.connect("clicked", self._on_save)
        save_group.add(self._save_btn)

    def _on_change(self):
        self._save_btn.set_sensitive(True)

    def _on_save(self, _btn):
        theme_choices = self._settings.get_theme_choice_list()
        self._settings.theme = theme_choices[self._theme_row.get_selected()]

        language_choices = self._settings.get_language_choice_list()
        new_language = language_choices[self._language_row.get_selected()]
        language_changed = new_language != self._settings.language
        self._settings.language = new_language

        new_use_system_icon_theme = self._system_icon_row.get_active()
        icon_theme_changed = new_use_system_icon_theme != self._settings.use_system_icon_theme
        self._settings.use_system_icon_theme = new_use_system_icon_theme

        new_display_hidden = self._hidden_files_row.get_active()
        hidden_files_changed = new_display_hidden != self._settings.should_display_hidden()
        self._settings.set_should_display_hidden(new_display_hidden)

        new_single_click_open = self._single_click_open_row.get_active()
        single_click_open_changed = (
            new_single_click_open != self._settings.should_open_on_single_click()
        )
        self._settings.set_should_open_on_single_click(new_single_click_open)

        self._user_settings_api.save()

        if self._on_saved:
            self._on_saved(hidden_files_changed, single_click_open_changed)

        self.close()

        if language_changed or icon_theme_changed:
            # gettext translations are bound at process start (language),
            # and every icon already on screen was built under the old
            # icon-theme choice (icon theme) — restart to make either
            # change take effect everywhere, same trick as dupotEasyFlatpak.
            os.execv(sys.executable, [sys.executable] + sys.argv)
