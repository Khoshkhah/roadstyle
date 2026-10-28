//! Data-driven colour and width (render_edges' color_by, colors, cmap, vmin, vmax, width_by, color_table, color_options, color_active,
//! legend) on a part of Monaco: the style and the legend data (metadata "roadstyle:color_options", the page's colour options) against
//! goldens that the Rust engine makes (tests/data/monaco_part/cases/colors_<case>.json; `ROADSTYLE_BLESS=1 cargo test --test colors`
//! writes them). The last check of these cases against Python's export_inline was 2026-10-24 (the goldens of make_goldens.py's colors).

mod common;

use serde_json::{json, Value};
use std::path::PathBuf;

fn data(p: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)
}

/// The case's keywords (make_goldens.py's CASES, until 2026-10-24).
fn args(case: &str) -> Value {
    match case {
        "plain" => json!({}),
        "numeric" => json!({"color_by": "lanes", "cmap": "YlOrRd", "vmin": 1, "vmax": 4}),
        "numeric_width" => json!({"color_by": "lanes", "cmap": "viridis", "width_by": [1.0, 6.0]}),
        "categorical" => json!({"color_by": "access", "colors": {"private": "#d62728", "destination": "#ff7f0e", "no": "#7f7f7f"}}),
        "color_table" => json!({"color_table": table_of_colours()}),
        "color_options" => json!({"color_options": {"class": {}, "lanes": {"color_by": "lanes", "cmap": "Blues", "vmin": 1, "vmax": 3},
                                                    "access": {"color_by": "access", "colors": {"private": "#d62728"}, "missing": "self"}},
                                  "color_active": "lanes"}),
        "no_legend" => json!({"color_by": "lanes", "cmap": "magma", "legend": false}),
        _ => unreachable!("no case {case}"),
    }
}

/// Every third road: one of three colours, by its edge_id (the keys as text, as a JSON object has them).
fn table_of_colours() -> Value {
    let t = roadstyle_rs::read::read_roads(std::fs::read(data("monaco_part/roads.parquet")).unwrap(), "geometry").unwrap();
    let cols = ["#e41a1c", "#377eb8", "#4daf4a"];
    let id = |r: usize| {
        let c = t.get(r, "edge_id").unwrap();
        c.as_i64().map(|i| i.to_string()).or_else(|| c.as_str().map(String::from)).unwrap()
    };
    Value::Object((0..t.len()).step_by(3).map(|r| (id(r), json!(cols[r % 3]))).collect())
}

fn check(case: &str) {
    let mut look: Value = serde_json::from_str(&std::fs::read_to_string(data("look.json")).unwrap()).unwrap();
    look["args"]["arrows"] = true.into(); // the engine always makes the names and arrows
    look["args"]["labels"] = true.into();
    look["args"]["export"] = true.into(); // an export (audit N2)
    for (k, v) in args(case).as_object().unwrap() {
        look["args"][k] = v.clone();
    }
    let roads = std::fs::read(data("monaco_part/roads.parquet")).unwrap();
    let style = roadstyle_rs::inline_style(roads, &roadstyle_rs::Look::from_value(look).unwrap(), None, None, None).unwrap_or_else(|e| panic!("{case}: {e}"));
    let style: Value = serde_json::from_str(&style).unwrap();
    let options = style["metadata"].get("roadstyle:color_options").cloned().unwrap_or(json!([]));
    let names: Vec<Value> = options.as_array().into_iter().flatten().map(|o| o["name"].clone()).collect();
    common::golden(&format!("monaco_part/cases/colors_{case}.json"),
                   &json!({"style": common::summary(&style), "color_options": {"names": names, "hash": common::hash16(&options)}}));
}

#[test]
fn plain() {
    check("plain");
}

#[test]
fn numeric_cmap_vmin_vmax() {
    check("numeric");
}

#[test]
fn numeric_width_by() {
    check("numeric_width");
}

#[test]
fn categorical() {
    check("categorical");
}

#[test]
fn color_table() {
    check("color_table");
}

#[test]
fn color_options() {
    check("color_options");
}

#[test]
fn no_legend() {
    check("no_legend");
}
