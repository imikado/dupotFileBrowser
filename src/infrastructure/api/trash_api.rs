//! The real `~/.local/share/Trash`, read and written by hand per the
//! freedesktop.org spec. Not `$XDG_DATA_HOME` nor `g_file_trash()`: Flatpak
//! redirects those to the app's private data, invisible to other file
//! managers. Not `trash://` either, which needs gvfsd-trash running.

use std::fs;
use std::path::{Path, PathBuf};

use crate::domain::contract::file_system_repository::FileSystemRepository;
use crate::domain::contract::trash_repository::TrashRepository;
use crate::domain::entity::trash_entry_entity::TrashEntryEntity;
use crate::domain::error::{DomainError, DomainResult};
use crate::domain::shared::path::{file_name, parent_dir};
use crate::domain::shared::trash_info::{build_trash_info, parse_trash_info, unique_trashed_name};
use crate::infrastructure::api::file_system_api::FileSystemApi;

const INFO_EXTENSION: &str = ".trashinfo";

pub struct TrashApi {
    base_dir: PathBuf,
}

impl TrashApi {
    pub fn new(base_dir: impl Into<PathBuf>) -> Self {
        Self {
            base_dir: base_dir.into(),
        }
    }

    fn info_dir(&self) -> PathBuf {
        self.base_dir.join("info")
    }

    fn info_path(&self, trashed_path: &Path) -> PathBuf {
        self.info_dir()
            .join(format!("{}{INFO_EXTENSION}", file_name(trashed_path)))
    }

    fn remove_info(&self, trashed_path: &Path) {
        let _ = fs::remove_file(self.info_path(trashed_path));
    }
}

impl Default for TrashApi {
    fn default() -> Self {
        Self::new(FileSystemApi.home_dir().join(".local/share/Trash"))
    }
}

fn now_iso() -> String {
    gtk::glib::DateTime::now_local()
        .and_then(|now| now.format("%Y-%m-%dT%H:%M:%S"))
        .map(|text| text.to_string())
        .unwrap_or_default()
}

impl TrashRepository for TrashApi {
    fn trash_dir(&self) -> PathBuf {
        self.base_dir.join("files")
    }

    fn trash(&self, path: &Path) -> DomainResult<()> {
        let files_dir = self.trash_dir();
        fs::create_dir_all(&files_dir)?;
        fs::create_dir_all(self.info_dir())?;
        let name = unique_trashed_name(&file_name(path), |candidate| {
            files_dir.join(candidate).symlink_metadata().is_ok()
        });
        let trashed_path = files_dir.join(&name);
        FileSystemApi.move_path(path, &trashed_path)?;
        let info = build_trash_info(&path.to_string_lossy(), &now_iso());
        fs::write(self.info_path(&trashed_path), info)?;
        Ok(())
    }

    fn list(&self) -> Vec<TrashEntryEntity> {
        let Ok(iterator) = fs::read_dir(self.trash_dir()) else {
            return Vec::new();
        };
        let mut entries: Vec<TrashEntryEntity> = iterator
            .flatten()
            .map(|entry| {
                let trashed_path = entry.path();
                let info = fs::read_to_string(self.info_path(&trashed_path)).unwrap_or_default();
                let (original_path, deletion_date) = parse_trash_info(&info);
                TrashEntryEntity {
                    display_name: entry.file_name().to_string_lossy().into_owned(),
                    is_dir: entry.file_type().is_ok_and(|t| t.is_dir()),
                    trashed_path,
                    original_path,
                    deletion_date,
                }
            })
            .collect();
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
        self.remove_info(&entry.trashed_path);
        Ok(())
    }

    fn delete(&self, trashed_path: &Path) -> DomainResult<()> {
        let is_dir = fs::symlink_metadata(trashed_path)?.is_dir();
        if is_dir {
            fs::remove_dir_all(trashed_path)?;
        } else {
            fs::remove_file(trashed_path)?;
        }
        self.remove_info(trashed_path);
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
