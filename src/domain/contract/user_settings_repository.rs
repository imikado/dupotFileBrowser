use crate::domain::entity::user_settings_entity::UserSettingsEntity;
use crate::domain::error::DomainResult;

pub trait UserSettingsRepository: Send + Sync {
    /// `Ok(None)` when no settings were saved yet.
    fn load(&self) -> DomainResult<Option<UserSettingsEntity>>;
    fn save(&self, settings: &UserSettingsEntity) -> DomainResult<()>;
}
