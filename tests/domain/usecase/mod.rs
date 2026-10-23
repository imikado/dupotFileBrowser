mod destination;
mod list_directory;

use std::path::{Path, PathBuf};

use dupot_file_browser::domain::contract::file_system_repository::FileSystemRepository;
use dupot_file_browser::domain::entity::file_entry_entity::FileEntryEntity;
use dupot_file_browser::domain::entity::file_properties_entity::FilePropertiesEntity;
use dupot_file_browser::domain::error::DomainResult;

/// In-memory folder: `entries` are the paths that exist.
pub struct FakeFileSystem {
    pub entries: Vec<FileEntryEntity>,
}

impl FakeFileSystem {
    pub fn with(names: &[(&str, bool)]) -> Self {
        Self {
            entries: names
                .iter()
                .map(|(name, is_dir)| FileEntryEntity {
                    name: name.to_string(),
                    path: Path::new("/data").join(name),
                    is_dir: *is_dir,
                    size: None,
                    mtime: None,
                })
                .collect(),
        }
    }
}

impl FileSystemRepository for FakeFileSystem {
    fn list_dir(&self, _: &Path) -> Vec<FileEntryEntity> {
        self.entries.clone()
    }
    fn exists(&self, path: &Path) -> bool {
        self.entries.iter().any(|entry| entry.path == path)
    }
    fn is_dir(&self, path: &Path) -> bool {
        self.entries
            .iter()
            .any(|entry| entry.path == path && entry.is_dir)
    }
    fn home_dir(&self) -> PathBuf {
        "/data".into()
    }
    fn copy_path(&self, _: &Path, _: &Path) -> DomainResult<()> {
        unimplemented!()
    }
    fn move_path(&self, _: &Path, _: &Path) -> DomainResult<()> {
        unimplemented!()
    }
    fn dir_size(&self, _: &Path) -> u64 {
        unimplemented!()
    }
    fn file_properties(&self, _: &Path) -> FilePropertiesEntity {
        unimplemented!()
    }
    fn set_permissions(&self, _: &Path, _: u32) -> DomainResult<()> {
        unimplemented!()
    }
}
