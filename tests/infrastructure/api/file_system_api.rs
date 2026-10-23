use std::fs;
use std::os::unix::fs::{PermissionsExt, symlink};

use dupot_file_browser::domain::contract::file_system_repository::FileSystemRepository;
use dupot_file_browser::infrastructure::api::file_system_api::FileSystemApi;

use super::temp_dir;

#[test]
fn lists_entries_with_metadata() {
    let dir = temp_dir("fs-list");
    fs::write(dir.join("a.txt"), "hello").unwrap();
    fs::create_dir(dir.join("sub")).unwrap();
    symlink(dir.join("sub"), dir.join("link")).unwrap();

    let mut entries = FileSystemApi.list_dir(&dir);
    entries.sort_by(|a, b| a.name.cmp(&b.name));
    let summary: Vec<_> = entries
        .iter()
        .map(|e| (e.name.as_str(), e.is_dir, e.size))
        .collect();
    assert_eq!(
        summary,
        [
            ("a.txt", false, Some(5)),
            ("link", true, None),
            ("sub", true, None)
        ]
    );
    assert!(entries.iter().all(|e| e.mtime.is_some()));
    assert!(FileSystemApi.list_dir(&dir.join("missing")).is_empty());
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn copy_keeps_tree_symlinks_and_permissions() {
    let dir = temp_dir("fs-copy");
    let source = dir.join("src");
    fs::create_dir_all(source.join("nested")).unwrap();
    fs::write(source.join("nested/run.sh"), "#!/bin/sh").unwrap();
    fs::set_permissions(
        source.join("nested/run.sh"),
        fs::Permissions::from_mode(0o750),
    )
    .unwrap();
    symlink("nested/run.sh", source.join("shortcut")).unwrap();

    let copy = dir.join("copy");
    FileSystemApi.copy_path(&source, &copy).unwrap();
    assert_eq!(
        fs::read_to_string(copy.join("nested/run.sh")).unwrap(),
        "#!/bin/sh"
    );
    let mode = fs::metadata(copy.join("nested/run.sh"))
        .unwrap()
        .permissions()
        .mode();
    assert_eq!(mode & 0o777, 0o750);
    assert_eq!(
        fs::read_link(copy.join("shortcut")).unwrap().to_str(),
        Some("nested/run.sh")
    );
    assert_eq!(FileSystemApi.dir_size(&copy), 9);

    assert!(
        FileSystemApi.copy_path(&source, &copy).is_err(),
        "never overwrites"
    );
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn move_and_permissions() {
    let dir = temp_dir("fs-move");
    fs::write(dir.join("a"), "x").unwrap();
    FileSystemApi
        .move_path(&dir.join("a"), &dir.join("b"))
        .unwrap();
    assert!(!FileSystemApi.exists(&dir.join("a")));
    FileSystemApi
        .set_permissions(&dir.join("b"), 0o600)
        .unwrap();

    let properties = FileSystemApi.file_properties(&dir.join("b"));
    assert_eq!(properties.name, "b");
    assert_eq!(properties.location, dir.to_string_lossy());
    assert_eq!(properties.mode, Some(0o600));
    assert_eq!(properties.size, Some(1));
    assert!(properties.owner.is_some());

    let folder = FileSystemApi.file_properties(&dir);
    assert!(folder.is_dir);
    assert_eq!(folder.item_count, Some(1));
    let _ = fs::remove_dir_all(dir);
}
