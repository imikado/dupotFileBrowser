#!/usr/bin/env python3
"""Regenerates export/screenshots/*.png by driving the real app
in-process and rendering each window state straight to a texture (Gsk
render-to-texture — no window manager/compositor involved, works
headless too) — see capture(). Runs against an isolated fake $HOME and
a temp app-settings dir populated with demo folders/files, never the
real user's data.

Usage:
    ./generate_screenshots.py
"""
import os
import shutil
import sys
import tempfile

SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
sys.path.insert(0, SRC_DIR)

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gsk", "4.0")

from gi.repository import Adw, GLib, Gtk

import gettext

gettext.install("dupot_file_browser", os.path.join(SRC_DIR, "infrastructure", "locales"))

Adw.init()

from domain.conf.path_conf import PathConf
from domain.entity.user_settings_entity import UserSettingsEntity
from infrastructure.api.system_api import SystemApi
from infrastructure.api.user_settings_api import UserSettingsApi
from infrastructure.ui.app_window import MainWindow
from infrastructure.ui.menu.parameters_dialog import ParametersDialog
from infrastructure.ui.shared.color_picker_popup import show_color_picker_popup
from infrastructure.ui.shared.properties_dialog import show_properties_dialog

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "export", "screenshots")
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 700

VACATION_COLOR = "#5294e2"
FAMILY_COLOR = "#50c16f"


def wait(ms=200):
    loop = GLib.MainLoop()
    GLib.timeout_add(ms, loop.quit)
    loop.run()


def render_widget_to_texture(widget):
    native = widget.get_native()
    width = widget.get_width()
    height = widget.get_height()
    paintable = Gtk.WidgetPaintable.new(widget)
    snapshot = Gtk.Snapshot.new()
    paintable.snapshot(snapshot, width, height)
    node = snapshot.to_node()
    texture = native.get_renderer().render_texture(node, None)
    return texture, width, height


def capture(window, filename):
    wait(80)
    texture, width, height = render_widget_to_texture(window)
    texture.save_to_png(os.path.join(OUTPUT_DIR, filename))
    print(f"  -> {filename} ({width}x{height})")


def capture_popover(popover, filename):
    """Popovers render on their own GDK surface (not part of the parent
    window's own render tree), so they need their own capture, not a
    region of the window's — see find_popover_on."""
    wait(80)
    texture, width, height = render_widget_to_texture(popover)
    texture.save_to_png(os.path.join(OUTPUT_DIR, filename))
    print(f"  -> {filename} ({width}x{height}, popover)")


def find_popover_on(widget):
    model = widget.observe_children()
    for i in range(model.get_n_items()):
        child = model.get_item(i)
        if isinstance(child, Gtk.Popover):
            return child
    return None


def find_row(column, name):
    row = column._list_box.get_first_child()
    while row is not None:
        entry = getattr(row, "entry", None)
        if entry is not None and entry.name == name:
            return row
        row = row.get_next_sibling()
    return None


def close_popovers_on(widget):
    popover = find_popover_on(widget)
    if popover is not None:
        popover.popdown()


def close_all_dialogs(window):
    for dialog in window.get_dialogs():
        dialog.force_close()


def build_demo_home(home_dir):
    def mkfile(path, content=""):
        with open(path, "w") as f:
            f.write(content)

    for name in ("Desktop", "Downloads", "Projects", "Public", "Templates", "Videos", "dupotFileBrowser"):
        os.makedirs(os.path.join(home_dir, name), exist_ok=True)

    documents = os.path.join(home_dir, "Documents")
    os.makedirs(documents, exist_ok=True)
    mkfile(os.path.join(documents, "report.odt"))
    mkfile(os.path.join(documents, "invoice.pdf"))
    mkfile(os.path.join(documents, "notes.txt"), "Meeting notes\n")

    os.makedirs(os.path.join(home_dir, "Music"), exist_ok=True)

    pictures = os.path.join(home_dir, "Pictures")
    os.makedirs(pictures, exist_ok=True)
    for name in ("vacation_photos", "family_photos", "screenshots", "sync"):
        os.makedirs(os.path.join(pictures, name), exist_ok=True)
    mkfile(os.path.join(pictures, "artwork.xcf"))

    return documents, pictures


