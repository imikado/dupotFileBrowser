import stat

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")

from gi.repository import Adw, Gio, GLib, Gtk

from domain.entity.file_properties_entity import FilePropertiesEntity
from infrastructure.ui.shared.open_with_popup import get_app_choices, show_app_chooser_dialog

# rwx bit, per who-class — drives both the checkbox grid and the mode int
# rebuilt from it (see _add_permissions_page/_apply_permissions).
_WHO_CLASSES = [
    (stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR),
    (stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP),
    (stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH),
]


def show_properties_dialog(root, system_api, name: str, path: str, is_dir: bool):
    """Adw.PreferencesDialog listing `path`'s filesystem properties.
    Adw.PreferencesPage switches to a tabbed layout on its own once more
    than one page is added, so each "tab" below (General, Permissions,
    and — files only — Open With) is just its own page: General/type/
    size/dates, Unix owner/group/editable mode, and (for a file) the
    registered applications for its mime type, mirroring
    Nemo/Nautilus/Files."""
    properties: FilePropertiesEntity = system_api.get_file_properties(path)

    dialog = Adw.PreferencesDialog()
    dialog.set_title(name)
    dialog.set_content_width(420)
    # Tall enough that the permissions grid + Open With tab don't need
    # their own inner scroll on a normal window size.
    dialog.set_content_height(560)

    general_page = Adw.PreferencesPage(title=_("General"), icon_name="dialog-information-symbolic")
    dialog.add(general_page)
    general_group = Adw.PreferencesGroup()
    general_page.add(general_group)
    _add_row(general_group, _("Name"), properties.name)
    _add_row(general_group, _("Location"), properties.location)
    _add_row(general_group, _("Type"), properties.type_description)
    _add_row(
        general_group,
        _("Contains") if properties.is_dir else _("Size"),
        properties.size_display,
    )
    _add_row(general_group, _("Modified"), properties.modified_display)

    _add_permissions_page(dialog, system_api, properties, path)

    if not is_dir:
        _add_open_with_page(dialog, root, system_api, path)

    dialog.present(root)


def _add_row(group: Adw.PreferencesGroup, title: str, value: str | None):
    row = Adw.ActionRow()
    row.set_title(title)
    row.set_subtitle(value if value else "—")
    # A path or a long type name should be copy-pastable, not just visible.
    row.set_subtitle_selectable(True)
    group.add(row)


def _add_permissions_page(
    dialog: Adw.PreferencesDialog, system_api, properties: FilePropertiesEntity, path: str
):
    page = Adw.PreferencesPage(title=_("Permissions"), icon_name="system-lock-screen-symbolic")
    dialog.add(page)

    info_group = Adw.PreferencesGroup()
    page.add(info_group)
    _add_row(info_group, _("Owner"), properties.owner)
    _add_row(info_group, _("Group"), properties.group)

    access_group = Adw.PreferencesGroup()
    access_group.set_title(_("Access"))
    page.add(access_group)

    if properties.mode is None:
        # Nothing to edit — get_file_properties couldn't even os.stat it.
        _add_row(access_group, _("Access"), properties.permissions_display)
        return

    mode_row = Adw.ActionRow()
    mode_row.set_title(_("Current"))
    mode_row.set_subtitle(_mode_to_symbolic(properties.mode, properties.is_dir))
    access_group.add(mode_row)

    # One ActionRow per who-class, R/W/X checkboxes as suffixes — not a
    # bare Gtk.Grid dropped into the group. A raw non-row widget added via
    # Adw.PreferencesGroup.add() sits in the list but never reliably gets
    # its clicks (that's why the old Apply button did nothing); suffix
    # widgets on a real row are the pattern already proven elsewhere in
    # this app (see TrashPage's restore/delete buttons).
    # Created before the checkboxes below so their "toggled" handler can
    # reference it — starts disabled (nothing's been changed yet) and
    # only turns on once a checkbox actually moves away from the mode on
    # disk, so its enabled state always answers "is there anything to
    # apply right now".
    apply_button = Gtk.Button(label=_("Apply"))
    apply_button.add_css_class("suggested-action")
    apply_button.set_valign(Gtk.Align.CENTER)
    apply_button.set_sensitive(False)

    who_labels = [_("Owner"), _("Group"), _("Others")]
    perm_labels = [_("R"), _("W"), _("X")]
    checks: list[list[Gtk.CheckButton]] = []
    for who_label, bits in zip(who_labels, _WHO_CLASSES):
        row = Adw.ActionRow()
        row.set_title(who_label)
        row_checks = []
        for perm_label, bit in zip(perm_labels, bits):
            pair = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            pair.set_valign(Gtk.Align.CENTER)
            pair.append(Gtk.Label(label=perm_label))
            check = Gtk.CheckButton()
            check.set_active(bool(properties.mode & bit))
            pair.append(check)
            row.add_suffix(pair)
            row_checks.append(check)
        checks.append(row_checks)
        access_group.add(row)

    def _on_check_toggled(*_args):
        new_mode = _mode_from_checks(checks)
        mode_row.set_subtitle(_mode_to_symbolic(new_mode, properties.is_dir))
        apply_button.set_sensitive(new_mode != properties.mode)

    for row_checks in checks:
        for check in row_checks:
            check.connect("toggled", _on_check_toggled)

    apply_row = Adw.ActionRow()
    apply_row.set_title(_("Apply changes"))
    apply_button.connect(
        "clicked",
        lambda _b: _apply_permissions(
            dialog, system_api, path, checks, mode_row, apply_button, properties
        ),
    )
    apply_row.add_suffix(apply_button)
    apply_row.set_activatable_widget(apply_button)
    access_group.add(apply_row)


