//! The Snap recipe, its launcher and build script must agree with what the
//! app expects when started with `--packaging=snap`.

use dupot_file_browser::domain::shared::folder_color::SIDECAR_FILE_NAME;
use dupot_file_browser::domain::shared::icon_theme::FALLBACK_ICON_THEME;
use dupot_file_browser::domain::shared::packaging::Packaging;
use dupot_file_browser::domain::shared::trash_info::HOME_TRASH_DIR;

const RECIPE: &str = include_str!("../../export/snap/snapcraft.yaml");
const LAUNCHER: &str = include_str!("../../export/snap/launcher.sh");
const BUILD_SCRIPT: &str = include_str!("../../build_snap.sh");

/// Lines of `RECIPE`'s `apps:` section.
fn app_plugs() -> Vec<&'static str> {
    RECIPE
        .lines()
        .skip_while(|line| !line.starts_with("    plugs:"))
        .skip(1)
        .take_while(|line| line.trim_start().starts_with("- "))
        .map(|line| line.trim_start().trim_start_matches("- "))
        .collect()
}

#[test]
fn launcher_starts_the_app_as_a_snap() {
    let packaging = format!("--packaging={}", Packaging::Snap.id());
    assert!(LAUNCHER.contains(&packaging));
    assert!(BUILD_SCRIPT.contains(&format!("packaging=\"{}\"", Packaging::Snap.id())));
}

#[test]
fn launcher_puts_the_staged_data_first() {
    // Icon themes, schemas and MIME data come from the snap, not core26.
    assert!(LAUNCHER.contains("export XDG_DATA_DIRS=\"$SNAP/usr/share:"));
}

#[test]
fn stages_the_fallback_icon_theme() {
    let package = format!("- {}-icon-theme", FALLBACK_ICON_THEME.to_lowercase());
    assert!(
        RECIPE.lines().any(|line| line.trim() == package),
        "{package}"
    );
}

#[test]
fn hidden_home_files_have_their_interface() {
    // `home` doesn't grant hidden files at the top of $HOME.
    for (plug, path) in [
        ("trash", format!("$HOME/{HOME_TRASH_DIR}")),
        ("color-tags", format!("$HOME/{SIDECAR_FILE_NAME}")),
    ] {
        assert!(app_plugs().contains(&plug), "app lacks plug {plug}");
        let declared = RECIPE
            .split(&format!("\n  {plug}:\n"))
            .nth(1)
            .is_some_and(|rest| {
                rest.lines()
                    .take_while(|line| line.starts_with("    ") || line.trim().is_empty())
                    .any(|line| line.trim() == format!("- {path}"))
            });
        assert!(declared, "plug {plug} must grant {path}");
        assert!(
            BUILD_SCRIPT.contains(&format!("snap connect \"$snap_name:{plug}\"")),
            "build_snap.sh --install must connect {plug}"
        );
    }
}

#[test]
fn is_strictly_confined() {
    assert!(Packaging::Snap.is_sandboxed());
    assert!(RECIPE.lines().any(|line| line == "confinement: strict"));
}
