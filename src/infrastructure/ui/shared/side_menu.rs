//! Left sidebar: Home, Trash, host folders and favorites, under section
//! headings.

use std::cell::RefCell;
use std::path::{Path, PathBuf};
use std::rc::Rc;

use gtk::prelude::*;
use gtk::{gdk, glib};

use crate::infrastructure::service::i18n_service::tr;
use crate::infrastructure::ui::shared::context_menu::{MenuItem, show_context_menu};

pub type PathCallback = Rc<dyn Fn(PathBuf)>;

pub struct SideMenuItem {
    /// Symbolic icon, like the rest of the window chrome.
    pub icon_name: &'static str,
    pub label: String,
    pub path: PathBuf,
    pub on_activate: PathCallback,
    /// Offers "Remove from favorites" on right-click when set.
    pub on_remove: Option<PathCallback>,
}

pub enum SideMenuEntry {
    Heading(String),
    Item(SideMenuItem),
}

pub struct SideMenu {
    list_box: gtk::ListBox,
    /// One per row; `None` for a heading.
    items: RefCell<Vec<Option<Rc<SideMenuItem>>>>,
}

impl SideMenu {
    pub fn new() -> Rc<Self> {
        let list_box = gtk::ListBox::new();
        list_box.add_css_class("navigation-sidebar");
        list_box.add_css_class("fb-side-menu");
        list_box.set_selection_mode(gtk::SelectionMode::Single);
        list_box.set_vexpand(true);
        let menu = Rc::new(Self {
            list_box,
            items: RefCell::default(),
        });
        let weak = Rc::downgrade(&menu);
        menu.list_box.connect_row_activated(move |_, row| {
            let Some(menu) = weak.upgrade() else { return };
            let item = menu
                .items
                .borrow()
                .get(row.index() as usize)
                .cloned()
                .flatten();
            if let Some(item) = item {
                (item.on_activate)(item.path.clone());
            }
        });
        menu
    }

    pub fn widget(&self) -> &gtk::ListBox {
        &self.list_box
    }

    pub fn set_entries(&self, entries: Vec<SideMenuEntry>) {
        self.list_box.remove_all();
        let mut items = Vec::with_capacity(entries.len());
        for entry in entries {
            match entry {
                SideMenuEntry::Heading(title) => {
                    self.list_box.append(&heading_row(&title));
                    items.push(None);
                }
                SideMenuEntry::Item(item) => {
                    let item = Rc::new(item);
                    self.list_box.append(&item_row(&item));
                    items.push(Some(item));
                }
            }
        }
        *self.items.borrow_mut() = items;
    }

    pub fn set_selected_path(&self, path: &Path) {
        let index = self
            .items
            .borrow()
            .iter()
            .position(|item| item.as_ref().is_some_and(|item| item.path == path));
        match index.and_then(|index| self.list_box.row_at_index(index as i32)) {
            Some(row) => self.list_box.select_row(Some(&row)),
            None => self.list_box.unselect_all(),
        }
    }
}

fn heading_row(title: &str) -> gtk::ListBoxRow {
    let row = gtk::ListBoxRow::new();
    row.set_selectable(false);
    row.set_activatable(false);
    row.set_can_focus(false);
    row.add_css_class("fb-heading-row");
    let label = gtk::Label::new(Some(title));
    label.add_css_class("heading");
    label.add_css_class("dim-label");
    label.set_halign(gtk::Align::Start);
    label.set_ellipsize(gtk::pango::EllipsizeMode::End);
    row.set_child(Some(&label));
    row
}

fn item_row(item: &Rc<SideMenuItem>) -> gtk::ListBoxRow {
    let row = gtk::ListBoxRow::new();
    let content = gtk::Box::new(gtk::Orientation::Horizontal, 10);
    content.append(&gtk::Image::from_icon_name(item.icon_name));
    let label = gtk::Label::new(Some(&item.label));
    label.set_halign(gtk::Align::Start);
    label.set_ellipsize(gtk::pango::EllipsizeMode::End);
    content.append(&label);
    row.set_child(Some(&content));
    row.set_tooltip_text(Some(&item.path.to_string_lossy()));

    if item.on_remove.is_some() {
        let click = gtk::GestureClick::new();
        click.set_button(gdk::BUTTON_SECONDARY);
        let (item, weak_row) = (item.clone(), row.downgrade());
        click.connect_pressed(move |gesture, _, x, y| {
            gesture.set_state(gtk::EventSequenceState::Claimed);
            let (Some(row), Some(on_remove)) = (weak_row.upgrade(), item.on_remove.clone()) else {
                return;
            };
            let path = item.path.clone();
            glib::idle_add_local_full(glib::Priority::HIGH_IDLE, move || {
                let (on_remove, path) = (on_remove.clone(), path.clone());
                show_context_menu(
                    &row,
                    x,
                    y,
                    vec![
                        MenuItem::new(tr("Remove from favorites"), move || on_remove(path.clone()))
                            .destructive(),
                    ],
                );
                glib::ControlFlow::Break
            });
        });
        row.add_controller(click);
    }
    row
}