def _mode_from_checks(checks: list[list[Gtk.CheckButton]]) -> int:
    mode = 0
    for row_checks, bits in zip(checks, _WHO_CLASSES):
        for check, bit in zip(row_checks, bits):
            if check.get_active():
                mode |= bit
    return mode


def _mode_to_symbolic(mode: int, is_dir: bool) -> str:
    type_char = "d" if is_dir else "-"
    perm_chars = ""
    for bits in _WHO_CLASSES:
        for bit, char in zip(bits, "rwx"):
            perm_chars += char if mode & bit else "-"
    return f"{type_char}{perm_chars} ({mode:03o})"


def _apply_permissions(
    dialog: Adw.PreferencesDialog,
    system_api,
    path: str,
    checks: list[list[Gtk.CheckButton]],
    mode_row: Adw.ActionRow,
    apply_button: Gtk.Button,
    properties: FilePropertiesEntity,
):
    new_mode = _mode_from_checks(checks)
    if system_api.set_file_permissions(path, new_mode):
        mode_row.set_subtitle(_mode_to_symbolic(new_mode, properties.is_dir))
        # New baseline: the checkboxes now match what's on disk, so
        # there's nothing pending until the next toggle moves away from it.
        properties.mode = new_mode
        apply_button.set_sensitive(False)
    else:
        # Left enabled — nothing was actually applied, so the user can
        # still retry (e.g. after fixing the underlying permission issue).
        _show_permissions_error(dialog)


def _show_permissions_error(root):
    dialog = Adw.AlertDialog(
        heading=_("Could not change permissions"),
        body=_("You may not own this file, or lack permission to change it."),
    )
    dialog.add_response("ok", _("OK"))
    dialog.present(root)


def _add_open_with_page_flatpak(group: Adw.PreferencesGroup, dialog, system_api, path: str):
    row = Adw.ActionRow()
    row.set_title(_("Open with"))
    row.set_subtitle(_("Choose an application to open this file"))
    button = Gtk.Button(label=_("Choose…"))
    button.set_valign(Gtk.Align.CENTER)

    def _choose(_b):
        system_api.open_with_chooser(path)
        dialog.close()

    button.connect("clicked", _choose)
    row.add_suffix(button)
    row.set_activatable_widget(button)
    group.add(row)


