//! Persisted user preferences, stored as JSON. Field names and values match
//! the files written by the previous (Python) versions of the app.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::domain::error::DomainResult;

pub const DEFAULT_VERSION: u32 = 1;
pub const MIN_GRID_ICON_SIZE: i32 = 48;
pub const MAX_GRID_ICON_SIZE: i32 = 256;
pub const DEFAULT_LANGUAGE_CODE: &str = "en";
pub const SUPPORTED_LANGUAGE_CODES: [&str; 3] = ["en", "fr", "it"];

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Theme {
    Dark,
    Light,
    #[default]
    #[serde(other)]
    System,
}

impl Theme {
    pub const ALL: [Theme; 3] = [Theme::Dark, Theme::Light, Theme::System];

    /// Also the gettext msgid of its label.
    pub fn id(self) -> &'static str {
        match self {
            Theme::Dark => "dark",
            Theme::Light => "light",
            Theme::System => "system",
        }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Language {
    English,
    French,
    Italian,
    #[default]
    #[serde(other)]
    System,
}

impl Language {
    pub const ALL: [Language; 4] = [
        Language::System,
        Language::English,
        Language::French,
        Language::Italian,
    ];

    /// Also the gettext msgid of its label.
    pub fn id(self) -> &'static str {
        match self {
            Language::System => "system",
            Language::English => "english",
            Language::French => "french",
            Language::Italian => "italian",
        }
    }

    /// Language code to translate into; `system_code` is the one resolved
    /// from the desktop locale (see `resolve_system_language`).
    pub fn code(self, system_code: &str) -> String {
        match self {
            Language::System => system_code.to_string(),
            Language::English => "en".into(),
            Language::French => "fr".into(),
            Language::Italian => "it".into(),
        }
    }
}

/// First supported language among locale names such as `fr_FR.UTF-8`,
/// `it`, `C`; English when none matches.
pub fn resolve_system_language<S: AsRef<str>>(locale_names: &[S]) -> &'static str {
    locale_names
        .iter()
        .filter_map(|name| {
            let base = name.as_ref().split(['.', '@']).next()?.split('_').next()?;
            let base = base.to_lowercase();
            SUPPORTED_LANGUAGE_CODES
                .into_iter()
                .find(|code| *code == base)
        })
        .next()
        .unwrap_or(DEFAULT_LANGUAGE_CODE)
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ViewMode {
    Grid,
    Details,
    #[default]
    #[serde(other)]
    Columns,
}

impl ViewMode {
    pub const ALL: [ViewMode; 3] = [ViewMode::Columns, ViewMode::Grid, ViewMode::Details];

    pub fn id(self) -> &'static str {
        match self {
            ViewMode::Columns => "columns",
            ViewMode::Grid => "grid",
            ViewMode::Details => "details",
        }
    }

    pub fn from_id(id: &str) -> Option<Self> {
        Self::ALL.into_iter().find(|mode| mode.id() == id)
    }

    /// Grid and Details show one folder at a time; Columns shows a chain.
    pub fn is_single_folder(self) -> bool {
        self != ViewMode::Columns
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FavoriteMove {
    Up,
    Down,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Favorite {
    pub label: String,
    pub path: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default, rename_all = "camelCase")]
pub struct UserSettingsEntity {
    pub version: u32,
    pub theme: Theme,
    pub language: Language,
    pub use_system_icon_theme: bool,
    pub window_width: i32,
    pub window_height: i32,
    pub favorite_list: Vec<Favorite>,
    pub display_hidden: bool,
    pub view_mode: ViewMode,
    pub grid_icon_size: i32,
    /// Grid and Details only: open on a single click instead of a double one.
    pub single_click_open: bool,
}

impl Default for UserSettingsEntity {
    fn default() -> Self {
        Self {
            version: DEFAULT_VERSION,
            theme: Theme::System,
            language: Language::System,
            use_system_icon_theme: true,
            window_width: 1000,
            window_height: 700,
            favorite_list: Vec::new(),
            display_hidden: false,
            view_mode: ViewMode::Columns,
            grid_icon_size: 96,
            single_click_open: false,
        }
    }
}

impl UserSettingsEntity {
    /// Parses a settings file; missing fields take their default, and a file
    /// written for another settings version is reset to defaults.
    pub fn from_json(text: &str) -> DomainResult<Self> {
        let mut settings: Self = serde_json::from_str(text)?;
        if settings.version != DEFAULT_VERSION {
            settings = Self::default();
        }
        settings.grid_icon_size = clamp_grid_icon_size(settings.grid_icon_size);
        Ok(settings)
    }

    pub fn to_json(&self) -> DomainResult<String> {
        Ok(serde_json::to_string_pretty(self)?)
    }

    pub fn set_window_size(&mut self, width: i32, height: i32) {
        self.window_width = width;
        self.window_height = height;
    }

    /// No-op when `path` is already a favorite.
    pub fn add_favorite(&mut self, label: &str, path: &str) {
        if self.is_favorite(path) {
            return;
        }
        self.favorite_list.push(Favorite {
            label: label.to_string(),
            path: path.to_string(),
        });
    }

    pub fn remove_favorite(&mut self, path: &str) {
        self.favorite_list.retain(|favorite| favorite.path != path);
    }

    /// Whether the favorite at `path` can move that way (not past the ends).
    pub fn can_move_favorite(&self, path: &str, direction: FavoriteMove) -> bool {
        self.favorite_target_index(path, direction).is_some()
    }

    /// Swaps the favorite at `path` with its neighbor; `false` when it's
    /// unknown or already at that end.
    pub fn move_favorite(&mut self, path: &str, direction: FavoriteMove) -> bool {
        let Some((index, target)) = self.favorite_target_index(path, direction) else {
            return false;
        };
        self.favorite_list.swap(index, target);
        true
    }

    fn favorite_target_index(&self, path: &str, direction: FavoriteMove) -> Option<(usize, usize)> {
        let index = self
            .favorite_list
            .iter()
            .position(|favorite| favorite.path == path)?;
        let target = match direction {
            FavoriteMove::Up => index.checked_sub(1)?,
            FavoriteMove::Down => index + 1,
        };
        (target < self.favorite_list.len()).then_some((index, target))
    }

    /// Follows a folder renamed or moved from `old` to `new`: favorites of
    /// it or inside it get the new path, and a favorite still labelled with
    /// the old name gets the new one. `true` if any changed.
    pub fn rename_favorites(&mut self, old: &Path, new: &Path) -> bool {
        let old_name = old.file_name().map(|name| name.to_string_lossy());
        let mut changed = false;
        for favorite in &mut self.favorite_list {
            let path = PathBuf::from(&favorite.path);
            let Ok(rest) = path.strip_prefix(old) else {
                continue;
            };
            let moved = if rest.as_os_str().is_empty() {
                if old_name.as_deref() == Some(favorite.label.as_str())
                    && let Some(new_name) = new.file_name()
                {
                    favorite.label = new_name.to_string_lossy().into_owned();
                }
                new.to_path_buf()
            } else {
                new.join(rest)
            };
            favorite.path = moved.to_string_lossy().into_owned();
            changed = true;
        }
        changed
    }

    pub fn is_favorite(&self, path: &str) -> bool {
        self.favorite_list
            .iter()
            .any(|favorite| favorite.path == path)
    }

    pub fn set_grid_icon_size(&mut self, size: i32) {
        self.grid_icon_size = clamp_grid_icon_size(size);
    }
}

fn clamp_grid_icon_size(size: i32) -> i32 {
    size.clamp(MIN_GRID_ICON_SIZE, MAX_GRID_ICON_SIZE)
}
