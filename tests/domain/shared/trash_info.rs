use dupot_file_browser::domain::shared::trash_info::{
    build_trash_info, format_deletion_date, parse_trash_info, percent_decode, percent_encode,
    unique_trashed_name,
};

#[test]
fn trash_info_round_trip() {
    let info = build_trash_info("/home/me/my file é.txt", "2024-01-15T10:30:00");
    assert!(info.starts_with("[Trash Info]\nPath=/home/me/my%20file%20%C3%A9.txt\n"));
    assert_eq!(
        parse_trash_info(&info),
        (
            "/home/me/my file é.txt".to_string(),
            "2024-01-15T10:30:00".to_string()
        )
    );
    assert_eq!(parse_trash_info("garbage"), (String::new(), String::new()));
}

#[test]
fn percent_coding() {
    assert_eq!(percent_encode("a b/c~"), "a%20b/c~");
    assert_eq!(percent_decode("a%20b%zz"), "a b%zz");
}

#[test]
fn unique_names_follow_the_spec_scheme() {
    let taken = ["a.txt", "a.2.txt", "dir"];
    let exists = |name: &str| taken.contains(&name);
    assert_eq!(unique_trashed_name("b.txt", exists), "b.txt");
    assert_eq!(unique_trashed_name("a.txt", exists), "a.3.txt");
    assert_eq!(unique_trashed_name("dir", exists), "dir.2");
}

#[test]
fn deletion_date_display() {
    assert_eq!(
        format_deletion_date("2024-01-15T10:30:00"),
        "2024-01-15 10:30"
    );
    assert_eq!(format_deletion_date("yesterday"), "yesterday");
    assert_eq!(format_deletion_date(""), "");
}
