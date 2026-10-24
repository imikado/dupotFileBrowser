//! Right-click menu of a file or folder, shared by the three browser views.

use std::path::{Path, PathBuf};
use std::rc::{Rc, Weak};

use gtk::prelude::*;
use gtk::{gdk, gio, glib};

use crate::domain::entity::file_entry_entity::FileEntryEntity;
use crate::domain::entity::file_operation_entity::FileOperationEntity;
use crate::domain::shared::path::{file_name, parent_dir};
use crate::infrastructure::service::i18n_service::{tr, trf};
use crate::infrastructure::ui::app_context::{AppContext, BrowserEvent, EventSink};
use crate::infrastructure::ui::shared::alert_dialog::{show_confirm, show_error};
use crate::infrastructure::ui::shared::color_picker_popup::show_color_picker;
use crate::infrastructure::ui::shared::compress_dialog::show_compress_dialog;
use crate::infrastructure::ui::shared::context_menu::{MenuItem, show_sectioned_menu};
use crate::infrastructure::ui::shared::open_with_popup::show_open_with_popup;
use crate::infrastructure::ui::shared::properties_dialog::show_properties_dialog;
use crate::infrastructure::ui::shared::rename_dialog::show_rename_dialog;

pub type RenamedHook = Rc<dyn Fn(&FileEntryEntity, PathBuf)>;

/// How the view reacts to what the menu did.
#[derive(Clone)]
pub struct EntryMenuHooks {
    pub open: Rc<dyn Fn(&FileEntryEntity)>,
    /// After a rename, with the new path.
    pub renamed: RenamedHook,
    /// After the entry moved to the Trash.
    pub trashed: Rc<dyn Fn(&FileEntryEntity)>,
    /// After its color changed.
    pub recolored: Rc<dyn Fn(&FileEntryEntity)>,
}

/// Menu hooks of the single-folder views: everything but "Open" reloads.
pub fn single_folder_hooks<P: 'static>(
    page: &Weak<P>,
    open: fn(&P, &FileEntryEntity),
    reload: fn(&P),
) -> EntryMenuHooks {
    let reload_hook = {
        let page = page.clone();
        move || {
            if let Some(page) = page.upgrade() {
                reload(&page);
            }
        }
    };
    let page = page.clone();
    let (renamed, trashed, recolored) = (reload_hook.clone(), reload_hook.clone(), reload_hook);
    EntryMenuHooks {
        open: Rc::new(move |entry| {
            if let Some(page) = page.upgrade() {
                open(&page, entry);
            }
        }),
        renamed: Rc::new(move |_, _| renamed()),
        trashed: Rc::new(move |_| trashed()),
        recolored: Rc::new(move |_| recolored()),
    }
}

/// File + URI list on the clipboard, the way Nautilus does it, so Paste
/// works across GTK file managers.
pub fn copy_file_to_clipboard(widget: &impl IsA<gtk::Widget>, path: &Path, cut: bool) {
    let uri = gio::File::for_path(path).uri();
    let gnome = format!("{}\n{uri}\n", if cut { "cut" } else { "copy" });
    let uri_list = format!("{uri}\r\n");
    let provider = gdk::ContentProvider::new_union(&[
        gdk::ContentProvider::for_bytes(
            "x-special/gnome-copied-files",
            &glib::Bytes::from_owned(gnome.into_bytes()),
        ),
        gdk::ContentProvider::for_bytes(
            "text/uri-list",
            &glib::Bytes::from_owned(uri_list.into_bytes()),
        ),
    ]);
    let _ = widget.clipboard().set_content(Some(&provider));
}

pub fn copy_text_to_clipboard(widget: &impl IsA<gtk::Widget>, text: &str) {
    widget.clipboard().set_text(text);
}

/// Opens `path` with its default application, telling the user when that
/// fails (no application for the type, missing file…).
pub fn open_file(parent: &impl IsA<gtk::Widget>, ctx: &AppContext, path: &Path) {
    if let Err(error) = ctx.desktop.open_path(path) {
        let body = trf(
            "\"{name}\" could not be opened.",
            &[("name", &file_name(path))],
        );
        show_error(
            parent,
            &tr("Could not open file"),
            &format!("{body}\n\n{error}"),
        );
    }
}

/// Sets the wallpaper off the main thread (several host commands).
fn set_wallpaper(parent: &gtk::Widget, ctx: &Rc<AppContext>, path: &Path) {
    let desktop = ctx.desktop.clone();
    let path = path.to_path_buf();
    let weak_parent = parent.downgrade();
    glib::spawn_future_local(async move {
        let done = gio::spawn_blocking(move || desktop.set_wallpaper(&path)).await;
        if !done.unwrap_or(false)
            && let Some(parent) = weak_parent.upgrade()
        {
            show_error(
                &parent,
                &tr("Could not set wallpaper"),
                &tr("No supported desktop environment setting could be found."),
            );
        }
    });
}

/// Everything a menu action needs.
struct Target {
    anchor: gtk::Widget,
    ctx: Rc<AppContext>,
    entry: FileEntryEntity,
    color: Option<String>,
    events: EventSink,
    hooks: EntryMenuHooks,
}

