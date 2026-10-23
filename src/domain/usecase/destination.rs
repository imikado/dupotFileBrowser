//! Where file operations write, and whether the user must pick another name.

use std::path::{Path, PathBuf};

use crate::domain::contract::file_system_repository::FileSystemRepository;
use crate::domain::shared::archive::{ArchiveFormat, archive_base_name};
use crate::domain::shared::path::{file_name, parent_dir, valid_file_name};

/// Outcome of choosing a destination path.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Destination {
    Free(PathBuf),
    /// Already exists: ask for another name, starting from this one.
    Taken(String),
    /// Empty or otherwise unusable name: nothing to do.
    Invalid,
}

fn check(
    repository: &dyn FileSystemRepository,
    folder: &Path,
    name: &str,
    suffix: &str,
) -> Destination {
    let Some(name) = valid_file_name(name) else {
        return Destination::Invalid;
    };
    let destination = folder.join(format!("{name}{suffix}"));
    if repository.exists(&destination) {
        Destination::Taken(name.to_string())
    } else {
        Destination::Free(destination)
    }
}

/// Pasting `source` into `folder`, under `name` (its own name by default).
pub fn paste_destination(
    repository: &dyn FileSystemRepository,
    folder: &Path,
    source: &Path,
    name: Option<&str>,
) -> Destination {
    let default_name = file_name(source);
    check(repository, folder, name.unwrap_or(&default_name), "")
}

/// Folder `archive` is extracted into, next to it.
pub fn extract_destination(
    repository: &dyn FileSystemRepository,
    archive: &Path,
    name: Option<&str>,
) -> Destination {
    let default_name = archive_base_name(archive);
    check(
        repository,
        &parent_dir(archive),
        name.unwrap_or(&default_name),
        "",
    )
}

/// Archive of `source` named `archive_name` + the format's extension.
pub fn compress_destination(
    repository: &dyn FileSystemRepository,
    source: &Path,
    archive_name: &str,
    format: ArchiveFormat,
) -> Destination {
    check(
        repository,
        &parent_dir(source),
        archive_name,
        format.extension(),
    )
}

/// Renaming `path` to `new_name`; `Invalid` when the name is unchanged.
pub fn rename_destination(
    repository: &dyn FileSystemRepository,
    path: &Path,
    new_name: &str,
) -> Destination {
    if valid_file_name(new_name) == Some(file_name(path).as_str()) {
        return Destination::Invalid;
    }
    check(repository, &parent_dir(path), new_name, "")
}
