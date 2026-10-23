use std::path::Path;

use dupot_file_browser::domain::shared::archive::{
    ArchiveFormat, ArchiveKind, archive_base_name, archive_kind, is_extractable, rar_extract_argv,
};

#[test]
fn longest_extension_wins() {
    assert_eq!(
        archive_kind("a.tar.gz"),
        Some(ArchiveKind::Format(ArchiveFormat::TarGz))
    );
    assert_eq!(
        archive_kind("a.TGZ"),
        Some(ArchiveKind::Format(ArchiveFormat::TarGz))
    );
    assert_eq!(
        archive_kind("a.tar"),
        Some(ArchiveKind::Format(ArchiveFormat::Tar))
    );
    assert_eq!(archive_kind("a.rar"), Some(ArchiveKind::Rar));
    assert_eq!(archive_kind("a.gz"), None);
    assert!(
        !is_extractable(".zip"),
        "a bare extension is not an archive name"
    );
}

#[test]
fn base_name_strips_the_archive_extension() {
    assert_eq!(archive_base_name(Path::new("/x/photos.tar.gz")), "photos");
    assert_eq!(archive_base_name(Path::new("/x/photos.ZIP")), "photos");
    assert_eq!(archive_base_name(Path::new("/x/notes.txt")), "notes.txt");
}

#[test]
fn every_format_round_trips_through_its_extension() {
    for format in ArchiveFormat::ALL {
        let name = format!("x{}", format.extension());
        assert_eq!(archive_kind(&name), Some(ArchiveKind::Format(format)));
    }
}

#[test]
fn rar_commands() {
    assert_eq!(
        rar_extract_argv("unrar", "/a.rar", "/out"),
        ["unrar", "x", "-o+", "-y", "/a.rar", "/out/"]
    );
    assert_eq!(
        rar_extract_argv("7z", "/a.rar", "/out"),
        ["7z", "x", "-o/out", "-y", "/a.rar"]
    );
    assert_eq!(
        rar_extract_argv("bsdtar", "/a.rar", "/out"),
        ["bsdtar", "-xf", "/a.rar", "-C", "/out"]
    );
}
