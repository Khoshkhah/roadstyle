//! The popup fields of an overlay are not in its tiles: each feature has its row as the id, and a props file holds the fields by row
//! (docs/design/tile_v2_plan.md, "the base map has the same mechanism as the roads").

mod common;

use serde_json::{json, Value};
use std::path::PathBuf;

#[test]
fn an_overlay_with_popup_fields_has_them_in_a_props_file_by_row() {
    let data = |p: &str| std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)).unwrap();
    let mut look: Value = serde_json::from_slice(&data("look.json")).unwrap();
    let point = |name: &str, lon: f64| json!({"type": "Feature", "properties": {"name": name, "n": 1}, "geometry": {"type": "Point", "coordinates": [lon, 43.7387]}});
    let fc = json!({"type": "FeatureCollection", "features": [point("A", 7.4235), point("B", 7.4236)]});
    look["args"]["overlays"] = json!([{"fc": fc, "label": "pois", "popup": ["name"]}]);
    let look = roadstyle_rs::Look::from_value(look).unwrap();
    let (_, tiles, _) = roadstyle_rs::tiled_from_parquet(data("monaco/roads.parquet"), &look, None, None, "rs://", &[]).unwrap();
    let [(layer, text)] = tiles.props_files.as_slice() else { panic!("one props file: {:?}", tiles.props_files) };
    assert_eq!(serde_json::from_str::<Value>(text).unwrap(), json!([{"name": "A"}, {"name": "B"}]), "the fields by row");
    let n = (1u64 << 15) as f64;
    let (x, y) = (((7.4235 + 180.0) / 360.0 * n) as u32, ((1.0 - 43.7387f64.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n) as u32);
    let t = common::decode_tile(&tiles.tile(15, x, y));
    let feats = &t[layer.as_str()];
    assert_eq!(feats.iter().map(|f| f.0).collect::<Vec<_>>(), [Some(0), Some(1)], "the row is the id");
    assert!(feats.iter().all(|f| !f.1.contains_key("name") && !f.1.contains_key("n")), "no popup field in the tile: {:?}", feats[0].1);
}
