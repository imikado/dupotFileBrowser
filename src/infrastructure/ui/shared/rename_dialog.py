import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk


def show_rename_dialog(
    root,
    system_api,
    name: str,
    path: str,
    on_renamed,
    initial_name: str | None = None,
):
    """Adw.AlertDialog asking for a new name for `path` (currently called
    `name`). Validates the destination is free — re-asking, with the
    attempted name kept, if it isn't — performs the rename via
    system_api.move_path, and calls on_renamed(destination) once it
    succeeds. Shows its own error dialog on failure."""
    name_entry = Gtk.Entry()
    name_entry.set_text(initial_name or name)
    name_entry.set_activates_default(True)

    dialog = Adw.AlertDialog(
        heading=_("Rename"),
        body=_('Choose a new name for "{name}".').format(name=name),
    )
    dialog.set_extra_child(name_entry)
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("rename", _("Rename"))
    dialog.set_default_response("rename")
    dialog.set_close_response("cancel")
    dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)

    def on_response(_dialog, response):
        if response != "rename":
            return
        new_name = name_entry.get_text().strip()
        if not new_name or new_name == name:
            return
        parent = system_api.get_parent_dir(path)
        destination = os.path.join(parent, new_name)
        if system_api.file_exists(destination):
            # Still taken: ask again, keeping the attempted name so the
            # user can tweak it instead of retyping from scratch.
            GLib.idle_add(
                show_rename_dialog, root, system_api, name, path, on_renamed, new_name
            )
            return
        _perform_rename(root, system_api, name, path, destination, on_renamed)

    dialog.connect("response", on_response)
    dialog.present(root)


def _perform_rename(root, system_api, name: str, path: str, destination: str, on_renamed):
    # move_path() runs in-process (shutil.move), same as the Cut/Paste
    # "move" job (see SystemApi.move_path). A rename is a same-directory
    # move, so it runs synchronously — it's a plain filesystem rename, not
    # a data copy.
    error = system_api.move_path(path, destination)
    if error is not None:
        _show_rename_error(root, name, error)
        return
    on_renamed(destination)


def _show_rename_error(root, name: str, output: str):
    body = _('Could not rename "{name}".').format(name=name)
    if output.strip():
        body += "\n\n" + output.strip()
    dialog = Adw.AlertDialog(heading=_("Rename failed"), body=body)
    dialog.add_response("ok", _("OK"))
    dialog.present(root)
