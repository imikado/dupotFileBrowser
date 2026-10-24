//! The packaging given by `--packaging` at launch, readable from anywhere.

use std::sync::OnceLock;

use crate::domain::shared::packaging::Packaging;

static PACKAGING: OnceLock<Packaging> = OnceLock::new();

/// Read once at launch, before any window exists; later calls are ignored.
pub fn init(packaging: Packaging) {
    let _ = PACKAGING.set(packaging);
}

/// `Native` when the option wasn't given.
pub fn current() -> Packaging {
    PACKAGING.get().copied().unwrap_or_default()
}
