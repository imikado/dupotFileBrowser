//! The Flatpak manifest and build script must agree with what the app
//! expects when started with `--packaging=flatpak`.

use dupot_file_browser::domain::shared::packaging::Packaging;

const MANIFEST: &str = include_str!("../../export/flatpak/org.dupot.filebrowser.yml");
const BUILD_SCRIPT: &str = include_str!("../../build_flatpak.sh");

#[test]
fn launcher_starts_the_app_as_a_flatpak() {
    assert!(MANIFEST.contains("--packaging=@PACKAGING@"));
    assert!(BUILD_SCRIPT.contains(&format!("packaging=\"{}\"", Packaging::Flatpak.id())));
    assert!(BUILD_SCRIPT.contains("s/@PACKAGING@/$packaging/"));
}

#[test]
fn host_system_dirs_are_mounted() {
    // /run/host/{etc,usr} only exist with access to the host file system.
    assert!(!Packaging::Flatpak.host_system_dirs().is_empty());
    assert!(
        MANIFEST
            .lines()
            .any(|line| line.trim() == "- --filesystem=host")
    );
}
