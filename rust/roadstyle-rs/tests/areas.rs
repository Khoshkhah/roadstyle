//! Whole areas: Monaco, the Södermalm sample and Tartu. The style and the tiles are checked against goldens that the Rust engine makes
//! (`ROADSTYLE_BLESS=1 cargo test --test areas` writes them: tests/data/<area>/rust_style.json and rust_tiles.json, summaries in git;
//! common::golden). The last check against Python's output was N27 (2026-10-24); since then the Rust API is the design. The levels too
//! (rust_levels_*.json: the counts, and the rows' hash of the tags rule; every solve is feasible). Tartu's inputs are on the pre-release
//! rust-test-data (tests/get_goldens.sh).

mod common;

use serde_json::{json, Value};
use std::path::PathBuf;

fn data(p: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)
}

/// An area's look: its options (golden_options.json.gz), as an export (the roads source too, audit N2).
fn look(area: &str) -> roadstyle_rs::Look {
    let o = common::gz_json(&format!("{area}/golden_options.json.gz"));
    let mut look = roadstyle_rs::look::make_look(&o).unwrap();
    look["args"]["export"] = true.into();
    roadstyle_rs::Look::from_value(look).unwrap()
}

fn roads(area: &str) -> Vec<u8> {
    std::fs::read(data(&format!("{area}/roads.parquet"))).unwrap()
}

/// The size and the first 16 hex characters of the SHA-256 of a text: what the bindings must give byte for byte
/// (tests/test_binding.py compares the Python binding's texts with these).
fn text(b: &[u8]) -> Value {
    use sha2::{Digest, Sha256};
    json!({"bytes": b.len(), "sha16": Sha256::digest(b).iter().take(8).map(|x| format!("{x:02x}")).collect::<String>()})
}

/// The style of an area (stage 1, export_inline's) as a summary, with its road table's rows, columns and hash, and the two texts.
fn style(area: &str) -> Value {
    let s = roadstyle_rs::make_sources(roads(area), &look(area), None, None, None).unwrap();
    let (mut out, mut table) = (Vec::new(), Vec::new());
    s.write_style(&mut out).unwrap();
    roadstyle_rs::write_road_table(&s, &mut table).unwrap();
    let (style_text, table_text) = (text(&out), text(&table));
    let table: Value = serde_json::from_slice(&table).unwrap();
    let cols: Vec<String> = table["props"][0].as_object().map(|o| o.keys().cloned().collect()).unwrap_or_default();
    let mut sum = common::summary(&serde_json::from_slice(&out).unwrap());
    sum["road_table"] = json!({"rows": table["props"].as_array().map(Vec::len), "columns": cols, "hash": common::hash16(&table),
                               "text": table_text});
    sum["text"] = style_text;
    sum
}

/// The page of an area (page_from with the area's look, state "live", and no other option): its text.
fn page(area: &str) -> Value {
    let t = roadstyle_rs::read::read_roads(roads(area), "geometry").unwrap();
    let l = look(area).with_arg("state", "live".into()).unwrap();
    let p = roadstyle_rs::page_options::page_from(t, None, &l, &roadstyle_rs::look::Options::default(), &serde_json::Map::new()).unwrap();
    json!({"page": text(p.html.as_bytes()), "warnings": p.warnings})
}

/// The tiles of an area (make_tiled, every column of the roads kept): the 3 x 3 tiles around the roads' centre at zooms 12, 14 and 15,
/// and for each zoom and tile layer the number of tiles with it, of its features and a hash of them (decoded: ids, properties and
/// geometry), with the tiled style's summary.
fn tiles(area: &str) -> Value {
    let t = roadstyle_rs::read::read_roads(roads(area), "geometry").unwrap();
    let keep: Vec<String> = t.names().iter().filter(|n| !n.starts_with("__rs_")).cloned().collect();
    let (mut lo, mut hi) = ([f64::INFINITY; 2], [f64::NEG_INFINITY; 2]);
    for p in (0..t.len()).filter_map(|r| t.line(r)).flatten() {
        (lo, hi) = ([lo[0].min(p[0]), lo[1].min(p[1])], [hi[0].max(p[0]), hi[1].max(p[1])]);
    }
    let (lon, lat) = ((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0);
    let (style, tiles, _) = roadstyle_rs::make_tiled(roads(area), &look(area), None, None, "rs://", &keep).unwrap();
    let mut out = serde_json::Map::new();
    for z in [12u32, 14, 15] {
        let n = (1u64 << z) as f64;
        let x = ((lon + 180.0) / 360.0 * n) as i64;
        let y = ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n) as i64;
        let mut layers: indexmap::IndexMap<String, (usize, Vec<Value>)> = indexmap::IndexMap::new();
        for (dx, dy) in (-1..=1).flat_map(|dx| (-1..=1).map(move |dy| (dx, dy))) {
            for (name, feats) in common::decode_tile(&tiles.tile(z, (x + dx) as u32, (y + dy) as u32)) {
                let e = layers.entry(name).or_default();
                e.0 += 1;
                e.1.extend(feats.into_iter().map(|(id, props, kind, parts)| json!([id, props, kind, parts])));
            }
        }
        out.insert(format!("z{z}"), layers.into_iter().map(|(k, (n, f))| (k, json!({"tiles": n, "features": f.len(),
            "hash": common::hash16(&Value::Array(f))}))).collect());
    }
    json!({"style": common::summary(&serde_json::from_str(&style).unwrap()), "tiles": out})
}

#[test]
fn monaco_and_sodermalm_are_their_goldens() {
    for area in ["monaco", "sodermalm"] {
        common::golden(&format!("{area}/rust_style.json"), &style(area));
        common::golden(&format!("{area}/rust_tiles.json"), &tiles(area));
    }
    common::golden("monaco/rust_page.json", &page("monaco"));
}

/// The engine's levels (roadstyle-levels) of an area's roads: one rank, as the roads are one table.
fn levels(area: &str, method: roadstyle_rs::levels::Method) -> roadstyle_rs::levels::Levels {
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
    levels(&edges, &Options { method, ..Default::default() }).unwrap().unwrap()
}

/// The levels of Monaco and Södermalm, by the tags rule and solved: their goldens (common::levels_summary; a solve is feasible, the solver
/// checks it).
#[test]
fn the_levels_are_their_goldens() {
    use roadstyle_rs::levels::Method::{Solve, Tags};
    for area in ["monaco", "sodermalm"] {
        for (method, name) in [(Tags, "tags"), (Solve, "solve")] {
            common::golden(&format!("{area}/rust_levels_{name}.json"), &common::levels_summary(&levels(area, method)));
        }
    }
}

/// Tartu (its inputs from the pre-release: tests/get_goldens.sh): the style, the tiles and the levels by the tags rule against the Rust
/// goldens.
#[test]
#[ignore = "needs tests/get_goldens.sh"]
fn tartu_is_its_goldens() {
    assert!(data("tartu/roads.parquet").exists(), "no Tartu inputs: run tests/get_goldens.sh");
    common::golden("tartu/rust_style.json", &style("tartu"));
    common::golden("tartu/rust_tiles.json", &tiles("tartu"));
    common::golden("tartu/rust_levels_tags.json", &common::levels_summary(&levels("tartu", roadstyle_rs::levels::Method::Tags)));
}
