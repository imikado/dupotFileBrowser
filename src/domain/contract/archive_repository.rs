use std::path::Path;

use crate::domain::error::DomainResult;
use crate::domain::shared::archive::ArchiveFormat;

pub trait ArchiveRepository: Send + Sync {
    /// Writes `destination` (extension included) from a file or folder.
    fn compress(
        &self,
        source: &Path,
        destination: &Path,
        format: ArchiveFormat,
    ) -> DomainResult<()>;
    /// Unpacks `source` into `destination_dir`, created if needed.
    fn extract(&self, source: &Path, destination_dir: &Path) -> DomainResult<()>;
}
