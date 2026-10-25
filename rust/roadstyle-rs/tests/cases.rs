//! The engine's cases on a part of Monaco (review D5), each with a golden that the Rust engine makes (tests/data/monaco_part/cases/,
//! `ROADSTYLE_BLESS=1 cargo test --test cases` writes them): column names of the user's own (ColumnMap), cap_col, the boundary, metre
//! widths with and without the mitre ends, the overlays of each kind, the items, the 3D decks, the live state, export_look and a page
//! with views. A golden is a summary (common::summary): the layers, the sources, the metadata and the hash of the whole output.

mod common;

use roadstyle_rs::Look;
use serde_json::{json, Map, Value};
use std::path::PathBuf;

fn data(p: &str) -> Vec<u8> {
    std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)).unwrap()
}

/// The fixture's look (tests/data/look.json) with the names and the arrows on, and these keywords over it.
fn look(args: Value) -> Look {
    let mut look = Look::from_json(&String::from_utf8(data("look.json")).unwrap()).unwrap();
    for (k, v) in json!({"arrows": true, "labels": true}).as_object().unwrap().iter().chain(args.as_object().unwrap()) {
        look = look.with_arg(k, v.clone()).unwrap();
    }
    look
}

/// Monaco's part as GeoJSON features, `edit` applied to each feature's properties (with its row number).
fn roads(edit: impl Fn(usize, &mut Map<String, Value>)) -> roadstyle_rs::RoadTable {
    let mut fc = roadstyle_rs::read::features(data("monaco_part/roads.parquet")).unwrap();
    for (i, f) in fc["features"].as_array_mut().unwrap().iter_mut().enumerate() {
        edit(i, f["properties"].as_object_mut().unwrap());
    }
    roadstyle_rs::geojson::read_roads(fc.to_string().as_bytes()).unwrap()
}

/// The style of stage 1 (sources_of, write_style) and its road table's columns and hash.
fn style(roads: roadstyle_rs::RoadTable, look: &Look) -> Value {
    let s = roadstyle_rs::sources_of(roads, look, None, None, None).unwrap();
    let (mut out, mut table) = (Vec::new(), Vec::new());
    s.write_style(&mut out, roadstyle_rs::sources::SourceMode::INLINE).unwrap();
    roadstyle_rs::write_road_table(&s, None, &mut table).unwrap();
    let table: Value = serde_json::from_slice(&table).unwrap();
    let cols: Vec<String> = table["props"][0].as_object().map(|o| o.keys().cloned().collect()).unwrap_or_default();
    let mut sum = common::summary(&serde_json::from_slice(&out).unwrap());
    sum["road_table"] = json!({"rows": table["props"].as_array().map(Vec::len), "columns": cols, "hash": common::hash16(&table)});
    sum
}

fn case(name: &str, got: Value) {
    common::golden(&format!("monaco_part/cases/{name}.json"), &got);
}

/// The first 40 roads of the part with a line of at least 0.0003 degrees: their edge_id, name and line.
fn some_roads() -> Vec<(i64, Value, Vec<Value>)> {
    let fc = roadstyle_rs::read::features(data("monaco_part/roads.parquet")).unwrap();
    fc["features"].as_array().unwrap().iter().filter_map(|f| {
        let c = f["geometry"]["coordinates"].as_array()?.clone();
        let (a, b) = (&c[0], &c[c.len() - 1]);
        let len = ((a[0].as_f64()? - b[0].as_f64()?).powi(2) + (a[1].as_f64()? - b[1].as_f64()?).powi(2)).sqrt();
        let id = f["properties"]["edge_id"].as_i64().or_else(|| f["properties"]["edge_id"].as_str()?.parse().ok())?;
        (len >= 0.0003).then(|| (id, f["properties"]["name"].clone(), c))
    }).take(40).collect()
}

fn fc(features: Vec<Value>) -> Value {
    json!({"type": "FeatureCollection", "features": features})
}

#[test]
fn column_names_of_the_users_own() {
    let rename = [("highway", "fclass"), ("tunnel", "tun"), ("bridge", "brg"), ("layer", "lyr"), ("edge_id", "eid")];
    let r = roads(|_, p| for (own, user) in rename {
        if let Some(v) = p.shift_remove(own) {
            p.insert(user.into(), v);
        }
    });
    let l = look(json!({"highway_col": "fclass", "tunnel_col": "tun", "bridge_col": "brg", "layer_col": "lyr", "edge_id_col": "eid", "view_3d": true}));
    case("column_names", style(r, &l));
}

#[test]
fn cap_col_and_the_end_columns() {
    // a cap for both ends ("square", another true value, "round", none); with the end columns too, an end's own cap wins
    let caps = ["square", "flat", "round"];
    let with_cap = |ends: bool| roads(move |i, p| {
        p.insert("cap".into(), if i % 4 == 3 { Value::Null } else { caps[i % 4].into() });
        if ends {
            p.insert("cap_start".into(), if i % 5 == 0 { "round".into() } else { Value::Null });
            p.insert("cap_end".into(), if i % 6 == 0 { "square".into() } else { Value::Null });
        }
    });
    case("cap_col_only", style(with_cap(false), &look(json!({"cap_col": "cap", "cap_start_col": null, "cap_end_col": null}))));
    case("cap_col_and_ends", style(with_cap(true), &look(json!({"cap_col": "cap"}))));
}

