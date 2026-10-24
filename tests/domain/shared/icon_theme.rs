use std::path::{Path, PathBuf};

use dupot_file_browser::domain::shared::icon_theme::{FALLBACK_ICON_THEME, icon_theme_override};

fn search_path() -> Vec<PathBuf> {
    vec![
        "/snap/app/x1/usr/share/icons".into(),
        "/home/u/.icons".into(),
    ]
}

#[test]
fn keeps_a_theme_found_in_the_search_path() {
    let is_file = |path: &Path| path == Path::new("/home/u/.icons/Mint-Y-Sand/index.theme");
    assert_eq!(
        icon_theme_override("Mint-Y-Sand", &search_path(), is_file),
        None
    );
}

#[test]
fn falls_back_when_the_desktop_theme_is_not_visible() {
    // Snap: the host's /usr/share/icons/Mint-Y-Sand isn't in the sandbox.
    let is_file = |path: &Path| path == Path::new("/usr/share/icons/Mint-Y-Sand/index.theme");
    assert_eq!(
        icon_theme_override("Mint-Y-Sand", &search_path(), is_file),
        Some(FALLBACK_ICON_THEME)
    );
}

#[test]
fn a_folder_without_index_theme_is_not_a_theme() {
    assert_eq!(
        icon_theme_override("Mint-Y-Sand", &search_path(), |_| false),
        Some(FALLBACK_ICON_THEME)
    );
}

#[test]
fn never_overrides_the_fallback_itself() {
    assert_eq!(
        icon_theme_override(FALLBACK_ICON_THEME, &search_path(), |_| false),
        None
    );
}
