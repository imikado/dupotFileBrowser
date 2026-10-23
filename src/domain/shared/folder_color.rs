//! Color tags. Folders use Nemo's "Folder Color" convention (a GVFS
//! `metadata::custom-icon` pointing at a Mint-Y icon variant), so colors set
//! here and in Nemo are the same; files, and folders when GVFS metadata is
//! unavailable, use a `.dupotFileBrowser` JSON sidecar in their parent.

use std::collections::HashMap;

use serde_json::{Map, Value, json};

/// (gettext msgid of the label, hex): Nemo's own palette.
pub const PALETTE: [(&str, &str); 13] = [
    ("Blue", "#5294e2"),
    ("Navy", "#004988"),
    ("Aqua", "#57b8ec"),
    ("Teal", "#45abb7"),
    ("Cyan", "#00bcd4"),
    ("Green", "#50c16f"),
    ("Sand", "#f9c470"),
    ("Grey", "#aaaaaa"),
    ("Orange", "#ff804f"),
    ("Yaru", "#ff7446"),
    ("Red", "#f54f54"),
    ("Pink", "#f26a9a"),
    ("Purple", "#a27ae4"),
];

/// Hex -> Mint-Y icon theme variant, mirroring
/// `/usr/share/folder-color-switcher/colors.d/Mint-Y.json`.
const NEMO_THEMES: [(&str, &str); 13] = [
    ("#5294e2", "Mint-Y-Blue"),
    ("#004988", "Mint-Y-Navy"),
    ("#57b8ec", "Mint-Y-Aqua"),
    ("#45abb7", "Mint-Y-Teal"),
    ("#00bcd4", "Mint-Y-Cyan"),
    ("#50c16f", "Mint-Y"),
    ("#f9c470", "Mint-Y-Sand"),
    ("#aaaaaa", "Mint-Y-Grey"),
    ("#ff804f", "Mint-Y-Orange"),
    ("#ff7446", "Mint-Y-Yaru"),
    ("#f54f54", "Mint-Y-Red"),
    ("#f26a9a", "Mint-Y-Pink"),
    ("#a27ae4", "Mint-Y-Purple"),
];

pub const NEMO_CUSTOM_ICON_ATTRIBUTE: &str = "metadata::custom-icon";
const NEMO_ICON_SIZE: u32 = 48;

pub const SIDECAR_FILE_NAME: &str = ".dupotFileBrowser";
const FIELD_COLORED_PATH_LIST: &str = "coloredPathList";
const FIELD_NAME: &str = "name";
const FIELD_COLOR: &str = "color";

/// Icon URI Nemo would store for `color`; `None` if Nemo has no variant.
pub fn nemo_icon_uri(color: &str) -> Option<String> {
    let color = color.to_lowercase();
    NEMO_THEMES
        .iter()
        .find(|(hex, _)| *hex == color)
        .map(|(_, theme)| {
            format!("file:///usr/share/icons/{theme}/places/{NEMO_ICON_SIZE}/folder.png")
        })
}

/// Reverse of `nemo_icon_uri`: matches `/<Mint-Y variant>/places/<size>[@2x]/folder*.png`
/// at the end of `uri`. `None` for any other custom icon.
pub fn color_from_nemo_icon_uri(uri: &str) -> Option<&'static str> {
    let parts: Vec<&str> = uri.rsplitn(5, '/').collect();
    let [file, size, places, theme, _] = parts.as_slice() else {
        return None;
    };
    let size = size.strip_suffix("@2x").unwrap_or(size);
    let valid = file.starts_with("folder")
        && file.ends_with(".png")
        && !size.is_empty()
        && size.chars().all(|c| c.is_ascii_digit())
        && *places == "places";
    if !valid {
        return None;
    }
    NEMO_THEMES
        .iter()
        .find(|(_, name)| name == theme)
        .map(|(hex, _)| *hex)
}

/// `{name: color}` of the entries tagged in a sidecar file's JSON.
pub fn colored_path_map(sidecar: &Value) -> HashMap<String, String> {
    let Some(list) = sidecar
        .get(FIELD_COLORED_PATH_LIST)
        .and_then(Value::as_array)
    else {
        return HashMap::new();
    };
    list.iter()
        .filter_map(|item| {
            let name = item.get(FIELD_NAME)?.as_str()?;
            let color = item.get(FIELD_COLOR)?.as_str()?;
            (!name.is_empty() && !color.is_empty()).then(|| (name.to_string(), color.to_string()))
        })
        .collect()
}

/// Sidecar JSON with `name` tagged `color` (or untagged for `None`), other
/// keys kept. `None` when nothing changes (removing an absent tag).
pub fn with_colored_path(sidecar: &Value, name: &str, color: Option<&str>) -> Option<Value> {
    let mut root: Map<String, Value> = sidecar.as_object().cloned().unwrap_or_default();
    let original: Vec<Value> = root
        .get(FIELD_COLORED_PATH_LIST)
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut list: Vec<Value> = original
        .iter()
        .filter(|item| item.get(FIELD_NAME).and_then(Value::as_str) != Some(name))
        .cloned()
        .collect();
    match color {
        Some(color) => list.push(json!({ FIELD_NAME: name, FIELD_COLOR: color })),
        None if list.len() == original.len() => return None,
        None => {}
    }
    root.insert(FIELD_COLORED_PATH_LIST.into(), Value::Array(list));
    Some(Value::Object(root))
}
