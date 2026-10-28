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

fn check(case: &str) {
    let mut look: Value = serde_json::from_str(&std::fs::read_to_string(data("look.json")).unwrap()).unwrap();
    look["args"]["arrows"] = true.into(); // the engine always makes the names and arrows
    look["args"]["labels"] = true.into();
    look["args"]["export"] = true.into(); // an export (audit N2)
    for (k, v) in common::colour_args(case).as_object().unwrap() {
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
