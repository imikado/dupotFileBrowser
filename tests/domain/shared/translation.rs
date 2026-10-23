use dupot_file_browser::domain::shared::translation::{format_named, parse_po};

const PO: &str = r#"
msgid ""
msgstr ""
"Language: fr\n"

#: a.py:1
msgid "Open"
msgstr "Ouvrir"

#, python-brace-format
msgid "{count} items"
msgstr "{count} éléments"

#, fuzzy
msgid "Cut"
msgstr "Couper ?"

msgid "Untranslated"
msgstr ""

msgid ""
"\"{name}\" will be "
"moved."
msgstr "\"{name}\" sera\n"
"déplacé."
"#;

#[test]
fn parses_entries_and_skips_header_fuzzy_and_empty() {
    let catalog = parse_po(PO);
    assert_eq!(catalog["Open"], "Ouvrir");
    assert_eq!(catalog["{count} items"], "{count} éléments");
    assert_eq!(
        catalog["\"{name}\" will be moved."],
        "\"{name}\" sera\ndéplacé."
    );
    assert!(!catalog.contains_key("Cut"));
    assert!(!catalog.contains_key("Untranslated"));
    assert!(!catalog.contains_key(""));
}

#[test]
fn named_placeholders() {
    assert_eq!(
        format_named("{count} items in {name}", &[("count", "3"), ("name", "a")]),
        "3 items in a"
    );
    assert_eq!(format_named("no {key}", &[]), "no {key}");
}
