//! The style must be byte for byte the style of geolibre-roadstyle's Rust port at commit 0806ac2 (its `make_style`, natively, from the
//! same inputs), with two changes:
//! - the building heights follow rule C (the higher of the height tag and the levels, features.rs), not 0806ac2's rule A (the height
//!   tag first): on 2026-10-23 the `height` of 15 buildings of Monaco and 355 of Tartu;
//! - the slots have Python's key order (__rs_cls before __rs_arw, tests/colors.rs): the same data, other bytes.
//!
//! The reference styles are too large for git (Monaco 26 MB, Tartu 151 MB), so the test compares their SHA-256. `tests/old_style.sh`
//! makes 0806ac2's style again, to see a difference.

use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

/// The fixture's look as the GeoLibre plugin draws it: with the names and the arrows. The look's args have arrows and labels false
/// (from mapstyle's keywords), and the engine follows them as Python does; tests/make_goldens.py also sets them true.
fn plugin_look(bytes: &[u8]) -> String {
    let mut look: serde_json::Value = serde_json::from_slice(bytes).unwrap();
    look["args"]["arrows"] = true.into();
    look["args"]["labels"] = true.into();
    look.to_string()
}

fn style_hash(area: &Path) -> String {
    let data = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data");
    let read = |p: PathBuf| std::fs::read(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    let look = plugin_look(&read(data.join("look.json")));
    let style = roadstyle_rs::make_style(read(area.join("roads.parquet")), &look, Some(read(area.join("features.parquet"))), None, None).unwrap();
    Sha256::digest(style.as_bytes()).iter().map(|b| format!("{b:02x}")).collect()
}

#[test]
fn monaco_style() {
    let area = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/monaco");
    assert_eq!(style_hash(&area), "abca96d8f217e49df8d6fc1aedf92413f561d70a98790c6aa843073b952db760");
}

/// Tartu's inputs are not in git: get them with `tests/get_goldens.sh`, then `cargo test --release -- --ignored`.
#[test]
#[ignore = "needs tests/get_goldens.sh"]
fn tartu_style() {
    let area = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/tartu");
    assert!(area.join("roads.parquet").exists(), "{}: no Tartu inputs, run tests/get_goldens.sh", area.display());
    assert_eq!(style_hash(&area), "afb6db082d50ac2f1d5688dce29d9532abdb6c9a70c001399e6c8d9b9ae70833");
}

/// The vector tiles (make_tiled): the SHA-256 of the style and of every tile of the roads' box at zooms 12, 14 and 15 (each tile with
/// its zoom, x and y), so a change in the memory use cannot change a tile. The tiles follow tiles.py; tests/areas.rs compares them
/// with Python's (P0: the tile range, the ids and the properties changed to tiles.py's rules on 2026-10-23).
fn tiles_hash(area: &Path) -> String {
    let data = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data");
    let read = |p: PathBuf| std::fs::read(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    let look = plugin_look(&read(data.join("look.json")));
    let roads = read(area.join("roads.parquet"));
    let (mut x0, mut y0, mut x1, mut y1) = (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY);
    let t = roadstyle_rs::read::read_roads(roads.clone(), "geometry").unwrap();
    for c in (0..t.len()).filter_map(|i| t.line(i)).flatten() {
        (x0, y0, x1, y1) = (x0.min(c[0]), y0.min(c[1]), x1.max(c[0]), y1.max(c[1]));
    }
    let keep = ["osm_id".to_string(), "access".to_string()];
    let (style, tiles) = roadstyle_rs::make_tiled(roads, &look, Some(read(area.join("features.parquet"))), None, "rs://", &keep).unwrap();
    let mut h = Sha256::new();
    h.update(style.as_bytes());
    for z in [12u32, 14, 15] {
        let n = (1u64 << z) as f64;
        let tx = |lon: f64| ((lon + 180.0) / 360.0 * n) as u32;
        let ty = |lat: f64| ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n) as u32;
        for x in tx(x0)..=tx(x1) {
            for y in ty(y1)..=ty(y0) {
                let t = tiles.tile(z, x, y);
                if !t.is_empty() {
                    h.update(format!("{z}/{x}/{y}:{}:", t.len()).as_bytes());
                    h.update(&t);
                }
            }
        }
    }
    h.finalize().iter().map(|b| format!("{b:02x}")).collect()
}

#[test]
fn monaco_tiles() {
    let area = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/monaco");
    assert_eq!(tiles_hash(&area), "2c24d3b5cbb50dab3aa8e5ac9bcf10a24af8dbc1cd5280222d4aca180373917e");
}

#[test]
#[ignore = "needs tests/get_goldens.sh"]
fn tartu_tiles() {
    let area = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/tartu");
    assert!(area.join("roads.parquet").exists(), "{}: no Tartu inputs, run tests/get_goldens.sh", area.display());
    assert_eq!(tiles_hash(&area), "c7ec0b3714a9a8508970fe7326c029dcce58ebc632997ab0b5ce7192d1201d4e");
}
