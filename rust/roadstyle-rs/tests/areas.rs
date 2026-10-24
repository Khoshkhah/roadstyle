//! The engine against roadstyle's own output (Python) for whole areas (docs/design/rust_library.md, P0): Monaco, the Södermalm sample
//! and Tartu. The goldens come from tests/make_goldens.py; the large ones are on the pre-release rust-test-data (tests/get_goldens.sh).

mod common;

use serde_json::{json, Value};
use std::path::PathBuf;

fn data(p: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)
}

/// The engine's roads-only style for an area, with the look made from the golden's options.
fn style(area: &str) -> Value {
    let o = common::gz_json(&format!("{area}/golden_options.json.gz"));
    let mut look = roadstyle_rs::look::make_look(&o).unwrap();
    look["args"]["export"] = true.into();        // the goldens are exports: the roads source too (audit N2)
    let roads = std::fs::read(data(&format!("{area}/roads.parquet"))).unwrap();
    serde_json::from_str(&roadstyle_rs::make_style(roads, &roadstyle_rs::Look::from_value(look.clone()).unwrap(), None, None, None).unwrap()).unwrap()
}

fn style_differences(area: &str) -> Vec<(String, usize)> {
    let (got, want) = (style(area), common::as_decided(common::gz_json(&format!("{area}/golden_style.json.gz"))));
    // the top level: the engine writes mapstyle's export (its key order); below it, all is compared
    let mut keys: Vec<&String> = got.as_object().unwrap().keys().collect();
    keys.sort();
    let mut out = Vec::new();
    for k in keys {
        out.extend(common::diff_summary(&got[k], want.get(k).unwrap_or(&json!(null))).into_iter().map(|(p, n)| (format!("{k}{p}"), n)));
    }
    out
}

/// Known difference (docs/design/rust_library.md, P0): 4 slots of Monaco have another nearest road. The two directions of one way
/// (156242228#1, 448186734#1) have the same line, so a slot's middle is at distance 0 from both; GEOS's STRtree.nearest takes the
/// one its tree reaches first, the engine the lower index (the higher index does not match either: then 8 differ). 2 of them get a
/// twin (__rs_edge2) as a result.
const MONACO_SLOT_TIES: usize = 4;

#[test]
fn monaco_style_against_python() {
    let d = style_differences("monaco");
    assert_eq!(d, vec![("sources.slots.data.features[].properties.__rs_edge".to_string(), MONACO_SLOT_TIES),
                       ("sources.slots.data.features[].properties: keys (only Rust [\"__rs_edge2\"], only Python [])".to_string(), 2)]);
}

#[test]
fn sodermalm_style_against_python() {
    let d = style_differences("sodermalm");
    assert!(d.is_empty(), "{d:#?}");
}

#[test]
#[ignore = "a look at the slots that differ, of the area $AREA (default monaco; P0's list of differences)"]
fn slot_differences() {
    let area = std::env::var("AREA").unwrap_or_else(|_| "monaco".into());
    let (got, want) = (style(&area), common::gz_json(&format!("{area}/golden_style.json.gz")));
    let (g, w) = (got["sources"]["slots"]["data"]["features"].as_array().unwrap(), want["sources"]["slots"]["data"]["features"].as_array().unwrap());
    let roads = &got["sources"]["roads"]["data"]["features"];
    for (a, b) in g.iter().zip(w) {
        if a["properties"]["__rs_edge"] != b["properties"]["__rs_edge"] {
            let (ea, eb) = (a["properties"]["__rs_edge"].as_u64().unwrap() as usize, b["properties"]["__rs_edge"].as_u64().unwrap() as usize);
            println!("slot {} chain {} name {}: Rust edge {ea} ({}), Python edge {eb} ({}); the slot {}", a["properties"]["slot"], a["properties"]["chain"],
                     a["properties"]["name"], roads[ea]["properties"]["edge_ref"], roads[eb]["properties"]["edge_ref"], a["geometry"]["coordinates"]);
        }
    }
}

/// Two features' properties are the same: the same keys, and the same values, a number by its value (MapLibre reads 0 and 0.0, an
/// int_value -1 and a sint_value -1, as the same number).
fn same_props(a: &serde_json::Map<String, Value>, b: &serde_json::Map<String, Value>) -> bool {
    a.len() == b.len() && a.iter().all(|(k, v)| b.get(k).is_some_and(|w| match (v.as_f64(), w.as_f64()) {
        (Some(x), Some(y)) => x == y,
        _ => v == w,
    }))
}

