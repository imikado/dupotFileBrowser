from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk

from infrastructure.ui.shared.confirm_dialog import show_confirm_dialog
from infrastructure.ui.shared.file_icons import build_icon_image


class TrashPage(Gtk.Box):
    """Flat list of everything in the Trash, via SystemApi.list_trash()
    (reads Trash/files + Trash/info/*.trashinfo directly) — unlike
    browsing ~/.local/share/Trash/files as a plain folder, this gets each
    item's original location, deletion date, and a working Restore
    action, with no dependency on the gvfsd-trash daemon being installed
    or running."""

    def __init__(self, system_api):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._system_api = system_api

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_top(12)
        header.set_margin_bottom(12)
        header.set_margin_start(16)
        header.set_margin_end(16)

        title = Gtk.Label(label=_("Trash"))
        title.add_css_class("title-2")
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)
        header.append(title)

        self._empty_trash_button = Gtk.Button(label=_("Empty Trash"))
        self._empty_trash_button.add_css_class("destructive-action")
        self._empty_trash_button.connect("clicked", self._on_empty_trash_clicked)
        header.append(self._empty_trash_button)

        self.append(header)
        self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        self._list_box = Gtk.ListBox()
        self._list_box.add_css_class("boxed-list")
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list_box.set_margin_top(6)
        self._list_box.set_margin_start(12)
        self._list_box.set_margin_end(12)

        self._empty_label = Gtk.Label(label=_("Trash is empty"))
        self._empty_label.add_css_class("dim-label")
        self._empty_label.set_valign(Gtk.Align.START)
        self._empty_label.set_margin_top(24)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self._list_box)

        self._stack = Gtk.Stack()
        self._stack.set_vexpand(True)
        self._stack.add_named(scroll, "list")
        self._stack.add_named(self._empty_label, "empty")

        self.append(self._stack)

    def refresh(self):
        child = self._list_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._list_box.remove(child)
            child = next_child

        entry_list = self._system_api.list_trash()
        self._empty_trash_button.set_sensitive(bool(entry_list))

        for entry in entry_list:
            row = Adw.ActionRow()
            row.set_title(GLib.markup_escape_text(entry.display_name))
            row.set_title_lines(1)
            subtitle_parts = []
            if entry.original_path:
                subtitle_parts.append(entry.original_path)
            deleted_label = _format_deletion_date(entry.deletion_date)
            if deleted_label:
                subtitle_parts.append(_("Deleted {when}").format(when=deleted_label))
            if subtitle_parts:
                row.set_subtitle(GLib.markup_escape_text(" — ".join(subtitle_parts)))
                row.set_subtitle_lines(1)
            row.add_prefix(build_icon_image(entry.get_icon_key()))

            restore_button = Gtk.Button()
            restore_button.set_child(build_icon_image("edit-undo"))
            restore_button.set_tooltip_text(_("Restore"))
            restore_button.add_css_class("flat")
            restore_button.set_valign(Gtk.Align.CENTER)
            restore_button.connect(
                "clicked", lambda _b, e=entry: self._on_restore_clicked(e)
            )
            row.add_suffix(restore_button)

            delete_button = Gtk.Button()
            delete_button.set_child(build_icon_image("user-trash"))
            delete_button.set_tooltip_text(_("Delete Permanently"))
            delete_button.add_css_class("flat")
            delete_button.set_valign(Gtk.Align.CENTER)
            delete_button.connect(
                "clicked", lambda _b, e=entry: self._on_delete_clicked(e)
            )
            row.add_suffix(delete_button)

            self._list_box.append(row)

        self._stack.set_visible_child_name("list" if entry_list else "empty")

    def _on_restore_clicked(self, entry):
        if not entry.original_path:
            self._show_error(
                _("Could not restore"),
                _('"{name}" has no recorded original location.').format(
                    name=entry.display_name
                ),
            )
            return
        if self._system_api.file_exists(entry.original_path):
            self._show_error(
                _("Could not restore"),
                _('"{name}" already exists at its original location:\n{path}').format(
                    name=entry.display_name, path=entry.original_path
                ),
            )
            return
        if not self._system_api.restore_trash_entry(entry.trashed_path, entry.original_path):
            self._show_error(
                _("Could not restore"),
                _('"{name}" could not be restored.').format(name=entry.display_name),
            )
            return
        self.refresh()

    def _on_delete_clicked(self, entry):
        show_confirm_dialog(
            self.get_root(),
            _("Delete Permanently?"),
            _(
                '"{name}" will be permanently deleted. This cannot be undone.'
            ).format(name=entry.display_name),
            _("Delete Permanently"),
            lambda: self._perform_delete(entry),
        )

    def _perform_delete(self, entry):
        if not self._system_api.delete_trash_entry(entry.trashed_path):
            self._show_error(
                _("Could not delete"),
                _('"{name}" could not be permanently deleted.').format(
                    name=entry.display_name
                ),
            )
            return
        self.refresh()

    def _on_empty_trash_clicked(self, _button):
        show_confirm_dialog(
            self.get_root(),
            _("Empty Trash?"),
            _("All items in the Trash will be permanently deleted. This cannot be undone."),
            _("Empty Trash"),
            self._perform_empty_trash,
        )

    def _perform_empty_trash(self):
        if not self._system_api.empty_trash():
            self._show_error(
                _("Could not empty Trash"),
                _("Some items could not be permanently deleted."),
            )
        self.refresh()

    def _show_error(self, heading: str, body: str):
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("ok", _("OK"))
        dialog.present(self.get_root())


def _format_deletion_date(deletion_date: str) -> str:
    """"2024-01-15T10:30:00" -> "2024-01-15 10:30", or the raw string back
    if it's not parseable. Plain datetime.fromisoformat(), not
    GLib.DateTime.new_from_iso8601() — the latter raises TypeError (not
    just returning None) on a parse failure in PyGObject, which was
    silently aborting refresh() before any row got added."""
    if not deletion_date:
        return ""
    try:
        return datetime.fromisoformat(deletion_date).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return deletion_date
