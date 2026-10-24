use dupot_file_browser::domain::entity::user_settings_entity::{
    FavoriteMove, Language, Theme, UserSettingsEntity, ViewMode, resolve_system_language,
};

#[test]
fn reads_files_written_by_the_python_version() {
    let json = r#"{"version": 1, "theme": "dark", "language": "french", "useSystemIconTheme": false,
        "windowWidth": 1200, "windowHeight": 800,
        "favoriteList": [{"label": "Music", "path": "/home/me/Music"}],
        "displayHidden": true, "viewMode": "grid", "gridIconSize": 128, "singleClickOpen": true}"#;
    let settings = UserSettingsEntity::from_json(json).unwrap();
    assert_eq!(settings.theme, Theme::Dark);
    assert_eq!(settings.language, Language::French);
    assert!(!settings.use_system_icon_theme);
    assert_eq!((settings.window_width, settings.window_height), (1200, 800));
    assert_eq!(settings.favorite_list[0].path, "/home/me/Music");
    assert!(settings.display_hidden);
    assert_eq!(settings.view_mode, ViewMode::Grid);
    assert_eq!(settings.grid_icon_size, 128);
    assert!(settings.single_click_open);
}

#[test]
fn missing_and_unknown_values_take_defaults() {
    let settings =
        UserSettingsEntity::from_json(r#"{"theme": "neon", "viewMode": "tree"}"#).unwrap();
    assert_eq!(settings.theme, Theme::System);
    assert_eq!(settings.view_mode, ViewMode::Columns);
    assert_eq!(settings.window_width, 1000);
}

#[test]
fn other_version_resets_to_defaults() {
    let settings = UserSettingsEntity::from_json(r#"{"version": 2, "theme": "dark"}"#).unwrap();
    assert_eq!(settings, UserSettingsEntity::default());
}

#[test]
fn json_round_trip_uses_camel_case() {
    let mut settings = UserSettingsEntity::default();
    settings.add_favorite("Docs", "/home/me/Docs");
    let json = settings.to_json().unwrap();
    assert!(json.contains("\"displayHidden\""));
    assert!(json.contains("\"favoriteList\""));
    assert_eq!(UserSettingsEntity::from_json(&json).unwrap(), settings);
}

#[test]
fn favorites_are_unique_by_path() {
    let mut settings = UserSettingsEntity::default();
    settings.add_favorite("A", "/a");
    settings.add_favorite("A again", "/a");
    settings.add_favorite("B", "/b");
    assert_eq!(settings.favorite_list.len(), 2);
    settings.remove_favorite("/a");
    assert!(!settings.is_favorite("/a"));
    assert!(settings.is_favorite("/b"));
}

fn favorite_paths(settings: &UserSettingsEntity) -> Vec<&str> {
    settings
        .favorite_list
        .iter()
        .map(|favorite| favorite.path.as_str())
        .collect()
}

#[test]
fn favorites_move_up_and_down_within_the_list() {
    let mut settings = UserSettingsEntity::default();
    for path in ["/a", "/b", "/c"] {
        settings.add_favorite(path, path);
    }
    assert!(settings.move_favorite("/b", FavoriteMove::Up));
    assert_eq!(favorite_paths(&settings), ["/b", "/a", "/c"]);
    assert!(settings.move_favorite("/a", FavoriteMove::Down));
    assert_eq!(favorite_paths(&settings), ["/b", "/c", "/a"]);
}

#[test]
fn favorites_never_move_past_the_ends() {
    let mut settings = UserSettingsEntity::default();
    for path in ["/a", "/b"] {
        settings.add_favorite(path, path);
    }
    assert!(!settings.can_move_favorite("/a", FavoriteMove::Up));
    assert!(settings.can_move_favorite("/a", FavoriteMove::Down));
    assert!(settings.can_move_favorite("/b", FavoriteMove::Up));
    assert!(!settings.can_move_favorite("/b", FavoriteMove::Down));
    assert!(!settings.move_favorite("/a", FavoriteMove::Up));
    assert!(!settings.move_favorite("/b", FavoriteMove::Down));
    assert!(!settings.move_favorite("/unknown", FavoriteMove::Up));
    assert_eq!(favorite_paths(&settings), ["/a", "/b"]);
}

#[test]
fn a_single_favorite_cannot_move() {
    let mut settings = UserSettingsEntity::default();
    settings.add_favorite("A", "/a");
    assert!(!settings.can_move_favorite("/a", FavoriteMove::Up));
    assert!(!settings.can_move_favorite("/a", FavoriteMove::Down));
}

#[test]
fn grid_icon_size_is_clamped() {
    let mut settings = UserSettingsEntity::default();
    settings.set_grid_icon_size(1000);
    assert_eq!(settings.grid_icon_size, 256);
    settings.set_grid_icon_size(1);
    assert_eq!(settings.grid_icon_size, 48);
}

#[test]
fn language_codes() {
    assert_eq!(Language::System.code("it"), "it");
    assert_eq!(Language::French.code("it"), "fr");
    assert_eq!(resolve_system_language(&["fr_FR.UTF-8", "fr"]), "fr");
    assert_eq!(resolve_system_language(&["de_DE", "it_IT@euro"]), "it");
    assert_eq!(resolve_system_language::<&str>(&[]), "en");
}

#[test]
fn view_mode_ids() {
    for mode in ViewMode::ALL {
        assert_eq!(ViewMode::from_id(mode.id()), Some(mode));
    }
    assert!(ViewMode::Grid.is_single_folder());
    assert!(!ViewMode::Columns.is_single_folder());
}

#[test]
fn renamed_folders_keep_their_favorites() {
    let mut settings = UserSettingsEntity::default();
    settings.add_favorite("Music", "/home/me/Music");
    settings.add_favorite("Rock", "/home/me/Music/Rock");
    settings.add_favorite("Musician", "/home/me/Musician");
    let changed = settings.rename_favorites(
        std::path::Path::new("/home/me/Music"),
        std::path::Path::new("/home/me/Songs"),
    );
    assert!(changed);
    let favorites: Vec<(&str, &str)> = settings
        .favorite_list
        .iter()
        .map(|f| (f.label.as_str(), f.path.as_str()))
        .collect();
    assert_eq!(
        favorites,
        [
            ("Songs", "/home/me/Songs"),
            ("Rock", "/home/me/Songs/Rock"),
            ("Musician", "/home/me/Musician"),
        ]
    );
    assert!(!settings.rename_favorites(
        std::path::Path::new("/elsewhere"),
        std::path::Path::new("/x")
    ));
}
