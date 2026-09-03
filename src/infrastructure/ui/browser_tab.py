import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

from domain.entity.user_settings_entity import UserSettingsEntity
from infrastructure.ui.details_page import DetailsPage
from infrastructure.ui.grid_page import GridPage
from infrastructure.ui.path_page import PathPage
from infrastructure.ui.trash_page import TrashPage


class BrowserTab(Gtk.Stack):
    """One tab's content: its own PathPage/GridPage/DetailsPage/TrashPage
    and current_path, switched between as the view mode or location
    changes. MainWindow owns one of these per Adw.TabPage."""

    def __init__(
        self,
        system_api,
        settings: UserSettingsEntity,
        home_path: str,
        trash_path: str,
        on_path_changed,
        on_favorites_changed,
        on_file_copied,
        on_file_cut,
        on_compress_requested,
        on_extract_requested,
    ):
        super().__init__()
        self._system_api = system_api
        self._settings = settings
        self._home_path = home_path
        self._trash_path = trash_path
        self.current_path = home_path
        self.showing_trash = False
        self.tab_page = None  # set by MainWindow right after Adw.TabView.append

        self._path_page = PathPage(
            on_path_changed, on_favorites_changed, on_file_copied, on_file_cut,
            on_compress_requested, on_extract_requested,
        )
        self._grid_page = GridPage(
            on_path_changed, on_favorites_changed, on_file_copied, on_file_cut,
            on_compress_requested, on_extract_requested,
        )
        self._details_page = DetailsPage(
            on_path_changed, on_favorites_changed, on_file_copied, on_file_cut,
            on_compress_requested, on_extract_requested,
        )
        self._trash_page = TrashPage(system_api)

        self.set_hexpand(True)
        self.add_named(self._path_page, "browser")
        self.add_named(self._grid_page, "grid")
        self.add_named(self._details_page, "details")
        self.add_named(self._trash_page, "trash")

    def _browser_view_name(self) -> str:
        if self._settings.use_grid_view():
            return "grid"
        if self._settings.use_details_view():
            return "details"
        return "browser"

    def active_browser_page(self):
        if self._settings.use_grid_view():
            return self._grid_page
        if self._settings.use_details_view():
            return self._details_page
        return self._path_page

    def uses_single_folder_view(self) -> bool:
        return self._settings.use_grid_view() or self._settings.use_details_view()

    def load_path(self, path: str):
        self.showing_trash = False
        self.set_visible_child_name(self._browser_view_name())
        self.current_path = path
        self.active_browser_page().load_path(path)

    def load_path_chain(self, path: str):
        self.showing_trash = False
        self.set_visible_child_name("browser")
        self.current_path = path
        self._path_page.load_path_chain(path)

    def navigate(self, path: str, as_chain: bool = False):
        """Single-folder views (Grid/Details) always just load `path`.
        Columns mode defaults to a plain single column too (sidebar
        clicks) — pass as_chain=True to rebuild the full ancestor chain
        instead (path entry commits, or coming from another view mode)."""
        if self.uses_single_folder_view():
            self.load_path(path)
        elif as_chain:
            self.load_path_chain(path)
        else:
            self.load_path(path)

    def go_to_trash(self):
        self.showing_trash = True
        self.set_visible_child_name("trash")
        self._trash_page.refresh()
        self.current_path = self._trash_path

    def go_up(self) -> str | None:
        """Returns the new path if it moved up in place (single-folder
        view), or None if PathPage handled it itself by prepending a
        column (current_path/tab title unaffected either way)."""
        if self.uses_single_folder_view():
            parent_path = self._system_api.get_parent_dir(self.current_path)
            if parent_path != self.current_path:
                self.load_path(parent_path)
                return parent_path
            return None
        self._path_page.prepend_parent()
        return None

    def apply_view_mode(self):
        if not self.showing_trash:
            self.navigate(self.current_path, as_chain=True)

    def refresh_path(self, path: str):
        self._path_page.refresh_path(path)
        self._grid_page.refresh_path(path)
        self._details_page.refresh_path(path)

    def refresh_hidden_files(self):
        self._path_page.refresh_hidden_files()
        self._grid_page.refresh_hidden_files()
        self._details_page.refresh_hidden_files()

    def refresh_trash(self):
        self._trash_page.refresh()

    def apply_click_to_open_setting(self):
        self._grid_page.apply_click_to_open_setting()
        self._details_page.apply_click_to_open_setting()

    def set_grid_icon_size(self, size: int):
        self._grid_page.set_icon_size(size)