/// Menu pointing at `(x, y)` in `anchor`.
pub fn show_entry_menu(
    anchor: &gtk::Widget,
    (x, y): (f64, f64),
    entry: &FileEntryEntity,
    color: Option<String>,
    ctx: &Rc<AppContext>,
    events: &EventSink,
    hooks: &EntryMenuHooks,
) {
    let target = Rc::new(Target {
        anchor: anchor.clone(),
        ctx: ctx.clone(),
        entry: entry.clone(),
        color,
        events: events.clone(),
        hooks: hooks.clone(),
    });
    let item = |label: String, action: fn(&Rc<Target>)| {
        let target = target.clone();
        MenuItem::new(label, move || action(&target))
    };

    let mut open = vec![item(tr("Open"), |t| (t.hooks.open)(&t.entry))];
    if !entry.is_dir {
        open.push(item(tr("Open With…"), |t| {
            show_open_with_popup(&t.anchor, &t.ctx, &t.entry.path)
        }));
    }
    open.push(item(tr("Open Terminal Here"), |t| {
        if !t.ctx.desktop.open_terminal(&t.entry.path) {
            show_error(
                &t.anchor,
                &tr("No terminal found"),
                &tr("No terminal emulator could be found on this system."),
            );
        }
    }));

    let clipboard = vec![
        item(tr("Cut"), |t| copy_to_clipboard(t, true)),
        item(tr("Copy"), |t| copy_to_clipboard(t, false)),
        item(tr("Copy Path"), |t| {
            copy_text_to_clipboard(&t.anchor, &t.entry.path.to_string_lossy())
        }),
    ];

    let mut organize = vec![
        item(tr("Rename"), |t| {
            let target = t.clone();
            let on_renamed: Rc<dyn Fn(PathBuf)> = Rc::new(move |destination| {
                let moved_favorites = target
                    .ctx
                    .settings_mut()
                    .rename_favorites(&target.entry.path, &destination);
                if moved_favorites {
                    target.ctx.save_settings();
                    (target.events)(BrowserEvent::FavoritesChanged);
                }
                (target.hooks.renamed)(&target.entry, destination);
                (target.events)(BrowserEvent::FolderChanged(parent_dir(&target.entry.path)));
            });
            show_rename_dialog(&t.anchor, &t.ctx, &t.entry.path, None, on_renamed);
        }),
        item(tr("Add Color"), |t| {
            let target = t.clone();
            show_color_picker(&t.anchor, t.color.as_deref(), move |picked| {
                target.ctx.set_color(&target.entry, picked.as_deref());
                (target.hooks.recolored)(&target.entry);
            });
        }),
    ];
    if entry.is_dir {
        organize.push(item(tr("Add to favorites"), |t| {
            t.ctx
                .settings_mut()
                .add_favorite(&t.entry.name, &t.entry.path.to_string_lossy());
            t.ctx.save_settings();
            (t.events)(BrowserEvent::FavoritesChanged);
        }));
    }

    let mut tools = vec![item(tr("Compress…"), |t| {
        let events = t.events.clone();
        let on_confirmed: Rc<dyn Fn(FileOperationEntity)> =
            Rc::new(move |job| events(BrowserEvent::Job(job)));
        show_compress_dialog(&t.anchor, &t.ctx, &t.entry.path, None, on_confirmed);
    })];
    if entry.is_extractable_archive() {
        tools.push(item(tr("Extract"), |t| {
            (t.events)(BrowserEvent::Extract(t.entry.path.clone()))
        }));
    }
    if entry.is_image() {
        tools.push(item(tr("Use as Wallpaper"), |t| {
            set_wallpaper(&t.anchor, &t.ctx, &t.entry.path)
        }));
    }

    let info = vec![item(tr("Properties"), |t| {
        show_properties_dialog(&t.anchor, &t.ctx, &t.entry.path)
    })];
    let trash = vec![item(tr("Move to Trash"), confirm_trash).destructive()];

    show_sectioned_menu(
        anchor,
        x,
        y,
        vec![open, clipboard, organize, tools, info, trash],
    );
}

fn copy_to_clipboard(target: &Rc<Target>, cut: bool) {
    copy_file_to_clipboard(&target.anchor, &target.entry.path, cut);
    (target.events)(BrowserEvent::Clipboard {
        path: target.entry.path.clone(),
        cut,
    });
}

fn confirm_trash(target: &Rc<Target>) {
    let name = target.entry.name.clone();
    let target_for_action = target.clone();
    show_confirm(
        &target.anchor,
        &tr("Move to Trash?"),
        &trf("\"{name}\" will be moved to the Trash.", &[("name", &name)]),
        &tr("Move to Trash"),
        true,
        move || {
            let t = &target_for_action;
            match t.ctx.trash.trash(&t.entry.path) {
                Ok(()) => {
                    (t.hooks.trashed)(&t.entry);
                    (t.events)(BrowserEvent::FolderChanged(parent_dir(&t.entry.path)));
                    (t.events)(BrowserEvent::FolderChanged(t.ctx.trash.trash_dir()));
                }
                Err(_) => show_error(
                    &t.anchor,
                    &tr("Could not move to Trash"),
                    &trf(
                        "\"{name}\" could not be moved to the Trash.",
                        &[("name", &t.entry.name)],
                    ),
                ),
            }
        },
    );
}
