use std::fs;

use dupot_file_browser::domain::contract::archive_repository::ArchiveRepository;
use dupot_file_browser::domain::shared::archive::ArchiveFormat;
use dupot_file_browser::infrastructure::api::archive_api::ArchiveApi;

use super::temp_dir;

#[test]
fn every_format_round_trips_a_folder() {
    let dir = temp_dir("archive");
    let source = dir.join("photos");
    fs::create_dir_all(source.join("2024")).unwrap();
    fs::write(source.join("2024/beach.txt"), "sand").unwrap();
    fs::write(source.join("cover.txt"), "cover").unwrap();

    for format in ArchiveFormat::ALL {
        let archive = dir.join(format!("photos{}", format.extension()));
        ArchiveApi.compress(&source, &archive, format).unwrap();
        let out = dir.join(format!("out{}", format.extension()));
        ArchiveApi.extract(&archive, &out).unwrap();
        assert_eq!(
            fs::read_to_string(out.join("photos/2024/beach.txt")).unwrap(),
            "sand",
            "{format:?}"
        );
        assert_eq!(
            fs::read_to_string(out.join("photos/cover.txt")).unwrap(),
            "cover",
            "{format:?}"
        );
    }
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn single_file_and_failures() {
    let dir = temp_dir("archive-file");
    fs::write(dir.join("notes.txt"), "n").unwrap();
    let archive = dir.join("notes.tar.gz");
    ArchiveApi
        .compress(&dir.join("notes.txt"), &archive, ArchiveFormat::TarGz)
        .unwrap();
    ArchiveApi.extract(&archive, &dir.join("out")).unwrap();
    assert_eq!(fs::read_to_string(dir.join("out/notes.txt")).unwrap(), "n");

    let broken = dir.join("broken.zip");
    fs::write(&broken, "not a zip").unwrap();
    assert!(ArchiveApi.extract(&broken, &dir.join("out2")).is_err());
    assert!(
        ArchiveApi
            .compress(&dir.join("missing"), &dir.join("m.zip"), ArchiveFormat::Zip)
            .is_err()
    );
    assert!(!dir.join("m.zip").exists(), "partial archive removed");
    let _ = fs::remove_dir_all(dir);
}
