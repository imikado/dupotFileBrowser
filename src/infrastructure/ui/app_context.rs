//! What every view shares: the repositories, the user settings, and the
//! channel views use to tell the window what happened.

use std::cell::{Ref, RefCell, RefMut};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::sync::Arc;

use crate::domain::contract::archive_repository::ArchiveRepository;
use crate::domain::contract::color_tag_repository::ColorTagRepository;
use crate::domain::contract::desktop_repository::DesktopRepository;
use crate::domain::contract::file_system_repository::FileSystemRepository;
use crate::domain::contract::trash_repository::TrashRepository;
use crate::domain::contract::user_settings_repository::UserSettingsRepository;
use crate::domain::entity::file_entry_entity::FileEntryEntity;
use crate::domain::entity::file_operation_entity::FileOperationEntity;
use crate::domain::entity::user_settings_entity::UserSettingsEntity;
use crate::domain::usecase::list_directory::list_directory;
use crate::infrastructure::api::archive_api::ArchiveApi;
use crate::infrastructure::api::color_tag_api::ColorTagApi;
use crate::infrastructure::api::desktop_api::DesktopApi;
use crate::infrastructure::api::file_system_api::FileSystemApi;
use crate::infrastructure::api::trash_api::TrashApi;
use crate::infrastructure::api::user_settings_api::UserSettingsApi;

/// Something a browser view asks the window to handle.
#[derive(Clone, Debug)]
pub enum BrowserEvent {
    /// The view now shows this folder.
    PathChanged(PathBuf),
    FavoritesChanged,
    /// The listing of this folder changed (rename, trash): other tabs
    /// showing it reload.
    FolderChanged(PathBuf),
    /// Copy (or cut) put this file on the clipboard.
    Clipboard {
        path: PathBuf,
        cut: bool,
    },
    /// Queue a background job.
    Job(FileOperationEntity),
    /// Extract this archive next to itself (the window picks the name).
    Extract(PathBuf),
}

pub type EventSink = Rc<dyn Fn(BrowserEvent)>;

pub struct AppContext {
    pub file_system: Arc<dyn FileSystemRepository>,
    pub archives: Arc<dyn ArchiveRepository>,
    pub trash: Arc<dyn TrashRepository>,
    pub color_tags: Arc<dyn ColorTagRepository>,
    pub desktop: Arc<dyn DesktopRepository>,
    settings_repository: Arc<dyn UserSettingsRepository>,
    settings: RefCell<UserSettingsEntity>,
}

impl AppContext {
    /// Production wiring; settings are loaded (or created) from disk.
    pub fn new() -> Rc<Self> {
        let settings_repository: Arc<dyn UserSettingsRepository> =
            Arc::new(UserSettingsApi::default());
        let settings = match settings_repository.load() {
            Ok(Some(settings)) => settings,
            Ok(None) | Err(_) => {
                let defaults = UserSettingsEntity::default();
                let _ = settings_repository.save(&defaults);
                defaults
            }
        };
        Rc::new(Self {
            file_system: Arc::new(FileSystemApi),
            archives: Arc::new(ArchiveApi),
            trash: Arc::new(TrashApi::default()),
            color_tags: Arc::new(ColorTagApi),
            desktop: Arc::new(DesktopApi),
            settings_repository,
            settings: RefCell::new(settings),
        })
    }

    pub fn settings(&self) -> Ref<'_, UserSettingsEntity> {
        self.settings.borrow()
    }

    pub fn settings_mut(&self) -> RefMut<'_, UserSettingsEntity> {
        self.settings.borrow_mut()
    }

    pub fn save_settings(&self) {
        if let Err(error) = self.settings_repository.save(&self.settings.borrow()) {
            eprintln!("could not save settings: {error}");
        }
    }

    /// Sorted entries of `path`, honouring the hidden-files setting.
    pub fn list(&self, path: &Path) -> Vec<FileEntryEntity> {
        list_directory(
            self.file_system.as_ref(),
            path,
            self.settings().display_hidden,
        )
    }

    /// `{name: color}` for `entries` of `path`: one sidecar read for the
    /// files, one metadata query per folder (Nemo stores it on the folder).
    pub fn color_map(&self, path: &Path, entries: &[FileEntryEntity]) -> HashMap<String, String> {
        let mut colors = self.color_tags.colored_path_map(path);
        for entry in entries.iter().filter(|entry| entry.is_dir) {
            if let Some(color) = self.color_tags.folder_color(&entry.path) {
                colors.insert(entry.name.clone(), color);
            }
        }
        colors
    }

    /// Color tag of `path`, read before a rename (folder metadata is keyed
    /// by path).
    pub fn color_at(&self, path: &Path) -> Option<String> {
        if self.file_system.is_dir(path) {
            self.color_tags.folder_color(path)
        } else {
            let parent = crate::domain::shared::path::parent_dir(path);
            let name = crate::domain::shared::path::file_name(path);
            self.color_tags.colored_path_map(&parent).remove(&name)
        }
    }

    /// Puts `color` (from `color_at` before the move) on `new` and clears
    /// what was recorded for `old`.
    pub fn transfer_color(&self, old: &Path, new: &Path, color: Option<&str>) {
        let Some(color) = color else { return };
        use crate::domain::shared::path::{file_name, parent_dir};
        if self.file_system.is_dir(new) {
            // Clears the stale sidecar entry; the metadata left on the old
            // path has no file to point at.
            self.color_tags.set_folder_color(old, None);
            self.color_tags.set_folder_color(new, Some(color));
        } else {
            self.color_tags
                .set_file_color(&parent_dir(old), &file_name(old), None);
            self.color_tags
                .set_file_color(&parent_dir(new), &file_name(new), Some(color));
        }
    }

    /// Tags (or untags) an entry: folders the Nemo way, files in the sidecar.
    pub fn set_color(&self, entry: &FileEntryEntity, color: Option<&str>) {
        if entry.is_dir {
            self.color_tags.set_folder_color(&entry.path, color);
        } else {
            let parent = crate::domain::shared::path::parent_dir(&entry.path);
            self.color_tags.set_file_color(&parent, &entry.name, color);
        }
    }
}
