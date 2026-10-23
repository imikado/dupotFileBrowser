use std::path::{Path, PathBuf};

use dupot_file_browser::domain::entity::file_operation_entity::{
    FileOperationEntity, FileOperationKind,
};
use dupot_file_browser::domain::shared::archive::ArchiveFormat;

#[test]
fn paste_kind_depends_on_cut() {
    let (src, dst) = (Path::new("/a/f"), Path::new("/b/f"));
    assert_eq!(
        FileOperationEntity::paste(src, dst, true).kind,
        FileOperationKind::Move
    );
    assert_eq!(
        FileOperationEntity::paste(src, dst, false).kind,
        FileOperationKind::Copy
    );
}

#[test]
fn refresh_targets() {
    let copy = FileOperationEntity::paste(Path::new("/a/f"), Path::new("/b/f"), false);
    assert_eq!(copy.refresh_targets(), vec![PathBuf::from("/b")]);

    let moved = FileOperationEntity::paste(Path::new("/a/f"), Path::new("/b/f"), true);
    assert_eq!(
        moved.refresh_targets(),
        vec![PathBuf::from("/b"), PathBuf::from("/a")]
    );

    let extract = FileOperationEntity::new(
        FileOperationKind::Extract,
        Path::new("/a/x.zip"),
        Path::new("/a/x"),
    );
    assert_eq!(extract.refresh_targets(), vec![PathBuf::from("/a/x")]);

    let compress = FileOperationEntity::new(
        FileOperationKind::Compress(ArchiveFormat::Zip),
        Path::new("/a/x"),
        Path::new("/a/x.zip"),
    );
    assert_eq!(compress.refresh_targets(), vec![PathBuf::from("/a")]);
}

#[test]
fn error_messages_name_the_source() {
    let job =
        FileOperationEntity::paste(Path::new("/a/photo.png"), Path::new("/b/photo.png"), false);
    assert_eq!(job.error_messages().0, "Copy failed");
    assert!(job.error_messages().1.contains("{name}"));
    assert_eq!(job.source_name(), "photo.png");
}
