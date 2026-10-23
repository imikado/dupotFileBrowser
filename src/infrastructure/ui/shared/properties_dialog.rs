//! Properties: General, Permissions and (files) Open With tabs, each an
//! `AdwPreferencesPage` (the dialog shows tabs once it has several).

use std::cell::Cell;
use std::path::{Path, PathBuf};
use std::rc::Rc;

use adw::prelude::*;
use gtk::{gio, glib};

use crate::domain::entity::file_properties_entity::FilePropertiesEntity;
use crate::domain::shared::path::file_name;
use crate::domain::shared::permissions::{WHO_CLASSES, mode_from_flags, mode_to_symbolic};
use crate::infrastructure::api::file_system_api::content_type;
use crate::infrastructure::service::i18n_service::{tr, trf};
use crate::infrastructure::ui::app_context::AppContext;
use crate::infrastructure::ui::shared::alert_dialog::{root_of, show_error};
use crate::infrastructure::ui::shared::open_with_popup::{
    app_choices, app_label, launch, show_app_chooser_dialog,
};

/// `YYYY-MM-DD hh:mm` in local time.
pub fn format_timestamp(seconds: i64) -> String {
    glib::DateTime::from_unix_local(seconds)
        .and_then(|date| date.format("%Y-%m-%d %H:%M"))
        .map(|text| text.to_string())
        .unwrap_or_default()
}

fn add_row(group: &adw::PreferencesGroup, title: &str, value: Option<&str>) -> adw::ActionRow {
    let row = adw::ActionRow::new();
    row.set_title(title);
    row.set_subtitle(&glib::markup_escape_text(
        value.filter(|v| !v.is_empty()).unwrap_or("—"),
    ));
    row.set_subtitle_selectable(true);
    group.add(&row);
    row
}

pub fn show_properties_dialog(parent: &gtk::Widget, ctx: &Rc<AppContext>, path: &Path) {
    let properties = ctx.file_system.file_properties(path);
    let dialog = adw::PreferencesDialog::new();
    dialog.set_title(&file_name(path));
    dialog.set_content_width(420);
    dialog.set_content_height(560);

    let general = adw::PreferencesPage::new();
    general.set_title(&tr("General"));
    general.set_icon_name(Some("dialog-information-symbolic"));
    dialog.add(&general);
    let group = adw::PreferencesGroup::new();
    general.add(&group);
    add_row(&group, &tr("Name"), Some(&properties.name));
    add_row(&group, &tr("Location"), Some(&properties.location));
    add_row(&group, &tr("Type"), Some(&properties.type_description));
    if properties.is_dir {
        let count = properties
            .item_count
            .map(|count| trf("{count} items", &[("count", &count.to_string())]));
        add_row(&group, &tr("Contains"), count.as_deref());
        add_dir_size_row(&group, ctx, path);
    } else {
        let size = properties
            .size
            .map(|size| glib::format_size(size).to_string());
        add_row(&group, &tr("Size"), size.as_deref());
    }
    let modified = properties.modified.map(format_timestamp);
    add_row(&group, &tr("Modified"), modified.as_deref());

    add_permissions_page(&dialog, ctx, &properties, path);
    if !properties.is_dir {
        add_open_with_page(&dialog, parent, ctx, path);
    }
    dialog.present(Some(&root_of(parent)));
}

/// Total size of a folder, walked in the background: shows "Calculating…"
/// until done.
fn add_dir_size_row(group: &adw::PreferencesGroup, ctx: &Rc<AppContext>, path: &Path) {
    let row = add_row(group, &tr("Size"), Some(&tr("Calculating…")));
    row.set_subtitle_selectable(false);
    let file_system = ctx.file_system.clone();
    let path = path.to_path_buf();
    let weak_row = row.downgrade();
    glib::spawn_future_local(async move {
        let Ok(total) = gio::spawn_blocking(move || file_system.dir_size(&path)).await else {
            return;
        };
        if let Some(row) = weak_row.upgrade() {
            row.set_subtitle(&glib::format_size(total));
            row.set_subtitle_selectable(true);
        }
    });
}

