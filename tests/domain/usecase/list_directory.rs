use std::path::Path;

use dupot_file_browser::domain::usecase::list_directory::list_directory;

use super::FakeFileSystem;

fn names(show_hidden: bool) -> Vec<String> {
    let fs = FakeFileSystem::with(&[
        ("b.txt", false),
        ("Zeta", true),
        (".hidden", false),
        ("A.txt", false),
        ("alpha", true),
        (".config", true),
    ]);
    list_directory(&fs, Path::new("/data"), show_hidden)
        .into_iter()
        .map(|entry| entry.name)
        .collect()
}

#[test]
fn folders_first_then_name_ignoring_case() {
    assert_eq!(names(false), ["alpha", "Zeta", "A.txt", "b.txt"]);
}

#[test]
fn hidden_entries_after_visible_ones() {
    assert_eq!(
        names(true),
        ["alpha", "Zeta", ".config", "A.txt", "b.txt", ".hidden"]
    );
}
