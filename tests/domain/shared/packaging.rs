use dupot_file_browser::domain::shared::packaging::Packaging;

#[test]
fn ids_round_trip() {
    for packaging in Packaging::ALL {
        assert_eq!(Packaging::from_id(packaging.id()), Some(packaging));
    }
    assert_eq!(Packaging::from_id("appimage"), None);
}

#[test]
fn native_by_default_and_only_native_is_unconfined() {
    assert_eq!(Packaging::default(), Packaging::Native);
    assert!(Packaging::Flatpak.is_sandboxed());
    assert!(Packaging::Snap.is_sandboxed());
    assert!(!Packaging::Native.is_sandboxed());
}

#[test]
fn snap_reads_the_real_home_others_home() {
    assert_eq!(Packaging::Snap.home_variable(), "SNAP_REAL_HOME");
    assert_eq!(Packaging::Flatpak.home_variable(), "HOME");
    assert_eq!(Packaging::Native.home_variable(), "HOME");
}

#[test]
fn only_flatpak_runs_host_commands_through_flatpak_spawn() {
    let argv = vec!["sh".to_string(), "-c".to_string(), "true".to_string()];
    assert_eq!(
        Packaging::Flatpak.host_argv(&argv),
        ["flatpak-spawn", "--host", "sh", "-c", "true"]
    );
    assert_eq!(Packaging::Snap.host_argv(&argv), argv);
    assert_eq!(Packaging::Native.host_argv(&argv), argv);
}

#[test]
fn only_flatpak_shows_the_host_system_dirs() {
    assert_eq!(
        Packaging::Flatpak.host_system_dirs(),
        ["/run/host/etc", "/run/host/usr"]
    );
    assert!(Packaging::Snap.host_system_dirs().is_empty());
    assert!(Packaging::Native.host_system_dirs().is_empty());
}
