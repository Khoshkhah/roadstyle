//! The road layer `roads-simple` of a Monaco style (docs/design/tile_speed.md, "The road layer in MapLibre"): what its style keeps
//! for the speed of MapLibre's tile build.

use serde_json::Value;
use std::path::PathBuf;

fn data(p: &str) -> Vec<u8> {
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p);
    std::fs::read(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

/// The style of Monaco with the fixture's look and these args.
fn style(args: &[(&str, Value)]) -> Value {
    let mut look: Value = serde_json::from_slice(&data("look.json")).unwrap();
    for (k, v) in args {
        look["args"][*k] = v.clone();
    }
    let look = roadstyle_rs::Look::from_value(look).unwrap();
    serde_json::from_str(&roadstyle_rs::inline_style(data("monaco/roads.parquet"), &look, Some(data("monaco/features.parquet")), None, None).unwrap()).unwrap()
}

fn road_layers(style: &Value) -> Vec<&Value> {
    style["layers"].as_array().unwrap().iter().filter(|l| l["id"].as_str().unwrap().starts_with("roads-simple")).collect()
}

/// 2j: the road layer is one layer for each band of zooms (below z14, z14 to z15, from z15). The first has the id `roads-simple`, and a
/// road is picked on every band.
#[test]
fn the_road_layer_has_a_layer_for_each_band_of_zooms() {
    let s = style(&[("state", "live".into())]);
    let bands = road_layers(&s);
    let zooms: Vec<(&str, Option<f64>, Option<f64>)> = bands.iter().map(|l| (l["id"].as_str().unwrap(), l["minzoom"].as_f64(), l["maxzoom"].as_f64())).collect();
    assert_eq!(zooms, [("roads-simple", None, Some(14.0)), ("roads-simple-z14", Some(14.0), Some(15.0)), ("roads-simple-z15", Some(15.0), None)]);
    let pick: Vec<&str> = s["metadata"]["roadstyle:controls"]["pick"].as_array().unwrap().iter().map(|v| v.as_str().unwrap()).collect();
    assert_eq!(pick, ["roads-simple", "roads-simple-z14", "roads-simple-z15"]);
    // below z14 the offset and the blur are constants; from z15 they are zoom curves
    assert_eq!((&bands[0]["paint"]["line-offset"], &bands[0]["paint"]["line-blur"]), (&Value::from(0), &Value::from(0)));
    assert!(bands[2]["paint"]["line-offset"].is_array() && bands[2]["paint"]["line-blur"].is_array());
    // every band keeps the sort key
    assert!(bands.iter().all(|l| l["layout"].get("line-sort-key").is_some()));
}
