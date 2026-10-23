//! Data-driven colour and width (render_edges' color_by, colors, cmap, vmin, vmax, width_by, color_table, color_options, color_active,
//! legend): the style must be roadstyle's own (Python export_inline) for a part of Monaco, and the legend data
//! (metadata "roadstyle:color_options") the page's COLOR_OPTIONS. The goldens come from tests/make_goldens.py; each case's options are
//! added to look["args"].

mod common;

use common::diff;
use serde_json::Value;
use std::path::PathBuf;

fn data(p: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)
}

fn check(case: &str) {
    let golden = common::gz_json(&format!("monaco_part/{case}.json.gz"));
    let mut look: Value = serde_json::from_str(&std::fs::read_to_string(data("look.json")).unwrap()).unwrap();
    look["args"]["arrows"] = true.into(); // as tests/make_goldens.py: the engine always makes the names and arrows
    look["args"]["labels"] = true.into();
    for (k, v) in golden["args"].as_object().unwrap() {
        look["args"][k] = v.clone();
    }
    let roads = std::fs::read(data("monaco_part/roads.parquet")).unwrap();
    let style = roadstyle_rs::make_style(roads, &look.to_string(), None, None, None).unwrap_or_else(|e| panic!("{case}: {e}"));
    let mut style: Value = serde_json::from_str(&style).unwrap();
    let options = style["metadata"].as_object_mut().unwrap().shift_remove("roadstyle:color_options").unwrap_or(Value::Array(vec![]));
    // the top level: the engine writes mapstyle's export (its key order); below it, all must be the same
    let mut out = Vec::new();
    let (mut a, mut b): (Vec<&String>, Vec<&String>) = (style.as_object().unwrap().keys().collect(), golden["style"].as_object().unwrap().keys().collect());
    a.sort();
    b.sort();
    assert_eq!(a, b, "{case}: the keys of the style");
    for k in a {
        diff(&style[k], &golden["style"][k], &format!("style.{k}"), &mut out);
    }
    diff(&options, &golden["color_options"], "color_options", &mut out);
    assert!(out.is_empty(), "{case}: the first differences:\n{}", out.join("\n"));
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
