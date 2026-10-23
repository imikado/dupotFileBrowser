//! Some environments don't export GIO_EXTRA_MODULES, so GIO never loads the
//! host's `libgvfsdbus.so` and every `metadata::*` attribute (Nemo folder
//! colors) silently misses. Must run before the first GIO call.

use std::path::{Path, PathBuf};

pub fn ensure_metadata_module_discoverable() {
    if std::env::var_os("GIO_EXTRA_MODULES").is_some() {
        return;
    }
    if let Some(dir) = module_dir_candidates()
        .into_iter()
        .find(|dir| has_gvfs_module(dir))
    {
        // SAFETY: called first thing in `main`, before any other thread exists.
        unsafe { std::env::set_var("GIO_EXTRA_MODULES", dir) };
    }
}

fn module_dir_candidates() -> Vec<PathBuf> {
    let mut candidates: Vec<PathBuf> = std::fs::read_dir("/usr/lib")
        .into_iter()
        .flatten()
        .flatten()
        .map(|entry| entry.path().join("gio/modules"))
        .collect();
    candidates.sort();
    candidates.push("/usr/lib64/gio/modules".into());
    candidates.push("/usr/lib/gio/modules".into());
    candidates
}

fn has_gvfs_module(dir: &Path) -> bool {
    std::fs::read_dir(dir)
        .into_iter()
        .flatten()
        .flatten()
        .any(|entry| entry.file_name().to_string_lossy().contains("gvfsdbus"))
}
