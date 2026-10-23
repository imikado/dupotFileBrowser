//! Color tags: GVFS metadata for folders (Nemo-compatible), with the
//! `.dupotFileBrowser` sidecar file as fallback and for files.

use std::collections::HashMap;
use std::path::Path;

use gtk::gio;
use gtk::gio::prelude::*;
use gtk::glib;
use gtk::glib::translate::ToGlibPtr;
use serde_json::Value;

use crate::domain::contract::color_tag_repository::ColorTagRepository;
use crate::domain::shared::folder_color::{
    NEMO_CUSTOM_ICON_ATTRIBUTE, SIDECAR_FILE_NAME, color_from_nemo_icon_uri, colored_path_map,
    nemo_icon_uri, with_colored_path,
};
use crate::domain::shared::path::{file_name, parent_dir};

#[derive(Clone, Copy, Debug, Default)]
pub struct ColorTagApi;

fn read_sidecar(directory: &Path) -> Value {
    std::fs::read_to_string(directory.join(SIDECAR_FILE_NAME))
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
        .filter(Value::is_object)
        .unwrap_or_else(|| Value::Object(Default::default()))
}

fn update_sidecar(directory: &Path, name: &str, color: Option<&str>) {
    if let Some(updated) = with_colored_path(&read_sidecar(directory), name, color) {
        let _ = std::fs::write(directory.join(SIDECAR_FILE_NAME), updated.to_string());
    }
}

/// Sets or clears (`None`) the Nemo custom icon; `false` when GVFS metadata
/// is unavailable or Nemo has no icon for `color`.
fn set_metadata_color(folder: &Path, color: Option<&str>) -> bool {
    let file = gio::File::for_path(folder);
    match color {
        Some(color) => nemo_icon_uri(color).is_some_and(|uri| {
            file.set_attribute_string(
                NEMO_CUSTOM_ICON_ATTRIBUTE,
                &uri,
                gio::FileQueryInfoFlags::NONE,
                gio::Cancellable::NONE,
            )
            .is_ok()
        }),
        None => unset_attribute(&file, NEMO_CUSTOM_ICON_ATTRIBUTE),
    }
}

/// `g_file_set_attribute` with `G_FILE_ATTRIBUTE_TYPE_INVALID`, which the
/// bindings don't expose: how GVFS metadata is removed.
fn unset_attribute(file: &gio::File, attribute: &str) -> bool {
    let mut error = std::ptr::null_mut();
    // SAFETY: valid GFile and NUL-terminated attribute; the INVALID type
    // takes no value pointer.
    unsafe {
        let ok = gio::ffi::g_file_set_attribute(
            file.to_glib_none().0,
            attribute.to_glib_none().0,
            gio::ffi::G_FILE_ATTRIBUTE_TYPE_INVALID,
            std::ptr::null_mut(),
            gio::ffi::G_FILE_QUERY_INFO_NONE,
            std::ptr::null_mut(),
            &mut error,
        );
        if !error.is_null() {
            glib::ffi::g_error_free(error);
        }
        ok != glib::ffi::GFALSE
    }
}

fn metadata_color(folder: &Path) -> Option<String> {
    let info = gio::File::for_path(folder)
        .query_info(
            NEMO_CUSTOM_ICON_ATTRIBUTE,
            gio::FileQueryInfoFlags::NONE,
            gio::Cancellable::NONE,
        )
        .ok()?;
    let uri = info.attribute_string(NEMO_CUSTOM_ICON_ATTRIBUTE)?;
    color_from_nemo_icon_uri(&uri).map(str::to_string)
}

impl ColorTagRepository for ColorTagApi {
    fn colored_path_map(&self, directory: &Path) -> HashMap<String, String> {
        colored_path_map(&read_sidecar(directory))
    }

    fn set_file_color(&self, directory: &Path, name: &str, color: Option<&str>) {
        update_sidecar(directory, name, color);
    }

    fn folder_color(&self, folder: &Path) -> Option<String> {
        metadata_color(folder).or_else(|| {
            self.colored_path_map(&parent_dir(folder))
                .remove(&file_name(folder))
        })
    }

    fn set_folder_color(&self, folder: &Path, color: Option<&str>) {
        let (parent, name) = (parent_dir(folder), file_name(folder));
        if set_metadata_color(folder, color) {
            // Metadata wins: drop any stale sidecar entry.
            update_sidecar(&parent, &name, None);
        } else {
            update_sidecar(&parent, &name, color);
        }
    }
}
