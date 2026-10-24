//! freedesktop.org Trash specification: `.trashinfo` files and names.

use std::path::{Path, PathBuf};

use crate::domain::shared::path::split_extension;

/// The home Trash, relative to the user's home.
pub const HOME_TRASH_DIR: &str = ".local/share/Trash";

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

/// Trash folders of a mounted disk other than the home one, in the order
/// the spec tries them: the administrator's `$topdir/.Trash/$uid`, then
/// the user's own `$topdir/.Trash-$uid`.
pub fn topdir_trash_dirs(topdir: &Path, uid: u32) -> [PathBuf; 2] {
    [
        topdir.join(".Trash").join(uid.to_string()),
        topdir.join(format!(".Trash-{uid}")),
    ]
}

/// `Path=` value for an item trashed from `original`: relative to `topdir`
/// for a disk's own trash (it may be mounted elsewhere later), absolute in
/// the home trash.
pub fn trash_info_path(original: &Path, topdir: Option<&Path>) -> String {
    topdir
        .and_then(|topdir| original.strip_prefix(topdir).ok())
        .unwrap_or(original)
        .to_string_lossy()
        .into_owned()
}

/// Original location from a `Path=` value, relative ones being resolved
/// against the disk's `topdir`.
pub fn resolve_trash_info_path(value: &str, topdir: Option<&Path>) -> String {
    match topdir {
        Some(topdir) if !value.is_empty() && !value.starts_with('/') => {
            topdir.join(value).to_string_lossy().into_owned()
        }
        _ => value.to_string(),
    }
}

/// File systems with no user files: never searched for a trash folder
/// (looking could also trigger automounts or hang on network mounts).
const PSEUDO_FILE_SYSTEMS: &[&str] = &[
    "autofs",
    "binfmt_misc",
    "bpf",
    "cgroup",
    "cgroup2",
    "configfs",
    "debugfs",
    "devpts",
    "devtmpfs",
    "efivarfs",
    "fusectl",
    "fuse.gvfsd-fuse",
    "fuse.portal",
    "hugetlbfs",
    "mqueue",
    "nsfs",
    "proc",
    "pstore",
    "ramfs",
    "securityfs",
    "squashfs",
    "sysfs",
    "tmpfs",
    "tracefs",
];

/// Mount points of `/proc/self/mounts` that can hold user files.
pub fn user_mount_points(mounts: &str) -> Vec<PathBuf> {
    mounts
        .lines()
        .filter_map(|line| {
            let mut fields = line.split_whitespace();
            let (_device, mount_point, fs_type) = (fields.next()?, fields.next()?, fields.next()?);
            let mount_point = unescape_mount_field(mount_point);
            let system = ["/proc", "/sys", "/dev", "/run/user", "/snap"]
                .iter()
                .any(|prefix| Path::new(&mount_point).starts_with(prefix));
            (!system && !PSEUDO_FILE_SYSTEMS.contains(&fs_type)).then(|| PathBuf::from(mount_point))
        })
        .collect()
}

/// `/proc/self/mounts` writes space, tab, newline and backslash as `\040`…
fn unescape_mount_field(field: &str) -> String {
    let mut text = field.to_string();
    for (escaped, plain) in [
        ("\\040", " "),
        ("\\011", "\t"),
        ("\\012", "\n"),
        ("\\134", "\\"),
    ] {
        text = text.replace(escaped, plain);
    }
    text
}
