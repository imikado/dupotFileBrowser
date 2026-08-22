import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk

# (archive_format passed to SystemApi.compress_path, label, file extension).
# Built by a function rather than kept as a module-level constant so the
# labels are translated lazily (picked up on a language switch), same
# reasoning as FileEntryEntity's _ICON_KEY_TYPE_LABEL.
def _format_choices() -> list[tuple[str, str, str]]:
    return [
        ("zip", _("ZIP archive (.zip)"), ".zip"),
        ("tar.gz", _("Tar.gz archive (.tar.gz)"), ".tar.gz"),
        ("tar.bz2", _("Tar.bz2 archive (.tar.bz2)"), ".tar.bz2"),
        ("tar.xz", _("Tar.xz archive (.tar.xz)"), ".tar.xz"),
        ("tar", _("Tar archive (.tar)"), ".tar"),
    ]


def show_compress_dialog(
    root,
    system_api,
    name: str,
    path: str,
    on_confirmed,
    initial_name: str | None = None,
):
    """Adw.AlertDialog asking for an archive name and format for `path`
    (a folder, currently called `name`) — same "ask for a name, re-ask on
    collision" shape as show_rename_dialog. This dialog only resolves the
    name/format/collision, it never runs the compression itself:
    compressing a large folder can take a while, so once a free
    destination is settled on, this hands (path, destination,
    archive_format) to `on_confirmed` and lets the caller queue it
    through MainWindow's background job queue — the same one copy/move
    (paste) jobs run through, so a compress never blocks the UI or races
    another file operation."""
    format_choices = _format_choices()

    name_entry = Gtk.Entry()
    name_entry.set_text(initial_name or name)
    name_entry.set_activates_default(True)

    format_dropdown = Gtk.DropDown.new_from_strings([label for _key, label, _ext in format_choices])
    format_dropdown.set_selected(0)  # defaults to ZIP — the most broadly compatible pick

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.append(name_entry)
    box.append(format_dropdown)

    dialog = Adw.AlertDialog(
        heading=_("Compress"),
        body=_('Choose an archive name and format for "{name}".').format(name=name),
    )
    dialog.set_extra_child(box)
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("compress", _("Compress"))
    dialog.set_default_response("compress")
    dialog.set_close_response("cancel")
    dialog.set_response_appearance("compress", Adw.ResponseAppearance.SUGGESTED)

    def on_response(_dialog, response):
        if response != "compress":
            return
        archive_name = name_entry.get_text().strip()
        if not archive_name:
            return
        archive_format, _label, extension = format_choices[format_dropdown.get_selected()]
        parent = system_api.get_parent_dir(path)
        destination = os.path.join(parent, archive_name + extension)
        if system_api.file_exists(destination):
            # Still taken: ask again, keeping the attempted name so the
            # user can tweak it instead of retyping from scratch.
            GLib.idle_add(
                show_compress_dialog,
                root,
                system_api,
                name,
                path,
                on_confirmed,
                archive_name,
            )
            return
        on_confirmed(path, destination, archive_format)

    dialog.connect("response", on_response)
    dialog.present(root)
