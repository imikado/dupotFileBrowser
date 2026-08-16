import gi

gi.require_version("Adw", "1")

from gi.repository import Adw


def show_confirm_dialog(
    root, heading: str, body: str, confirm_label: str, on_confirm, destructive: bool = True
):
    """Generic Cancel/Confirm Adw.AlertDialog. Calls on_confirm() (no args)
    only if the user picks the confirm response."""
    dialog = Adw.AlertDialog(heading=heading, body=body)
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("confirm", confirm_label)
    dialog.set_default_response("confirm")
    dialog.set_close_response("cancel")
    dialog.set_response_appearance(
        "confirm",
        Adw.ResponseAppearance.DESTRUCTIVE
        if destructive
        else Adw.ResponseAppearance.SUGGESTED,
    )

    def on_response(_dialog, response):
        if response == "confirm":
            on_confirm()

    dialog.connect("response", on_response)
    dialog.present(root)
