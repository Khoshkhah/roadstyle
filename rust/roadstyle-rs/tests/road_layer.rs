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

/// 2j: the road layer is one layer for every zoom (zoom bands, `roads-simple-z14` and `-z15`, were removed: MapLibre keeps the tiles of the old
/// zoom while the new ones come, and a layer of a band had no buckets in them, so the roads were missing at a pitched view). A road is picked on it.
#[test]
fn the_road_layer_is_one_layer_for_every_zoom() {
    let s = style(&[("state", "live".into())]);
    let layers: Vec<&Value> = road_layers(&s).into_iter().filter(|l| !l["id"].as_str().unwrap().ends_with("-dash")).collect();
    assert_eq!(layers.len(), 1);
    assert_eq!(layers[0]["id"], "roads-simple");
    assert!(layers[0].get("minzoom").is_none() && layers[0].get("maxzoom").is_none(), "no zoom range: every tile has its buckets");
    let pick: Vec<&str> = s["metadata"]["roadstyle:controls"]["pick"].as_array().unwrap().iter().map(|v| v.as_str().unwrap()).collect();
    assert_eq!(pick.iter().filter(|p| !p.ends_with("-dash")).count(), 1);
    assert!(pick.iter().all(|p| p.starts_with("roads-simple")), "a road is picked on every layer of the road: {pick:?}");
    assert!(layers[0]["layout"].get("line-sort-key").is_some());
}

/// 2f: only the dashed pieces (the tunnels' gaps and dashes, a piece with its own pattern) have `line-dasharray`, in a layer of their own.
#[test]
fn only_the_dashed_pieces_have_a_dash() {
    let s = style(&[]);
    let layers = road_layers(&s);
    let ids: Vec<&str> = layers.iter().map(|l| l["id"].as_str().unwrap()).collect();
    assert_eq!(ids, ["roads-simple-dash", "roads-simple"]);
    for l in &layers {
        assert_eq!(l["paint"].get("line-dasharray").is_some(), l["id"].as_str().unwrap().ends_with("-dash"), "{}", l["id"]);
    }
    // the dash layer is under the other layer and draws the tunnel gaps and dashes (kinds 3 and 4), the other layer does not
    assert!(layers[0]["filter"].to_string().contains(r#"["==",["get","__rs_k"],4]"#) && layers[1]["filter"].to_string().contains(r#"["!",["any",["==",["get","__rs_k"],3]"#));
}
