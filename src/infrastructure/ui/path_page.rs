//! Miller columns (macOS Finder style): clicking a folder opens a new
//! column to its right, dropping any column further right first. Nothing is
//! ever dropped from the left; going up prepends the parent instead.

use std::cell::{Cell, RefCell};
use std::path::{Path, PathBuf};
use std::rc::{Rc, Weak};

use gtk::prelude::*;
use gtk::{gdk, glib, pango};

use crate::domain::entity::file_entry_entity::FileEntryEntity;
use crate::domain::shared::path::{ancestor_chain, parent_dir};
use crate::infrastructure::service::i18n_service::tr;
use crate::infrastructure::ui::app_context::{AppContext, BrowserEvent, EventSink};
use crate::infrastructure::ui::shared::color_picker_popup::swatch_class;
use crate::infrastructure::ui::shared::empty_state::{EMPTY_FOLDER_ICON, empty_state};
use crate::infrastructure::ui::shared::entry_menu::{EntryMenuHooks, open_file, show_entry_menu};
use crate::infrastructure::ui::shared::file_icons::{ICON_DISPLAY_SIZE, folder_image, small_icon};

const COLUMN_WIDTH: i32 = 260;
const COLOR_DOT_SIZE: i32 = 10;

/// A right-click on the row that just opened a new column can land while
/// that column is still being laid out, and the menu then shows too late to
/// catch the next click: within this window, the menu waits a little.
const RECENT_ACTIVATION_WINDOW_US: i64 = 300_000;
const CONTEXT_MENU_SETTLE_DELAY_MS: u64 = 150;

type Row = (FileEntryEntity, Option<String>);

struct Column {
    path: PathBuf,
    /// The column with its right-hand separator.
    root: gtk::Box,
    list_box: gtk::ListBox,
    stack: gtk::Stack,
    rows: RefCell<Vec<Row>>,
    /// (row index, monotonic time) of the last single-click activation.
    last_activated: Cell<Option<(i32, i64)>>,
}

impl Column {
    fn new(path: &Path, page: &Weak<PathPage>) -> Rc<Self> {
        let list_box = gtk::ListBox::new();
        list_box.add_css_class("fb-column-list");
        list_box.set_selection_mode(gtk::SelectionMode::Single);

        let scroll = gtk::ScrolledWindow::new();
        scroll.set_vexpand(true);
        scroll.set_policy(gtk::PolicyType::Never, gtk::PolicyType::Automatic);
        scroll.set_child(Some(&list_box));

        let empty = empty_state(EMPTY_FOLDER_ICON, &tr("Empty folder"));

        let stack = gtk::Stack::new();
        stack.set_vexpand(true);
        stack.add_named(&scroll, Some("list"));
        stack.add_named(&empty, Some("empty"));

        stack.set_size_request(COLUMN_WIDTH, -1);
        let root = gtk::Box::new(gtk::Orientation::Horizontal, 0);
        root.append(&stack);
        root.append(&gtk::Separator::new(gtk::Orientation::Vertical));

        let column = Rc::new(Self {
            path: path.to_path_buf(),
            root,
            list_box,
            stack,
            rows: RefCell::default(),
            last_activated: Cell::new(None),
        });
        let (weak_column, page) = (Rc::downgrade(&column), page.clone());
        column.list_box.connect_row_activated(move |_, row| {
            let (Some(column), Some(page)) = (weak_column.upgrade(), page.upgrade()) else {
                return;
            };
            column
                .last_activated
                .set(Some((row.index(), glib::monotonic_time())));
            page.on_row_activated(&column, row.index() as usize, false);
        });
        column
    }

    fn set_rows(self: &Rc<Self>, rows: Vec<Row>, page: &Weak<PathPage>) {
        self.list_box.remove_all();
        for (index, (entry, color)) in rows.iter().enumerate() {
            let content = gtk::Box::new(gtk::Orientation::Horizontal, 8);
            content.append(&if entry.is_dir {
                folder_image(color.as_deref(), ICON_DISPLAY_SIZE)
            } else {
                small_icon(entry.icon_key())
            });
            let label = gtk::Label::new(Some(&entry.name));
            label.set_halign(gtk::Align::Start);
            label.set_hexpand(true);
            label.set_ellipsize(pango::EllipsizeMode::Middle);
            content.append(&label);
            if entry.is_dir {
                let chevron = gtk::Image::from_icon_name("go-next-symbolic");
                chevron.add_css_class("dim-label");
                content.append(&chevron);
            } else if let Some(color) = color {
                content.append(&color_dot(color));
            }
            let row = gtk::ListBoxRow::new();
            row.set_child(Some(&content));
            // Names are cut to one line: the tooltip shows long ones whole.
            row.set_tooltip_text(Some(&entry.name));
            self.attach_gestures(&row, index, page);
            self.list_box.append(&row);
        }
        self.stack
            .set_visible_child_name(if rows.is_empty() { "empty" } else { "list" });
        *self.rows.borrow_mut() = rows;
    }

