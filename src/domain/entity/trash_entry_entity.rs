use std::path::PathBuf;

/// One item currently in the Trash, read from `Trash/files` and its
/// `Trash/info/*.trashinfo`: carries the original location and deletion date.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TrashEntryEntity {
    pub trashed_path: PathBuf,
    pub display_name: String,
    /// Empty when the `.trashinfo` file is missing or unreadable.
    pub original_path: String,
    /// `YYYY-MM-DDThh:mm:ss`, or empty.
    pub deletion_date: String,
    pub is_dir: bool,
}

impl TrashEntryEntity {
    pub fn icon_key(&self) -> &'static str {
        if self.is_dir { "folder" } else { "generic" }
    }
}
