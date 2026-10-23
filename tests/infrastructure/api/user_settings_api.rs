use dupot_file_browser::domain::contract::user_settings_repository::UserSettingsRepository;
use dupot_file_browser::domain::entity::user_settings_entity::{Theme, UserSettingsEntity};
use dupot_file_browser::infrastructure::api::user_settings_api::UserSettingsApi;

use super::temp_dir;

#[test]
fn save_then_load() {
    let dir = temp_dir("settings");
    let api = UserSettingsApi::new(dir.join("app/user_settings.json"));
    assert_eq!(api.load().unwrap(), None);

    let settings = UserSettingsEntity {
        theme: Theme::Light,
        ..Default::default()
    };
    api.save(&settings).unwrap();
    assert_eq!(api.load().unwrap(), Some(settings));

    std::fs::write(dir.join("app/user_settings.json"), "{broken").unwrap();
    assert!(api.load().is_err());
    let _ = std::fs::remove_dir_all(dir);
}
