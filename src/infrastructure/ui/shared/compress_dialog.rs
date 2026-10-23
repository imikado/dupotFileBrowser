use std::path::{Path, PathBuf};
use std::rc::Rc;

use gtk::glib;
use gtk::prelude::*;

use crate::domain::entity::file_operation_entity::{FileOperationEntity, FileOperationKind};
use crate::domain::shared::archive::ArchiveFormat;
use crate::domain::shared::path::file_name;
use crate::domain::usecase::destination::{Destination, compress_destination};
use crate::infrastructure::service::i18n_service::{tr, trf};
use crate::infrastructure::ui::app_context::AppContext;
use crate::infrastructure::ui::shared::alert_dialog::ask_name;

/// Asks for an archive name and format for `path`, then hands the job to
/// `on_confirmed`. A name already taken asks again, keeping the attempt.
pub fn show_compress_dialog(
    parent: &gtk::Widget,
    ctx: &Rc<AppContext>,
    path: &Path,
    initial_name: Option<String>,
    on_confirmed: Rc<dyn Fn(FileOperationEntity)>,
) {
    let name = file_name(path);
    let labels: Vec<String> = ArchiveFormat::ALL.iter().map(|f| tr(f.label())).collect();
    let label_refs: Vec<&str> = labels.iter().map(String::as_str).collect();
    let format_dropdown = gtk::DropDown::from_strings(&label_refs);
    format_dropdown.set_selected(0);

    let (parent_widget, ctx, path) = (parent.clone(), ctx.clone(), PathBuf::from(path));
    let dropdown = format_dropdown.clone();
    ask_name(
        parent,
        &tr("Compress"),
        &trf(
            "Choose an archive name and format for \"{name}\".",
            &[("name", &name)],
        ),
        &tr("Compress"),
        initial_name.as_deref().unwrap_or(&name),
        Some(format_dropdown.upcast_ref()),
        move |archive_name| {
            let format =
                ArchiveFormat::ALL[dropdown.selected() as usize % ArchiveFormat::ALL.len()];
            match compress_destination(ctx.file_system.as_ref(), &path, &archive_name, format) {
                Destination::Free(destination) => on_confirmed(FileOperationEntity::new(
                    FileOperationKind::Compress(format),
                    &path,
                    &destination,
                )),
                Destination::Taken(taken) => {
                    let (parent, ctx, path, on_confirmed) = (
                        parent_widget.clone(),
                        ctx.clone(),
                        path.clone(),
                        on_confirmed.clone(),
                    );
                    glib::idle_add_local_once(move || {
                        show_compress_dialog(&parent, &ctx, &path, Some(taken), on_confirmed)
                    });
                }
                Destination::Invalid => {}
            }
        },
    );
}
