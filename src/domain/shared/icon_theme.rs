//! Icon theme fallback: the desktop's theme may not be visible from a
//! sandbox (Snap: no access to the host's /usr/share/icons), and GTK then
//! falls back to hicolor alone, which has no `*-symbolic` icons.

use std::path::{Path, PathBuf};

/// Bundled with every package (Snap: `adwaita-icon-theme` is staged).
pub const FALLBACK_ICON_THEME: &str = "Adwaita";

/// Theme to use instead of `requested` when no folder of `search_path`
/// holds it (`is_file` checks its `index.theme`); `None` keeps it.
pub fn icon_theme_override(
    requested: &str,
    search_path: &[PathBuf],
    is_file: impl Fn(&Path) -> bool,
) -> Option<&'static str> {
    let installed = search_path
        .iter()
        .any(|dir| is_file(&dir.join(requested).join("index.theme")));
    (!installed && requested != FALLBACK_ICON_THEME).then_some(FALLBACK_ICON_THEME)
}
