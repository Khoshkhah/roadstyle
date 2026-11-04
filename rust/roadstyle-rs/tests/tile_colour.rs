//! No colour text in a tile (docs/design/tile_v2_plan.md, step 6 and the colour modes): a colour by a column (numeric and categorical), a
//! colour table and colour options keep the colours in the style. A piece holds the place of its fill and casing colour in a table of
//! the style, and the road layer reads the colour from there. For each mode, on a part of Monaco:
//! - no text value of a tile feature is a colour;
//! - the fill and casing properties are whole numbers inside the style's table;
//! - the colour at that place is the colour that the road has in the road table (the export's `roads` source, the same rows);
//! - a piece with no fill or casing of its own has a role colour (docs/design/restyle_without_retile.md, D1): the palette's colour of its
//!   access kind, else its class's colour, which the road layer gives by its class index; that colour is the road's colour in the road table.

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

/// The tiles of zoom `zoom` that the roads of Monaco's part touch.
fn tile_numbers(zoom: u32) -> Vec<(u32, u32)> {
    let t = roadstyle_rs::read::read_roads(data("monaco_part/roads.parquet"), "geometry").unwrap();
    let (mut x0, mut y0, mut x1, mut y1) = (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY);
    for c in (0..t.len()).filter_map(|i| t.line(i)).flatten() {
        (x0, y0, x1, y1) = (x0.min(c[0]), y0.min(c[1]), x1.max(c[0]), y1.max(c[1]));
    }
    let n = (1u64 << zoom) as f64;
    let tx = |lon: f64| ((lon + 180.0) / 360.0 * n) as u32;
    let ty = |lat: f64| ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n) as u32;
    (tx(x0)..=tx(x1)).flat_map(|x| (ty(y1)..=ty(y0)).map(move |y| (x, y))).collect()
}

fn check(case: &str) {
    check_counts(case, true, ZOOM);
}

/// `check`, and the numbers of pieces compared by a place and by a role colour, and of the role colours of an access kind.
fn check_counts(case: &str, data_colours: bool, zoom: u32) -> (usize, usize, usize) {
    let roads = data("monaco_part/roads.parquet");
    let tiled = look(case, false);
    let (style, tiles, _) = roadstyle_rs::tiled_from_parquet(roads.clone(), &tiled, None, None, "rs://", &[]).unwrap();
    let style: Value = serde_json::from_str(&style).unwrap();
    let (fills, casings) = tables(&style);
    // the role colours: each class's fill and casing (by the class index of the style's class list), and each access kind's fill
    let classes: Vec<String> = serde_json::from_value(style["metadata"][roadstyle_rs::props::CLASSES].clone()).unwrap();
    let by_class = roadstyle_rs::colors::ClassColours::of(&tiled.road, &tiled.model.classes);
    let role = |props: &serde_json::Map<String, Value>, i: usize| -> Value {
        let access = props.get(Mark::Access.name()).and_then(Value::as_str).and_then(|k| tiled.road.access.get(k)).filter(|c| !c.is_null());
        match (i, access) {
            (0, Some(c)) => c.clone(),
            _ => by_class.of_class(props[roadstyle_rs::layers::CLASS_INDEX].as_u64().and_then(|n| classes.get(n as usize)).map(String::as_str))[i].clone(),
        }
    };
    let (mut roles, mut access_roles) = (0, 0);
    let export: Value = serde_json::from_str(&roadstyle_rs::inline_style(roads, &look(case, true), None, None, None).unwrap()).unwrap();
    let rows = export["sources"]["roads"]["data"]["features"].as_array().expect("the export's roads");
    let fill_keys: Vec<String> = (0..4).map(|i| option_fill(i).into_owned()).collect();
    let casing_key = Mark::Casing.name();
    let (mut places, mut same) = (0, 0);
    for (x, y) in tile_numbers(zoom) {
        for (_, feats) in common::decode_tile(&tiles.tile(zoom, x, y)) {
            for (id, props, ..) in feats {
                // a fill or a casing that the piece does not hold is its role colour, and that is its road's colour
                let kind = props.get(Mark::PieceKind.name()).and_then(Value::as_u64);
                for (k, i) in [(fill_keys[0].as_str(), 0usize), (casing_key, 1)].into_iter().filter(|(k, _)| !props.contains_key(*k)) {
                    if (i == 0 && kind != Some(1)) || (i == 1 && kind != Some(0)) {
                        continue;        // a fill piece draws the fill, a casing piece the casing
                    }
                    let road = &rows[id.expect("a piece has its road's row") as usize]["properties"][k];
                    if !road.is_null() {
                        assert_eq!(*road, role(&props, i), "{case}: row {id:?} {k}: the road's colour is not its role colour");
                        roles += 1;
                        access_roles += usize::from(i == 0 && props.get(Mark::Access.name()).is_some_and(|a| !a.is_null()));
                    }
                }
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
    assert!(!data_colours || places > 0, "{case}: no piece holds a colour place");
    assert!(same + roles > 0, "{case}: no piece was compared with its road");
    (places, roles, access_roles)
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

/// The duckOSM page's options: a colour option by class and the access column. No piece holds a colour: every fill and casing is a role
/// colour, and a private road's is the palette's access colour (a private road is drawn from zoom 15, the last zoom of the tiles).
#[test]
fn the_page_options_give_role_colours() {
    let (places, roles, access) = check_counts("class_access", false, 15);
    assert_eq!(places, 0, "no piece holds a colour place");
    assert!(roles > 0 && access > 0, "the pieces were compared by their role colours ({roles}), private roads too ({access})");
}

/// A view's palette: the casing is a role colour (D1), so no piece holds a copy of it (`<property>@<palette>`); the road layer switches the
/// class casing by the state `rs_palette`. A copy that a piece holds (a data colour that differs) is a place, not a colour.
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
    assert!(places.is_empty(), "the casing is a role colour: no piece holds a copy of it");
    let all = (0..simple.pieces.len()).flat_map(|i| simple.piece(&s.roads.roads, i).1.into_iter().filter(|(k, _)| k.contains('@')).map(|(_, v)| v.clone()).collect::<Vec<_>>()).collect::<Vec<_>>();
    assert!(all.iter().all(Value::is_u64), "a copy is a place, not a colour: {:?}", all.iter().find(|v| !v.is_u64()));
    let road = s.layers.iter().find(|l| l["id"] == "roads-simple").expect("the road layer");
    let colour = road["paint"]["line-color"].to_string();
    assert!(colour.contains("rs_palette") && colour.contains("#707d00") && colour.contains("#5c5c5c"),
            "the road layer has amber's and mono's casing of secondary, picked by rs_palette");
}
