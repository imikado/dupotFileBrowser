//! Unix permission bits, as edited by the Properties dialog.

/// (read, write, execute) bits for owner, group and others.
pub const WHO_CLASSES: [[u32; 3]; 3] = [
    [0o400, 0o200, 0o100],
    [0o040, 0o020, 0o010],
    [0o004, 0o002, 0o001],
];

/// `drwxr-xr-x (755)`.
pub fn mode_to_symbolic(mode: u32, is_dir: bool) -> String {
    let mut text = String::from(if is_dir { "d" } else { "-" });
    for bits in WHO_CLASSES {
        for (bit, letter) in bits.into_iter().zip(['r', 'w', 'x']) {
            text.push(if mode & bit != 0 { letter } else { '-' });
        }
    }
    format!("{text} ({:03o})", mode & 0o777)
}

/// Mode from a 3x3 grid of checkboxes laid out like `WHO_CLASSES`.
pub fn mode_from_flags(flags: [[bool; 3]; 3]) -> u32 {
    WHO_CLASSES
        .iter()
        .flatten()
        .zip(flags.iter().flatten())
        .filter(|(_, set)| **set)
        .fold(0, |mode, (bit, _)| mode | bit)
}