#[test]
fn the_boundary() {
    let ring = json!([[7.4170, 43.7290], [7.4290, 43.7290], [7.4290, 43.7380], [7.4170, 43.7380], [7.4170, 43.7290]]);
    let b = fc(vec![json!({"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}})]);
    case("boundary", style(roads(|_, _| {}), &look(json!({"boundary": b}))));
}

#[test]
fn metre_widths_with_and_without_the_mitre_ends() {
    let r = || roads(|_, p| {
        let w = p.get("lanes").and_then(Value::as_f64).filter(|n| *n > 0.0).map(|n| json!(3.5 * n)).unwrap_or(Value::Null);
        p.insert("width_m".into(), w);
        p.insert("cap".into(), "flat".into());
    });
    case("metre_widths", style(r(), &look(json!({"width_m_col": "width_m"}))));
    case("metre_widths_options", style(r(), &look(json!({"width_m_col": "width_m", "casing_m": 0.3, "casing_min_px": 0.5, "width_m_zoom": 15}))));
    case("metre_widths_mitre", style(r(), &look(json!({"width_m_col": "width_m", "cap_col": "cap", "cap_start_col": null, "cap_end_col": null}))));
}

#[test]
fn overlays_of_each_kind() {
    let rs = some_roads();
    let feat = |props: Value, geom: Value| json!({"type": "Feature", "properties": props, "geometry": geom});
    let mid = |c: &[Value]| c[c.len() / 2].clone();
    let zones = fc(rs.iter().map(|(_, n, c)| {
        let (x, y) = (mid(c)[0].as_f64().unwrap(), mid(c)[1].as_f64().unwrap());
        let d = 0.0002;
        feat(json!({"name": n}), json!({"type": "Polygon", "coordinates": [[[x - d, y - d], [x + d, y - d], [x + d, y + d], [x - d, y + d], [x - d, y - d]]]}))
    }).collect());
    let pois = fc(rs.iter().map(|(_, n, c)| feat(json!({"name": n}), json!({"type": "Point", "coordinates": mid(c)}))).collect());
    let lines = fc(rs.iter().map(|(_, n, c)| feat(json!({"name": n}), json!({"type": "LineString", "coordinates": c}))).collect());
    let on_edges = fc(rs.iter().map(|(e, _, c)| feat(json!({"edge_id": e, "w": 2.5}), json!({"type": "LineString", "coordinates": c}))).collect());
    let kinds = json!([{"fc": zones, "label": "zones", "placement": "under", "popup": ["name"]},
                       {"fc": pois, "label": "pois", "color": "#ff0000", "tooltip": ["name"]},
                       {"fc": lines, "kind": "line", "dash": [2, 2], "min_zoom": 14, "popup": []}]);
    case("overlays_kinds", style(roads(|_, _| {}), &look(json!({"overlays": kinds}))));
    let text = json!([{"fc": lines, "kind": "text", "text_col": "name", "text_halo": "#ffffff"}]);
    case("overlays_text", style(roads(|_, _| {}), &look(json!({"overlays": text}))));
    let edges = json!([{"fc": on_edges, "label": "on edge", "edge_col": "edge_id", "color": "#00aa00"},
                       {"fc": on_edges, "label": "lanes", "edge_col": "edge_id", "width_m_col": "w", "color": "#00aa00"}]);
    case("overlays_on_edges", style(roads(|_, _| {}), &look(json!({"overlays": edges}))));
}

#[test]
fn the_items_of_the_roads() {
    // two lanes on each road: a width and an offset in metres, a colour, an order, some dashed, picked or with a minzoom
    let items = fc(some_roads().iter().enumerate().flat_map(|(i, (e, _, c))| [-1.0f64, 1.0].map(|side| json!({"type": "Feature",
        "geometry": {"type": "LineString", "coordinates": c},
        "properties": {"edge_id": e, "width_m": 3.0, "offset_m": side * 1.5, "color": if side < 0.0 { "#cc3333" } else { "#3333cc" },
                       "order": i32::from(side > 0.0), "dash": if side > 0.0 && i % 3 == 0 { json!("2,2") } else { Value::Null },
                       "pick": side > 0.0 && i % 5 == 0, "minzoom": if side > 0.0 && i % 7 == 0 { json!(17) } else { Value::Null }}}))).collect());
    case("items", style(roads(|_, _| {}), &look(json!({"items": items}))));
}

#[test]
fn the_3d_decks_and_the_live_state() {
    case("decks", style(roads(|_, _| {}), &look(json!({"view_3d": true}))));
    case("live", style(roads(|_, _| {}), &look(json!({"state": "live", "live_data": true}))));
}

#[test]
fn export_look_for_another_apps_layer() {
    let cols = roadstyle_rs::export_look::LookCols { highway: "highway", oneway: "oneway", tunnel: "tunnel", bridge: "bridge", id: "edge_id" };
    let got = roadstyle_rs::export_look::export_look(&look(json!({})), &cols, &[-1, 0, 1, 2]).unwrap();
    case("export_look", common::summary(&got));
}

#[test]
fn a_page_with_views() {
    // a look of roadstyle's own palettes (the fixture's look.json has mapstyle's base map, whose palette a view cannot change)
    let o = roadstyle_rs::look::Options::from_value(&json!({"palette": "amber", "args": {"state": "live", "arrows": true, "labels": true,
        "views": {"plain": {"road_fill": false}, "carto": {"palette": "carto"}, "bridges": {"bridges": true, "classes": ["primary"]}}}})).unwrap();
    let l = Look::resolve(&o).unwrap();
    // the page's keys (views) come from the call, not from the look
    let page = roadstyle_rs::page_options::page_from(roads(|_, _| {}), None, &l, &o, o.args.as_object().unwrap()).unwrap();
    case("page_views", json!({"bytes": page.html.len(), "hash": common::hash16(&json!(page.html)), "warnings": page.warnings}));
}
