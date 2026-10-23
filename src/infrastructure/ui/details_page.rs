//! Sortable table of one folder (Name, Type, Size, Modified): click a header
//! to sort, again to reverse. Folders always come first.

use std::cell::RefCell;
use std::cmp::Ordering;
use std::path::{Path, PathBuf};
use std::rc::{Rc, Weak};

use gtk::prelude::*;
use gtk::{gdk, gio, glib, pango};

use crate::domain::entity::file_entry_entity::{FileEntryEntity, TypeLabel};
use crate::domain::usecase::list_directory::compare_by;
use crate::infrastructure::service::i18n_service::{tr, trf};
use crate::infrastructure::ui::app_context::{AppContext, BrowserEvent, EventSink};
use crate::infrastructure::ui::shared::entry_menu::{show_entry_menu, single_folder_hooks};
use crate::infrastructure::ui::shared::file_icons::{ICON_DISPLAY_SIZE, folder_image, small_icon};
use crate::infrastructure::ui::shared::properties_dialog::format_timestamp;

/// One row of the list model.
struct DetailsRow {
    entry: FileEntryEntity,
    color: Option<String>,
}

pub fn type_label_text(entry: &FileEntryEntity) -> String {
    match entry.type_label() {
        TypeLabel::Folder => tr("Folder"),
        TypeLabel::Kind(label) => tr(label),
        TypeLabel::Extension(extension) => trf("{extension} File", &[("extension", &extension)]),
        TypeLabel::File => tr("File"),
    }
}

fn row_of(item: &glib::Object) -> std::cell::Ref<'_, DetailsRow> {
    item.downcast_ref::<glib::BoxedAnyObject>()
        .expect("rows are BoxedAnyObject")
        .borrow::<DetailsRow>()
}

/// Folders first, then `key`, then name.
fn sorter<K: PartialOrd>(key: impl Fn(&FileEntryEntity) -> K + 'static) -> gtk::CustomSorter {
    gtk::CustomSorter::new(move |a, b| {
        let (a, b) = (row_of(a), row_of(b));
        let ordering: Ordering = compare_by(&a.entry, &b.entry, &key(&a.entry), &key(&b.entry));
        ordering.into()
    })
}

pub struct DetailsPage {
    ctx: Rc<AppContext>,
    events: EventSink,
    stack: gtk::Stack,
    store: gio::ListStore,
    column_view: gtk::ColumnView,
    current_path: RefCell<Option<PathBuf>>,
    weak_self: Weak<DetailsPage>,
}

impl DetailsPage {
    pub fn new(ctx: &Rc<AppContext>, events: EventSink) -> Rc<Self> {
        let store = gio::ListStore::new::<glib::BoxedAnyObject>();
        let sort_model = gtk::SortListModel::new(Some(store.clone()), None::<gtk::Sorter>);
        let selection = gtk::SingleSelection::new(Some(sort_model.clone()));
        selection.set_autoselect(false);
        selection.set_can_unselect(true);

        let column_view = gtk::ColumnView::new(Some(selection.clone()));
        column_view.set_show_row_separators(true);
        column_view.set_show_column_separators(false);
        column_view.set_single_click_activate(ctx.settings().single_click_open);
        sort_model.set_sorter(column_view.sorter().as_ref());

        let scroll = gtk::ScrolledWindow::new();
        scroll.set_vexpand(true);
        scroll.set_hexpand(true);
        scroll.set_child(Some(&column_view));

        let empty = gtk::Label::new(Some(&tr("Empty folder")));
        empty.add_css_class("dim-label");
        empty.set_valign(gtk::Align::Start);
        empty.set_margin_top(24);

        let stack = gtk::Stack::new();
        stack.set_vexpand(true);
        stack.add_named(&scroll, Some("details"));
        stack.add_named(&empty, Some("empty"));

        let page = Rc::new_cyclic(|weak_self| Self {
            ctx: ctx.clone(),
            events,
            stack,
            store,
            column_view,
            current_path: RefCell::default(),
            weak_self: weak_self.clone(),
        });
        page.build_columns();

        let weak = Rc::downgrade(&page);
        page.column_view.connect_activate(move |_, position| {
            let Some(page) = weak.upgrade() else { return };
            let entry = selection
                .item(position)
                .map(|item| row_of(&item).entry.clone());
            if let Some(entry) = entry {
                page.open_entry(&entry);
            }
        });
        page
    }

    fn build_columns(&self) {
        let name = self.add_column(
            &tr("Name"),
            true,
            sorter(|e| e.name.to_lowercase()),
            |cell, row| {
                let icon_slot = cell
                    .first_child()
                    .and_downcast::<gtk::Box>()
                    .expect("icon slot");
                let label = cell
                    .last_child()
                    .and_downcast::<gtk::Label>()
                    .expect("label");
                while let Some(child) = icon_slot.first_child() {
                    icon_slot.remove(&child);
                }
                let icon = if row.entry.is_dir {
                    folder_image(row.color.as_deref(), ICON_DISPLAY_SIZE)
                } else {
                    small_icon(row.entry.icon_key())
                };
                icon_slot.append(&icon);
                label.set_label(&row.entry.display_name());
                label.set_tooltip_text(Some(&row.entry.display_name()));
            },
        );
        self.add_column(
            &tr("Type"),
            false,
            sorter(|e| type_label_text(e).to_lowercase()),
            |cell, row| {
                label_of(cell).set_label(&type_label_text(&row.entry));
            },
        );
        self.add_column(
            &tr("Size"),
            false,
            sorter(|e| e.size.map_or(-1, |s| s as i128)),
            |cell, row| {
                let text = match (row.entry.is_dir, row.entry.size) {
                    (false, Some(size)) => glib::format_size(size).to_string(),
                    _ => String::new(),
                };
                label_of(cell).set_label(&text);
            },
        );
        self.add_column(
            &tr("Modified"),
            false,
            sorter(|e| e.mtime.unwrap_or(-1)),
            |cell, row| {
                label_of(cell)
                    .set_label(&row.entry.mtime.map(format_timestamp).unwrap_or_default());
            },
        );
        self.column_view
            .sort_by_column(Some(&name), gtk::SortType::Ascending);
    }

