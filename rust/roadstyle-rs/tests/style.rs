//! The style must be byte for byte the style of geolibre-roadstyle's Rust port at commit eea9f49 (its `make_style`, natively, from the
//! same inputs). The reference styles are too large for git (Monaco 26 MB, Tartu 151 MB), so the test compares their SHA-256.
//! `tests/old_style.sh` makes a reference style again, to see a difference.

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
fn monaco_style_equals_eea9f49() {
    let area = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/monaco");
    assert_eq!(style_hash(&area), "73866c91712a646256eadfc787817cfc97ae8d41e0a58ee9fc258491741b3c97");
}

/// Tartu's inputs (9.5 MB) are not in git: `ROADSTYLE_RS_TARTU=<folder with roads.parquet and features.parquet> cargo test --release -- --ignored`.
#[test]
#[ignore = "needs ROADSTYLE_RS_TARTU"]
fn tartu_style_equals_eea9f49() {
    let area = std::env::var("ROADSTYLE_RS_TARTU").expect("ROADSTYLE_RS_TARTU: the folder of Tartu's roads.parquet and features.parquet");
    assert_eq!(style_hash(Path::new(&area)), "7e75de83bf43e83b557694706297d9c4ba6342af3ad9aefbf4f06cd1c9d8a0c4");
}
