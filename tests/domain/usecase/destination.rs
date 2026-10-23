use std::path::{Path, PathBuf};

use dupot_file_browser::domain::shared::archive::ArchiveFormat;
use dupot_file_browser::domain::usecase::destination::{
    Destination, compress_destination, extract_destination, paste_destination, rename_destination,
};

use super::FakeFileSystem;

fn fs() -> FakeFileSystem {
    FakeFileSystem::with(&[
        ("report.pdf", false),
        ("photos", true),
        ("photos.zip", false),
    ])
}

#[test]
fn paste_uses_the_source_name_unless_taken() {
    let fs = fs();
    let data = Path::new("/data");
    assert_eq!(
        paste_destination(&fs, data, Path::new("/elsewhere/new.txt"), None),
        Destination::Free(PathBuf::from("/data/new.txt"))
    );
    assert_eq!(
        paste_destination(&fs, data, Path::new("/elsewhere/report.pdf"), None),
        Destination::Taken("report.pdf".into())
    );
    assert_eq!(
        paste_destination(
            &fs,
            data,
            Path::new("/elsewhere/report.pdf"),
            Some(" report 2.pdf ")
        ),
        Destination::Free(PathBuf::from("/data/report 2.pdf"))
    );
    assert_eq!(
        paste_destination(&fs, data, Path::new("/x"), Some("")),
        Destination::Invalid
    );
}

#[test]
fn extract_next_to_the_archive() {
    let fs = fs();
    let archive = Path::new("/data/photos.zip");
    assert_eq!(
        extract_destination(&fs, archive, None),
        Destination::Taken("photos".into())
    );
    assert_eq!(
        extract_destination(&fs, archive, Some("photos-2")),
        Destination::Free(PathBuf::from("/data/photos-2"))
    );
}

#[test]
fn compress_adds_the_format_extension() {
    let fs = fs();
    let source = Path::new("/data/photos");
    assert_eq!(
        compress_destination(&fs, source, "photos", ArchiveFormat::Zip),
        Destination::Taken("photos".into())
    );
    assert_eq!(
        compress_destination(&fs, source, "photos", ArchiveFormat::TarXz),
        Destination::Free(PathBuf::from("/data/photos.tar.xz"))
    );
}

#[test]
fn rename_ignores_unchanged_names() {
    let fs = fs();
    let path = Path::new("/data/report.pdf");
    assert_eq!(
        rename_destination(&fs, path, "report.pdf"),
        Destination::Invalid
    );
    assert_eq!(
        rename_destination(&fs, path, "photos"),
        Destination::Taken("photos".into())
    );
    assert_eq!(
        rename_destination(&fs, path, "final.pdf"),
        Destination::Free(PathBuf::from("/data/final.pdf"))
    );
}
