//! `std::fs` implementation of the domain's `FileSystemRepository`. The
//! Flatpak build has `--filesystem=host`, so no host process is needed.

use std::ffi::CStr;
use std::fs::{self, File, FileTimes, Metadata};
use std::os::unix::fs::{MetadataExt, PermissionsExt, symlink};
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

use gtk::gio;
use gtk::gio::prelude::*;

use crate::domain::contract::file_system_repository::FileSystemRepository;
use crate::domain::entity::file_entry_entity::FileEntryEntity;
use crate::domain::entity::file_properties_entity::FilePropertiesEntity;
use crate::domain::error::{DomainError, DomainResult};
use crate::domain::shared::path::{file_name, parent_dir};

const EXDEV: i32 = 18;

#[derive(Clone, Copy, Debug, Default)]
pub struct FileSystemApi;

fn error_at(path: &Path, error: impl std::fmt::Display) -> DomainError {
    DomainError::new(format!("{}: {error}", path.display()))
}

fn mtime(metadata: &Metadata) -> Option<i64> {
    metadata
        .modified()
        .ok()?
        .duration_since(UNIX_EPOCH)
        .ok()
        .map(|d| d.as_secs() as i64)
}

fn copy_recursive(source: &Path, destination: &Path) -> DomainResult<()> {
    let metadata = fs::symlink_metadata(source).map_err(|e| error_at(source, e))?;
    let file_type = metadata.file_type();
    if file_type.is_symlink() {
        let target = fs::read_link(source).map_err(|e| error_at(source, e))?;
        symlink(&target, destination).map_err(|e| error_at(destination, e))?;
        return Ok(());
    }
    if file_type.is_dir() {
        fs::create_dir(destination).map_err(|e| error_at(destination, e))?;
        for entry in fs::read_dir(source).map_err(|e| error_at(source, e))? {
            let entry = entry.map_err(|e| error_at(source, e))?;
            copy_recursive(&entry.path(), &destination.join(entry.file_name()))?;
        }
    } else {
        fs::copy(source, destination).map_err(|e| error_at(source, e))?;
    }
    fs::set_permissions(destination, metadata.permissions())
        .map_err(|e| error_at(destination, e))?;
    // Best effort, like `cp -a` on a file system without time support.
    if let (Ok(modified), Ok(accessed), Ok(file)) = (
        metadata.modified(),
        metadata.accessed(),
        File::open(destination),
    ) {
        let _ = file.set_times(
            FileTimes::new()
                .set_modified(modified)
                .set_accessed(accessed),
        );
    }
    Ok(())
}

fn remove_recursive(path: &Path) -> std::io::Result<()> {
    if fs::symlink_metadata(path)?.is_dir() {
        fs::remove_dir_all(path)
    } else {
        fs::remove_file(path)
    }
}

fn user_name(uid: u32) -> Option<String> {
    let mut buffer = vec![0 as libc::c_char; 4096];
    let mut passwd: libc::passwd = unsafe { std::mem::zeroed() };
    let mut result: *mut libc::passwd = std::ptr::null_mut();
    // SAFETY: every pointer refers to a live, correctly sized buffer.
    let status = unsafe {
        libc::getpwuid_r(
            uid,
            &mut passwd,
            buffer.as_mut_ptr(),
            buffer.len(),
            &mut result,
        )
    };
    if status != 0 || result.is_null() {
        return None;
    }
    // SAFETY: on success pw_name points into `buffer`, NUL-terminated.
    Some(
        unsafe { CStr::from_ptr(passwd.pw_name) }
            .to_string_lossy()
            .into_owned(),
    )
}

fn group_name(gid: u32) -> Option<String> {
    let mut buffer = vec![0 as libc::c_char; 4096];
    let mut group: libc::group = unsafe { std::mem::zeroed() };
    let mut result: *mut libc::group = std::ptr::null_mut();
    // SAFETY: every pointer refers to a live, correctly sized buffer.
    let status = unsafe {
        libc::getgrgid_r(
            gid,
            &mut group,
            buffer.as_mut_ptr(),
            buffer.len(),
            &mut result,
        )
    };
    if status != 0 || result.is_null() {
        return None;
    }
    // SAFETY: on success gr_name points into `buffer`, NUL-terminated.
    Some(
        unsafe { CStr::from_ptr(group.gr_name) }
            .to_string_lossy()
            .into_owned(),
    )
}

