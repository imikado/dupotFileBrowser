/// A file or folder's metadata, shown by the Properties dialog. `None`
/// fields could not be read.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FilePropertiesEntity {
    pub name: String,
    pub location: String,
    pub type_description: String,
    pub is_dir: bool,
    /// File size in bytes (files only).
    pub size: Option<u64>,
    /// Number of direct children (folders only).
    pub item_count: Option<usize>,
    /// Seconds since the Unix epoch.
    pub modified: Option<i64>,
    pub owner: Option<String>,
    pub group: Option<String>,
    /// Permission bits (`st_mode & 0o7777`), editable from the dialog.
    pub mode: Option<u32>,
}
