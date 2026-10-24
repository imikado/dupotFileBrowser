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
