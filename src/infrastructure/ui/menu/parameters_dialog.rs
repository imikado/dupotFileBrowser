use std::os::unix::process::CommandExt;
use std::rc::Rc;

use adw::prelude::*;

use crate::domain::entity::user_settings_entity::{Language, Theme};
use crate::infrastructure::service::i18n_service::tr;
use crate::infrastructure::ui::app_context::AppContext;

/// What changed when the parameters were saved.
#[derive(Clone, Copy, Debug, Default)]
pub struct SettingsChanges {
    pub hidden_files: bool,
    pub single_click_open: bool,
}

fn switch_row(title: &str, subtitle: &str, active: bool) -> adw::SwitchRow {
    let row = adw::SwitchRow::new();
    row.set_title(title);
    row.set_subtitle(subtitle);
    row.set_active(active);
    row
}

fn combo_row(title: &str, ids: &[&str], selected: usize) -> adw::ComboRow {
    let labels: Vec<String> = ids.iter().map(|id| tr(id)).collect();
    let label_refs: Vec<&str> = labels.iter().map(String::as_str).collect();
    let row = adw::ComboRow::new();
    row.set_title(title);
    row.set_model(Some(&gtk::StringList::new(&label_refs)));
    row.set_selected(selected as u32);
    row
}

/// Restarts the process: translations and icons are bound at startup.
fn restart() {
    if let Ok(exe) = std::env::current_exe() {
        let error = std::process::Command::new(exe)
            .args(std::env::args_os().skip(1))
            .exec();
        eprintln!("could not restart: {error}");
    }
}

pub fn show_parameters_dialog(
    parent: &impl IsA<gtk::Widget>,
    ctx: &Rc<AppContext>,
    on_saved: impl Fn(SettingsChanges) + 'static,
) {
    let settings = ctx.settings().clone();
    let dialog = adw::PreferencesDialog::new();
    dialog.set_title(&tr("Parameters"));
    let page = adw::PreferencesPage::new();
    dialog.add(&page);
    let group = adw::PreferencesGroup::new();
    group.set_title(&tr("Appearance"));
    page.add(&group);

    let theme_ids: Vec<&str> = Theme::ALL.iter().map(|t| t.id()).collect();
    let theme_row = combo_row(
        &tr("Theme"),
        &theme_ids,
        Theme::ALL
            .iter()
            .position(|t| *t == settings.theme)
            .unwrap_or(0),
    );
    let language_ids: Vec<&str> = Language::ALL.iter().map(|l| l.id()).collect();
    let language_row = combo_row(
        &tr("Language"),
        &language_ids,
        Language::ALL
            .iter()
            .position(|l| *l == settings.language)
            .unwrap_or(0),
    );
    let system_icon_row = switch_row(
        &tr("Use system icon theme"),
        &tr(
            "Show the same file icons as your file manager (Nemo, Nautilus...). Falls back to the built-in icons for any file type your theme doesn't cover.",
        ),
        settings.use_system_icon_theme,
    );
    let hidden_row = switch_row(
        &tr("Show hidden files"),
        &tr("Display files and folders whose name starts with a dot."),
        settings.display_hidden,
    );
    let single_click_row = switch_row(
        &tr("Open with a single click"),
        &tr(
            "In Grid and Details view, open a file or folder with a single click instead of a double click. Doesn't affect Columns view.",
        ),
        settings.single_click_open,
    );
    group.add(&theme_row);
    group.add(&language_row);
    group.add(&system_icon_row);
    group.add(&hidden_row);
    group.add(&single_click_row);

    let save_group = adw::PreferencesGroup::new();
    page.add(&save_group);
    let save = gtk::Button::with_label(&tr("Save"));
    save.add_css_class("suggested-action");
    save.add_css_class("pill");
    save.set_halign(gtk::Align::Center);
    save.set_margin_top(8);
    save.set_margin_bottom(8);
    save.set_sensitive(false);
    save_group.add(&save);

    let enable_save = {
        let save = save.clone();
        move || save.set_sensitive(true)
    };
    for row in [&theme_row, &language_row] {
        let enable_save = enable_save.clone();
        row.connect_selected_notify(move |_| enable_save());
    }
    for row in [&system_icon_row, &hidden_row, &single_click_row] {
        let enable_save = enable_save.clone();
        row.connect_active_notify(move |_| enable_save());
    }

    let (ctx, weak_dialog) = (ctx.clone(), dialog.downgrade());
    save.connect_clicked(move |_| {
        let theme = Theme::ALL[theme_row.selected() as usize % Theme::ALL.len()];
        let language = Language::ALL[language_row.selected() as usize % Language::ALL.len()];
        let (restart_needed, changes) = {
            let mut settings = ctx.settings_mut();
            let restart_needed = language != settings.language
                || system_icon_row.is_active() != settings.use_system_icon_theme;
            let changes = SettingsChanges {
                hidden_files: hidden_row.is_active() != settings.display_hidden,
                single_click_open: single_click_row.is_active() != settings.single_click_open,
            };
            settings.theme = theme;
            settings.language = language;
            settings.use_system_icon_theme = system_icon_row.is_active();
            settings.display_hidden = hidden_row.is_active();
            settings.single_click_open = single_click_row.is_active();
            (restart_needed, changes)
        };
        ctx.save_settings();
        on_saved(changes);
        if let Some(dialog) = weak_dialog.upgrade() {
            dialog.close();
        }
        if restart_needed {
            restart();
        }
    });

    dialog.present(Some(parent));
}
