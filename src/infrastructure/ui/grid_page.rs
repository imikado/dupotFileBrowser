//! Icon / thumbnail grid of one folder at a time: opening a subfolder
//! replaces the grid in place. Single click selects and double click opens,
//! unless "Open with a single click" is set.

use std::cell::{Cell, RefCell};
use std::path::{Path, PathBuf};
use std::rc::{Rc, Weak};

use gtk::prelude::*;
use gtk::{gdk, glib, pango};

use crate::domain::entity::file_entry_entity::FileEntryEntity;
use crate::infrastructure::service::i18n_service::tr;
use crate::infrastructure::ui::app_context::{AppContext, BrowserEvent, EventSink};
use crate::infrastructure::ui::shared::entry_menu::{show_entry_menu, single_folder_hooks};
use crate::infrastructure::ui::shared::file_icons::{folder_image, icon_image, thumbnail};

const TILE_PADDING: i32 = 24;
const LABEL_LINES: i32 = 2;

type Tile = (FileEntryEntity, Option<String>);

pub struct GridPage {
    ctx: Rc<AppContext>,
    events: EventSink,
    stack: gtk::Stack,
    flow_box: gtk::FlowBox,
    current_path: RefCell<Option<PathBuf>>,
    icon_size: Cell<i32>,
    tiles: RefCell<Vec<Tile>>,
    weak_self: Weak<GridPage>,
}

impl GridPage {
    pub fn new(ctx: &Rc<AppContext>, events: EventSink) -> Rc<Self> {
        let flow_box = gtk::FlowBox::new();
        flow_box.set_valign(gtk::Align::Start);
        flow_box.set_homogeneous(true);
        flow_box.set_min_children_per_line(1);
        flow_box.set_max_children_per_line(1000);
        flow_box.set_row_spacing(12);
        flow_box.set_column_spacing(12);
        flow_box.set_margin_top(12);
        flow_box.set_margin_bottom(12);
        flow_box.set_margin_start(12);
        flow_box.set_margin_end(12);
        flow_box.set_selection_mode(gtk::SelectionMode::Single);
        flow_box.set_activate_on_single_click(ctx.settings().single_click_open);

        let scroll = gtk::ScrolledWindow::new();
        scroll.set_vexpand(true);
        scroll.set_hexpand(true);
        scroll.set_policy(gtk::PolicyType::Never, gtk::PolicyType::Automatic);
        scroll.set_child(Some(&flow_box));

        let empty = gtk::Label::new(Some(&tr("Empty folder")));
        empty.add_css_class("dim-label");
        empty.set_valign(gtk::Align::Start);
        empty.set_margin_top(24);

        let stack = gtk::Stack::new();
        stack.set_vexpand(true);
        stack.add_named(&scroll, Some("grid"));
        stack.add_named(&empty, Some("empty"));

        let page = Rc::new_cyclic(|weak_self| Self {
            ctx: ctx.clone(),
            events,
            stack,
            flow_box,
            current_path: RefCell::default(),
            icon_size: Cell::new(ctx.settings().grid_icon_size),
            tiles: RefCell::default(),
            weak_self: weak_self.clone(),
        });
        let weak = Rc::downgrade(&page);
        page.flow_box.connect_child_activated(move |_, child| {
            if let Some(page) = weak.upgrade()
                && let Some((entry, _)) = page.tile(child.index() as usize)
            {
                page.open_entry(&entry);
            }
        });
        page
    }

    pub fn widget(&self) -> &gtk::Stack {
        &self.stack
    }

    fn tile(&self, index: usize) -> Option<Tile> {
        self.tiles.borrow().get(index).cloned()
    }

    pub fn load_path(&self, path: &Path) {
        *self.current_path.borrow_mut() = Some(path.to_path_buf());
        self.reload();
    }

    pub fn refresh_path(&self, path: &Path) {
        if self.current_path.borrow().as_deref() == Some(path) {
            self.reload();
        }
    }

    pub fn set_icon_size(&self, size: i32) {
        self.icon_size.set(size);
        self.reload();
    }

    pub fn apply_click_to_open_setting(&self) {
        self.flow_box
            .set_activate_on_single_click(self.ctx.settings().single_click_open);
    }

    pub fn reload(&self) {
        let Some(path) = self.current_path.borrow().clone() else {
            return;
        };
        let entries = self.ctx.list(&path);
        let colors = self.ctx.color_map(&path, &entries);
        let tiles: Vec<Tile> = entries
            .into_iter()
            .map(|entry| {
                let color = colors.get(&entry.name).cloned();
                (entry, color)
            })
            .collect();
        self.flow_box.remove_all();
        for tile in &tiles {
            self.flow_box.append(&self.build_tile(tile));
        }
        self.stack
            .set_visible_child_name(if tiles.is_empty() { "empty" } else { "grid" });
        *self.tiles.borrow_mut() = tiles;
    }

    fn build_tile(&self, (entry, color): &Tile) -> gtk::FlowBoxChild {
        let size = self.icon_size.get();
        let content = gtk::Box::new(gtk::Orientation::Vertical, 6);
        content.set_size_request(size + TILE_PADDING, -1);

        let icon: gtk::Image = if entry.is_dir {
            folder_image(color.as_deref(), size)
        } else if entry.is_image() {
            thumbnail(&entry.path, size).unwrap_or_else(|| icon_image(entry.icon_key(), size))
        } else {
            icon_image(entry.icon_key(), size)
        };
        icon.set_halign(gtk::Align::Center);
        content.append(&icon);

        let label = gtk::Label::new(Some(&entry.display_name()));
        label.set_justify(gtk::Justification::Center);
        label.set_wrap(true);
        label.set_wrap_mode(pango::WrapMode::WordChar);
        label.set_lines(LABEL_LINES);
        label.set_ellipsize(pango::EllipsizeMode::End);
        // Wrap to the tile's width rather than the text's natural width.
        label.set_max_width_chars(1);
        label.set_tooltip_text(Some(&entry.display_name()));
        content.append(&label);

        let child = gtk::FlowBoxChild::new();
        child.set_child(Some(&content));

        let right = gtk::GestureClick::new();
        right.set_button(gdk::BUTTON_SECONDARY);
        let (page, weak_child) = (self.weak_self.clone(), child.downgrade());
        right.connect_pressed(move |gesture, _, x, y| {
            gesture.set_state(gtk::EventSequenceState::Claimed);
            let (page, weak_child) = (page.clone(), weak_child.clone());
            glib::idle_add_local_full(glib::Priority::HIGH_IDLE, move || {
                if let (Some(page), Some(child)) = (page.upgrade(), weak_child.upgrade()) {
                    page.show_menu(&child, x, y);
                }
                glib::ControlFlow::Break
            });
        });
        child.add_controller(right);
        child
    }

    fn open_entry(&self, entry: &FileEntryEntity) {
        if entry.is_dir {
            self.load_path(&entry.path);
            (self.events)(BrowserEvent::PathChanged(entry.path.clone()));
        } else {
            let _ = self.ctx.desktop.open_path(&entry.path);
        }
    }

    fn show_menu(&self, child: &gtk::FlowBoxChild, x: f64, y: f64) {
        let Some((entry, color)) = self.tile(child.index() as usize) else {
            return;
        };
        let hooks = single_folder_hooks(&self.weak_self, Self::open_entry, Self::reload);
        show_entry_menu(
            child.upcast_ref(),
            (x, y),
            &entry,
            color,
            &self.ctx,
            &self.events,
            &hooks,
        );
    }
}
