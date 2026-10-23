//! One tab's content: its own columns / grid / details / trash views and
//! current folder, switched as the view mode or location changes.

use std::cell::{Cell, RefCell};
use std::path::{Path, PathBuf};
use std::rc::{Rc, Weak};

use gtk::prelude::*;

use crate::domain::entity::user_settings_entity::ViewMode;
use crate::domain::shared::path::parent_dir;
use crate::infrastructure::ui::app_context::{AppContext, BrowserEvent, EventSink};
use crate::infrastructure::ui::details_page::DetailsPage;
use crate::infrastructure::ui::grid_page::GridPage;
use crate::infrastructure::ui::path_page::PathPage;
use crate::infrastructure::ui::trash_page::TrashPage;

/// Receives a tab's events, with the tab they came from.
pub type TabEventSink = Rc<dyn Fn(&Rc<BrowserTab>, BrowserEvent)>;

pub struct BrowserTab {
    ctx: Rc<AppContext>,
    stack: gtk::Stack,
    path_page: Rc<PathPage>,
    grid_page: Rc<GridPage>,
    details_page: Rc<DetailsPage>,
    trash_page: Rc<TrashPage>,
    current_path: RefCell<PathBuf>,
    showing_trash: Cell<bool>,
}

impl BrowserTab {
    pub fn new(ctx: &Rc<AppContext>, sink: TabEventSink) -> Rc<Self> {
        Rc::new_cyclic(|weak: &Weak<BrowserTab>| {
            let weak = weak.clone();
            let events: EventSink = Rc::new(move |event| {
                let Some(tab) = weak.upgrade() else { return };
                if let BrowserEvent::PathChanged(path) = &event {
                    *tab.current_path.borrow_mut() = path.clone();
                }
                sink(&tab, event);
            });
            let path_page = PathPage::new(ctx, events.clone());
            let grid_page = GridPage::new(ctx, events.clone());
            let details_page = DetailsPage::new(ctx, events);
            let trash_page = TrashPage::new(ctx);

            let stack = gtk::Stack::new();
            stack.set_hexpand(true);
            stack.add_named(path_page.widget(), Some(ViewMode::Columns.id()));
            stack.add_named(grid_page.widget(), Some(ViewMode::Grid.id()));
            stack.add_named(details_page.widget(), Some(ViewMode::Details.id()));
            stack.add_named(trash_page.widget(), Some("trash"));

            Self {
                ctx: ctx.clone(),
                stack,
                path_page,
                grid_page,
                details_page,
                trash_page,
                current_path: RefCell::new(ctx.file_system.home_dir()),
                showing_trash: Cell::new(false),
            }
        })
    }

    pub fn widget(&self) -> &gtk::Stack {
        &self.stack
    }

    pub fn current_path(&self) -> PathBuf {
        self.current_path.borrow().clone()
    }

    pub fn showing_trash(&self) -> bool {
        self.showing_trash.get()
    }

    fn view_mode(&self) -> ViewMode {
        self.ctx.settings().view_mode
    }

    fn show(&self, path: &Path, name: &str) {
        self.showing_trash.set(false);
        self.stack.set_visible_child_name(name);
        *self.current_path.borrow_mut() = path.to_path_buf();
    }

    /// Grid and Details load `path`; Columns too, as a single column unless
    /// `as_chain` (path typed in, or coming from another view mode).
    pub fn navigate(&self, path: &Path, as_chain: bool) {
        let mode = self.view_mode();
        self.show(path, mode.id());
        match mode {
            ViewMode::Grid => self.grid_page.load_path(path),
            ViewMode::Details => self.details_page.load_path(path),
            ViewMode::Columns if as_chain => self.path_page.load_path_chain(path),
            ViewMode::Columns => self.path_page.load_path(path),
        }
    }

    pub fn go_to_trash(&self) {
        self.showing_trash.set(true);
        self.stack.set_visible_child_name("trash");
        self.trash_page.refresh();
        *self.current_path.borrow_mut() = self.ctx.trash.trash_dir();
    }

    /// New folder when it moved up in place (single-folder views). Columns
    /// prepends the parent column and reports it through its own event.
    pub fn go_up(&self) -> Option<PathBuf> {
        if !self.view_mode().is_single_folder() {
            self.path_page.prepend_parent();
            return None;
        }
        let current = self.current_path();
        let parent = parent_dir(&current);
        if parent == current {
            return None;
        }
        self.navigate(&parent, false);
        Some(parent)
    }

    pub fn apply_view_mode(&self) {
        if !self.showing_trash() {
            self.navigate(&self.current_path(), true);
        }
    }

    pub fn refresh_path(&self, path: &Path) {
        self.path_page.refresh_path(path);
        self.grid_page.refresh_path(path);
        self.details_page.refresh_path(path);
    }

    /// Hidden-files setting or light/dark style changed.
    pub fn reload(&self) {
        self.path_page.reload();
        self.grid_page.reload();
        self.details_page.reload();
        if self.showing_trash() {
            self.trash_page.refresh();
        }
    }

    pub fn apply_click_to_open_setting(&self) {
        self.grid_page.apply_click_to_open_setting();
        self.details_page.apply_click_to_open_setting();
    }

    pub fn set_grid_icon_size(&self, size: i32) {
        self.grid_page.set_icon_size(size);
    }
}
