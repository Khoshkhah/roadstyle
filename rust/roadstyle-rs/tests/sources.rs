//! Stage 1 (docs/rust/architecture.md, "The three stages and the one call"): style_sources and write_sources on Monaco. The GeoJSON file
//! of each source is the data of that source in inline_style's style; the roads' file has only their drawing values; the road table has
//! one row for each road with every field; the GeoParquet files have one row for each feature.

use serde_json::{json, Value};
use std::path::PathBuf;

/// The fixture's look as an export (audit N2: the roads source too).
fn export_look() -> roadstyle_rs::Look {
    let mut look: Value = serde_json::from_slice(&data("look.json")).unwrap();
    look["args"]["export"] = true.into();
    roadstyle_rs::Look::from_value(look).unwrap()
}

fn data(p: &str) -> Vec<u8> {
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p);
    std::fs::read(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

#[test]
fn monaco_sources_as_files() {
    let look = export_look();
    let style: Value = serde_json::from_str(&roadstyle_rs::inline_style(data("monaco/roads.parquet"), &look, Some(data("monaco/features.parquet")), None, None).unwrap()).unwrap();
    let s = roadstyle_rs::style_sources(data("monaco/roads.parquet"), &look, Some(data("monaco/features.parquet")), None, None).unwrap();
    let dir = std::env::temp_dir().join(format!("roadstyle-sources-{}", std::process::id()));
    let files = roadstyle_rs::write_sources(&s, &dir.join("geojson"), roadstyle_rs::Format::GeoJson, &[]).unwrap();
    let names: Vec<&String> = style["sources"].as_object().unwrap().keys().collect();
    assert_eq!(files.len(), names.len() + 2, "a file for each source, the road table and style.json");
    let drawn = s.drawn(&[]);
    for n in &names {
        let got: Value = serde_json::from_slice(&std::fs::read(dir.join(format!("geojson/{n}.geojson"))).unwrap()).unwrap();
        let mut want = style["sources"][n.as_str()]["data"].clone();
        if *n == "roads" {
            // the roads' file: the drawing values only (their fields are in the road table), and no lines when no shown layer
            // draws the roads (the road table has them)
            for f in want["features"].as_array_mut().unwrap() {
                f["properties"].as_object_mut().unwrap().retain(|k, _| k.starts_with("__rs_") || drawn.contains(k));
                if !s.draws_roads() {
                    f["geometry"] = serde_json::Value::Null;
                }
            }
        }
        assert!(got == want, "{n}.geojson is not the source's data");
    }
    let saved: Value = serde_json::from_slice(&std::fs::read(dir.join("geojson/style.json")).unwrap()).unwrap();
    assert_eq!(saved["sources"]["simple"]["data"], "simple.geojson");
    assert_eq!(saved["layers"], style["layers"]);
    // the road table: a row for each road, a column for each field of the roads source, and the stage values that the page reads on a
    // row (R1: props::table_keeps)
    let roads = style["sources"]["roads"]["data"]["features"].as_array().unwrap();
    let table = roadstyle_rs::read::read_roads(std::fs::read(dir.join("geojson/road_table.parquet")).unwrap(), "geometry").unwrap();
    assert_eq!(table.len(), roads.len());
    let mut keys: Vec<&String> = roads.iter().flat_map(|f| f["properties"].as_object().unwrap().keys()).filter(|k| !k.starts_with("__rs_")).collect();
    keys.sort();
    keys.dedup();
    let cols: Vec<&String> = table.names().iter().filter(|n| !n.starts_with("__mid") && !n.starts_with("__bbox") && *n != "__heading").collect();
    let mut fields: Vec<&String> = cols.iter().copied().filter(|n| !n.starts_with("__rs_")).collect();
    fields.sort();
    assert_eq!(fields, keys);
    assert!(cols.iter().all(|n| roadstyle_rs::props::table_keeps(n)), "{cols:?}");
    assert!(cols.iter().any(|n| *n == "__rs_dup") && cols.iter().all(|n| *n != "__rs_cl"), "{cols:?}");
    assert!((0..table.len()).all(|i| table.line(i).is_some()), "the road table has every road's line");
    // GeoParquet: a row for each feature of each source
    roadstyle_rs::write_sources(&s, &dir.join("geoparquet"), roadstyle_rs::Format::GeoParquet, &[]).unwrap();
    for n in &names {
        let rows = roadstyle_rs::read::read_table(std::fs::read(dir.join(format!("geoparquet/{n}.parquet"))).unwrap(), "geometry").unwrap();
        assert_eq!(rows.len(), style["sources"][n.as_str()]["data"]["features"].as_array().unwrap().len(), "{n}.parquet");
    }
    std::fs::remove_dir_all(&dir).unwrap();
}

/// R1: the layers read the features' properties only by name (`["get", name]`, `["has", name]`), so props::drawn knows each one.
#[test]
fn the_layers_read_properties_by_name() {
    let look = export_look();
    let s = roadstyle_rs::style_sources(data("monaco/roads.parquet"), &look, Some(data("monaco/features.parquet")), None, None).unwrap();
    let (mut read, mut unknown) = (std::collections::HashSet::new(), Vec::new());
    s.layers.iter().for_each(|l| roadstyle_rs::props::expression_reads(l, &mut read, &mut unknown));
    assert!(unknown.is_empty(), "a layer reads a property whose name is not a literal: {unknown:?}");
    assert!(read.contains("__rs_fill") && read.contains("__rs_s"), "{read:?}");
}

/// R7: every style has the road roles and the pick layers (contract::describe), also with no interaction contract: with view_3d the
/// pick has the decks' tops and not their casing.
#[test]
fn a_style_with_no_contract_has_the_pick() {
    let mut look: Value = serde_json::from_slice(&data("look.json")).unwrap();
    look["args"]["view_3d"] = true.into();
    let look = roadstyle_rs::Look::from_value(look).unwrap();
    let style: Value = serde_json::from_str(&roadstyle_rs::inline_style(data("monaco_decks/roads.parquet"), &look, None, None, None).unwrap()).unwrap();
    let m = &style["metadata"];
    assert!(m["roadstyle:contract"].is_null());
    assert!(m["roadstyle:sources"].is_object());
    let pick: Vec<&str> = m["roadstyle:controls"]["pick"].as_array().unwrap().iter().map(|v| v.as_str().unwrap()).collect();
    assert!(pick.iter().any(|p| p.starts_with("roads-bridge-decks")), "{pick:?}");
    assert!(!pick.iter().any(|p| p.starts_with("roads-deck-casing")), "{pick:?}");
}

/// The pieces' sort keys (`__rs_s`) of an area's style: (the integer, its road).
fn sort_keys(area: &str) -> Vec<(i64, i64)> {
    let look = roadstyle_rs::Look::from_value(serde_json::from_slice(&data("look.json")).unwrap()).unwrap();
    let style: Value = serde_json::from_str(&roadstyle_rs::inline_style(data(&format!("{area}/roads.parquet")), &look, None, None, None).unwrap()).unwrap();
    style["sources"]["simple"]["data"]["features"].as_array().unwrap().iter()
        .map(|f| (f["properties"]["__rs_s"].as_i64().expect("an integer __rs_s"), f["properties"]["__rs_edge"].as_i64().unwrap())).collect()
}

/// The integer sort key (2026-10-25) has the order of the double before it (the key + the road * 1e-8): its key part is on the keys'
/// grid of 0.01, the road's tie-breaker never reaches the next key, and every value is a safe integer in JavaScript.
fn the_sort_key_keeps_its_order(keys: &[(i64, i64)]) {
    const UNIT: i64 = 100_000_000;
    for &(s, e) in keys {
        assert!((0..1_000_000).contains(&e) && s.unsigned_abs() < 1 << 53, "{s} {e}");
        assert_eq!((s - e) % (UNIT / 100), 0, "the key of {s} (road {e}) is not on the grid of 0.01");
    }
    let double = |&(s, e): &(i64, i64)| ((s - e) / (UNIT / 100)) as f64 / 100.0 + e as f64 * 1e-8;
    let mut by_int: Vec<usize> = (0..keys.len()).collect();
    let mut by_double = by_int.clone();
    by_int.sort_by_key(|&i| (keys[i].0, i));
    by_double.sort_by(|&a, &b| double(&keys[a]).total_cmp(&double(&keys[b])).then(a.cmp(&b)));
    assert_eq!(by_int, by_double);
}

#[test]
fn monaco_sort_keys() {
    the_sort_key_keeps_its_order(&sort_keys("monaco"));
}

/// Tartu's inputs are not in git: `tests/get_goldens.sh`, then `cargo test --release -- --ignored`.
#[test]
#[ignore]
fn tartu_sort_keys() {
    let keys = sort_keys("tartu");
    assert!(keys.len() > 100_000, "{}", keys.len());
    the_sort_key_keeps_its_order(&keys);
}

/// A tile has no `__rs_*` flag that is false (2026-10-25), so every layer reads a flag with `to-boolean` (a missing key is false): each
/// `["get", k]` of a `__rs_*` property that is false on some feature of the style is the argument of a `to-boolean`.
#[test]
fn a_missing_flag_is_false_for_every_layer() {
    let mut look: Value = serde_json::from_slice(&data("look.json")).unwrap();
    for k in ["view_3d", "arrows", "labels"] {
        look["args"][k] = true.into();
    }
    let look = roadstyle_rs::Look::from_value(look).unwrap();
    let style: Value = serde_json::from_str(&roadstyle_rs::inline_style(data("monaco/roads.parquet"), &look, Some(data("monaco/features.parquet")), None, None).unwrap()).unwrap();
    let mut flags = std::collections::BTreeSet::new();
    for s in style["sources"].as_object().unwrap().values() {
        for f in s["data"]["features"].as_array().into_iter().flatten() {
            for (k, v) in f["properties"].as_object().into_iter().flatten() {
                if k.starts_with("__rs_") && v == false {
                    flags.insert(k.clone());
                }
            }
        }
    }
    assert!(flags.contains("__rs_bridge") && flags.contains("__rs_twoway"), "{flags:?}");
    fn walk(v: &Value, parent: Option<&str>, flags: &std::collections::BTreeSet<String>, at: &str, bad: &mut Vec<String>) {
        let Value::Array(a) = v else {
            if let Value::Object(o) = v {
                o.iter().for_each(|(k, x)| walk(x, None, flags, &format!("{at}.{k}"), bad));
            }
            return;
        };
        let op = a.first().and_then(Value::as_str);
        if matches!(op, Some("get" | "has")) && a.len() == 2 && a[1].as_str().is_some_and(|k| flags.contains(k)) && (op == Some("has") || parent != Some("to-boolean")) {
            bad.push(format!("{at}: {v}"));
        }
        a.iter().for_each(|x| walk(x, op, flags, at, bad));
    }
    let mut bad = Vec::new();
    for l in style["layers"].as_array().unwrap() {
        walk(&json!([l["filter"], l["paint"], l["layout"]]), None, &flags, l["id"].as_str().unwrap(), &mut bad);
    }
    assert!(bad.is_empty(), "a flag read with no to-boolean: {bad:#?}");
}
