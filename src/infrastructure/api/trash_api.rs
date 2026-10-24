//! The real `~/.local/share/Trash`, read and written by hand per the
//! freedesktop.org spec. Not `$XDG_DATA_HOME` nor `g_file_trash()`: Flatpak
//! redirects those to the app's private data, invisible to other file
//! managers. Not `trash://` either, which needs gvfsd-trash running.
//!
//! Items of another disk (USB key, second drive) go to that disk's own
//! trash, `$topdir/.Trash/$uid` or `$topdir/.Trash-$uid`: an instant rename
//! instead of a copy to the home disk. The Trash page lists them all.

use std::fs::{self, DirBuilder};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, PermissionsExt};
use std::path::{Path, PathBuf};

use crate::domain::contract::file_system_repository::FileSystemRepository;
use crate::domain::contract::trash_repository::TrashRepository;
use crate::domain::entity::trash_entry_entity::TrashEntryEntity;
use crate::domain::error::{DomainError, DomainResult};
use crate::domain::shared::path::{file_name, parent_dir};
use crate::domain::shared::trash_info::{
    build_trash_info, parse_trash_info, resolve_trash_info_path, topdir_trash_dirs,
    trash_info_path, unique_trashed_name, user_mount_points,
};
use crate::infrastructure::api::file_system_api::FileSystemApi;

const INFO_EXTENSION: &str = ".trashinfo";
const MOUNTS_FILE: &str = "/proc/self/mounts";
const STICKY_BIT: u32 = 0o1000;

/// A trash folder (holding `files/` and `info/`), with the disk it belongs
/// to for a disk's own trash.
struct TrashRoot {
    dir: PathBuf,
    topdir: Option<PathBuf>,
}

pub struct TrashApi {
    base_dir: PathBuf,
    /// Whether other disks get their own trash (off in tests, which must
    /// not see the machine's real disks).
    other_disks: bool,
}

impl TrashApi {
    /// Only the trash at `base_dir`.
    pub fn new(base_dir: impl Into<PathBuf>) -> Self {
        Self {
            base_dir: base_dir.into(),
            other_disks: false,
        }
    }

    /// `.trashinfo` of an item of any trash: `<root>/info/<name>.trashinfo`
    /// next to its `<root>/files/<name>`.
    fn info_path(trashed_path: &Path) -> PathBuf {
        let root = parent_dir(&parent_dir(trashed_path));
        root.join("info")
            .join(format!("{}{INFO_EXTENSION}", file_name(trashed_path)))
    }

    fn remove_info(trashed_path: &Path) {
        let _ = fs::remove_file(Self::info_path(trashed_path));
    }

    /// The home trash, then every other disk's existing trash.
    fn roots(&self) -> Vec<TrashRoot> {
        let mut roots = vec![TrashRoot {
            dir: self.base_dir.clone(),
            topdir: None,
        }];
        if !self.other_disks {
            return roots;
        }
        let mounts = fs::read_to_string(MOUNTS_FILE).unwrap_or_default();
        for topdir in user_mount_points(&mounts) {
            for dir in topdir_trash_dirs(&topdir, current_uid()) {
                if dir != self.base_dir && is_real_dir(&dir) {
                    roots.push(TrashRoot {
                        dir,
                        topdir: Some(topdir.clone()),
                    });
                }
            }
        }
        roots
    }

    /// The trash of the disk holding `folder`, when that's not the home
    /// disk and the disk accepts one; `None` means the home trash.
    fn disk_trash_for(&self, folder: &Path) -> Option<TrashRoot> {
        if !self.other_disks {
            return None;
        }
        let home_device = device_of(&nearest_existing(&self.base_dir))?;
        let folder = fs::canonicalize(folder).ok()?;
        if device_of(&folder)? == home_device {
            return None;
        }
        let topdir = mount_root(&folder)?;
        // Only disks the Trash page lists (not /tmp's tmpfs…), or the item
        // would vanish from view.
        let mounts = fs::read_to_string(MOUNTS_FILE).unwrap_or_default();
        if !user_mount_points(&mounts).contains(&topdir) {
            return None;
        }
        let [admin_dir, user_dir] = topdir_trash_dirs(&topdir, current_uid());
        // The administrator's shared `.Trash` must be a real, sticky folder.
        let shared_trash = parent_dir(&admin_dir);
        let shared_ok = fs::symlink_metadata(&shared_trash)
            .is_ok_and(|m| m.is_dir() && m.permissions().mode() & STICKY_BIT != 0);
        if shared_ok && create_private_dir(&admin_dir) {
            return Some(TrashRoot {
                dir: admin_dir,
                topdir: Some(topdir),
            });
        }
        create_private_dir(&user_dir).then_some(TrashRoot {
            dir: user_dir,
            topdir: Some(topdir),
        })
    }

