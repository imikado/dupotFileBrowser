use std::fs;

use dupot_file_browser::domain::contract::trash_repository::TrashRepository;
use dupot_file_browser::infrastructure::api::trash_api::TrashApi;

use super::temp_dir;

#[test]
fn trash_list_restore_delete() {
    let dir = temp_dir("trash");
    let trash = TrashApi::new(dir.join("Trash"));
    let home = dir.join("home");
    fs::create_dir_all(home.join("folder")).unwrap();
    fs::write(home.join("a.txt"), "1").unwrap();

    trash.trash(&home.join("a.txt")).unwrap();
    fs::write(home.join("a.txt"), "2").unwrap();
    trash.trash(&home.join("a.txt")).unwrap();
    trash.trash(&home.join("folder")).unwrap();
    assert!(!home.join("a.txt").exists());

    let entries = trash.list();
    let mut names: Vec<_> = entries.iter().map(|e| e.display_name.as_str()).collect();
    names.sort();
    assert_eq!(names, ["a.2.txt", "a.txt", "folder"]);
    let info = fs::read_to_string(dir.join("Trash/info/a.2.txt.trashinfo")).unwrap();
    assert!(info.contains("DeletionDate="));

    let second = entries
        .iter()
        .find(|e| e.display_name == "a.2.txt")
        .unwrap();
    assert_eq!(second.original_path, home.join("a.txt").to_string_lossy());
    trash.restore(second).unwrap();
    assert_eq!(fs::read_to_string(home.join("a.txt")).unwrap(), "2");
    assert!(!dir.join("Trash/info/a.2.txt.trashinfo").exists());

    let folder = entries.iter().find(|e| e.display_name == "folder").unwrap();
    assert!(folder.is_dir);
    trash.delete(&folder.trashed_path).unwrap();
    trash.empty().unwrap();
    assert!(trash.list().is_empty());
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn failed_trash_leaves_no_trashinfo() {
    let dir = temp_dir("trash-missing");
    let trash = TrashApi::new(dir.join("Trash"));
    assert!(trash.trash(&dir.join("does-not-exist.txt")).is_err());
    let info = fs::read_dir(dir.join("Trash/info")).unwrap().count();
    assert_eq!(info, 0);
    let _ = fs::remove_dir_all(dir);
}
