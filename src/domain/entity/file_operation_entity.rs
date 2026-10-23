use std::path::{Path, PathBuf};

use crate::domain::shared::archive::ArchiveFormat;
use crate::domain::shared::path::{file_name, parent_dir};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FileOperationKind {
    Copy,
    Move,
    Compress(ArchiveFormat),
    Extract,
}

/// A queued background job (paste, compress, extract), run one at a time.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FileOperationEntity {
    pub kind: FileOperationKind,
    pub source: PathBuf,
    pub destination: PathBuf,
}

impl FileOperationEntity {
    pub fn new(kind: FileOperationKind, source: &Path, destination: &Path) -> Self {
        Self {
            kind,
            source: source.to_path_buf(),
            destination: destination.to_path_buf(),
        }
    }

    pub fn paste(source: &Path, destination: &Path, cut: bool) -> Self {
        let kind = if cut {
            FileOperationKind::Move
        } else {
            FileOperationKind::Copy
        };
        Self::new(kind, source, destination)
    }

    /// Folders whose listing changed once the job succeeded.
    pub fn refresh_targets(&self) -> Vec<PathBuf> {
        let written = match self.kind {
            FileOperationKind::Extract => self.destination.clone(),
            _ => parent_dir(&self.destination),
        };
        let mut targets = vec![written];
        if self.kind == FileOperationKind::Move {
            let source_parent = parent_dir(&self.source);
            if !targets.contains(&source_parent) {
                targets.push(source_parent);
            }
        }
        targets
    }

    /// Untranslated (heading, body) of the error dialog; the body has a
    /// `{name}` placeholder for `self.source_name()`.
    pub fn error_messages(&self) -> (&'static str, &'static str) {
        match self.kind {
            FileOperationKind::Move => ("Move failed", "Could not move \"{name}\" to this folder."),
            FileOperationKind::Compress(_) => {
                ("Compression failed", "Could not compress \"{name}\".")
            }
            FileOperationKind::Extract => ("Extraction failed", "Could not extract \"{name}\"."),
            FileOperationKind::Copy => ("Copy failed", "Could not copy \"{name}\" to this folder."),
        }
    }

    pub fn source_name(&self) -> String {
        file_name(&self.source)
    }
}