    fn trash_into(&self, root: &TrashRoot, path: &Path) -> DomainResult<()> {
        let files_dir = root.dir.join("files");
        fs::create_dir_all(&files_dir)?;
        fs::create_dir_all(root.dir.join("info"))?;
        let name = unique_trashed_name(&file_name(path), |candidate| {
            files_dir.join(candidate).symlink_metadata().is_ok()
        });
        let trashed_path = files_dir.join(&name);
        // The spec writes the .trashinfo first: a failed write then leaves
        // the file in place rather than in the Trash with no way back.
        let original = trash_info_path(path, root.topdir.as_deref());
        fs::write(
            Self::info_path(&trashed_path),
            build_trash_info(&original, &now_iso()),
        )?;
        if let Err(error) = FileSystemApi.move_path(path, &trashed_path) {
            Self::remove_info(&trashed_path);
            return Err(error);
        }
        Ok(())
    }
}

impl Default for TrashApi {
    fn default() -> Self {
        Self {
            base_dir: FileSystemApi.home_dir().join(".local/share/Trash"),
            other_disks: true,
        }
    }
}

fn now_iso() -> String {
    gtk::glib::DateTime::now_local()
        .and_then(|now| now.format("%Y-%m-%dT%H:%M:%S"))
        .map(|text| text.to_string())
        .unwrap_or_default()
}

fn current_uid() -> u32 {
    // SAFETY: getuid has no preconditions and cannot fail.
    unsafe { libc::getuid() }
}

fn device_of(path: &Path) -> Option<u64> {
    fs::metadata(path).ok().map(|metadata| metadata.dev())
}

/// A folder, not a symlink to one (the spec refuses those as trash).
fn is_real_dir(path: &Path) -> bool {
    fs::symlink_metadata(path).is_ok_and(|metadata| metadata.is_dir())
}

/// `path`, or its closest ancestor that exists.
fn nearest_existing(path: &Path) -> PathBuf {
    path.ancestors()
        .find(|ancestor| ancestor.exists())
        .unwrap_or(Path::new("/"))
        .to_path_buf()
}

/// Top folder of the file system holding `folder` (canonical path).
fn mount_root(folder: &Path) -> Option<PathBuf> {
    let device = device_of(folder)?;
    let mut root = folder;
    while let Some(parent) = root.parent() {
        if device_of(parent) != Some(device) {
            break;
        }
        root = parent;
    }
    Some(root.to_path_buf())
}

/// `dir` existing as a real folder owned by the user, created `0700` if
/// needed.
fn create_private_dir(dir: &Path) -> bool {
    if !dir.exists() {
        let _ = DirBuilder::new().recursive(true).mode(0o700).create(dir);
    }
    fs::symlink_metadata(dir).is_ok_and(|m| m.is_dir() && m.uid() == current_uid())
}

impl TrashRepository for TrashApi {
    fn trash_dir(&self) -> PathBuf {
        self.base_dir.join("files")
    }

    fn trash(&self, path: &Path) -> DomainResult<()> {
        if let Some(root) = self.disk_trash_for(&parent_dir(path))
            && self.trash_into(&root, path).is_ok()
        {
            return Ok(());
        }
        let home = TrashRoot {
            dir: self.base_dir.clone(),
            topdir: None,
        };
        self.trash_into(&home, path)
    }

    fn list(&self) -> Vec<TrashEntryEntity> {
        let mut entries: Vec<TrashEntryEntity> = Vec::new();
        for root in self.roots() {
            let Ok(iterator) = fs::read_dir(root.dir.join("files")) else {
                continue;
            };
            entries.extend(iterator.flatten().map(|entry| {
                let trashed_path = entry.path();
                let info = fs::read_to_string(Self::info_path(&trashed_path)).unwrap_or_default();
                let (original_path, deletion_date) = parse_trash_info(&info);
                TrashEntryEntity {
                    display_name: entry.file_name().to_string_lossy().into_owned(),
                    is_dir: entry.file_type().is_ok_and(|t| t.is_dir()),
                    trashed_path,
                    original_path: resolve_trash_info_path(&original_path, root.topdir.as_deref()),
                    deletion_date,
                }
            }));
        }
        entries.sort_by(|a, b| b.deletion_date.cmp(&a.deletion_date));
        entries
    }

    fn restore(&self, entry: &TrashEntryEntity) -> DomainResult<()> {
        let original = Path::new(&entry.original_path);
        if entry.original_path.is_empty() {
            return Err(DomainError::new("no recorded original location"));
        }
        fs::create_dir_all(parent_dir(original))?;
        FileSystemApi.move_path(&entry.trashed_path, original)?;
        Self::remove_info(&entry.trashed_path);
        Ok(())
    }

    fn delete(&self, trashed_path: &Path) -> DomainResult<()> {
        let is_dir = fs::symlink_metadata(trashed_path)?.is_dir();
        if is_dir {
            fs::remove_dir_all(trashed_path)?;
        } else {
            fs::remove_file(trashed_path)?;
        }
        Self::remove_info(trashed_path);
        Ok(())
    }
    fn empty(&self) -> DomainResult<()> {
        let failures = self
            .list()
            .iter()
            .filter(|entry| self.delete(&entry.trashed_path).is_err())
            .count();
        if failures == 0 {
            Ok(())
        } else {
            Err(DomainError::new(format!(
                "{failures} item(s) could not be deleted"
            )))
        }
    }
}
