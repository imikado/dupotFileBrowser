//! Placeholder shown instead of an empty listing.

use adw::prelude::*;

/// Icons GTK bundles itself, present even without a host icon theme.
pub const EMPTY_FOLDER_ICON: &str = "folder-symbolic";
pub const EMPTY_TRASH_ICON: &str = "user-trash-symbolic";

pub fn empty_state(icon_name: &str, title: &str) -> adw::StatusPage {
    let page = adw::StatusPage::new();
    page.set_icon_name(Some(icon_name));
    page.set_title(title);
    page.add_css_class("compact");
    page.set_vexpand(true);
    page
}
