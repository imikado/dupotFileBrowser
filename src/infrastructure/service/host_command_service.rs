//! Runs host programs (terminals, wallpaper setters, RAR tools). Inside the
//! Flatpak sandbox they go through `flatpak-spawn --host`, since none of
//! them is part of the GNOME runtime.

use std::io::Read;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use crate::domain::shared::packaging::Packaging;
use crate::domain::shared::shell::quote;
use crate::infrastructure::service::packaging_service;

const PROBE_TIMEOUT: Duration = Duration::from_secs(5);

fn host_command(argv: &[String]) -> Command {
    let mut full: Vec<String> = Vec::new();
    if packaging_service::current() == Packaging::Flatpak {
        full.extend(["flatpak-spawn".into(), "--host".into()]);
    }
    full.extend(argv.iter().cloned());
    let mut command = Command::new(&full[0]);
    command.args(&full[1..]);
    command
}

/// Whether `binary` is on the host's PATH.
pub fn command_exists(binary: &str) -> bool {
    run(&[
        "sh".into(),
        "-c".into(),
        format!("command -v {}", quote(binary)),
    ])
}

/// Runs a short-lived command; `true` if it exited successfully.
pub fn run(argv: &[String]) -> bool {
    run_capture(argv, PROBE_TIMEOUT).is_ok()
}

/// Runs a command to completion: its stdout, or why it failed (stderr,
/// stdout or exit code).
pub fn run_capture(argv: &[String], timeout: Duration) -> Result<String, String> {
    let mut child = host_command(argv)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;
    let stdout = child.stdout.take().map(read_in_background);
    let stderr = child.stderr.take().map(read_in_background);

    let deadline = Instant::now() + timeout;
    let status = loop {
        match child.try_wait().map_err(|e| e.to_string())? {
            Some(status) => break status,
            None if Instant::now() >= deadline => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(format!("timed out after {}s", timeout.as_secs()));
            }
            None => std::thread::sleep(Duration::from_millis(20)),
        }
    };
    let collect = |handle: Option<std::thread::JoinHandle<String>>| {
        handle.and_then(|h| h.join().ok()).unwrap_or_default()
    };
    let (out, err) = (collect(stdout), collect(stderr));
    if status.success() {
        return Ok(out);
    }
    let message = [err.trim(), out.trim()]
        .into_iter()
        .find(|text| !text.is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| format!("exit code {}", status.code().unwrap_or(-1)));
    Err(message)
}

fn read_in_background(mut pipe: impl Read + Send + 'static) -> std::thread::JoinHandle<String> {
    std::thread::spawn(move || {
        let mut text = String::new();
        let _ = pipe.read_to_string(&mut text);
        text
    })
}

/// Starts a long-running program without waiting for it.
pub fn spawn(argv: &[String]) -> bool {
    match host_command(argv)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(mut child) => {
            std::thread::spawn(move || child.wait());
            true
        }
        Err(_) => false,
    }
}
