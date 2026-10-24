//! A popover of flat buttons: the app's stand-in for `GtkPopoverMenu`,
//! whose items don't reliably register clicks right after the right-click
//! that opened it.

use std::rc::Rc;

use gtk::prelude::*;
use gtk::{gdk, glib};

pub struct MenuItem {
    pub label: String,
    pub action: Rc<dyn Fn()>,
    pub destructive: bool,
}

impl MenuItem {
    pub fn new(label: impl Into<String>, action: impl Fn() + 'static) -> Self {
        Self {
            label: label.into(),
            action: Rc::new(action),
            destructive: false,
        }
    }

    pub fn destructive(mut self) -> Self {
        self.destructive = true;
        self
    }
}

/// Shows `popover` on a high-priority idle: never synchronously from
/// another popover's click or a right-click gesture, whose grab teardown
/// would leave the new one unresponsive ("Broken accounting of active
/// state"), and ahead of default-priority layout work.
pub fn popup_deferred(popover: &gtk::Popover) {
    let popover = popover.clone();
    glib::idle_add_local_full(glib::Priority::HIGH_IDLE, move || {
        popover.popup();
        glib::ControlFlow::Break
    });
}

/// Closes `popover` then runs `action`, from one high-priority idle: the
/// popover has let go of its grab before `action` opens anything else.
pub fn run_then_close(popover: &gtk::Popover, action: impl FnOnce() + 'static) {
    let popover = popover.clone();
    let mut action = Some(action);
    glib::idle_add_local_full(glib::Priority::HIGH_IDLE, move || {
        popover.popdown();
        if let Some(action) = action.take() {
            action();
        }
        glib::ControlFlow::Break
    });
}

/// Popover attached to `parent`, unparented once closed.
pub fn attached_popover(
    parent: &impl IsA<gtk::Widget>,
    child: &impl IsA<gtk::Widget>,
) -> gtk::Popover {
    let popover = gtk::Popover::new();
    popover.set_child(Some(child));
    popover.set_parent(parent);
    popover.set_autohide(true);
    popover.connect_closed(|popover| popover.unparent());
    popover
}

/// Menu pointing at (`x`, `y`) in `parent`.
pub fn show_context_menu(parent: &impl IsA<gtk::Widget>, x: f64, y: f64, items: Vec<MenuItem>) {
    show_sectioned_menu(parent, x, y, vec![items]);
}

/// Menu of `sections` separated by lines; empty sections are skipped.
pub fn show_sectioned_menu(
    parent: &impl IsA<gtk::Widget>,
    x: f64,
    y: f64,
    sections: Vec<Vec<MenuItem>>,
) {
    let content = gtk::Box::new(gtk::Orientation::Vertical, 0);
    content.add_css_class("menu");
    let popover = attached_popover(parent, &content);
    popover.set_pointing_to(Some(&gdk::Rectangle::new(x as i32, y as i32, 1, 1)));

    let sections = sections.into_iter().filter(|section| !section.is_empty());
    for (index, section) in sections.enumerate() {
        if index > 0 {
            let separator = gtk::Separator::new(gtk::Orientation::Horizontal);
            separator.set_margin_top(4);
            separator.set_margin_bottom(4);
            content.append(&separator);
        }
        append_items(&content, &popover, section);
    }
    popup_deferred(&popover);
}

fn append_items(content: &gtk::Box, popover: &gtk::Popover, items: Vec<MenuItem>) {
    for item in items {
        let label = gtk::Label::new(Some(&item.label));
        label.set_xalign(0.0);
        let button = gtk::Button::new();
        button.set_child(Some(&label));
        button.add_css_class("flat");
        // The whole row is clickable, not just the text: a click on dead
        // space would close the popover without running anything.
        button.add_css_class("fb-menu-item");
        button.set_hexpand(true);
        if item.destructive {
            button.add_css_class("destructive-action");
        }
        let weak_popover = popover.downgrade();
        let action = item.action.clone();
        button.connect_clicked(move |_| {
            if let Some(popover) = weak_popover.upgrade() {
                let action = action.clone();
                run_then_close(&popover, move || action());
            }
        });
        content.append(&button);
    }
}