/// The engine's tiles against export_style's (tiles.py), decoded: for each tile layer, (features in Python, in Rust, same id, same
/// properties, same geometry), summed over the golden tiles of each zoom.
fn tile_summary(area: &str) -> Vec<(String, [usize; 5])> {
    let o = common::gz_json(&format!("{area}/golden_options.json.gz"));
    let mut look = roadstyle_rs::look::make_look(&o).unwrap();
    look["args"]["export"] = true.into();        // export_style's tiles (audit N2)
    let roads = std::fs::read(data(&format!("{area}/roads.parquet"))).unwrap();
    let golden = common::gz_json(&format!("{area}/golden_tiles.json.gz"));
    let style = common::gz_json(&format!("{area}/golden_style.json.gz"));
    let keep: Vec<String> = style["sources"]["roads"]["data"]["features"][0]["properties"].as_object().unwrap().keys()
        .filter(|k| !k.starts_with("__rs_")).cloned().collect();
    let (tstyle, tiles, _) = roadstyle_rs::make_tiled(roads, &roadstyle_rs::Look::from_value(look.clone()).unwrap(), None, None, "rs://", &keep).unwrap();
    let tstyle: Value = serde_json::from_str(&tstyle).unwrap();
    let read = common::drawn_of(&tstyle);       // R1: the roads' stage values that are read, and the pieces' (on the tile layer "simple")
    let layers: Vec<Value> = tstyle["layers"].as_array().unwrap().iter().map(|l| {
        let mut l = l.clone();
        if l["source-layer"] == "simple" { l["source"] = "simple".into(); }
        l
    }).collect();
    let pieces = roadstyle_rs::props::piece_reads(&layers);
    let classes = common::classes_of(&style);
    use base64::Engine;
    let mut sums: indexmap::IndexMap<(String, String), [usize; 5]> = indexmap::IndexMap::new();
    for (name, b64) in golden.as_object().unwrap() {
        let zxy: Vec<u32> = name.split('/').map(|v| v.parse().unwrap()).collect();
        let mut py = common::decode_tile(&base64::engine::general_purpose::STANDARD.decode(b64.as_str().unwrap()).unwrap());
        for f in py.get_mut("simple").into_iter().flatten() {
            let ci = common::class_place(&classes, f.1.get("highway").and_then(Value::as_str));
            f.1.insert("__rs_ci".into(), ci.into());        // R8: the class index
            let item = f.1.get("__rs_k") == Some(&Value::from(5));
            f.1.retain(|k, _| pieces.contains(k) || (item && !k.starts_with("__rs_")));
        }
        for f in py.get_mut("roads").into_iter().flatten() {
            f.1.retain(|k, _| !k.starts_with("__rs_") || read.contains(k));
        }
        let rs = common::decode_tile(&tiles.tile(zxy[0], zxy[1], zxy[2]));
        for layer in py.keys().chain(rs.keys()).collect::<indexmap::IndexSet<_>>() {
            let (p, r) = (py.get(layer).map_or(&[][..], |v| v.as_slice()), rs.get(layer).map_or(&[][..], |v| v.as_slice()));
            let s = sums.entry((format!("z{}", zxy[0]), layer.clone())).or_default();
            s[0] += p.len();
            s[1] += r.len();
            for (a, b) in p.iter().zip(r) {
                s[2] += (a.0 == b.0) as usize;
                s[3] += same_props(&a.1, &b.1) as usize;
                s[4] += (a.2 == b.2 && a.3 == b.3) as usize;
            }
        }
    }
    sums.into_iter().map(|((z, l), s)| (format!("{z} {l}"), s)).collect()
}

#[test]
fn tiles_against_python() {
    for area in ["monaco", "sodermalm"] {
        for (layer, s) in tile_summary(area) {
            let ties = if area == "monaco" && layer.ends_with(" slots") { MONACO_SLOT_TIES } else { 0 };
            assert_eq!(s, [s[0], s[0], s[0], s[0] - ties, s[0]], "{area} {layer}: features in Python, in Rust, same id, same properties, same geometry");
        }
    }
}