    fn attach_gestures(
        self: &Rc<Self>,
        row: &gtk::ListBoxRow,
        index: usize,
        page: &Weak<PathPage>,
    ) {
        // Files open on a double click; a single click only selects them.
        let left = gtk::GestureClick::new();
        left.set_button(gdk::BUTTON_PRIMARY);
        let (column, page_ref) = (Rc::downgrade(self), page.clone());
        left.connect_pressed(move |_, n_press, _, _| {
            if n_press == 2
                && let (Some(column), Some(page)) = (column.upgrade(), page_ref.upgrade())
            {
                page.on_row_activated(&column, index, true);
            }
        });
        row.add_controller(left);

        let right = gtk::GestureClick::new();
        right.set_button(gdk::BUTTON_SECONDARY);
        let (column, page, weak_row) = (Rc::downgrade(self), page.clone(), row.downgrade());
        right.connect_pressed(move |gesture, _, x, y| {
            gesture.set_state(gtk::EventSequenceState::Claimed);
            let (Some(column_rc), Some(_)) = (column.upgrade(), page.upgrade()) else {
                return;
            };
            let just_activated = column_rc.last_activated.get().is_some_and(|(row, at)| {
                row == index as i32 && glib::monotonic_time() - at < RECENT_ACTIVATION_WINDOW_US
            });
            let (column, page, weak_row) = (column.clone(), page.clone(), weak_row.clone());
            let show = move || {
                if let (Some(column), Some(page), Some(row)) =
                    (column.upgrade(), page.upgrade(), weak_row.upgrade())
                {
                    page.show_menu(&column, index, row.upcast_ref(), x, y);
                }
            };
            if just_activated {
                glib::timeout_add_local_once(
                    std::time::Duration::from_millis(CONTEXT_MENU_SETTLE_DELAY_MS),
                    show,
                );
            } else {
                glib::idle_add_local_full(glib::Priority::HIGH_IDLE, move || {
                    show();
                    glib::ControlFlow::Break
                });
            }
        });
        row.add_controller(right);
    }

    fn select_path(&self, path: &Path) {
        let index = self
            .rows
            .borrow()
            .iter()
            .position(|(entry, _)| entry.path == path);
        if let Some(row) = index.and_then(|index| self.list_box.row_at_index(index as i32)) {
            self.list_box.select_row(Some(&row));
        }
    }

    fn entry(&self, index: usize) -> Option<Row> {
        self.rows.borrow().get(index).cloned()
    }
}

/// Small round swatch next to a tagged file (folders get a tinted icon).
fn color_dot(color: &str) -> gtk::Box {
    let dot = gtk::Box::new(gtk::Orientation::Horizontal, 0);
    dot.set_size_request(COLOR_DOT_SIZE, COLOR_DOT_SIZE);
    dot.set_valign(gtk::Align::Center);
    dot.add_css_class("fb-color-dot");
    dot.add_css_class(&swatch_class(color));
    dot
}

pub struct PathPage {
    ctx: Rc<AppContext>,
    events: EventSink,
    scroll: gtk::ScrolledWindow,
    columns_box: gtk::Box,
    columns: RefCell<Vec<Rc<Column>>>,
    weak_self: Weak<PathPage>,
}

impl PathPage {
    pub fn new(ctx: &Rc<AppContext>, events: EventSink) -> Rc<Self> {
        let columns_box = gtk::Box::new(gtk::Orientation::Horizontal, 0);
        let scroll = gtk::ScrolledWindow::new();
        scroll.set_hexpand(true);
        scroll.set_vexpand(true);
        scroll.set_policy(gtk::PolicyType::Automatic, gtk::PolicyType::Never);
        // Always visible: the main way back to columns scrolled out of view.
        scroll.set_overlay_scrolling(false);
        scroll.set_child(Some(&columns_box));

        Rc::new_cyclic(|weak_self| Self {
            ctx: ctx.clone(),
            events,
            scroll,
            columns_box,
            columns: RefCell::default(),
            weak_self: weak_self.clone(),
        })
    }

    pub fn widget(&self) -> &gtk::ScrolledWindow {
        &self.scroll
    }

    fn fill(&self, column: &Rc<Column>) {
        let entries = self.ctx.list(&column.path);
        let colors = self.ctx.color_map(&column.path, &entries);
        let rows = entries
            .into_iter()
            .map(|entry| {
                let color = colors.get(&entry.name).cloned();
                (entry, color)
            })
            .collect();
        column.set_rows(rows, &self.weak_self);
    }

    fn new_column(&self, path: &Path) -> Rc<Column> {
        let column = Column::new(path, &self.weak_self);
        self.fill(&column);
        column
    }

    fn push_column(&self, path: &Path) {
        let column = self.new_column(path);
        self.columns_box.append(&column.root);
        self.columns.borrow_mut().push(column);
    }

    fn reset_columns(&self) {
        for column in self.columns.borrow_mut().drain(..) {
            self.columns_box.remove(&column.root);
        }
    }

