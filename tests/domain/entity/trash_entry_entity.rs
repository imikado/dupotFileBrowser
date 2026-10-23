use dupot_file_browser::domain::entity::trash_entry_entity::TrashEntryEntity;

#[test]
fn icon_key_by_kind() {
    let mut entry = TrashEntryEntity {
        trashed_path: "/t/files/a".into(),
        display_name: "a".into(),
        original_path: "/home/a".into(),
        deletion_date: String::new(),
        is_dir: true,
    };
    assert_eq!(entry.icon_key(), "folder");
    entry.is_dir = false;
    assert_eq!(entry.icon_key(), "generic");
}
