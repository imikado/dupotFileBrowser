use std::path::{Path, PathBuf};

use dupot_file_browser::domain::shared::trash_info::{
    build_trash_info, format_deletion_date, parse_trash_info, percent_decode, percent_encode,
    resolve_trash_info_path, topdir_trash_dirs, trash_info_path, unique_trashed_name,
    user_mount_points,
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

#[test]
fn disk_trash_folders_in_spec_order() {
    assert_eq!(
        topdir_trash_dirs(Path::new("/media/usb"), 1000),
        [
            PathBuf::from("/media/usb/.Trash/1000"),
            PathBuf::from("/media/usb/.Trash-1000")
        ]
    );
}

#[test]
fn disk_trash_paths_are_relative_to_the_disk() {
    let usb = Path::new("/media/usb");
    assert_eq!(
        trash_info_path(Path::new("/media/usb/photos/a.png"), Some(usb)),
        "photos/a.png"
    );
    assert_eq!(trash_info_path(Path::new("/home/me/a"), None), "/home/me/a");
    assert_eq!(
        resolve_trash_info_path("photos/a.png", Some(usb)),
        "/media/usb/photos/a.png"
    );
    assert_eq!(resolve_trash_info_path("/abs/a", Some(usb)), "/abs/a");
    assert_eq!(resolve_trash_info_path("", Some(usb)), "");
}

#[test]
fn mount_points_skip_pseudo_file_systems() {
    let mounts = "\
/dev/sda2 / ext4 rw 0 0
proc /proc proc rw 0 0
tmpfs /run tmpfs rw 0 0
/dev/sdb1 /media/me/My\\040Disk vfat rw 0 0
/dev/loop3 /snap/core26/1 squashfs ro 0 0
gvfsd-fuse /run/user/1000/gvfs fuse.gvfsd-fuse rw 0 0
";
    assert_eq!(
        user_mount_points(mounts),
        [PathBuf::from("/"), PathBuf::from("/media/me/My Disk")]
    );
}
