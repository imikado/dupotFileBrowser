mod archive_api;
mod color_tag_api;
mod file_system_api;
mod trash_api;
mod user_settings_api;

/// Fresh, empty folder for one test.
pub fn temp_dir(name: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("dupot-fb-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}
