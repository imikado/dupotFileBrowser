//! How the app was installed, given at launch by `--packaging=<id>` (the
//! Flatpak and Snap launchers pass it; a native install passes nothing).

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Packaging {
    Flatpak,
    Snap,
    #[default]
    Native,
}

impl Packaging {
    pub const ALL: [Packaging; 3] = [Packaging::Flatpak, Packaging::Snap, Packaging::Native];

    /// Value of the `--packaging` option.
    pub fn id(self) -> &'static str {
        match self {
            Packaging::Flatpak => "flatpak",
            Packaging::Snap => "snap",
            Packaging::Native => "native",
        }
    }

    pub fn from_id(id: &str) -> Option<Self> {
        Self::ALL.into_iter().find(|packaging| packaging.id() == id)
    }

    /// Confined: GIO can't see the host's applications, the desktop portal
    /// has to be used instead.
    pub fn is_sandboxed(self) -> bool {
        self != Packaging::Native
    }

    /// Variable holding the user's home: in a snap, `$HOME` is the snap's
    /// private folder (`~/snap/<name>/<revision>`).
    pub fn home_variable(self) -> &'static str {
        match self {
            Packaging::Snap => "SNAP_REAL_HOME",
            Packaging::Flatpak | Packaging::Native => "HOME",
        }
    }

    /// Prepended to host commands: Flatpak's runtime doesn't ship them.
    pub fn host_command_prefix(self) -> &'static [&'static str] {
        match self {
            Packaging::Flatpak => &["flatpak-spawn", "--host"],
            Packaging::Snap | Packaging::Native => &[],
        }
    }

    /// `argv` as run on the host.
    pub fn host_argv(self, argv: &[String]) -> Vec<String> {
        self.host_command_prefix()
            .iter()
            .map(|arg| arg.to_string())
            .chain(argv.iter().cloned())
            .collect()
    }

    /// The host's own system folders, mounted by the sandbox.
    pub fn host_system_dirs(self) -> &'static [&'static str] {
        match self {
            Packaging::Flatpak => &["/run/host/etc", "/run/host/usr"],
            Packaging::Snap | Packaging::Native => &[],
        }
    }
}
