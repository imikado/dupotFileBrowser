use std::collections::HashMap;
use std::path::Path;

/// Color tags on files and folders (see `domain::shared::folder_color`).
pub trait ColorTagRepository: Send + Sync {
    /// `{entry name: color}` for the files tagged directly in `directory`.
    fn colored_path_map(&self, directory: &Path) -> HashMap<String, String>;
    /// Tags (or untags, with `None`) the file `name` of `directory`.
    fn set_file_color(&self, directory: &Path, name: &str, color: Option<&str>);
    fn folder_color(&self, folder: &Path) -> Option<String>;
    fn set_folder_color(&self, folder: &Path, color: Option<&str>);
}