/// The engine's levels (levels.rs) of an area's roads: one rank, as the roads are one table.
fn levels(area: &str, method: roadstyle_rs::levels::Method) -> Vec<Value> {
    use roadstyle_rs::levels::{levels, LevelEdge, LevelEdges, Options};
    let mut edges = LevelEdges::default();
    let t = roadstyle_rs::read::read_roads(std::fs::read(data(&format!("{area}/roads.parquet"))).unwrap(), "geometry").unwrap();
    for i in 0..t.len() {
        let text = |k: &str| t.get(i, k).and_then(roadstyle_rs::Cell::as_str).map(String::from);
        let id = match t.get(i, "edge_id").map(roadstyle_rs::Cell::to_value) { Some(Value::String(s)) => s.parse().unwrap(), Some(v) => v.as_i64().unwrap(), None => panic!("no edge_id") };
        edges.add(0, LevelEdge { edge_id: id, highway: text("highway").unwrap_or_default(), tunnel: text("tunnel"), bridge: text("bridge"),
                                 layer: text("layer"), junction: text("junction"), geometry: t.line(i).unwrap().iter().map(|&[x, y]| (x, y)).collect(),
                                 ..Default::default() });
    }
    levels(&edges, &Options { method, ..Default::default() }).unwrap().unwrap().rows.iter().map(|r| match method {
        roadstyle_rs::levels::Method::Tags => json!([r.edge_id.to_string(), r.casing_start, r.casing_level, r.casing_end, r.fill_level]),
        _ => json!([r.edge_id.to_string(), r.casing_start, r.casing_level, r.casing_end, r.fill_level, r.head_start_m, r.head_end_m, r.cap_start, r.cap_end]),
    }).collect()
}

/// The rows of Rust and Python by edge id: (rows in Python, rows in Rust, equal rows).
fn level_rows(area: &str, method: roadstyle_rs::levels::Method, golden: &str) -> (usize, usize, usize) {
    let got = levels(area, method);
    let want = common::gz_json(&format!("{area}/{golden}"));
    let by_id: std::collections::HashMap<&str, &Value> = want.as_array().unwrap().iter().map(|r| (r[0].as_str().unwrap(), r)).collect();
    let equal = got.iter().filter(|r| by_id.get(r[0].as_str().unwrap()).is_some_and(|w| *w == *r)).count();
    (want.as_array().unwrap().len(), got.len(), equal)
}

/// Known difference (P0): 8 rows of Monaco's solve differ, in the casing heads of a few roads. Both answers are equally good under
/// roadstyle's rules (0 hard rules broken, 0 stack parts not lifted, 16 order wishes not kept, 9 numbers): Python's LP (OR-tools) and the
/// engine's min-cost flow take different answers among equal best ones.
const MONACO_SOLVE_OTHER_ROWS: usize = 8;

#[test]
fn levels_against_python() {
    use roadstyle_rs::levels::Method::{Solve, Tags};
    assert_eq!(level_rows("monaco", Tags, "golden_levels_tags.json.gz"), (13_298, 13_298, 13_298));
    assert_eq!(level_rows("sodermalm", Tags, "golden_levels_tags.json.gz"), (4_563, 4_563, 4_563));
    assert_eq!(level_rows("monaco", Solve, "golden_levels_solve.json.gz"), (13_298, 13_298, 13_298 - MONACO_SOLVE_OTHER_ROWS));
    assert_eq!(level_rows("sodermalm", Solve, "golden_levels_solve.json.gz"), (4_563, 4_563, 4_563));
}

/// Tartu (inputs and goldens from the pre-release: tests/get_goldens.sh): the style, the tiles and the tags rule (no solve: Python
/// needs too much memory for it).
#[test]
#[ignore = "needs tests/get_goldens.sh"]
fn tartu_against_python() {
    assert!(data("tartu/golden_style.json.gz").exists(), "no Tartu goldens: run tests/get_goldens.sh");
    // the same known difference as Monaco's (MONACO_SLOT_TIES): 10 slots on the two directions of one way, 3 with a twin as a result
    assert_eq!(style_differences("tartu"), vec![("sources.slots.data.features[].properties.__rs_edge".to_string(), 10),
                                                ("sources.slots.data.features[].properties: keys (only Rust [\"__rs_edge2\"], only Python [])".to_string(), 3)]);
    for (layer, s) in tile_summary("tartu") {
        let ties = if layer == "z14 slots" { 2 } else { 0 };     // the tied slots in the golden tiles
        assert_eq!(s, [s[0], s[0], s[0], s[0] - ties, s[0]], "tartu {layer}: features in Python, in Rust, same id, same properties, same geometry");
    }
    assert_eq!(level_rows("tartu", roadstyle_rs::levels::Method::Tags, "golden_levels_tags.json.gz"), (64_828, 64_828, 64_828));
}