fn add_permissions_page(
    dialog: &adw::PreferencesDialog,
    ctx: &Rc<AppContext>,
    properties: &FilePropertiesEntity,
    path: &Path,
) {
    let page = adw::PreferencesPage::new();
    page.set_title(&tr("Permissions"));
    page.set_icon_name(Some("system-lock-screen-symbolic"));
    dialog.add(&page);

    let info = adw::PreferencesGroup::new();
    page.add(&info);
    add_row(&info, &tr("Owner"), properties.owner.as_deref());
    add_row(&info, &tr("Group"), properties.group.as_deref());

    let access = adw::PreferencesGroup::new();
    access.set_title(&tr("Access"));
    page.add(&access);

    let Some(mode) = properties.mode else {
        add_row(&access, &tr("Access"), None);
        return;
    };
    let is_dir = properties.is_dir;
    let applied_mode = Rc::new(Cell::new(mode));

    let current = adw::ActionRow::new();
    current.set_title(&tr("Current"));
    current.set_subtitle(&mode_to_symbolic(mode, is_dir));
    access.add(&current);

    let apply_button = gtk::Button::with_label(&tr("Apply"));
    apply_button.add_css_class("suggested-action");
    apply_button.set_valign(gtk::Align::Center);
    apply_button.set_sensitive(false);

    let mut checks: Vec<[gtk::CheckButton; 3]> = Vec::new();
    for (who, bits) in [tr("Owner"), tr("Group"), tr("Others")]
        .iter()
        .zip(WHO_CLASSES)
    {
        let row = adw::ActionRow::new();
        row.set_title(who);
        let row_checks = [tr("R"), tr("W"), tr("X")]
            .iter()
            .zip(bits)
            .map(|(label, bit)| {
                let pair = gtk::Box::new(gtk::Orientation::Horizontal, 4);
                pair.set_valign(gtk::Align::Center);
                pair.append(&gtk::Label::new(Some(label)));
                let check = gtk::CheckButton::new();
                check.set_active(mode & bit != 0);
                pair.append(&check);
                row.add_suffix(&pair);
                check
            })
            .collect::<Vec<_>>()
            .try_into()
            .expect("three permission bits");
        checks.push(row_checks);
        access.add(&row);
    }
    let checks = Rc::new(checks);
    let selected_mode = {
        let checks = checks.clone();
        move || {
            let mut flags = [[false; 3]; 3];
            for (who, row) in checks.iter().enumerate() {
                for (bit, check) in row.iter().enumerate() {
                    flags[who][bit] = check.is_active();
                }
            }
            mode_from_flags(flags) | special_bits(mode)
        }
    };

    for check in checks.iter().flatten() {
        let (current, apply_button, applied_mode, selected_mode) = (
            current.clone(),
            apply_button.clone(),
            applied_mode.clone(),
            selected_mode.clone(),
        );
        check.connect_toggled(move |_| {
            let new_mode = selected_mode();
            current.set_subtitle(&mode_to_symbolic(new_mode, is_dir));
            apply_button.set_sensitive(new_mode != applied_mode.get());
        });
    }

    let apply_row = adw::ActionRow::new();
    apply_row.set_title(&tr("Apply changes"));
    {
        let (ctx, path, dialog) = (ctx.clone(), PathBuf::from(path), dialog.clone());
        apply_button.connect_clicked(move |button| {
            let new_mode = selected_mode();
            if ctx.file_system.set_permissions(&path, new_mode).is_ok() {
                current.set_subtitle(&mode_to_symbolic(new_mode, is_dir));
                applied_mode.set(new_mode);
                button.set_sensitive(false);
            } else {
                show_error(
                    &dialog,
                    &tr("Could not change permissions"),
                    &tr("You may not own this file, or lack permission to change it."),
                );
            }
        });
    }
    apply_row.add_suffix(&apply_button);
    apply_row.set_activatable_widget(Some(&apply_button));
    access.add(&apply_row);
}

/// setuid/setgid/sticky bits are not editable here, but kept.
fn special_bits(mode: u32) -> u32 {
    mode & 0o7000
}

