//! Archive formats the app writes and reads.

use crate::domain::shared::path::file_name;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ArchiveFormat {
    Zip,
    TarGz,
    TarBz2,
    TarXz,
    Tar,
}

impl ArchiveFormat {
    /// In the order offered by the Compress dialog (ZIP first: the most
    /// broadly compatible).
    pub const ALL: [ArchiveFormat; 5] = [
        ArchiveFormat::Zip,
        ArchiveFormat::TarGz,
        ArchiveFormat::TarBz2,
        ArchiveFormat::TarXz,
        ArchiveFormat::Tar,
    ];

    pub fn extension(self) -> &'static str {
        match self {
            ArchiveFormat::Zip => ".zip",
            ArchiveFormat::TarGz => ".tar.gz",
            ArchiveFormat::TarBz2 => ".tar.bz2",
            ArchiveFormat::TarXz => ".tar.xz",
            ArchiveFormat::Tar => ".tar",
        }
    }

    /// Gettext msgid of its label.
    pub fn label(self) -> &'static str {
        match self {
            ArchiveFormat::Zip => "ZIP archive (.zip)",
            ArchiveFormat::TarGz => "Tar.gz archive (.tar.gz)",
            ArchiveFormat::TarBz2 => "Tar.bz2 archive (.tar.bz2)",
            ArchiveFormat::TarXz => "Tar.xz archive (.tar.xz)",
            ArchiveFormat::Tar => "Tar archive (.tar)",
        }
    }
}

/// How an archive file is unpacked, decided from its name.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ArchiveKind {
    Format(ArchiveFormat),
    /// Proprietary: extracted by a host tool (see `RAR_TOOLS`).
    Rar,
}

/// Longest first, so `.tar.gz` matches whole instead of via `.gz`.
const EXTENSIONS: &[(&str, ArchiveKind)] = &[
    (".tar.gz", ArchiveKind::Format(ArchiveFormat::TarGz)),
    (".tar.bz2", ArchiveKind::Format(ArchiveFormat::TarBz2)),
    (".tar.xz", ArchiveKind::Format(ArchiveFormat::TarXz)),
    (".tgz", ArchiveKind::Format(ArchiveFormat::TarGz)),
    (".tbz2", ArchiveKind::Format(ArchiveFormat::TarBz2)),
    (".txz", ArchiveKind::Format(ArchiveFormat::TarXz)),
    (".tar", ArchiveKind::Format(ArchiveFormat::Tar)),
    (".zip", ArchiveKind::Format(ArchiveFormat::Zip)),
    (".rar", ArchiveKind::Rar),
];

fn matching_extension(name: &str) -> Option<(&'static str, ArchiveKind)> {
    let lowered = name.to_lowercase();
    EXTENSIONS
        .iter()
        .find(|(extension, _)| lowered.ends_with(extension) && lowered.len() > extension.len())
        .copied()
}

pub fn archive_kind(name: &str) -> Option<ArchiveKind> {
    matching_extension(name).map(|(_, kind)| kind)
}

pub fn is_extractable(name: &str) -> bool {
    archive_kind(name).is_some()
}

/// File name without its archive extension (`photos.tar.gz` -> `photos`):
/// the default folder an archive is extracted into. Other names are kept
/// whole.
pub fn archive_base_name(path: &std::path::Path) -> String {
    let name = file_name(path);
    match matching_extension(&name) {
        Some((extension, _)) => name[..name.len() - extension.len()].to_string(),
        None => name,
    }
}

/// Host tools tried in order to extract a `.rar`.
pub const RAR_TOOLS: [&str; 5] = ["unrar", "7z", "7za", "unar", "bsdtar"];

/// Command extracting `source` into the existing `destination_dir` with
/// `tool` (one of `RAR_TOOLS`), overwriting without prompting.
pub fn rar_extract_argv(tool: &str, source: &str, destination_dir: &str) -> Vec<String> {
    let argv: Vec<String> = match tool {
        "unrar" => vec![
            "unrar".into(),
            "x".into(),
            "-o+".into(),
            "-y".into(),
            source.into(),
            format!("{destination_dir}/"),
        ],
        "7z" | "7za" => vec![
            tool.into(),
            "x".into(),
            format!("-o{destination_dir}"),
            "-y".into(),
            source.into(),
        ],
        "unar" => vec![
            "unar".into(),
            "-force-overwrite".into(),
            "-output-directory".into(),
            destination_dir.into(),
            source.into(),
        ],
        _ => vec![
            tool.into(),
            "-xf".into(),
            source.into(),
            "-C".into(),
            destination_dir.into(),
        ],
    };
    argv
}
