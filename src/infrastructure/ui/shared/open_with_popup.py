import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib, Gtk

from infrastructure.ui.shared.popup_shared import close_then_run, popup_deferred


def get_app_choices(content_type: str):
    """(app_infos, default_app, default_index) for `content_type` — every
    application GIO has registered for it, the system default among them
    (None if there isn't one registered), and that default's index in
    app_infos (0 if there's no default or app_infos is empty). Shared by
    this popover and properties_dialog.py's "Open With" tab."""
    default_app = Gio.AppInfo.get_default_for_type(content_type, False)
    app_infos = _dedupe(Gio.AppInfo.get_all_for_type(content_type), default_app)
    default_index = 0
    if default_app is not None:
        for i, app in enumerate(app_infos):
            if app.get_id() == default_app.get_id():
                default_index = i
                break
    return app_infos, default_app, default_index


def _app_key(app_info):
    # Same binary registered under two different .desktop ids (a distro
    # package's entry plus one the app wrote for itself, or the same
    # .desktop picked up from more than one applications/ directory) is
    # the actual cause of the duplicate rows — id alone doesn't catch it
    # since that's exactly the field that differs between them. basename
    # drops path-prefix differences like "/usr/bin/x" vs "x".
    executable = os.path.basename(app_info.get_executable() or "")
    return (executable, app_info.get_display_name() or app_info.get_name())


def _dedupe(app_infos, default_app):
    """Collapses same-app duplicates (see _app_key), keeping whichever
    one matches `default_app`'s id when a duplicate group has it — so
    the default-detection loop in get_app_choices can still find it by
    id afterwards — otherwise the first one GIO returned."""
    default_id = default_app.get_id() if default_app is not None else None
    chosen: dict[tuple, Gio.AppInfo] = {}
    order = []
    for app in app_infos:
        key = _app_key(app)
        if key not in chosen:
            chosen[key] = app
            order.append(key)
        elif app.get_id() == default_id:
            chosen[key] = app
    return [chosen[key] for key in order]


def show_open_with_popup(row, path: str, system_api):
    """Popover with a dropdown of every application registered for this
    file's type, the system default pre-selected, plus a way to browse
    the full application list for anything not registered."""
    content_type = system_api.get_content_type(path)
    app_infos, _default_app, default_index = get_app_choices(content_type)

    other_label = _("Other application…")
    names = [app.get_display_name() or app.get_name() for app in app_infos]
    names.append(other_label)

    if not app_infos:
        default_index = len(names) - 1  # nothing registered: land on "Other…"

    dropdown = Gtk.DropDown.new_from_strings(names)
    dropdown.set_selected(max(default_index, 0))

    open_button = Gtk.Button(label=_("Open"))
    open_button.add_css_class("suggested-action")

    cancel_button = Gtk.Button(label=_("Cancel"))

    buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    buttons_box.set_halign(Gtk.Align.END)
    buttons_box.append(cancel_button)
    buttons_box.append(open_button)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.set_margin_top(8)
    box.set_margin_bottom(8)
    box.set_margin_start(8)
    box.set_margin_end(8)
    box.append(dropdown)
    box.append(buttons_box)

    popover = Gtk.Popover()
    popover.set_child(box)
    popover.set_parent(row)
    popover.set_autohide(True)
    popover.connect("closed", lambda p: p.unparent())

    def _open():
        index = dropdown.get_selected()
        if 0 <= index < len(app_infos):
            app_infos[index].launch([Gio.File.new_for_path(path)], None)
        else:
            show_app_chooser_dialog(row.get_root(), path, content_type)

    # See close_then_run: don't popdown() synchronously from inside
    # these buttons' own "clicked" handler (Flatpak-observed GTK
    # bookkeeping corruption that can silently drop the click).
    open_button.connect("clicked", lambda _b: close_then_run(popover, _open))
    # Filet de sécurité explicite : même si l'autohide/Escape est
    # perturbé par le popup() différé (voir popup_deferred), un clic sur
    # Cancel referme toujours la popover.
    cancel_button.connect("clicked", lambda _b: close_then_run(popover, lambda: None))
    # See popup_deferred: this popover is opened from inside the
    # right-click menu's own "Open With…" item activation, so it must not
    # popup() synchronously either.
    GLib.idle_add(popup_deferred, popover, priority=GLib.PRIORITY_HIGH_IDLE)


def show_app_chooser_dialog(root, path: str, content_type: str):
    """Full GTK app chooser, for content types with no app already
    registered (or when the user asks for "Other application") — also
    used by properties_dialog.py's "Open With" tab."""
    dialog = Gtk.AppChooserDialog.new_for_content_type(
        root, Gtk.DialogFlags.MODAL, content_type
    )
    dialog.connect("response", _on_open_with_dialog_response, path)
    dialog.present()


def _on_open_with_dialog_response(dialog, response, path: str):
    if response == Gtk.ResponseType.OK:
        app_info = dialog.get_widget().get_app_info()
        if app_info is not None:
            app_info.launch([Gio.File.new_for_path(path)], None)
    dialog.destroy()
