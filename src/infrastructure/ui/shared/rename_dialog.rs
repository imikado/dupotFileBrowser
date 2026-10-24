use std::path::{Path, PathBuf};
use std::rc::Rc;

use gtk::glib;

use crate::domain::shared::path::file_name;
use crate::domain::usecase::destination::{Destination, rename_destination};
use crate::infrastructure::service::i18n_service::{tr, trf};
use crate::infrastructure::ui::app_context::AppContext;
use crate::infrastructure::ui::shared::alert_dialog::{ask_name, show_error};

/// Renames `path` (a plain same-folder move, done synchronously), then
/// calls `on_renamed` with the new path. A taken name asks again.
pub fn show_rename_dialog(
    parent: &gtk::Widget,
    ctx: &Rc<AppContext>,
    path: &Path,
    initial_name: Option<String>,
    on_renamed: Rc<dyn Fn(PathBuf)>,
) {
    let name = file_name(path);
    let (parent_widget, ctx, path) = (parent.clone(), ctx.clone(), PathBuf::from(path));
    ask_name(
        parent,
        &tr("Rename"),
        &trf("Choose a new name for \"{name}\".", &[("name", &name)]),
        &tr("Rename"),
        initial_name.as_deref().unwrap_or(&name),
        None,
        move |new_name| match rename_destination(ctx.file_system.as_ref(), &path, &new_name) {
            Destination::Free(destination) => {
                let color = ctx.color_at(&path);
                match ctx.file_system.move_path(&path, &destination) {
                    Ok(()) => {
                        ctx.transfer_color(&path, &destination, color.as_deref());
                        on_renamed(destination)
                    }
                    Err(error) => {
                        let body = format!(
                            "{}\n\n{error}",
                            trf(
                                "Could not rename \"{name}\".",
                                &[("name", &file_name(&path))]
                            )
                        );
                        show_error(&parent_widget, &tr("Rename failed"), &body);
                    }
                }
            }
            Destination::Taken(taken) => {
                let (parent, ctx, path, on_renamed) = (
                    parent_widget.clone(),
                    ctx.clone(),
                    path.clone(),
                    on_renamed.clone(),
                );
                glib::idle_add_local_once(move || {
                    show_rename_dialog(&parent, &ctx, &path, Some(taken), on_renamed)
                });
            }
            Destination::Invalid => {}
        },
    );
}
