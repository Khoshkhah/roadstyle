//! The style that a host page's map worker makes (`styleSources` and `tilesOfSources`, as roadstyle-wasm gives them) has what the dashboard reads:
//! with state "live" the controls (the base map's layers `overlays`, with the 3D layer of the buildings), and the colour options that the look asks
//! for. A look with state "static" has the road layers and the pick layers only: the host page's look must be live.

use roadstyle_rs::Look;
use serde_json::{json, Value};
use std::path::PathBuf;

fn data(p: &str) -> Vec<u8> {
    std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)).unwrap()
}

fn style(args: Value) -> Value {
    let mut look = Look::from_json(&String::from_utf8(data("look.json")).unwrap()).unwrap();
    for (k, v) in args.as_object().unwrap() {
        look = look.with_arg(k, v.clone()).unwrap();
    }
    let s = roadstyle_rs::style_sources(data("monaco/roads.parquet"), &look, Some(data("monaco/features.parquet")), None, None).unwrap();
    let (text, _) = roadstyle_rs::tiles_of_sources(&s, "rs-", &[]).unwrap();
    serde_json::from_str(&text).unwrap()
}

#[test]
fn a_live_tiled_style_has_the_overlays_and_the_colour_options_that_the_look_asks_for() {
    let live = style(json!({"state": "live", "color_options": {"Road class": {}}}));
    let ov = live["metadata"]["roadstyle:controls"]["overlays"].as_array().expect("overlays");
    assert!(ov.iter().any(|o| o["label"] == "water") && ov.iter().any(|o| o["label"] == "buildings" && o["extrude"].is_string()), "{ov:?}");
    assert!(live["layers"].as_array().unwrap().iter().any(|l| l["id"] == ov[0]["layers"][0]), "an overlay names layers of the style");
    assert_eq!(live["metadata"]["roadstyle:color_options"][0]["name"], "Road class");
    // the static look: the pick layers and nothing else of the controls
    let fixed = style(json!({"state": "static"}));
    assert_eq!(fixed["metadata"]["roadstyle:controls"].as_object().unwrap().keys().collect::<Vec<_>>(), ["pick"]);
}
