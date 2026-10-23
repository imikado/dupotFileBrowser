use std::path::{Path, PathBuf};

use dupot_file_browser::domain::shared::path::{
    ancestor_chain, file_name, parent_dir, split_extension, valid_file_name,
};

#[test]
fn parent_of_root_is_root() {
    assert_eq!(parent_dir(Path::new("/home/me")), PathBuf::from("/home"));
    assert_eq!(parent_dir(Path::new("/home")), PathBuf::from("/"));
    assert_eq!(parent_dir(Path::new("/")), PathBuf::from("/"));
}

#[test]
fn names() {
    assert_eq!(file_name(Path::new("/home/me/")), "me");
    assert_eq!(file_name(Path::new("/")), "/");
}

#[test]
fn chain_from_root() {
    assert_eq!(
        ancestor_chain(Path::new("/home/me")),
        vec![
            PathBuf::from("/"),
            PathBuf::from("/home"),
            PathBuf::from("/home/me")
        ]
    );
    assert_eq!(ancestor_chain(Path::new("/")), vec![PathBuf::from("/")]);
}

#[test]
fn file_name_validation() {
    assert_eq!(valid_file_name("  notes.txt "), Some("notes.txt"));
    assert_eq!(valid_file_name("   "), None);
    assert_eq!(valid_file_name("a/b"), None);
    assert_eq!(valid_file_name(".."), None);
}

#[test]
fn extension_like_python_splitext() {
    assert_eq!(split_extension("a.tar.gz"), ("a.tar", ".gz"));
    assert_eq!(split_extension(".bashrc"), (".bashrc", ""));
    assert_eq!(split_extension("..a.b"), ("..a", ".b"));
    assert_eq!(split_extension("README"), ("README", ""));
}
