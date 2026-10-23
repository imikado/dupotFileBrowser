//! JSON file implementation of the domain's `UserSettingsRepository`.

use std::path::PathBuf;

use crate::domain::contract::user_settings_repository::UserSettingsRepository;
use crate::domain::entity::app_info::APP;
use crate::domain::entity::user_settings_entity::UserSettingsEntity;
use crate::domain::error::DomainResult;

pub struct UserSettingsApi {
    path: PathBuf,
}

impl UserSettingsApi {
    pub fn new(path: impl Into<PathBuf>) -> Self {
        Self { path: path.into() }
    }
}

impl Default for UserSettingsApi {
    /// `$XDG_DATA_HOME/<app id>/user_settings.json`.
    fn default() -> Self {
        Self::new(
            gtk::glib::user_data_dir()
                .join(APP.id)
                .join("user_settings.json"),
        )
    }
}

impl UserSettingsRepository for UserSettingsApi {
    fn load(&self) -> DomainResult<Option<UserSettingsEntity>> {
        if !self.path.is_file() {
            return Ok(None);
        }
        let text = std::fs::read_to_string(&self.path)?;
        UserSettingsEntity::from_json(&text).map(Some)
    }

    fn save(&self, settings: &UserSettingsEntity) -> DomainResult<()> {
        if let Some(dir) = self.path.parent() {
            std::fs::create_dir_all(dir)?;
        }
        std::fs::write(&self.path, settings.to_json()?)?;
        Ok(())
    }
}
