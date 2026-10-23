//! Dupot File Browser, split along clean-architecture lines:
//! - `domain`: pure logic and types (no GTK, no I/O), unit-tested from `tests/`;
//! - `infrastructure`: GTK views, file system, archives, trash and desktop access.

pub mod domain;
pub mod infrastructure;