    /// Cells are a `gtk::Box` (icon slot + label) for the name column, a
    /// plain `gtk::Label` for the others; all open the context menu.
    fn add_column(
        &self,
        title: &str,
        is_name: bool,
        sorter: gtk::CustomSorter,
        bind: impl Fn(&gtk::Widget, &DetailsRow) + 'static,
    ) -> gtk::ColumnViewColumn {
        let factory = gtk::SignalListItemFactory::new();
        let page = self.weak_self.clone();
        factory.connect_setup(move |_, item| {
            let item = item.downcast_ref::<gtk::ListItem>().expect("list item");
            let label = gtk::Label::new(None);
            label.set_xalign(0.0);
            label.set_ellipsize(pango::EllipsizeMode::End);
            let cell: gtk::Widget = if is_name {
                let cell = gtk::Box::new(gtk::Orientation::Horizontal, 8);
                cell.append(&gtk::Box::new(gtk::Orientation::Horizontal, 0));
                cell.append(&label);
                cell.upcast()
            } else {
                label.upcast()
            };
            cell.set_margin_top(4);
            cell.set_margin_bottom(4);
            cell.set_margin_start(6);
            cell.set_margin_end(6);
            attach_context_menu(&cell, item, &page);
            item.set_child(Some(&cell));
        });
        factory.connect_bind(move |_, item| {
            let item = item.downcast_ref::<gtk::ListItem>().expect("list item");
            if let (Some(cell), Some(object)) = (item.child(), item.item()) {
                bind(&cell, &row_of(&object));
            }
        });
        let column = gtk::ColumnViewColumn::new(Some(title), Some(factory));
        column.set_resizable(true);
        column.set_expand(is_name);
        column.set_sorter(Some(&sorter));
        self.column_view.append_column(&column);
        column
    }

    pub fn widget(&self) -> &gtk::Stack {
        &self.stack
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

    pub fn apply_click_to_open_setting(&self) {
        self.column_view
            .set_single_click_activate(self.ctx.settings().single_click_open);
    }

    pub fn reload(&self) {
        let Some(path) = self.current_path.borrow().clone() else {
            return;
        };
        let entries = self.ctx.list(&path);
        let mut colors = self.ctx.color_map(&path, &entries);
        let is_empty = entries.is_empty();
        let rows: Vec<glib::BoxedAnyObject> = entries
            .into_iter()
            .map(|entry| {
                let color = colors.remove(&entry.name);
                glib::BoxedAnyObject::new(DetailsRow { entry, color })
            })
            .collect();
        self.store.remove_all();
        self.store.extend_from_slice(&rows);
        self.stack
            .set_visible_child_name(if is_empty { "empty" } else { "details" });
    }

    fn open_entry(&self, entry: &FileEntryEntity) {
        if entry.is_dir {
            self.load_path(&entry.path);
            (self.events)(BrowserEvent::PathChanged(entry.path.clone()));
        } else {
            let _ = self.ctx.desktop.open_path(&entry.path);
        }
    }

    fn show_menu(&self, anchor: &gtk::Widget, row: &DetailsRow, x: f64, y: f64) {
        let hooks = single_folder_hooks(&self.weak_self, Self::open_entry, Self::reload);
        show_entry_menu(
            anchor,
            (x, y),
            &row.entry,
            row.color.clone(),
            &self.ctx,
            &self.events,
            &hooks,
        );
    }
}

fn label_of(cell: &gtk::Widget) -> gtk::Label {
    cell.clone().downcast::<gtk::Label>().expect("label cell")
}

fn attach_context_menu(cell: &gtk::Widget, item: &gtk::ListItem, page: &Weak<DetailsPage>) {
    let click = gtk::GestureClick::new();
    click.set_button(gdk::BUTTON_SECONDARY);
    let (item, page) = (item.downgrade(), page.clone());
    click.connect_pressed(move |gesture, _, x, y| {
        gesture.set_state(gtk::EventSequenceState::Claimed);
        let (item, page) = (item.clone(), page.clone());
        glib::idle_add_local_full(glib::Priority::HIGH_IDLE, move || {
            let (Some(item), Some(page)) = (item.upgrade(), page.upgrade()) else {
                return glib::ControlFlow::Break;
            };
            if let (Some(cell), Some(object)) = (item.child(), item.item()) {
                page.show_menu(&cell, &row_of(&object), x, y);
            }
            glib::ControlFlow::Break
        });
    });
    cell.add_controller(click);
}
