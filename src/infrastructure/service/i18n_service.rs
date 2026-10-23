//! Translations: the `.po` catalogs are embedded in the binary and parsed at
//! startup for the chosen language.

use std::collections::HashMap;
use std::sync::OnceLock;

use crate::domain::entity::user_settings_entity::{DEFAULT_LANGUAGE_CODE, resolve_system_language};
use crate::domain::shared::translation::{format_named, parse_po};

const CATALOGS: [(&str, &str); 3] = [
    ("en", include_str!("../../../po/en.po")),
    ("fr", include_str!("../../../po/fr.po")),
    ("it", include_str!("../../../po/it.po")),
];

static CATALOG: OnceLock<HashMap<String, String>> = OnceLock::new();

/// Loads the catalog of `code`; only the first call has an effect.
pub fn init(code: &str) {
    let content = CATALOGS
        .iter()
        .find(|(c, _)| *c == code)
        .or_else(|| CATALOGS.iter().find(|(c, _)| *c == DEFAULT_LANGUAGE_CODE))
        .map_or("", |(_, content)| content);
    let _ = CATALOG.set(parse_po(content));
}

/// Language of the desktop session. `glib::language_names()` is the
/// reliable source in a sandbox, but can come back as just `C` before the
/// session exported its locale: the raw variables are read too.
pub fn system_language_code() -> &'static str {
    let mut names: Vec<String> = gtk::glib::language_names()
        .iter()
        .map(|name| name.to_string())
        .collect();
    for var in ["LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"] {
        if let Ok(value) = std::env::var(var) {
            names.extend(value.split(':').map(str::to_string));
        }
    }
    names.retain(|name| !name.is_empty() && name != "C");
    resolve_system_language(&names)
}

pub fn tr(msgid: &str) -> String {
    CATALOG
        .get()
        .and_then(|catalog| catalog.get(msgid))
        .cloned()
        .unwrap_or_else(|| msgid.to_string())
}

/// Translates then fills `{key}` placeholders.
pub fn trf(msgid: &str, args: &[(&str, &str)]) -> String {
    format_named(&tr(msgid), args)
}
