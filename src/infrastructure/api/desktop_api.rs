//! Desktop integration: default applications through GIO / the desktop
//! portal, and host programs for terminals and wallpapers.

use std::path::Path;

use gtk::gio;
use gtk::gio::prelude::*;
use gtk::glib;

use crate::domain::contract::desktop_repository::DesktopRepository;
use crate::domain::error::{DomainError, DomainResult};
use crate::domain::shared::path::parent_dir;
use crate::domain::shared::shell::{TERMINAL_CANDIDATES, terminal_argv};
use crate::infrastructure::service::host_command_service::{
    self, command_exists, run, run_capture,
};

#[derive(Clone, Copy, Debug, Default)]
pub struct DesktopApi;

fn args(items: &[&str]) -> Vec<String> {
    items.iter().map(|item| item.to_string()).collect()
}

/// Sets `schema`'s picture-uri: a non-zero exit means this desktop doesn't
/// have the schema. The dark variant only exists on recent versions.
fn set_gsettings_wallpaper(schema: &str, uri: &str) -> bool {
    if !run(&args(&["gsettings", "set", schema, "picture-uri", uri])) {
        return false;
    }
    run(&args(&[
        "gsettings",
        "set",
        schema,
        "picture-uri-dark",
        uri,
    ]));
    true
}

/// XFCE stores one backdrop per monitor and workspace: every property
/// ending in `last-image` is set.
fn set_xfce_wallpaper(path: &str) -> bool {
    if !command_exists("xfconf-query") {
        return false;
    }
    let Ok(listing) = run_capture(
        &args(&["xfconf-query", "-c", "xfce4-desktop", "-l"]),
        std::time::Duration::from_secs(5),
    ) else {
        return false;
    };
    listing
        .lines()
        .map(str::trim)
        .filter(|property| property.ends_with("last-image"))
        .map(|property| {
            run(&args(&[
                "xfconf-query",
                "-c",
                "xfce4-desktop",
                "-p",
                property,
                "-s",
                path,
            ]))
        })
        .filter(|done| *done)
        .count()
        > 0
}

impl DesktopRepository for DesktopApi {
    fn is_sandboxed(&self) -> bool {
        host_command_service::is_sandboxed()
    }

    fn open_path(&self, path: &Path) -> DomainResult<()> {
        let uri = gio::File::for_path(path).uri();
        gio::AppInfo::launch_default_for_uri(&uri, gio::AppLaunchContext::NONE)?;
        Ok(())
    }

    /// GIO cannot list host applications from inside the sandbox; the
    /// portal's chooser runs outside it. `OpenFile` takes a file descriptor,
    /// so the portal can read the file whatever our view of the file system.
    fn open_with_chooser(&self, path: &Path) -> DomainResult<()> {
        let file = std::fs::File::open(path)?;
        let fd_list = gio::UnixFDList::new();
        let index = fd_list.append(&file)?;
        let options = glib::VariantDict::new(None);
        options.insert("ask", true);
        let parameters = glib::Variant::tuple_from_iter([
            "".to_variant(),
            glib::variant::Handle(index).to_variant(),
            options.end(),
        ]);
        let bus = gio::bus_get_sync(gio::BusType::Session, gio::Cancellable::NONE)?;
        bus.call_with_unix_fd_list_sync(
            Some("org.freedesktop.portal.Desktop"),
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.OpenURI",
            "OpenFile",
            Some(&parameters),
            glib::VariantTy::new("(o)").ok(),
            gio::DBusCallFlags::NONE,
            -1,
            Some(&fd_list),
            gio::Cancellable::NONE,
        )
        .map_err(|e| DomainError::new(e.to_string()))?;
        Ok(())
    }

    fn open_terminal(&self, path: &Path) -> bool {
        let directory = if path.is_dir() {
            path.to_path_buf()
        } else {
            parent_dir(path)
        };
        if !directory.is_dir() {
            return false;
        }
        let directory = directory.to_string_lossy();
        TERMINAL_CANDIDATES
            .into_iter()
            .filter(|terminal| command_exists(terminal))
            .any(|terminal| host_command_service::spawn(&terminal_argv(terminal, &directory)))
    }

    /// No portal sets the wallpaper: desktop-specific setters are tried in
    /// turn (GNOME, Cinnamon, MATE, KDE, XFCE, then feh).
    fn set_wallpaper(&self, path: &Path) -> bool {
        let uri = gio::File::for_path(path).uri().to_string();
        let path = path.to_string_lossy().into_owned();
        let setters: [&dyn Fn() -> bool; 6] = [
            &|| set_gsettings_wallpaper("org.gnome.desktop.background", &uri),
            &|| set_gsettings_wallpaper("org.cinnamon.desktop.background", &uri),
            &|| {
                run(&args(&[
                    "gsettings",
                    "set",
                    "org.mate.background",
                    "picture-filename",
                    &path,
                ]))
            },
            &|| {
                command_exists("plasma-apply-wallpaperimage")
                    && run(&args(&["plasma-apply-wallpaperimage", &path]))
            },
            &|| set_xfce_wallpaper(&path),
            &|| command_exists("feh") && run(&args(&["feh", "--bg-fill", &path])),
        ];
        setters.iter().any(|setter| setter())
    }
}
