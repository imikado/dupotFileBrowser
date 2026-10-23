//! Header-bar button picking the view mode (columns, grid, details) and the
//! grid's icon size. Its icon shows the current mode. The toggle group is
//! returned too, so that other controls (shortcuts) can switch the mode.

use std::rc::Rc;

use gtk::prelude::*;

use crate::domain::entity::user_settings_entity::{
    MAX_GRID_ICON_SIZE, MIN_GRID_ICON_SIZE, ViewMode,
};
use crate::infrastructure::service::i18n_service::tr;

/// Icons GTK bundles itself, present even without a host icon theme.
fn icon_name(mode: ViewMode) -> &'static str {
    match mode {
        ViewMode::Columns => "view-dual-symbolic",
        ViewMode::Grid => "view-grid-symbolic",
        ViewMode::Details => "view-list-bullet-symbolic",
    }
}

fn tooltip(mode: ViewMode) -> String {
    match mode {
        ViewMode::Columns => tr("Columns"),
        ViewMode::Grid => tr("Grid"),
        ViewMode::Details => tr("Details"),
    }
}

pub fn build_view_mode_switcher(
    mode: ViewMode,
    icon_size: i32,
    on_mode_changed: impl Fn(ViewMode) + 'static,
    on_icon_size_changed: impl Fn(i32) + 'static,
) -> (gtk::MenuButton, adw::ToggleGroup) {
    let button = gtk::MenuButton::new();
    button.set_tooltip_text(Some(&tr("View")));
    button.set_icon_name(icon_name(mode));

    let content = gtk::Box::new(gtk::Orientation::Vertical, 12);
    content.set_margin_top(12);
    content.set_margin_bottom(12);
    content.set_margin_start(12);
    content.set_margin_end(12);

    let group = adw::ToggleGroup::new();
    for mode in ViewMode::ALL {
        let toggle = adw::Toggle::new();
        toggle.set_name(Some(mode.id()));
        toggle.set_icon_name(Some(icon_name(mode)));
        toggle.set_tooltip(&tooltip(mode));
        group.add(toggle);
    }
    group.set_active_name(Some(mode.id()));
    content.append(&group);

    let size_label = gtk::Label::new(Some(&tr("Icon size")));
    size_label.set_halign(gtk::Align::Start);
    size_label.add_css_class("dim-label");
    content.append(&size_label);

    let scale = gtk::Scale::with_range(
        gtk::Orientation::Horizontal,
        f64::from(MIN_GRID_ICON_SIZE),
        f64::from(MAX_GRID_ICON_SIZE),
        8.0,
    );
    scale.set_value(f64::from(icon_size));
    scale.set_hexpand(true);
    scale.set_size_request(180, -1);
    scale.set_draw_value(false);
    // Only meaningful for the grid; greyed out rather than hidden so the
    // popover doesn't jump.
    scale.set_sensitive(mode == ViewMode::Grid);
    scale.connect_value_changed(move |scale| on_icon_size_changed(scale.value() as i32));
    content.append(&scale);

    let on_mode_changed = Rc::new(on_mode_changed);
    {
        let (button, scale) = (button.clone(), scale.clone());
        group.connect_active_name_notify(move |group| {
            let Some(mode) = group
                .active_name()
                .and_then(|name| ViewMode::from_id(&name))
            else {
                return;
            };
            button.set_icon_name(icon_name(mode));
            scale.set_sensitive(mode == ViewMode::Grid);
            on_mode_changed(mode);
        });
    }

    let popover = gtk::Popover::new();
    popover.set_child(Some(&content));
    button.set_popover(Some(&popover));
    (button, group)
}