    /// A single column showing `path`.
    pub fn load_path(&self, path: &Path) {
        self.reset_columns();
        self.push_column(path);
    }

    /// One column per folder from `/` down to `path`, each highlighting the
    /// next, as if the user had clicked their way there.
    pub fn load_path_chain(&self, path: &Path) {
        self.reset_columns();
        for segment in ancestor_chain(path) {
            if let Some(last) = self.columns.borrow().last() {
                last.select_path(&segment);
            }
            self.push_column(&segment);
        }
        self.scroll_to_end();
    }

    /// Reloads open columns showing `path`, keeping columns and selection.
    pub fn refresh_path(&self, path: &Path) {
        let columns: Vec<Rc<Column>> = self.columns.borrow().clone();
        for column in columns.iter().filter(|column| column.path == path) {
            self.fill(column);
        }
    }

    /// Reloads every column (hidden-files setting, light/dark switch).
    pub fn reload(&self) {
        let columns: Vec<Rc<Column>> = self.columns.borrow().clone();
        for column in &columns {
            self.fill(column);
        }
    }

    /// Reveals the parent of the leftmost column; `None` at `/`.
    pub fn prepend_parent(&self) -> Option<PathBuf> {
        let leftmost = self.columns.borrow().first()?.path.clone();
        let parent = parent_dir(&leftmost);
        if parent == leftmost {
            return None;
        }
        let column = self.new_column(&parent);
        column.select_path(&leftmost);
        self.columns_box
            .insert_child_after(&column.root, None::<&gtk::Widget>);
        self.columns.borrow_mut().insert(0, column);
        (self.events)(BrowserEvent::PathChanged(parent.clone()));
        self.scroll_to(false);
        Some(parent)
    }

    fn scroll_to_end(&self) {
        self.scroll_to(true);
    }

    fn scroll_to(&self, end: bool) {
        let adjustment = self.scroll.hadjustment();
        glib::idle_add_local_once(move || {
            let value = if end {
                adjustment.upper() - adjustment.page_size()
            } else {
                0.0
            };
            adjustment.set_value(value);
        });
    }

    /// Drops every column right of `column`: the entry they showed may have
    /// been renamed, moved or trashed.
    fn drop_stale_columns(&self, column: &Rc<Column>) {
        let mut columns = self.columns.borrow_mut();
        if let Some(index) = columns.iter().position(|c| Rc::ptr_eq(c, column)) {
            for stale in columns.drain(index + 1..) {
                self.columns_box.remove(&stale.root);
            }
        }
    }

    /// Single click opens folders; files need a double click.
    fn on_row_activated(&self, column: &Rc<Column>, index: usize, double_click: bool) {
        let Some((entry, _)) = column.entry(index) else {
            return;
        };
        if entry.is_dir != double_click {
            self.open_entry(column, &entry);
        }
    }

    fn open_entry(&self, column: &Rc<Column>, entry: &FileEntryEntity) {
        self.drop_stale_columns(column);
        if !entry.is_dir {
            open_file(&column.root, &self.ctx, &entry.path);
            (self.events)(BrowserEvent::PathChanged(column.path.clone()));
            return;
        }
        self.push_column(&entry.path);
        (self.events)(BrowserEvent::PathChanged(entry.path.clone()));
        self.scroll_to_end();
    }

    fn show_menu(&self, column: &Rc<Column>, index: usize, anchor: &gtk::Widget, x: f64, y: f64) {
        let Some((entry, color)) = column.entry(index) else {
            return;
        };
        let page = self.weak_self.clone();
        let weak_column = Rc::downgrade(column);
        let with = move |action: fn(&PathPage, &Rc<Column>, &FileEntryEntity, Option<PathBuf>)| {
            let (page, column) = (page.clone(), weak_column.clone());
            move |entry: &FileEntryEntity, destination: Option<PathBuf>| {
                if let (Some(page), Some(column)) = (page.upgrade(), column.upgrade()) {
                    action(&page, &column, entry, destination);
                }
            }
        };
        let open = with(|page, column, entry, _| page.open_entry(column, entry));
        let renamed = with(|page, column, _, destination| {
            page.drop_stale_columns(column);
            page.refresh_path(&column.path);
            if let Some(destination) = destination {
                column.select_path(&destination);
            }
        });
        let trashed = with(|page, column, _, _| {
            page.drop_stale_columns(column);
            page.refresh_path(&column.path);
        });
        let recolored = with(|page, column, _, _| page.refresh_path(&column.path));
        let hooks = EntryMenuHooks {
            open: Rc::new(move |entry| open(entry, None)),
            renamed: Rc::new(move |entry, destination| renamed(entry, Some(destination))),
            trashed: Rc::new(move |entry| trashed(entry, None)),
            recolored: Rc::new(move |entry| recolored(entry, None)),
        };
        show_entry_menu(
            anchor,
            (x, y),
            &entry,
            color,
            &self.ctx,
            &self.events,
            &hooks,
        );
    }
}
