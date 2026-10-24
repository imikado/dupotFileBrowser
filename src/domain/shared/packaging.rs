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
}
