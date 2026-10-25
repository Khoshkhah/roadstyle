//! roadstyle's files, the one copy (docs/design/target_architecture.md, (g)): the look's profiles and palettes, the base map's files,
//! `cmaps.json`, `basemaps.json`, the dashboard's JS and CSS, the popup files, the page templates, the level editor's page and the vendored
//! MapLibre, by their path under `files/` (the paths they had under `src/roadstyle/`).
//!
//! A crate takes a file at compile time: `const CMAPS: &str = roadstyle_assets::text!("data/cmaps.json");` (`bytes!` for a binary
//! file). A wrong name is a compile error, and the binary has only the files that it names. A program that serves or lists the files
//! (the Python binding's `asset`) calls `get` at run time, which builds every file in.
#![no_std]

include!(concat!(env!("OUT_DIR"), "/files.rs"));

const fn eq(a: &str, b: &str) -> bool {
    let (a, b) = (a.as_bytes(), b.as_bytes());
    if a.len() != b.len() {
        return false;
    }
    let mut i = 0;
    while i < a.len() {
        if a[i] != b[i] {
            return false;
        }
        i += 1;
    }
    true
}

/// The bytes of a file, at compile time: `bytes!("data/sprite.png")`. A name that is not a file is a compile error.
#[macro_export]
macro_rules! bytes {
    ($name:literal) => {{
        const B: &[u8] = match $crate::get($name) {
            Some(b) => b,
            None => panic!(concat!("roadstyle-assets has no file ", $name)),
        };
        B
    }};
}

/// The text of a UTF-8 file, at compile time: `text!("data/cmaps.json")`. A name that is not a file, or a file that is not UTF-8, is a
/// compile error.
#[macro_export]
macro_rules! text {
    ($name:literal) => {{
        const T: &str = match core::str::from_utf8($crate::bytes!($name)) {
            Ok(t) => t,
            Err(_) => panic!(concat!("roadstyle-assets: not UTF-8: ", $name)),
        };
        T
    }};
}

#[cfg(test)]
mod tests {
    #[test]
    fn a_name_gives_its_file_and_the_list_has_it() {
        assert!(super::text!("data/cmaps.json").starts_with('{'));
        assert_eq!(&super::bytes!("data/sprite.png")[1..4], b"PNG");
        assert!(super::NAMES.contains(&"static/dashboard/index.js") && super::get("no/such/file").is_none());
        assert_eq!(super::DASHBOARD_JS.len(), super::text!("static/dashboard/files.txt").lines()
            .filter(|l| !l.trim().is_empty() && !l.starts_with('#')).count());
    }
}
