use std::cmp::Ordering;
use std::path::Path;

use crate::domain::contract::file_system_repository::FileSystemRepository;
use crate::domain::entity::file_entry_entity::FileEntryEntity;

/// Entries of `path`, dotfiles left out unless `show_hidden`: folders
/// first, then by name ignoring case.
pub fn list_directory(
    repository: &dyn FileSystemRepository,
    path: &Path,
    show_hidden: bool,
) -> Vec<FileEntryEntity> {
    let mut entries: Vec<FileEntryEntity> = repository
        .list_dir(path)
        .into_iter()
        .filter(|entry| show_hidden || !entry.is_hidden())
        .collect();
    sort_entries(&mut entries);
    entries
}

pub fn sort_entries(entries: &mut [FileEntryEntity]) {
    entries.sort_by(|a, b| compare_by(a, b, &(), &()));
}

/// Folders before files, then `key_a`/`key_b` (one column of the Details
/// view), then name ignoring case.
pub fn compare_by<K: PartialOrd>(
    a: &FileEntryEntity,
    b: &FileEntryEntity,
    key_a: &K,
    key_b: &K,
) -> Ordering {
    b.is_dir
        .cmp(&a.is_dir)
        .then_with(|| key_a.partial_cmp(key_b).unwrap_or(Ordering::Equal))
        .then_with(|| a.is_hidden().cmp(&b.is_hidden()))
        .then_with(|| a.name.to_lowercase().cmp(&b.name.to_lowercase()))
}
