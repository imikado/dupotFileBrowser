"""The app's version, shown in the "About" dialog (see app_window.py).

Kept in its own module — not just a constant in app_window.py — so that
bumping it (see ../../../update_version.py, which keeps this in sync with
export/flatpak/org.dupot.filebrowser.appdata.xml's <release> of record)
never has to touch app_window.py itself."""

APP_VERSION = "1.0.24"
