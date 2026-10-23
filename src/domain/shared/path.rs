use std::path::{Path, PathBuf};

/// Parent folder; `/` is its own parent.
pub fn parent_dir(path: &Path) -> PathBuf {
    match path.parent() {
        Some(parent) if !parent.as_os_str().is_empty() => parent.to_path_buf(),
        _ => PathBuf::from("/"),
    }
}

/// Last component, or the whole path for `/`.
pub fn file_name(path: &Path) -> String {
    path.file_name().map_or_else(
        || path.to_string_lossy().into_owned(),
        |name| name.to_string_lossy().into_owned(),
    )
}

/// Every folder from `/` down to `path` (inclusive), root first.
pub fn ancestor_chain(path: &Path) -> Vec<PathBuf> {
    let mut chain: Vec<PathBuf> = path.ancestors().map(Path::to_path_buf).collect();
    chain.reverse();
    chain
}

/// Like `ancestor_chain`, but starting at `root` when `path` is inside it
/// (the home folder: its parents are rarely where the user is headed).
pub fn ancestor_chain_from(path: &Path, root: &Path) -> Vec<PathBuf> {
    let mut chain = ancestor_chain(path);
    if let Some(start) = chain.iter().position(|folder| folder == root) {
        chain.drain(..start);
    }
    chain
}

/// Trimmed `name` if usable as a single file name in a folder.
pub fn valid_file_name(name: &str) -> Option<&str> {
    let name = name.trim();
    (!name.is_empty() && name != "." && name != ".." && !name.contains('/')).then_some(name)
}

/// `name` split into stem and extension like Python's `os.path.splitext`:
/// `a.tar.gz` -> (`a.tar`, `.gz`), `.bashrc` -> (`.bashrc`, ``).
pub fn split_extension(name: &str) -> (&str, &str) {
    let leading_dots = name.len() - name.trim_start_matches('.').len();
    match name[leading_dots..].rfind('.') {
        Some(index) => name.split_at(leading_dots + index),
        None => (name, ""),
    }
}
