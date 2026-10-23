use dupot_file_browser::domain::shared::permissions::{mode_from_flags, mode_to_symbolic};

#[test]
fn symbolic_mode() {
    assert_eq!(mode_to_symbolic(0o755, true), "drwxr-xr-x (755)");
    assert_eq!(mode_to_symbolic(0o640, false), "-rw-r----- (640)");
}

#[test]
fn mode_from_checkbox_grid() {
    let flags = [
        [true, true, false],
        [true, false, false],
        [false, false, false],
    ];
    assert_eq!(mode_from_flags(flags), 0o640);
    assert_eq!(mode_from_flags([[true; 3]; 3]), 0o777);
}