fn add_open_with_page(
    dialog: &adw::PreferencesDialog,
    parent: &gtk::Widget,
    ctx: &Rc<AppContext>,
    path: &Path,
) {
    let page = adw::PreferencesPage::new();
    page.set_title(&tr("Open With"));
    page.set_icon_name(Some("document-open-symbolic"));
    dialog.add(&page);
    let group = adw::PreferencesGroup::new();
    page.add(&group);

    if ctx.desktop.is_sandboxed() {
        let row = adw::ActionRow::new();
        row.set_title(&tr("Open with"));
        row.set_subtitle(&tr("Choose an application to open this file"));
        let button = gtk::Button::with_label(&tr("Choose…"));
        button.set_valign(gtk::Align::Center);
        let (ctx, path, dialog) = (ctx.clone(), PathBuf::from(path), dialog.clone());
        button.connect_clicked(move |_| {
            let _ = ctx.desktop.open_with_chooser(&path);
            dialog.close();
        });
        row.add_suffix(&button);
        row.set_activatable_widget(Some(&button));
        group.add(&row);
        return;
    }

    let content_type = content_type(path);
    let choices = app_choices(&content_type);
    let none = tr("None");
    let default_row = add_row(
        &group,
        &tr("Default application"),
        Some(
            choices
                .default
                .as_ref()
                .map(app_label)
                .as_deref()
                .unwrap_or(&none),
        ),
    );

    let mut names: Vec<String> = choices.apps.iter().map(app_label).collect();
    names.push(tr("Other application…"));
    let name_refs: Vec<&str> = names.iter().map(String::as_str).collect();
    let combo = adw::ComboRow::new();
    combo.set_title(&tr("Open with"));
    combo.set_model(Some(&gtk::StringList::new(&name_refs)));
    combo.set_selected(if choices.apps.is_empty() {
        (names.len() - 1) as u32
    } else {
        choices.default_index as u32
    });
    group.add(&combo);

    let set_default_row = adw::ActionRow::new();
    set_default_row.set_title(&tr("Make default"));
    let set_default = gtk::Button::with_label(&tr("Set as Default"));
    set_default.set_valign(gtk::Align::Center);
    set_default_row.add_suffix(&set_default);
    set_default_row.set_activatable_widget(Some(&set_default));
    group.add(&set_default_row);

    let apps = Rc::new(choices.apps);
    let default_id = Rc::new(std::cell::RefCell::new(
        choices.default.and_then(|app| app.id()),
    ));
    let update_sensitivity = {
        let (apps, default_id, set_default) =
            (apps.clone(), default_id.clone(), set_default.clone());
        move |combo: &adw::ComboRow| {
            let app = apps.get(combo.selected() as usize);
            let is_default =
                app.is_some_and(|app| app.id().is_some() && app.id() == *default_id.borrow());
            set_default.set_sensitive(app.is_some() && !is_default);
        }
    };
    update_sensitivity(&combo);
    combo.connect_selected_notify(update_sensitivity);

    {
        let (apps, combo, dialog) = (apps.clone(), combo.clone(), dialog.clone());
        let content_type = content_type.clone();
        set_default.connect_clicked(move |button| {
            let Some(app) = apps.get(combo.selected() as usize) else {
                return;
            };
            if app.set_as_default_for_type(&content_type).is_err() {
                show_error(
                    &dialog,
                    &tr("Could not change the default application"),
                    &tr("The system refused to register this application as the default for this file type."),
                );
                return;
            }
            default_row.set_subtitle(&glib::markup_escape_text(&app_label(app)));
            *default_id.borrow_mut() = app.id();
            button.set_sensitive(false);
        });
    }

    let open_row = adw::ActionRow::new();
    open_row.set_title(&tr("Launch"));
    let open = gtk::Button::with_label(&tr("Open"));
    open.add_css_class("suggested-action");
    open.set_valign(gtk::Align::Center);
    {
        let (dialog, parent, path) = (dialog.clone(), parent.clone(), PathBuf::from(path));
        open.connect_clicked(move |_| match apps.get(combo.selected() as usize) {
            Some(app) => {
                launch(app, &path);
                dialog.close();
            }
            None => show_app_chooser_dialog(&parent, &path, &content_type),
        });
    }
    open_row.add_suffix(&open);
    open_row.set_activatable_widget(Some(&open));
    group.add(&open_row);
}
