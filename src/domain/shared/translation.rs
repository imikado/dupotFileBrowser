//! Gettext `.po` catalogs, read at runtime (no `.mo` compilation step).

use std::collections::HashMap;

/// msgid -> msgstr of a `.po` file. Untranslated and fuzzy entries, and
/// the header, are left out so lookups fall back to the msgid.
pub fn parse_po(content: &str) -> HashMap<String, String> {
    let mut catalog = HashMap::new();
    let mut msgid = String::new();
    let mut msgstr = String::new();
    let mut fuzzy = false;
    let mut target: Option<bool> = None; // Some(true) = msgid, Some(false) = msgstr

    let mut flush = |msgid: &mut String, msgstr: &mut String, fuzzy: &mut bool| {
        if !msgid.is_empty() && !msgstr.is_empty() && !*fuzzy {
            catalog.insert(std::mem::take(msgid), std::mem::take(msgstr));
        }
        msgid.clear();
        msgstr.clear();
        *fuzzy = false;
    };

    for line in content.lines().map(str::trim) {
        if line.is_empty() {
            continue;
        }
        if let Some(flags) = line.strip_prefix("#,") {
            if target == Some(false) {
                flush(&mut msgid, &mut msgstr, &mut fuzzy);
                target = None;
            }
            fuzzy = flags.split(',').any(|flag| flag.trim() == "fuzzy");
        } else if line.starts_with('#') {
            continue;
        } else if let Some(rest) = line.strip_prefix("msgid ") {
            if target == Some(false) {
                flush(&mut msgid, &mut msgstr, &mut fuzzy);
            }
            msgid = unquote(rest);
            target = Some(true);
        } else if let Some(rest) = line.strip_prefix("msgstr ") {
            msgstr = unquote(rest);
            target = Some(false);
        } else if line.starts_with('"') {
            match target {
                Some(true) => msgid.push_str(&unquote(line)),
                Some(false) => msgstr.push_str(&unquote(line)),
                None => {}
            }
        }
    }
    flush(&mut msgid, &mut msgstr, &mut fuzzy);
    catalog
}

fn unquote(text: &str) -> String {
    let inner = text
        .trim()
        .strip_prefix('"')
        .and_then(|t| t.strip_suffix('"'))
        .unwrap_or(text);
    let mut out = String::with_capacity(inner.len());
    let mut chars = inner.chars();
    while let Some(c) = chars.next() {
        if c != '\\' {
            out.push(c);
            continue;
        }
        match chars.next() {
            Some('n') => out.push('\n'),
            Some('t') => out.push('\t'),
            Some(other) => out.push(other),
            None => out.push('\\'),
        }
    }
    out
}

/// Replaces `{key}` placeholders (Python brace format, as used in the
/// catalogs) with their values.
pub fn format_named(template: &str, args: &[(&str, &str)]) -> String {
    args.iter()
        .fold(template.to_string(), |text, (key, value)| {
            text.replace(&format!("{{{key}}}"), value)
        })
}
