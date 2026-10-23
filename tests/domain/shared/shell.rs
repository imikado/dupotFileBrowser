use dupot_file_browser::domain::shared::shell::{quote, terminal_argv};

#[test]
fn quoting_like_shlex() {
    assert_eq!(quote("/home/me"), "/home/me");
    assert_eq!(quote("my dir"), "'my dir'");
    assert_eq!(quote("it's"), "'it'\"'\"'s'");
    assert_eq!(quote(""), "''");
}

#[test]
fn terminals_get_their_own_flag() {
    assert_eq!(
        terminal_argv("gnome-terminal", "/tmp"),
        ["gnome-terminal", "--working-directory=/tmp"]
    );
    assert_eq!(
        terminal_argv("konsole", "/tmp"),
        ["konsole", "--workdir", "/tmp"]
    );
    assert_eq!(
        terminal_argv("kitty", "/tmp"),
        ["kitty", "--directory", "/tmp"]
    );
}

#[test]
fn others_inherit_the_working_directory() {
    assert_eq!(
        terminal_argv("xterm", "/my dir"),
        ["sh", "-c", "cd '/my dir' && exec xterm"]
    );
    assert_eq!(
        terminal_argv("x-terminal-emulator", "/tmp"),
        [
            "x-terminal-emulator",
            "-e",
            "sh",
            "-c",
            "cd /tmp && exec ${SHELL:-/bin/sh}"
        ]
    );
}
