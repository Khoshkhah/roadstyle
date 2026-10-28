//! render_map's `interaction` (the map option `{layer: {clickable, tooltip, popup}}`): a base-map layer's start values in its entry of
//! roadstyle:controls.overlays, which the dashboard reads (`interactive`, `tooltip`, `popup_window`), on Monaco's base map. A layer that
//! the map does not have is a warning; with no `interaction`, an entry is mapstyle's start (landcover: not clickable, no tooltip, popup).

use serde_json::{json, Value};
use std::path::PathBuf;

fn data(p: &str) -> Vec<u8> {
    std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)).unwrap()
}

/// The landcover entry of the style made with `interaction`, and the warnings.
fn landcover(interaction: Value) -> (Value, Vec<String>) {
    let mut look: Value = serde_json::from_slice(&data("look.json")).unwrap();
    look["args"]["state"] = "live".into();
    look["args"]["interaction"] = interaction;
    let look = roadstyle_rs::Look::from_value(look).unwrap();
    let s = roadstyle_rs::style_sources(data("monaco/roads.parquet"), &look, Some(data("monaco/features.parquet")), None, None).unwrap();
    let ovs = s.metadata["roadstyle:controls"]["overlays"].as_array().unwrap();
    (ovs.iter().find(|o| o["label"] == "landcover").unwrap().clone(), s.warnings)
}

#[test]
fn interaction_sets_a_layers_start_values() {
    let (start, w) = landcover(Value::Null);
    assert_eq!((&start["interactive"], &start["tooltip"], &start["popup_window"]), (&json!(false), &Value::Null, &json!(true)));
    assert!(w.iter().all(|w| !w.starts_with("interaction")));
    let (on, w) = landcover(json!({"landcover": {"clickable": true, "tooltip": true, "popup": false}, "nolayer": {}}));
    assert_eq!((&on["interactive"], &on["tooltip"], &on["popup_window"]), (&json!(true), &json!(true), &json!(false)));
    assert!(w.contains(&"interaction: no layer nolayer on this map".to_string()), "{w:?}");
}

/// A base-map layer with a 3D layer names it in its entry (`extrude`): the dashboard's 3D button finds it there, as a page's layers have no
/// metadata. Monaco's buildings.
#[test]
fn the_buildings_entry_names_its_3d_layer() {
    let mut look: Value = serde_json::from_slice(&data("look.json")).unwrap();
    look["args"]["state"] = "live".into();
    let look = roadstyle_rs::Look::from_value(look).unwrap();
    let s = roadstyle_rs::style_sources(data("monaco/roads.parquet"), &look, Some(data("monaco/features.parquet")), None, None).unwrap();
    let ovs = s.metadata["roadstyle:controls"]["overlays"].as_array().unwrap();
    let with: Vec<&Value> = ovs.iter().filter(|o| o.get("extrude").is_some()).collect();
    assert_eq!(with.len(), 1, "only the buildings have heights");
    let id = with[0]["extrude"].as_str().unwrap();
    assert_eq!(with[0]["label"], "buildings");
    assert!(s.layers.iter().any(|l| l["id"] == id && l["type"] == "fill-extrusion"), "{id}: no such 3D layer");
}
