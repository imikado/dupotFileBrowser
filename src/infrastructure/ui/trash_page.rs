//! Everything in the Trash, with its original location and deletion date,
//! and Restore / Delete Permanently / Empty Trash.

use std::rc::{Rc, Weak};

use adw::prelude::*;
use gtk::glib;

use crate::domain::entity::trash_entry_entity::TrashEntryEntity;
use crate::domain::shared::trash_info::format_deletion_date;
use crate::infrastructure::service::i18n_service::{tr, trf};
use crate::infrastructure::ui::app_context::AppContext;
use crate::infrastructure::ui::shared::alert_dialog::{show_confirm, show_error};
use crate::infrastructure::ui::shared::empty_state::{EMPTY_TRASH_ICON, empty_state};
use crate::infrastructure::ui::shared::file_icons::small_icon;

type RowAction = fn(&TrashPage, &TrashEntryEntity);

pub struct TrashPage {
    ctx: Rc<AppContext>,
    root: gtk::Box,
    list_box: gtk::ListBox,
    stack: gtk::Stack,
    empty_button: gtk::Button,
    weak_self: Weak<TrashPage>,
}

impl TrashPage {
    pub fn new(ctx: &Rc<AppContext>) -> Rc<Self> {
        let root = gtk::Box::new(gtk::Orientation::Vertical, 0);

        let header = gtk::Box::new(gtk::Orientation::Horizontal, 8);
        header.set_margin_top(12);
        header.set_margin_bottom(12);
        header.set_margin_start(16);
        header.set_margin_end(16);
        let title = gtk::Label::new(Some(&tr("Trash")));
        title.add_css_class("title-2");
        title.set_halign(gtk::Align::Start);
        title.set_hexpand(true);
        header.append(&title);
        let empty_button = gtk::Button::with_label(&tr("Empty Trash"));
        empty_button.add_css_class("destructive-action");
        header.append(&empty_button);
        root.append(&header);
        root.append(&gtk::Separator::new(gtk::Orientation::Horizontal));

        let list_box = gtk::ListBox::new();
        list_box.add_css_class("boxed-list");
        list_box.set_selection_mode(gtk::SelectionMode::None);
        list_box.set_margin_top(6);
        list_box.set_margin_start(12);
        list_box.set_margin_end(12);
        list_box.set_valign(gtk::Align::Start);

        let scroll = gtk::ScrolledWindow::new();
        scroll.set_vexpand(true);
        scroll.set_policy(gtk::PolicyType::Never, gtk::PolicyType::Automatic);
        scroll.set_child(Some(&list_box));

        let empty = empty_state(EMPTY_TRASH_ICON, &tr("Trash is empty"));

        let stack = gtk::Stack::new();
        stack.set_vexpand(true);
        stack.add_named(&scroll, Some("list"));
        stack.add_named(&empty, Some("empty"));
        root.append(&stack);

        let page = Rc::new_cyclic(|weak_self| Self {
            ctx: ctx.clone(),
            root,
            list_box,
            stack,
            empty_button,
            weak_self: weak_self.clone(),
        });
        let weak = Rc::downgrade(&page);
        page.empty_button.connect_clicked(move |_| {
            if let Some(page) = weak.upgrade() {
                page.confirm_empty();
            }
        });
        page
    }

    pub fn widget(&self) -> &gtk::Box {
        &self.root
    }

    pub fn refresh(&self) {
        self.list_box.remove_all();
        let entries = self.ctx.trash.list();
        self.empty_button.set_sensitive(!entries.is_empty());
        for entry in &entries {
            self.list_box.append(&self.build_row(entry));
        }
        self.stack
            .set_visible_child_name(if entries.is_empty() { "empty" } else { "list" });
    }

    fn build_row(&self, entry: &TrashEntryEntity) -> adw::ActionRow {
        let row = adw::ActionRow::new();
        row.set_title(&glib::markup_escape_text(&entry.display_name));
        row.set_title_lines(1);
        let mut subtitle = Vec::new();
        if !entry.original_path.is_empty() {
            subtitle.push(entry.original_path.clone());
        }
        let deleted = format_deletion_date(&entry.deletion_date);
        if !deleted.is_empty() {
            subtitle.push(trf("Deleted {when}", &[("when", &deleted)]));
        }
        if !subtitle.is_empty() {
            row.set_subtitle(&glib::markup_escape_text(&subtitle.join(" — ")));
            row.set_subtitle_lines(1);
        }
        row.add_prefix(&small_icon(entry.icon_key()));

        let buttons: [(&str, String, RowAction); 2] = [
            ("edit-undo-symbolic", tr("Restore"), Self::restore),
            (
                "user-trash-symbolic",
                tr("Delete Permanently"),
                Self::confirm_delete,
            ),
        ];
        for (icon, tooltip, action) in buttons {
            let button = gtk::Button::new();
            button.set_icon_name(icon);
            button.set_tooltip_text(Some(&tooltip));
            button.add_css_class("flat");
            button.set_valign(gtk::Align::Center);
            let (page, entry) = (self.weak_self.clone(), entry.clone());
            button.connect_clicked(move |_| {
                if let Some(page) = page.upgrade() {
                    action(&page, &entry);
                }
            });
            row.add_suffix(&button);
        }
        row
    }

    fn restore(&self, entry: &TrashEntryEntity) {
        let name = [("name", entry.display_name.as_str())];
        let error = if entry.original_path.is_empty() {
            Some(trf("\"{name}\" has no recorded original location.", &name))
        } else if self.ctx.file_system.exists(entry.original_path.as_ref()) {
            Some(trf(
                "\"{name}\" already exists at its original location:\n{path}",
                &[
                    ("name", &entry.display_name),
                    ("path", &entry.original_path),
                ],
            ))
        } else if self.ctx.trash.restore(entry).is_err() {
            Some(trf("\"{name}\" could not be restored.", &name))
        } else {
            None
        };
        match error {
            Some(body) => show_error(&self.root, &tr("Could not restore"), &body),
            None => self.refresh(),
        }
    }

    fn confirm_delete(&self, entry: &TrashEntryEntity) {
        let (page, entry) = (self.weak_self.clone(), entry.clone());
        show_confirm(
            &self.root,
            &tr("Delete Permanently?"),
            &trf(
                "\"{name}\" will be permanently deleted. This cannot be undone.",
                &[("name", &entry.display_name)],
            ),
            &tr("Delete Permanently"),
            true,
            move || {
                let Some(page) = page.upgrade() else { return };
                if page.ctx.trash.delete(&entry.trashed_path).is_err() {
                    show_error(
                        &page.root,
                        &tr("Could not delete"),
                        &trf(
                            "\"{name}\" could not be permanently deleted.",
                            &[("name", &entry.display_name)],
                        ),
                    );
                    return;
                }
                page.refresh();
            },
        );
    }

    fn confirm_empty(&self) {
        let page = self.weak_self.clone();
        show_confirm(
            &self.root,
            &tr("Empty Trash?"),
            &tr("All items in the Trash will be permanently deleted. This cannot be undone."),
            &tr("Empty Trash"),
            true,
            move || {
                let Some(page) = page.upgrade() else { return };
                if page.ctx.trash.empty().is_err() {
                    show_error(
                        &page.root,
                        &tr("Could not empty Trash"),
                        &tr("Some items could not be permanently deleted."),
                    );
                }
                page.refresh();
            },
        );
    }
}
