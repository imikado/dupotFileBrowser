use dupot_file_browser::domain::contract::color_tag_repository::ColorTagRepository;
use dupot_file_browser::domain::shared::folder_color::SIDECAR_FILE_NAME;
use dupot_file_browser::infrastructure::api::color_tag_api::ColorTagApi;

use super::temp_dir;

#[test]
fn file_colors_live_in_the_sidecar() {
    let dir = temp_dir("colors");
    ColorTagApi.set_file_color(&dir, "a.txt", Some("#5294e2"));
    ColorTagApi.set_file_color(&dir, "b.txt", Some("#f54f54"));
    let map = ColorTagApi.colored_path_map(&dir);
    assert_eq!(map["a.txt"], "#5294e2");
    assert_eq!(map.len(), 2);

    ColorTagApi.set_file_color(&dir, "a.txt", None);
    assert_eq!(ColorTagApi.colored_path_map(&dir).len(), 1);
    assert!(dir.join(SIDECAR_FILE_NAME).is_file());
    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn folder_color_is_found_again() {
    let dir = temp_dir("folder-color");
    let folder = dir.join("music");
    std::fs::create_dir(&folder).unwrap();
    assert_eq!(ColorTagApi.folder_color(&folder), None);
    // GVFS metadata when available, the parent's sidecar otherwise.
    ColorTagApi.set_folder_color(&folder, Some("#a27ae4"));
    assert_eq!(
        ColorTagApi.folder_color(&folder).as_deref(),
        Some("#a27ae4")
    );
    ColorTagApi.set_folder_color(&folder, None);
    assert_eq!(ColorTagApi.folder_color(&folder), None);
    let _ = std::fs::remove_dir_all(dir);
}