def run_scenes(window, system_api, documents, pictures):
    capture(window, "homepage.png")

    window._path_entry.set_text(documents)
    window._on_path_entry_activate(window._path_entry)
    window._path_entry.grab_focus()
    window._path_entry.set_position(-1)
    wait(200)
    capture(window, "columns_navigation.png")

    window._path_entry.set_text(pictures)
    window._on_path_entry_activate(window._path_entry)
    window._path_entry.grab_focus()
    window._path_entry.set_position(-1)
    wait(200)
    capture(window, "path_editable.png")

    tab = window._active_tab()
    path_page = tab._path_page
    last_column = path_page._columns[-1]
    row = find_row(last_column, "family_photos")
    if row is not None:
        last_column._list_box.select_row(row)
        wait(100)

        show_color_picker_popup(row, lambda _color: None, selected_color=getattr(row, "color", None))
        wait(200)
        popover = find_popover_on(row)
        if popover is not None:
            capture_popover(popover, "add_color.png")
            popover.popdown()
        wait(100)

        path_page._on_row_context_menu(last_column, row, 40, 20)
        wait(300)
        popover = find_popover_on(row)
        if popover is not None:
            capture_popover(popover, "folder_menu.png")
            popover.popdown()
        wait(100)

    show_properties_dialog(
        window, system_api, "artwork.xcf", os.path.join(pictures, "artwork.xcf"), False
    )
    wait(200)
    capture(window, "file_properties.png")
    close_all_dialogs(window)
    wait(100)

    parameters_dialog = ParametersDialog(lambda *_args: None)
    parameters_dialog.present(window)
    wait(150)
    parameters_dialog._system_icon_row.set_active(True)
    wait(150)
    capture(window, "parameters.png")
    close_all_dialogs(window)
    wait(100)

    window._settings.set_view_mode(UserSettingsEntity.VIEW_MODE_GRID)
    window._on_view_mode_changed(UserSettingsEntity.VIEW_MODE_GRID)
    window._go_to_path(pictures)
    wait(200)
    capture(window, "display_mode_icons.png")

    window._settings.set_view_mode(UserSettingsEntity.VIEW_MODE_DETAILS)
    window._on_view_mode_changed(UserSettingsEntity.VIEW_MODE_DETAILS)
    wait(200)
    capture(window, "display_mode_details.png")

    window._settings.set_view_mode(UserSettingsEntity.VIEW_MODE_COLUMNS)
    window._on_view_mode_changed(UserSettingsEntity.VIEW_MODE_COLUMNS)
    wait(200)
    capture(window, "display_mode_list.png")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # dir="/tmp" explicitly (not tempfile's own default, which can be a
    # deeper sandbox-specific scratch dir) — keeps the demo home shallow,
    # so the ancestor-chain screenshots (columns_navigation, path_editable)
    # show a clean, /home/user-like path instead of several extra
    # irrelevant nested folders.
    home_dir = tempfile.mkdtemp(prefix="dupot_screenshots_home_", dir="/tmp")
    data_dir = tempfile.mkdtemp(prefix="dupot_screenshots_data_", dir="/tmp")
    os.environ["HOME"] = home_dir

    documents, pictures = build_demo_home(home_dir)

    PathConf().set_data_path(data_dir)
    system_api = SystemApi()
    system_api.create_dir(PathConf().get_data_path())

    settings = UserSettingsEntity()
    settings.reset_to_defaults()
    settings.add_favorite("Documents", documents)
    settings.add_favorite("Music", os.path.join(home_dir, "Music"))
    UserSettingsApi(system_api).save()

    system_api.set_folder_color(os.path.join(pictures, "vacation_photos"), VACATION_COLOR)
    system_api.set_folder_color(os.path.join(pictures, "family_photos"), FAMILY_COLOR)

    app = Adw.Application(application_id="org.dupot.filebrowser.screenshots")

    def on_activate(application):
        window = MainWindow(application=application)
        window.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        window.present()
        wait(300)

        print("Generating screenshots...")
        run_scenes(window, system_api, documents, pictures)
        print("Done.")

        application.quit()

    app.connect("activate", on_activate)
    app.run([])

    shutil.rmtree(home_dir, ignore_errors=True)
    shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
