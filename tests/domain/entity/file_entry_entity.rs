use std::path::PathBuf;

use dupot_file_browser::domain::entity::file_entry_entity::{FileEntryEntity, TypeLabel};

fn file(name: &str) -> FileEntryEntity {
    FileEntryEntity {
        name: name.into(),
        path: PathBuf::from("/tmp").join(name),
        is_dir: false,
        size: Some(1),
        mtime: None,
    }
}

fn folder(name: &str) -> FileEntryEntity {
    FileEntryEntity {
        is_dir: true,
        size: None,
        ..file(name)
    }
}

#[test]
fn icon_key_from_extension_ignoring_case() {
    assert_eq!(file("photo.JPG").icon_key(), "image");
    assert_eq!(file("song.flac").icon_key(), "audio");
    assert_eq!(file("backup.tar.gz").icon_key(), "archive");
    assert_eq!(file("report.pdf").icon_key(), "document");
    assert_eq!(file("main.rs").icon_key(), "generic");
    assert_eq!(file("Makefile").icon_key(), "generic");
}

#[test]
fn images_and_archives() {
    assert!(file("a.png").is_image());
    assert!(!folder("a.png").is_image());
    assert!(file("a.tar.xz").is_extractable_archive());
    assert!(file("a.RAR").is_extractable_archive());
    assert!(!file("a.7z").is_extractable_archive());
    assert!(!folder("a.zip").is_extractable_archive());
}

#[test]
fn type_labels() {
    assert_eq!(folder("x").type_label(), TypeLabel::Folder);
    assert_eq!(file("x.png").type_label(), TypeLabel::Kind("Image"));
    assert_eq!(file("x.rs").type_label(), TypeLabel::Extension("RS".into()));
    assert_eq!(file("README").type_label(), TypeLabel::File);
}

#[test]
fn hidden_files_start_with_a_dot() {
    assert!(file(".bashrc").is_hidden());
    assert!(!file("bashrc").is_hidden());
}
