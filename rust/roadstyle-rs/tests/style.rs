//! The style must be byte for byte the style of geolibre-roadstyle's Rust port at commit 0806ac2 (its `make_style`, natively, from the
//! same inputs), with one change: the building heights follow rule C (the higher of the height tag and the levels, features.rs), not
//! 0806ac2's rule A (the height tag first). On 2026-10-23 the only differences from 0806ac2's style were the `height` of 15 buildings
//! of Monaco and 355 of Tartu. The reference styles are too large for git (Monaco 26 MB, Tartu 151 MB), so the test compares their
//! SHA-256. `tests/old_style.sh` makes 0806ac2's style again, to see a difference.

use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

fn style_hash(area: &Path) -> String {
    let data = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data");
    let read = |p: PathBuf| std::fs::read(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    let look = String::from_utf8(read(data.join("look.json"))).unwrap();
    let style = roadstyle_rs::make_style(read(area.join("roads.parquet")), &look, Some(read(area.join("features.parquet"))), None, None).unwrap();
    Sha256::digest(style.as_bytes()).iter().map(|b| format!("{b:02x}")).collect()
}

#[test]
fn monaco_style() {
    let area = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/monaco");
    assert_eq!(style_hash(&area), "814e09f47893b22038c45f60d0cdfc2bb587aa47f056651cf924f11c0ed218be");
}

/// Tartu's inputs (9.5 MB) are not in git: get them with `tests/get_tartu.sh`, then `cargo test --release -- --ignored`.
#[test]
#[ignore = "needs tests/get_tartu.sh"]
fn tartu_style() {
    let area = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/tartu");
    assert!(area.join("roads.parquet").exists(), "{}: no Tartu inputs, run tests/get_tartu.sh", area.display());
    assert_eq!(style_hash(&area), "3b35e26702d42e4b18167f249d85cd7012f6aac70324ffb53fc2353548b69d85");
}
