//! Building commands for host programs (terminals, `sh -c`).

/// Quotes `text` for a POSIX shell, like Python's `shlex.quote`.
pub fn quote(text: &str) -> String {
    let safe = !text.is_empty()
        && text
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "@%+=:,./-_".contains(c));
    if safe {
        text.to_string()
    } else {
        format!("'{}'", text.replace('\'', "'\"'\"'"))
    }
}

/// Terminals probed in order by "Open Terminal Here". `xdg-terminal-exec`
/// dispatches to whatever terminal the desktop is configured to use.
pub const TERMINAL_CANDIDATES: [&str; 15] = [
    "xdg-terminal-exec",
    "x-terminal-emulator",
    "gnome-terminal",
    "ptyxis",
    "kgx",
    "konsole",
    "xfce4-terminal",
    "mate-terminal",
    "tilix",
    "terminator",
    "alacritty",
    "kitty",
    "lxterminal",
    "deepin-terminal",
    "xterm",
];

/// Command starting `terminal` in `directory`.
///
/// Most terminals are single-instance apps whose server opens the window in
/// its own working directory, so they get their documented flag rather than
/// a `cd`. `x-terminal-emulator` is a Debian wrapper that only understands
/// xterm options, hence `-e sh -c`. The others (xterm, xdg-terminal-exec…)
/// inherit the working directory through `exec`.
pub fn terminal_argv(terminal: &str, directory: &str) -> Vec<String> {
    let flag: Option<Vec<String>> = match terminal {
        "gnome-terminal" | "ptyxis" | "kgx" | "xfce4-terminal" | "mate-terminal" | "tilix"
        | "terminator" | "lxterminal" => Some(vec![format!("--working-directory={directory}")]),
        "konsole" => Some(vec!["--workdir".into(), directory.into()]),
        "alacritty" => Some(vec!["--working-directory".into(), directory.into()]),
        "kitty" => Some(vec!["--directory".into(), directory.into()]),
        _ => None,
    };
    if let Some(flag) = flag {
        return std::iter::once(terminal.to_string()).chain(flag).collect();
    }
    if terminal == "x-terminal-emulator" {
        let inner = format!("cd {} && exec ${{SHELL:-/bin/sh}}", quote(directory));
        return vec![
            terminal.into(),
            "-e".into(),
            "sh".into(),
            "-c".into(),
            inner,
        ];
    }
    let command = format!("cd {} && exec {}", quote(directory), quote(terminal));
    vec!["sh".into(), "-c".into(), command]
}
