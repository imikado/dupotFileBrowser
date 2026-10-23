//! Every string the code translates must have a French and an Italian
//! translation: the catalogs are keyed by the English text.

use std::path::Path;

use dupot_file_browser::domain::entity::file_entry_entity::{FileEntryEntity, TypeLabel};
use dupot_file_browser::domain::entity::file_operation_entity::{
    FileOperationEntity, FileOperationKind,
};
use dupot_file_browser::domain::entity::user_settings_entity::{Language, Theme};
use dupot_file_browser::domain::shared::archive::ArchiveFormat;
use dupot_file_browser::domain::shared::folder_color::PALETTE;
use dupot_file_browser::domain::shared::translation::parse_po;

/// String literals passed to `tr(` / `trf(` in the sources.
fn literal_msgids(dir: &Path, found: &mut Vec<String>) {
    for entry in std::fs::read_dir(dir).unwrap().flatten() {
        let path = entry.path();
        if path.is_dir() {
            literal_msgids(&path, found);
            continue;
        }
        if path.extension().is_none_or(|ext| ext != "rs") {
            continue;
        }
        let source = std::fs::read_to_string(&path).unwrap();
        for marker in ["tr(\"", "trf(\""] {
            for (start, _) in source.match_indices(marker) {
                let after_identifier = source[..start]
                    .chars()
                    .next_back()
                    .is_some_and(|c| c.is_alphanumeric() || c == '_');
                if !after_identifier {
                    found.push(read_literal(&source[start + marker.len()..]));
                }
            }
        }
    }
}

fn read_literal(text: &str) -> String {
    let mut out = String::new();
    let mut chars = text.chars();
    while let Some(c) = chars.next() {
        match c {
            '"' => break,
            '\\' => match chars.next() {
                Some('n') => out.push('\n'),
                Some(other) => out.push(other),
                None => break,
            },
            c => out.push(c),
        }
    }
    out
}

fn msgids() -> Vec<String> {
    let mut found = Vec::new();
    literal_msgids(
        Path::new(concat!(env!("CARGO_MANIFEST_DIR"), "/src")),
        &mut found,
    );
    found.extend(Theme::ALL.iter().map(|t| t.id().to_string()));
    found.extend(Language::ALL.iter().map(|l| l.id().to_string()));
    found.extend(ArchiveFormat::ALL.iter().map(|f| f.label().to_string()));
    found.extend(PALETTE.iter().map(|(label, _)| label.to_string()));
    for kind in [
        FileOperationKind::Copy,
        FileOperationKind::Move,
        FileOperationKind::Compress(ArchiveFormat::Zip),
        FileOperationKind::Extract,
    ] {
        let (heading, body) =
            FileOperationEntity::new(kind, Path::new("/a"), Path::new("/b")).error_messages();
        found.extend([heading.to_string(), body.to_string()]);
    }
    for name in [
        "a.png", "a.mp3", "a.mp4", "a.zip", "a.pdf", "a.ods", "a.odp", "a.ttf", "a.exe",
    ] {
        let entry = FileEntryEntity {
            name: name.into(),
            path: name.into(),
            is_dir: false,
            size: None,
            mtime: None,
        };
        if let TypeLabel::Kind(label) = entry.type_label() {
            found.push(label.to_string());
        }
    }
    found.sort();
    found.dedup();
    found
}

#[test]
fn every_msgid_is_translated() {
    let ids = msgids();
    assert!(ids.len() > 100, "scanner found {} strings", ids.len());
    for language in ["fr", "it"] {
        let path = format!("{}/po/{language}.po", env!("CARGO_MANIFEST_DIR"));
        let catalog = parse_po(&std::fs::read_to_string(path).unwrap());
        let missing: Vec<&String> = ids.iter().filter(|id| !catalog.contains_key(*id)).collect();
        assert!(missing.is_empty(), "{language}: missing {missing:#?}");
    }
}
