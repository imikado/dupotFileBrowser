//! Small `AdwAlertDialog` helpers.

use adw::prelude::*;

use crate::infrastructure::service::i18n_service::tr;

/// The window holding `widget` (or `widget` itself when not shown yet):
/// what dialogs are presented on.
pub fn root_of(widget: &impl IsA<gtk::Widget>) -> gtk::Widget {
    widget
        .root()
        .map_or_else(|| widget.clone().upcast(), |root| root.upcast())
}

pub fn show_error(parent: &impl IsA<gtk::Widget>, heading: &str, body: &str) {
    let dialog = adw::AlertDialog::new(Some(heading), Some(body));
    dialog.add_response("ok", &tr("OK"));
    dialog.present(Some(&root_of(parent)));
}

/// Cancel / confirm; `on_confirm` only runs on confirm.
pub fn show_confirm(
    parent: &impl IsA<gtk::Widget>,
    heading: &str,
    body: &str,
    confirm_label: &str,
    destructive: bool,
    on_confirm: impl Fn() + 'static,
) {
    let dialog = adw::AlertDialog::new(Some(heading), Some(body));
    dialog.add_response("cancel", &tr("Cancel"));
    dialog.add_response("confirm", confirm_label);
    dialog.set_default_response(Some("confirm"));
    dialog.set_close_response("cancel");
    dialog.set_response_appearance(
        "confirm",
        if destructive {
            adw::ResponseAppearance::Destructive
        } else {
            adw::ResponseAppearance::Suggested
        },
    );
    dialog.connect_response(None, move |_, response| {
        if response == "confirm" {
            on_confirm();
        }
    });
    dialog.present(Some(&root_of(parent)));
}

/// Asks for a name in an entry prefilled with `initial`; `on_name` gets the
/// raw text when the user confirms.
pub fn ask_name(
    parent: &impl IsA<gtk::Widget>,
    heading: &str,
    body: &str,
    action_label: &str,
    initial: &str,
    extra: Option<&gtk::Widget>,
    on_name: impl Fn(String) + 'static,
) {
    let entry = gtk::Entry::new();
    entry.set_text(initial);
    entry.set_activates_default(true);
    let content = gtk::Box::new(gtk::Orientation::Vertical, 8);
    content.append(&entry);
    if let Some(extra) = extra {
        content.append(extra);
    }

    let dialog = adw::AlertDialog::new(Some(heading), Some(body));
    dialog.set_extra_child(Some(&content));
    dialog.add_response("cancel", &tr("Cancel"));
    dialog.add_response("ok", action_label);
    dialog.set_default_response(Some("ok"));
    dialog.set_close_response("cancel");
    dialog.set_response_appearance("ok", adw::ResponseAppearance::Suggested);
    dialog.connect_response(None, move |_, response| {
        if response == "ok" {
            on_name(entry.text().to_string());
        }
    });
    dialog.present(Some(&root_of(parent)));
}
