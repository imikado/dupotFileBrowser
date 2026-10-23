use std::path::{Path, PathBuf};
use std::rc::Rc;

use gtk::gio;
use gtk::prelude::*;

use crate::infrastructure::api::file_system_api::content_type;
use crate::infrastructure::service::i18n_service::tr;
use crate::infrastructure::ui::app_context::AppContext;
use crate::infrastructure::ui::shared::alert_dialog::root_of;
use crate::infrastructure::ui::shared::context_menu::{
    attached_popover, popup_deferred, run_then_close,
};

/// Applications registered for a content type, the system default among
/// them (`default_index` is 0 without one).
pub struct AppChoices {
    pub apps: Vec<gio::AppInfo>,
    pub default: Option<gio::AppInfo>,
    pub default_index: usize,
}

pub fn app_label(app: &gio::AppInfo) -> String {
    app.display_name().to_string()
}

/// Same binary registered under several desktop ids is listed once,
/// keeping the default's id when it is one of them.
pub fn app_choices(content_type: &str) -> AppChoices {
    let default = gio::AppInfo::default_for_type(content_type, false);
    let default_id = default.as_ref().and_then(|app| app.id());
    let key = |app: &gio::AppInfo| {
        let executable = app
            .executable()
            .file_name()
            .map(|name| name.to_string_lossy().into_owned())
            .unwrap_or_default();
        (executable, app_label(app))
    };
    let mut apps: Vec<gio::AppInfo> = Vec::new();
    for app in gio::AppInfo::all_for_type(content_type) {
        match apps.iter().position(|kept| key(kept) == key(&app)) {
            None => apps.push(app),
            Some(index) if app.id().is_some() && app.id() == default_id => apps[index] = app,
            Some(_) => {}
        }
    }
    let default_index = apps
        .iter()
        .position(|app| default_id.is_some() && app.id() == default_id)
        .unwrap_or(0);
    AppChoices {
        apps,
        default,
        default_index,
    }
}

pub fn launch(app: &gio::AppInfo, path: &Path) {
    let _ = app.launch(&[gio::File::for_path(path)], gio::AppLaunchContext::NONE);
}

/// GTK's full application chooser, for "Other application…".
#[allow(deprecated)]
pub fn show_app_chooser_dialog(parent: &gtk::Widget, path: &Path, content_type: &str) {
    let window = root_of(parent).downcast::<gtk::Window>().ok();
    let dialog = gtk::AppChooserDialog::for_content_type(
        window.as_ref(),
        gtk::DialogFlags::MODAL,
        content_type,
    );
    let path = path.to_path_buf();
    dialog.connect_response(move |dialog, response| {
        if response == gtk::ResponseType::Ok
            && let Some(app) = dialog.app_info()
        {
            launch(&app, &path);
        }
        dialog.destroy();
    });
    dialog.present();
}

/// Dropdown of the applications registered for the file's type, default
/// preselected. In Flatpak GIO can't list host applications: the portal's
/// own chooser is used instead.
pub fn show_open_with_popup(parent: &gtk::Widget, ctx: &Rc<AppContext>, path: &Path) {
    if ctx.desktop.is_sandboxed() {
        let _ = ctx.desktop.open_with_chooser(path);
        return;
    }
    let content_type = content_type(path);
    let choices = app_choices(&content_type);
    let mut names: Vec<String> = choices.apps.iter().map(app_label).collect();
    names.push(tr("Other application…"));
    let name_refs: Vec<&str> = names.iter().map(String::as_str).collect();
    let dropdown = gtk::DropDown::from_strings(&name_refs);
    let selected = if choices.apps.is_empty() {
        names.len() - 1
    } else {
        choices.default_index
    };
    dropdown.set_selected(selected as u32);

    let open_button = gtk::Button::with_label(&tr("Open"));
    open_button.add_css_class("suggested-action");
    let cancel_button = gtk::Button::with_label(&tr("Cancel"));
    let buttons = gtk::Box::new(gtk::Orientation::Horizontal, 8);
    buttons.set_halign(gtk::Align::End);
    buttons.append(&cancel_button);
    buttons.append(&open_button);

    let content = gtk::Box::new(gtk::Orientation::Vertical, 8);
    content.set_margin_top(8);
    content.set_margin_bottom(8);
    content.set_margin_start(8);
    content.set_margin_end(8);
    content.append(&dropdown);
    content.append(&buttons);

    let popover = attached_popover(parent, &content);
    let apps = Rc::new(choices.apps);
    let (parent, path) = (parent.clone(), PathBuf::from(path));
    {
        let popover = popover.clone();
        open_button.connect_clicked(move |_| {
            let (apps, parent, path, content_type) = (
                apps.clone(),
                parent.clone(),
                path.clone(),
                content_type.clone(),
            );
            let index = dropdown.selected() as usize;
            run_then_close(&popover, move || match apps.get(index) {
                Some(app) => launch(app, &path),
                None => show_app_chooser_dialog(&parent, &path, &content_type),
            });
        });
    }
    {
        let popover = popover.clone();
        cancel_button.connect_clicked(move |_| run_then_close(&popover, || {}));
    }
    popup_deferred(&popover);
}