def _add_open_with_page(dialog: Adw.PreferencesDialog, root, system_api, path: str):
    page = Adw.PreferencesPage(title=_("Open With"), icon_name="document-open-symbolic")
    dialog.add(page)
    group = Adw.PreferencesGroup()
    page.add(group)

    if system_api.is_running_flatpak():
        # See open_with_popup.show_open_with_popup / SystemApi.open_with_chooser:
        # GIO can neither list nor set host apps from inside the sandbox, so
        # the dropdown/default-application/set-default rows below would all
        # be empty or meaningless here — hand off to the portal's own native
        # chooser instead, same as the right-click "Open With…" entry.
        _add_open_with_page_flatpak(group, dialog, system_api, path)
        return

    content_type = system_api.get_content_type(path)
    app_infos, default_app, default_index = get_app_choices(content_type)

    default_row = Adw.ActionRow()
    default_row.set_title(_("Default application"))
    default_row.set_subtitle(_app_label(default_app))
    group.add(default_row)

    other_label = _("Other application…")
    names = [app.get_display_name() or app.get_name() for app in app_infos] + [other_label]

    combo_row = Adw.ComboRow()
    combo_row.set_title(_("Open with"))
    combo_row.set_model(Gtk.StringList.new(names))
    combo_row.set_selected(default_index if app_infos else len(names) - 1)
    group.add(combo_row)

    # "Set as Default" is its own row/button, separate from "Open" below —
    # picking an app in the dropdown only launches it once until this is
    # pressed; that's the missing piece that made the default look stuck.
    set_default_row = Adw.ActionRow()
    set_default_row.set_title(_("Make default"))
    set_default_button = Gtk.Button(label=_("Set as Default"))
    set_default_button.set_valign(Gtk.Align.CENTER)
    set_default_row.add_suffix(set_default_button)
    set_default_row.set_activatable_widget(set_default_button)
    group.add(set_default_row)

    def _update_set_default_sensitivity(*_args):
        index = combo_row.get_selected()
        is_real_app = 0 <= index < len(app_infos)
        already_default = (
            is_real_app
            and default_app is not None
            and app_infos[index].get_id() == default_app.get_id()
        )
        set_default_button.set_sensitive(is_real_app and not already_default)

    combo_row.connect("notify::selected", _update_set_default_sensitivity)
    _update_set_default_sensitivity()

    set_default_button.connect(
        "clicked",
        lambda _b: _set_default_app(
            root, default_row, combo_row, app_infos, content_type, set_default_button
        ),
    )

    open_row = Adw.ActionRow()
    open_row.set_title(_("Launch"))
    open_button = Gtk.Button(label=_("Open"))
    open_button.add_css_class("suggested-action")
    open_button.set_valign(Gtk.Align.CENTER)
    open_button.connect(
        "clicked",
        lambda _b: _open_selected_app(dialog, root, combo_row, app_infos, path, content_type),
    )
    open_row.add_suffix(open_button)
    open_row.set_activatable_widget(open_button)
    group.add(open_row)


def _app_label(app_info) -> str:
    if app_info is None:
        return _("None")
    return app_info.get_display_name() or app_info.get_name()


def _set_default_app(
    root,
    default_row: Adw.ActionRow,
    combo_row: Adw.ComboRow,
    app_infos,
    content_type: str,
    set_default_button: Gtk.Button,
):
    index = combo_row.get_selected()
    if not (0 <= index < len(app_infos)):
        return
    app_info = app_infos[index]
    try:
        app_info.set_as_default_for_type(content_type)
    except GLib.Error:
        _show_set_default_error(root)
        return
    default_row.set_subtitle(_app_label(app_info))
    set_default_button.set_sensitive(False)


def _show_set_default_error(root):
    dialog = Adw.AlertDialog(
        heading=_("Could not change the default application"),
        body=_("The system refused to register this application as the default for this file type."),
    )
    dialog.add_response("ok", _("OK"))
    dialog.present(root)


def _open_selected_app(
    dialog: Adw.PreferencesDialog,
    root,
    combo_row: Adw.ComboRow,
    app_infos,
    path: str,
    content_type: str,
):
    index = combo_row.get_selected()
    if 0 <= index < len(app_infos):
        app_infos[index].launch([Gio.File.new_for_path(path)], None)
        dialog.close()
    else:
        show_app_chooser_dialog(root, path, content_type)
