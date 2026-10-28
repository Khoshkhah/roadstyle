//! No colour text in a tile (docs/design/tile_v2_plan.md, step 6 and the colour modes): a colour by a column (numeric and categorical), a
//! colour table and colour options keep the colours in the style. A piece holds the place of its fill and casing colour in a table of
//! the style, and the road layer reads the colour from there. For each mode, on a part of Monaco:
//! - no text value of a tile feature is a colour;
//! - the fill and casing properties are whole numbers inside the style's table;
//! - the colour at that place is the colour that the road has in the road table (the export's `roads` source, the same rows).

mod common;

use roadstyle_rs::mark::{option_fill, Mark};
use serde_json::{json, Value};
use std::path::PathBuf;

const ZOOM: u32 = 14;

fn data(p: &str) -> Vec<u8> {
    std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)).unwrap()
}

fn look(case: &str, export: bool) -> roadstyle_rs::Look {
    let mut look: Value = serde_json::from_slice(&data("look.json")).unwrap();
    look["args"]["export"] = export.into();
    for (k, v) in common::colour_args(case).as_object().unwrap() {
        look["args"][k] = v.clone();
    }
    roadstyle_rs::Look::from_value(look).unwrap()
}

/// The colour tables (fill, casing) of the road layer: its colour is `["let", name, ["literal", fills], name, ["literal", casings], ...]`.
fn tables(style: &Value) -> (Vec<Value>, Vec<Value>) {
    let layer = style["layers"].as_array().unwrap().iter().find(|l| l["id"] == "roads-simple").expect("the road layer");
    let color = &layer["paint"]["line-color"];
    assert_eq!(color[0], "let", "the road layer reads its colours from tables");
    (color[2][1].as_array().unwrap().clone(), color[4][1].as_array().unwrap().clone())
}

/// The tiles of zoom `ZOOM` that the roads of Monaco's part touch.
fn tile_numbers() -> Vec<(u32, u32)> {
    let t = roadstyle_rs::read::read_roads(data("monaco_part/roads.parquet"), "geometry").unwrap();
    let (mut x0, mut y0, mut x1, mut y1) = (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY);
    for c in (0..t.len()).filter_map(|i| t.line(i)).flatten() {
        (x0, y0, x1, y1) = (x0.min(c[0]), y0.min(c[1]), x1.max(c[0]), y1.max(c[1]));
    }
    let n = (1u64 << ZOOM) as f64;
    let tx = |lon: f64| ((lon + 180.0) / 360.0 * n) as u32;
    let ty = |lat: f64| ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n) as u32;
    (tx(x0)..=tx(x1)).flat_map(|x| (ty(y1)..=ty(y0)).map(move |y| (x, y))).collect()
}

fn check(case: &str) {
    let roads = data("monaco_part/roads.parquet");
    let (style, tiles, _) = roadstyle_rs::tiled_from_parquet(roads.clone(), &look(case, false), None, None, "rs://", &[]).unwrap();
    let (fills, casings) = tables(&serde_json::from_str(&style).unwrap());
    let export: Value = serde_json::from_str(&roadstyle_rs::inline_style(roads, &look(case, true), None, None, None).unwrap()).unwrap();
    let rows = export["sources"]["roads"]["data"]["features"].as_array().expect("the export's roads");
    let fill_keys: Vec<String> = (0..4).map(|i| option_fill(i).into_owned()).collect();
    let casing_key = Mark::Casing.name();
    let (mut places, mut same) = (0, 0);
    for (x, y) in tile_numbers() {
        for (_, feats) in common::decode_tile(&tiles.tile(ZOOM, x, y)) {
            for (id, props, ..) in feats {
                for (k, v) in &props {
                    assert!(v.as_str().is_none_or(|s| !s.starts_with('#') && !s.starts_with("rgb")), "{case}: colour text {v} in {k}");
                    let table = if fill_keys.contains(k) { &fills } else if k == casing_key { &casings } else { continue };
                    let place = v.as_u64().unwrap_or_else(|| panic!("{case}: {k} is {v}, not a place")) as usize;
                    assert!(place < table.len(), "{case}: place {place} is outside the table of {}", table.len());
                    // the road table has the first option's fill and the casing; the other options' fills have no column there
                    if *k == fill_keys[0] || k == casing_key {
                        let road = &rows[id.expect("a piece has its road's row") as usize]["properties"][k];
                        assert!(road.is_null() || *road == table[place], "{case}: row {id:?} {k}: {road} != {}", table[place]);
                        same += usize::from(!road.is_null());
                    }
                    places += 1;
                }
            }
        }
    }
    assert!(places > 0, "{case}: no piece holds a colour place");
    assert!(same > 0, "{case}: no piece was compared with its road");
}

#[test]
fn a_colour_by_a_number() {
    check("numeric");
    check("numeric_width");
}

#[test]
fn a_colour_by_a_category() {
    check("categorical");
}

#[test]
fn a_colour_table() {
    check("color_table");
}

#[test]
fn colour_options() {
    check("color_options");
}

/// A view's palette has its own colour table: the pieces' copies of the colours that differ (`<property>@<palette>`) are places in it.
#[test]
fn a_views_palette_copies_hold_places() {
    let resolved = |palette: &str| roadstyle_rs::Look::resolve(&roadstyle_rs::look::Options::from_value(
        &json!({"palette": palette, "args": {"color_table": common::colour_args("color_table")["color_table"]}})).unwrap()).unwrap();
    let roads = || roadstyle_rs::read::read_roads(data("monaco_part/roads.parquet"), "geometry").unwrap();
    let base = resolved("amber");
    let mono = resolved("mono").with_map(base.map.clone()).unwrap();
    let mut s = roadstyle_rs::sources_of(roads(), &base, None, None, None).unwrap();
    roadstyle_rs::palettes::add(&mut s, "amber", &[("mono".into(), mono)]).unwrap();
    let simple = s.sources.iter().find_map(|(_, v)| match v { roadstyle_rs::Src::Simple(x) => Some(x), _ => None }).expect("the pieces");
    let key = roadstyle_rs::mark::in_palette(Mark::Casing.name(), "mono");
    let places = (0..simple.pieces.len()).filter_map(|i| simple.piece(&s.roads.roads, i).1.get(&key).cloned()).collect::<Vec<_>>();
    assert!(!places.is_empty(), "the palettes differ in the casing, and the pieces have its copy");
    assert!(places.iter().all(Value::is_u64), "a copy is a place, not a colour: {:?}", places.iter().find(|v| !v.is_u64()));
}
