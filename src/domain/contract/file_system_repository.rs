use std::path::{Path, PathBuf};

use crate::domain::entity::file_entry_entity::FileEntryEntity;
use crate::domain::entity::file_properties_entity::FilePropertiesEntity;
use crate::domain::error::DomainResult;

/// Plain file system access; implemented in `infrastructure::api`.
pub trait FileSystemRepository: Send + Sync {
    /// Entries of `path`, unsorted; empty when it cannot be read.
    fn list_dir(&self, path: &Path) -> Vec<FileEntryEntity>;
    fn exists(&self, path: &Path) -> bool;
    fn is_dir(&self, path: &Path) -> bool;
    fn home_dir(&self) -> PathBuf;
    /// Recursive copy keeping symlinks, permissions and times (`cp -a`).
    fn copy_path(&self, source: &Path, destination: &Path) -> DomainResult<()>;
    /// Rename, or copy then delete across file systems.
    fn move_path(&self, source: &Path, destination: &Path) -> DomainResult<()>;
    /// Total size of the files under `path`, symlinks not followed.
    fn dir_size(&self, path: &Path) -> u64;
    fn file_properties(&self, path: &Path) -> FilePropertiesEntity;
    fn set_permissions(&self, path: &Path, mode: u32) -> DomainResult<()>;
}
