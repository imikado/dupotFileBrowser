use std::path::Path;

use crate::domain::error::DomainResult;
use crate::domain::shared::packaging::Packaging;

/// Integration with the desktop and host programs.
pub trait DesktopRepository: Send + Sync {
    /// How the app was installed (`--packaging` at launch).
    fn packaging(&self) -> Packaging;
    /// Opens with the default application.
    fn open_path(&self, path: &Path) -> DomainResult<()>;
    /// Asks the desktop portal to show its own "Open With" chooser.
    fn open_with_chooser(&self, path: &Path) -> DomainResult<()>;
    /// Opens a terminal in `path` (its folder, for a file); `false` if no
    /// terminal could be found.
    fn open_terminal(&self, path: &Path) -> bool;
    /// `false` if no supported desktop setting could be changed.
    fn set_wallpaper(&self, path: &Path) -> bool;
}
