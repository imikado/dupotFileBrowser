//! freedesktop.org Trash specification: `.trashinfo` files and names.

use crate::domain::shared::path::split_extension;

/// Content of the `.trashinfo` file for an item trashed from `original_path`
/// at `deletion_date` (`YYYY-MM-DDThh:mm:ss`).
pub fn build_trash_info(original_path: &str, deletion_date: &str) -> String {
    format!(
        "[Trash Info]\nPath={}\nDeletionDate={deletion_date}\n",
        percent_encode(original_path)
    )
}

/// (original path, deletion date) from a `.trashinfo` file; empty strings
/// for whatever is missing.
pub fn parse_trash_info(content: &str) -> (String, String) {
    let mut in_section = false;
    let mut path = String::new();
    let mut date = String::new();
    for line in content.lines().map(str::trim) {
        if line.starts_with('[') {
            in_section = line == "[Trash Info]";
            continue;
        }
        if !in_section {
            continue;
        }
        if let Some((key, value)) = line.split_once('=') {
            match key.trim() {
                "Path" => path = percent_decode(value.trim()),
                "DeletionDate" => date = value.trim().to_string(),
                _ => {}
            }
        }
    }
    (path, date)
}

/// `name`, or `stem.2.ext`, `stem.3.ext`… : the first one `exists` rejects.
pub fn unique_trashed_name(name: &str, exists: impl Fn(&str) -> bool) -> String {
    if !exists(name) {
        return name.to_string();
    }
    let (stem, extension) = split_extension(name);
    (2..)
        .map(|counter| format!("{stem}.{counter}{extension}"))
        .find(|candidate| !exists(candidate))
        .expect("unbounded counter")
}

/// `2024-01-15T10:30:00` -> `2024-01-15 10:30`; anything else unchanged.
pub fn format_deletion_date(date: &str) -> String {
    let bytes = date.as_bytes();
    let well_formed =
        bytes.len() >= 16 && bytes[10] == b'T' && bytes[13] == b':' && date.is_char_boundary(16);
    if well_formed {
        format!("{} {}", &date[..10], &date[11..16])
    } else {
        date.to_string()
    }
}

/// Like Python's `urllib.parse.quote`: keeps `A-Za-z0-9_.-~/`.
pub fn percent_encode(text: &str) -> String {
    text.bytes()
        .map(|byte| {
            if byte.is_ascii_alphanumeric() || b"_.-~/".contains(&byte) {
                (byte as char).to_string()
            } else {
                format!("%{byte:02X}")
            }
        })
        .collect()
}

pub fn percent_decode(text: &str) -> String {
    let bytes = text.as_bytes();
    let mut decoded = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        let hex = bytes
            .get(i + 1..i + 3)
            .and_then(|h| std::str::from_utf8(h).ok())
            .and_then(|h| u8::from_str_radix(h, 16).ok());
        match (bytes[i], hex) {
            (b'%', Some(byte)) => {
                decoded.push(byte);
                i += 3;
            }
            (byte, _) => {
                decoded.push(byte);
                i += 1;
            }
        }
    }
    String::from_utf8_lossy(&decoded).into_owned()
}
