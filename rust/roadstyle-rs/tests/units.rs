//! Small cases of the engine through its public calls (review D5): the metre roads' flat ends meet in a mitre (simple.rs mitre_ends).

use serde_json::{json, Value};

/// The style of a GeoJSON FeatureCollection of roads with these keywords (render's args).
fn style(features: Value, args: Value) -> Value {
    let fc = json!({"type": "FeatureCollection", "features": features});
    let roads = roadstyle_rs::geojson::read_roads(fc.to_string().as_bytes()).unwrap();
    let look = roadstyle_rs::Look::resolve(&roadstyle_rs::look::Options::from_value(&json!({"args": args})).unwrap()).unwrap();
    let mut out = Vec::new();
    roadstyle_rs::sources_of(roads, &look, None, None, None).unwrap().write_style(&mut out, roadstyle_rs::sources::SourceMode::INLINE).unwrap();
    serde_json::from_slice(&out).unwrap()
}

fn road(id: i64, line: Value, cap: &str) -> Value {
    json!({"type": "Feature", "geometry": {"type": "LineString", "coordinates": line},
           "properties": {"edge_id": id, "highway": "primary", "w": 12.0, "cap": cap, "oneway": true}})
}

/// The largest longitude of the `simple` pieces of the first road (edge 0), which ends at 7.421 where the second road turns away.
fn reach(cap: &str) -> f64 {
    let s = style(json!([road(1, json!([[7.42, 43.73], [7.421, 43.73]]), cap), road(2, json!([[7.421, 43.73], [7.4215, 43.7305]]), cap)]),
                  json!({"width_m_col": "w", "cap_col": "cap"}));
    let feats = s["sources"]["simple"]["data"]["features"].as_array().expect("a simple source");
    feats.iter().filter(|f| f["id"] == 0)
        .flat_map(|f| f["geometry"]["coordinates"].as_array().cloned().unwrap_or_default())
        .filter_map(|p| p[0].as_f64()).fold(f64::MIN, f64::max)
}

#[test]
fn flat_metre_ends_meet_in_a_mitre() {
    // a flat end of a metre road reaches past the node, so that its corner meets the turning road's; a round end stops at the node
    let (flat, round) = (reach("flat"), reach("round"));
    assert!((round - 7.421).abs() < 1e-9, "a round end stops at the node: {round}");
    assert!(flat > 7.421 + 1e-6 && flat < 7.421 + 1e-3, "a flat end is pushed a few metres on: {flat}");
}
