//! Unit tests, laid out as a mirror of `src/`: the tests for
//! `src/<path>.rs` live in `tests/<path>.rs`. A single entry point keeps it
//! to one test binary. `tests/export/` checks the packaging files of
//! `export/` against what the app expects in each launch mode.

mod domain;
mod export;
mod infrastructure;
