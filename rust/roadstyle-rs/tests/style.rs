//! The style must be byte for byte the style of geolibre-roadstyle's Rust port at commit 0806ac2 (its `make_style`, natively, from the
//! same inputs), with nine changes:
//! - the building heights follow rule C (the higher of the height tag and the levels, features.rs), not 0806ac2's rule A (the height
//!   tag first): on 2026-10-23 the `height` of 15 buildings of Monaco and 355 of Tartu;
//! - the slots have Python's key order (__rs_cls before __rs_arw, tests/colors.rs): the same data, other bytes;
//! - design step (g), part 3 (2026-10-23): the export keeps the roads' pick and highlight layers shown (before: hidden when the data was
//!   inline), and its pieces have no page glow (tests/common: as_decided). The tiles are the same (tests/areas.rs, decoded).
//! - 2026-10-24: every style's pieces have their road's row as their feature id (`promoteId: "__rs_edge"` on `simple`, and on the
//!   vector source of the tiled style) and the glow of a selected or hovered road, so a dashboard drives any style, not only a page;
//! - R1 (2026-10-24): a piece keeps only the properties that the road layer and the page read on it (props::piece_reads: the layers on
//!   `simple`, static/dashboard/reads.json's `pieces`), a road only the stage values that a layer reads (its fields stay), in the GeoJSON,
//!   GeoParquet and tiles (tests/common: as_decided);
//! - R8 (2026-10-24): the road layer's class tables are one lookup by each feature's class index (`["at", ["get", "__rs_ci"],
//!   ["literal", [...]]]`; `__rs_ci` the last property of every feature of `simple`; layers::class_index);
//! - N8 (2026-10-24): every style's road layer reads a road's colour and its width factor from the feature state on its row
//!   (`["coalesce", ["feature-state", "rs_c"], fill]`, each width and offset stop × `["coalesce", ["feature-state", "rs_w"], 1]`);
//! - the mapstyle merge (2026-10-24): the background's land is the boundary less the sea (roadstyle-io duckosm::cut_sea, the facade's
//!   read_features), as mapstyle's load_layers makes it; before, the browser's whole boundary. Nothing else: with the cut off, the
//!   hashes of before pass.
//! - 2026-10-24, the tiles: a base-map source of points or polygons goes whole into every tile its box touches, from the first zoom
//!   (tiles.py's extra layers; before, it was clipped, and the sea at Monaco's west edge was missing from 5 tiles).
//!
//! The reference styles are too large for git (Monaco 26 MB, Tartu 151 MB), so the test compares their SHA-256. `tests/old_style.sh`
//! makes 0806ac2's style again, to see a difference.

use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

/// The fixture's look as the GeoLibre plugin draws it: with the names and the arrows. The look's args have arrows and labels false
/// (from mapstyle's keywords), and the engine follows them as Python does; tests/make_goldens.py also sets them true.
fn plugin_look(bytes: &[u8]) -> roadstyle_rs::Look {
    let mut look: serde_json::Value = serde_json::from_slice(bytes).unwrap();
    look["args"]["arrows"] = true.into();
    look["args"]["labels"] = true.into();
    look["args"]["export"] = true.into();        // the plugin's style is an export: the roads source too (audit N2)
    roadstyle_rs::Look::from_value(look).unwrap()
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
    assert_eq!(style_hash(&area), "2bf1199e67ef56de4acf972e7182e0ee80ec445d34a160f15a430965ebcb84bb");
}

/// Tartu's inputs are not in git: get them with `tests/get_goldens.sh`, then `cargo test --release -- --ignored`.
#[test]
#[ignore = "needs tests/get_goldens.sh"]
fn tartu_style() {
    let area = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/tartu");
    assert!(area.join("roads.parquet").exists(), "{}: no Tartu inputs, run tests/get_goldens.sh", area.display());
    assert_eq!(style_hash(&area), "ec21602f3f5d25ed63b7405a5eddea92381ad9239460ca9364ff42a9168c5c71");
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
    let (style, tiles, _) = roadstyle_rs::make_tiled(roads, &look, Some(read(area.join("features.parquet"))), None, "rs://", &keep).unwrap();
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
    assert_eq!(tiles_hash(&area), "e33584163186f97e226f7e120ec4a6ac9eab146ecefb08655faf0ceb0d23e9f1");
}

/// tiles.py's extra layers: the sea of Monaco (a polygon) is in the tiles at its west edge, where only its box reaches.
#[test]
fn the_sea_at_the_tile_edge() {
    let data = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data");
    let read = |p: PathBuf| std::fs::read(&p).unwrap();
    let mut look: serde_json::Value = serde_json::from_slice(&read(data.join("look.json"))).unwrap();
    look["args"]["export"] = true.into();
    let look = roadstyle_rs::Look::from_value(look).unwrap();
    let (_, tiles, _) = roadstyle_rs::make_tiled(read(data.join("monaco/roads.parquet")), &look, Some(read(data.join("monaco/features.parquet"))),
                                                 None, "rs://", &[]).unwrap();
    for (z, x, y) in [(14, 8528, 5973), (14, 8528, 5974), (15, 17057, 11946), (15, 17057, 11947), (15, 17057, 11948)] {
        let t = tiles.tile(z, x, y);
        assert!(!t.is_empty() && t.windows(3).any(|w| w == b"ov1"), "{z}/{x}/{y}: no sea");
    }
}

#[test]
#[ignore = "needs tests/get_goldens.sh"]
fn tartu_tiles() {
    let area = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/tartu");
    assert!(area.join("roads.parquet").exists(), "{}: no Tartu inputs, run tests/get_goldens.sh", area.display());
    assert_eq!(tiles_hash(&area), "1b72c9eeeb2b549ae58711b7556ac4f1fcdbc486e0ec1f2733fe35518e38dca1");
}
