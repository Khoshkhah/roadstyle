//! Stage 1 (docs/rust/architecture.md, "The three stages and the one call"): make_sources and save_sources on Monaco. The GeoJSON file
//! of each source is the data of that source in make_style's style; the roads' file has only their drawing values; the road table has
//! one row for each road with every field; the GeoParquet files have one row for each feature.

use serde_json::Value;
use std::path::PathBuf;

fn data(p: &str) -> Vec<u8> {
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p);
    std::fs::read(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

#[test]
fn monaco_sources_as_files() {
    let look = String::from_utf8(data("look.json")).unwrap();
    let style: Value = serde_json::from_str(&roadstyle_rs::make_style(data("monaco/roads.parquet"), &look, Some(data("monaco/features.parquet")), None, None).unwrap()).unwrap();
    let s = roadstyle_rs::make_sources(data("monaco/roads.parquet"), &look, Some(data("monaco/features.parquet")), None, None).unwrap();
    let dir = std::env::temp_dir().join(format!("roadstyle-sources-{}", std::process::id()));
    let files = roadstyle_rs::save_sources(&s, &dir.join("geojson"), roadstyle_rs::Format::GeoJson, &[]).unwrap();
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
    roadstyle_rs::save_sources(&s, &dir.join("geoparquet"), roadstyle_rs::Format::GeoParquet, &[]).unwrap();
    for n in &names {
        let rows = roadstyle_rs::read::read_table(std::fs::read(dir.join(format!("geoparquet/{n}.parquet"))).unwrap(), "geometry").unwrap();
        assert_eq!(rows.len(), style["sources"][n.as_str()]["data"]["features"].as_array().unwrap().len(), "{n}.parquet");
    }
    std::fs::remove_dir_all(&dir).unwrap();
}

/// R1: the layers read the features' properties only by name (`["get", name]`, `["has", name]`), so props::drawn knows each one.
#[test]
fn the_layers_read_properties_by_name() {
    let look = String::from_utf8(data("look.json")).unwrap();
    let s = roadstyle_rs::make_sources(data("monaco/roads.parquet"), &look, Some(data("monaco/features.parquet")), None, None).unwrap();
    let (mut read, mut unknown) = (std::collections::HashSet::new(), Vec::new());
    s.layers.iter().for_each(|l| roadstyle_rs::props::expression_reads(l, &mut read, &mut unknown));
    assert!(unknown.is_empty(), "a layer reads a property whose name is not a literal: {unknown:?}");
    assert!(read.contains("__rs_fill") && read.contains("__rs_s"), "{read:?}");
}