/// Description of the file's MIME type ("PNG image"…), from GIO.
pub fn type_description(path: &Path) -> String {
    let content_type = content_type(path);
    let description = gio::content_type_get_description(&content_type);
    if description.is_empty() {
        content_type
    } else {
        description.to_string()
    }
}

pub fn content_type(path: &Path) -> String {
    gio::File::for_path(path)
        .query_info(
            gio::FILE_ATTRIBUTE_STANDARD_CONTENT_TYPE,
            gio::FileQueryInfoFlags::NONE,
            gio::Cancellable::NONE,
        )
        .ok()
        .and_then(|info| info.content_type())
        .map_or_else(|| "application/octet-stream".to_string(), |t| t.to_string())
}

impl FileSystemRepository for FileSystemApi {
    fn list_dir(&self, path: &Path) -> Vec<FileEntryEntity> {
        let Ok(iterator) = fs::read_dir(path) else {
            return Vec::new();
        };
        iterator
            .flatten()
            .map(|entry| {
                let path = entry.path();
                let metadata = fs::metadata(&path).ok();
                let is_dir = metadata.as_ref().is_some_and(Metadata::is_dir);
                FileEntryEntity {
                    name: entry.file_name().to_string_lossy().into_owned(),
                    is_dir,
                    size: metadata.as_ref().filter(|_| !is_dir).map(Metadata::len),
                    mtime: metadata.as_ref().and_then(mtime),
                    path,
                }
            })
            .collect()
    }

    fn exists(&self, path: &Path) -> bool {
        fs::symlink_metadata(path).is_ok()
    }

    fn is_dir(&self, path: &Path) -> bool {
        path.is_dir()
    }

    fn home_dir(&self) -> PathBuf {
        std::env::var_os("HOME")
            .filter(|home| !home.is_empty())
            .map_or_else(gtk::glib::home_dir, PathBuf::from)
    }

    fn copy_path(&self, source: &Path, destination: &Path) -> DomainResult<()> {
        copy_recursive(source, destination)
    }

    fn move_path(&self, source: &Path, destination: &Path) -> DomainResult<()> {
        match fs::rename(source, destination) {
            Ok(()) => Ok(()),
            Err(error) if error.raw_os_error() == Some(EXDEV) => {
                copy_recursive(source, destination)?;
                remove_recursive(source).map_err(|e| error_at(source, e))
            }
            Err(error) => Err(error_at(source, error)),
        }
    }

    fn dir_size(&self, path: &Path) -> u64 {
        let Ok(iterator) = fs::read_dir(path) else {
            return 0;
        };
        iterator
            .flatten()
            .map(|entry| match entry.file_type() {
                Ok(t) if t.is_dir() => self.dir_size(&entry.path()),
                Ok(t) if t.is_file() => entry.metadata().map_or(0, |m| m.len()),
                _ => 0,
            })
            .sum()
    }

    fn file_properties(&self, path: &Path) -> FilePropertiesEntity {
        let metadata = fs::metadata(path).ok();
        let is_dir = metadata.as_ref().is_some_and(Metadata::is_dir);
        FilePropertiesEntity {
            name: file_name(path),
            location: parent_dir(path).to_string_lossy().into_owned(),
            type_description: type_description(path),
            is_dir,
            size: metadata.as_ref().filter(|_| !is_dir).map(Metadata::len),
            item_count: is_dir
                .then(|| fs::read_dir(path).ok().map(Iterator::count))
                .flatten(),
            modified: metadata.as_ref().and_then(mtime),
            owner: metadata
                .as_ref()
                .map(|m| user_name(m.uid()).unwrap_or_else(|| m.uid().to_string())),
            group: metadata
                .as_ref()
                .map(|m| group_name(m.gid()).unwrap_or_else(|| m.gid().to_string())),
            mode: metadata.as_ref().map(|m| m.mode() & 0o7777),
        }
    }

    fn set_permissions(&self, path: &Path, mode: u32) -> DomainResult<()> {
        fs::set_permissions(path, fs::Permissions::from_mode(mode)).map_err(|e| error_at(path, e))
    }
}
