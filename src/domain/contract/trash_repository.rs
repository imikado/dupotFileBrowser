use std::path::{Path, PathBuf};

use crate::domain::entity::trash_entry_entity::TrashEntryEntity;
use crate::domain::error::DomainResult;

/// The user's real Trash (`~/.local/share/Trash`), shared with the other
/// file managers.
pub trait TrashRepository: Send + Sync {
    /// Folder holding the trashed files.
    fn trash_dir(&self) -> PathBuf;
    fn trash(&self, path: &Path) -> DomainResult<()>;
    /// Newest first.
    fn list(&self) -> Vec<TrashEntryEntity>;
    fn restore(&self, entry: &TrashEntryEntity) -> DomainResult<()>;
    fn delete(&self, trashed_path: &Path) -> DomainResult<()>;
    /// Deletes everything; fails if any item could not be deleted.
    fn empty(&self) -> DomainResult<()>;
}
