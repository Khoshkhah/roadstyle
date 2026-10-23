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

/// The vector tiles (make_tiled): the SHA-256 of the style and of every tile of the roads' box at zooms 12, 14 and 16 (each tile with
/// its source, zoom, x and y), so a change in the memory use cannot change a tile.
fn tiles_hash(area: &Path) -> String {
    let data = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data");
    let read = |p: PathBuf| std::fs::read(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    let look = String::from_utf8(read(data.join("look.json"))).unwrap();
    let roads = read(area.join("roads.parquet"));
    let (mut x0, mut y0, mut x1, mut y1) = (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY);
    for c in roadstyle_rs::read::read_roads(roads.clone(), "geometry").unwrap().iter().filter_map(|f| f.coords.as_ref()).flatten() {
        (x0, y0, x1, y1) = (x0.min(c[0]), y0.min(c[1]), x1.max(c[0]), y1.max(c[1]));
    }
    let keep = ["osm_id".to_string(), "access".to_string()];
    let (style, tiles) = roadstyle_rs::make_tiled(roads, &look, Some(read(area.join("features.parquet"))), None, "rs://", &keep).unwrap();
    let sources: Vec<String> = serde_json::from_str::<serde_json::Value>(&style).unwrap()["sources"].as_object().unwrap().keys().cloned().collect();
    let mut h = Sha256::new();
    h.update(style.as_bytes());
    for z in [12u32, 14, 16] {
        let n = (1u64 << z) as f64;
        let tx = |lon: f64| ((lon + 180.0) / 360.0 * n) as u32;
        let ty = |lat: f64| ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n) as u32;
        for s in &sources {
            for x in tx(x0)..=tx(x1) {
                for y in ty(y1)..=ty(y0) {
                    let t = tiles.tile(s, z, x, y);
                    if !t.is_empty() {
                        h.update(format!("{s}/{z}/{x}/{y}:{}:", t.len()).as_bytes());
                        h.update(&t);
                    }
                }
            }
        }
    }
    h.finalize().iter().map(|b| format!("{b:02x}")).collect()
}

#[test]
fn monaco_tiles() {
    let area = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/monaco");
    assert_eq!(tiles_hash(&area), "e55082e48e667ef0ecb253384f40aef0ff954646071245c82903c3de9d4b676b");
}

#[test]
#[ignore = "needs tests/get_tartu.sh"]
fn tartu_tiles() {
    let area = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/tartu");
    assert!(area.join("roads.parquet").exists(), "{}: no Tartu inputs, run tests/get_tartu.sh", area.display());
    assert_eq!(tiles_hash(&area), "bc8359d0e0dfbb364d9569f882482e2a000c10561c30c5ff2ab381331df94624");
}
