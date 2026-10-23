use std::path::PathBuf;

use crate::domain::shared::archive;

/// Icon key for anything without a more specific one; names a PNG shipped
/// under `src/assets/icons/{light,dark}/<key>.png`.
pub const DEFAULT_ICON_KEY: &str = "generic";
pub const FOLDER_ICON_KEY: &str = "folder";
pub const IMAGE_ICON_KEY: &str = "image";

/// Extension (lowercase, no leading dot) -> icon key. Baked PNGs rather than
/// icon-theme names: a host theme may not carry `x-office-*` and friends.
const EXTENSION_ICON_MAP: &[(&str, &[&str])] = &[
    (
        "image",
        &[
            "png", "jpg", "jpeg", "gif", "bmp", "svg", "webp", "tiff", "tif", "ico", "heic",
        ],
    ),
    (
        "audio",
        &[
            "mp3", "wav", "flac", "ogg", "oga", "m4a", "aac", "wma", "opus",
        ],
    ),
    (
        "video",
        &[
            "mp4", "mkv", "avi", "mov", "webm", "flv", "wmv", "mpg", "mpeg", "m4v",
        ],
    ),
    (
        "archive",
        &[
            "zip", "tar", "gz", "tgz", "bz2", "tbz2", "xz", "7z", "rar", "deb", "rpm", "flatpak",
        ],
    ),
    ("document", &["pdf", "doc", "docx", "odt", "rtf"]),
    ("spreadsheet", &["xls", "xlsx", "ods", "csv"]),
    ("presentation", &["ppt", "pptx", "odp"]),
    ("font", &["ttf", "otf", "woff", "woff2"]),
    ("executable", &["exe", "appimage"]),
];

/// Icon key -> untranslated type label (gettext msgid).
const ICON_KEY_TYPE_LABEL: &[(&str, &str)] = &[
    ("image", "Image"),
    ("audio", "Audio"),
    ("video", "Video"),
    ("archive", "Archive"),
    ("document", "Document"),
    ("spreadsheet", "Spreadsheet"),
    ("presentation", "Presentation"),
    ("font", "Font"),
    ("executable", "Executable"),
];

/// Human-readable type of an entry, left untranslated: the view turns it
/// into text (`Kind` and the others are gettext msgids).
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TypeLabel {
    Folder,
    Kind(&'static str),
    /// `"{extension} File"`, with the extension upper-cased.
    Extension(String),
    File,
}

/// A single file or directory of a listing.
#[derive(Clone, Debug, PartialEq)]
pub struct FileEntryEntity {
    pub name: String,
    pub path: PathBuf,
    pub is_dir: bool,
    /// `None` for a directory, or when its metadata could not be read.
    pub size: Option<u64>,
    /// Modification time, seconds since the Unix epoch.
    pub mtime: Option<i64>,
}

impl FileEntryEntity {
    pub fn is_hidden(&self) -> bool {
        self.name.starts_with('.')
    }

    fn extension(&self) -> Option<&str> {
        self.name.rsplit_once('.').map(|(_, ext)| ext)
    }

    /// Key into `src/assets/icons/{light,dark}/`. Directories are drawn with
    /// the folder icon instead (it needs Nemo folder-color tinting).
    pub fn icon_key(&self) -> &'static str {
        let Some(extension) = self.extension() else {
            return DEFAULT_ICON_KEY;
        };
        let extension = extension.to_lowercase();
        EXTENSION_ICON_MAP
            .iter()
            .find(|(_, extensions)| extensions.contains(&extension.as_str()))
            .map_or(DEFAULT_ICON_KEY, |(key, _)| key)
    }

    pub fn is_image(&self) -> bool {
        !self.is_dir && self.icon_key() == IMAGE_ICON_KEY
    }

    /// Whether the archive API can unpack it; gates the "Extract" entry. A
    /// `.rar` still needs a RAR-capable tool on the host.
    pub fn is_extractable_archive(&self) -> bool {
        !self.is_dir && archive::is_extractable(&self.name)
    }

    pub fn type_label(&self) -> TypeLabel {
        if self.is_dir {
            return TypeLabel::Folder;
        }
        let key = self.icon_key();
        if let Some((_, label)) = ICON_KEY_TYPE_LABEL.iter().find(|(k, _)| *k == key) {
            return TypeLabel::Kind(label);
        }
        match self.extension() {
            Some(extension) => TypeLabel::Extension(extension.to_uppercase()),
            None => TypeLabel::File,
        }
    }
}
