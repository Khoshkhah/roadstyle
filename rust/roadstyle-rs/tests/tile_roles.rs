//! A tile holds facts, not the colours of a look (docs/design/restyle_without_retile.md, D1): a colour reaches a piece by its role (its
//! class, its access kind, its colour option), and the style holds the table from a role to a colour. So a look that changes only colours
//! makes the same tile bytes. On a part of Monaco, with the options of the duckOSM page (a colour option by class, the access column) and
//! without them, the tiles of every bundled palette and of an own palette in which two classes have one colour are compared byte by byte.

mod common;

use serde_json::{json, Value};
use std::path::PathBuf;

fn data(p: &str) -> Vec<u8> {
    std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)).unwrap()
}

/// An own palette over amber in which secondary has primary's fill and tertiary has residential's casing: the colours that were distinct
/// are equal, which moves every later place of a table of distinct colours.
const SAME_TWO: &str = "classes:\n  secondary: {fill: \"#f4c542\"}\n  tertiary: {casing: \"#bcbcbc\", fill: \"#f4c542\"}\n";

/// An own palette over amber with other access colours (the bundled palettes have the same ones).
const ACCESS_RED: &str = "access: {private: \"#ff0000\", bus: \"#00ff00\", pedestrian: \"#0000ff\", delivery: \"#ff00ff\"}\n";

fn look(palette: &str, args: &Value) -> roadstyle_rs::Look {
    roadstyle_rs::Look::resolve(&roadstyle_rs::look::Options::from_value(
        &json!({"palette": palette, "args": args, "files": {"palettes": {"same_two": SAME_TWO, "access_red": ACCESS_RED}}})).unwrap()).unwrap()
}

/// Every tile of the roads at the zooms 12 to 16, as (z, x, y, bytes).
fn tiles(palette: &str, args: &Value) -> Vec<(u32, u32, u32, Vec<u8>)> {
    let roads = data("monaco_part/roads.parquet");
    let t = roadstyle_rs::read::read_roads(roads.clone(), "geometry").unwrap();
    let (mut x0, mut y0, mut x1, mut y1) = (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY);
    for c in (0..t.len()).filter_map(|i| t.line(i)).flatten() {
        (x0, y0, x1, y1) = (x0.min(c[0]), y0.min(c[1]), x1.max(c[0]), y1.max(c[1]));
    }
    let (_, made, _) = roadstyle_rs::tiled_from_parquet(roads, &look(palette, args), None, None, "rs://", &[]).unwrap();
    let mut out = Vec::new();
    for z in 12..=16u32 {
        let n = (1u64 << z) as f64;
        let tx = |lon: f64| ((lon + 180.0) / 360.0 * n) as u32;
        let ty = |lat: f64| ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n) as u32;
        for x in tx(x0)..=tx(x1) {
            for y in ty(y1)..=ty(y0) {
                out.push((z, x, y, made.tile(z, x, y)));
            }
        }
    }
    out
}

fn same_tiles(args: Value) {
    let base = tiles("amber", &args);
    assert!(base.iter().any(|t| !t.3.is_empty()), "the roads make tiles");
    for palette in ["carto", "highsat", "mono", "same_two", "access_red"] {
        let other = tiles(palette, &args);
        assert_eq!(base.len(), other.len());
        let differ: Vec<String> = base.iter().zip(&other).filter(|(a, b)| a.3 != b.3).map(|(a, _)| format!("{}/{}/{}", a.0, a.1, a.2)).collect();
        assert!(differ.is_empty(), "{args}: palette {palette} changes {} of {} tiles, as {}", differ.len(), base.len(),
                differ.iter().take(4).cloned().collect::<Vec<_>>().join(", "));
    }
}

/// The class colours, no option: the class-only path.
#[test]
fn class_colours_make_the_same_tiles() {
    same_tiles(json!({}));
}

/// The duckOSM page's options: one colour option by class, and the access column.
#[test]
fn a_class_option_and_the_access_column_make_the_same_tiles() {
    same_tiles(json!({"color_options": {"Road class": {}}, "access_col": "access"}));
}

/// The access column alone: a private road has the palette's access colour.
#[test]
fn the_access_column_makes_the_same_tiles() {
    same_tiles(json!({"access_col": "access"}));
}
