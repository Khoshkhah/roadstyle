//! A style for a new look from a held stage 1 (docs/design/restyle_without_retile.md, D4): `LiveTiles::style_for(B)` on the map that look A
//! made is the style of a new map of look B, byte for byte. On Monaco with its base map and the duckOSM page's options (a colour option by
//! class, the access column, the names and the arrows, the live state). Look B is look A with other colours, made as the duckOSM page makes
//! a theme: by a change of the saved look's JSON (a base-map look gives the palette, so a palette is not an option with it).

use serde_json::{json, Value};
use std::path::PathBuf;

fn data(p: &str) -> Vec<u8> {
    std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)).unwrap()
}

/// The saved look (JSON) of a base-map theme, with the page's options.
fn look_json(theme: &str) -> Value {
    let args = json!({"color_options": {"Road class": {}}, "access_col": "access", "arrows": true, "labels": true, "state": "live"});
    let l = roadstyle_rs::Look::resolve(&roadstyle_rs::look::Options::from_value(&json!({"args": args,
        "base_map": {"mode": "all", "theme": theme, "paths": "google"}})).unwrap()).unwrap();
    serde_json::from_str(&l.to_json()).unwrap()
}

fn look(v: &Value) -> roadstyle_rs::Look {
    roadstyle_rs::Look::from_json(&v.to_string()).unwrap()
}

/// Each colour `#rrggbb` in `v` (every string that is one), changed by `f`.
fn recolour(v: &mut Value, f: &dyn Fn([u8; 3]) -> [u8; 3]) {
    match v {
        Value::String(s) if s.len() == 7 && s.starts_with('#') && s[1..].chars().all(|c| c.is_ascii_hexdigit()) => {
            let c = |i: usize| u8::from_str_radix(&s[i..i + 2], 16).unwrap();
            let [r, g, b] = f([c(1), c(3), c(5)]);
            *s = format!("#{r:02x}{g:02x}{b:02x}");
        }
        Value::Array(a) => a.iter_mut().for_each(|x| recolour(x, f)),
        Value::Object(o) => o.values_mut().for_each(|x| recolour(x, f)),
        _ => {}
    }
}

fn live(look: &roadstyle_rs::Look) -> roadstyle_rs::relevel::LiveTiles {
    let s = roadstyle_rs::style_sources(data("monaco/roads.parquet"), look, Some(data("monaco/features.parquet")), None, None).unwrap();
    roadstyle_rs::relevel::LiveTiles::new(s, look.clone(), "rs://1/", &["osm_id".to_string()]).unwrap()
}

/// The first place where two texts differ, with some text around it.
fn first_difference(a: &str, b: &str) -> String {
    let i = a.bytes().zip(b.bytes()).position(|(x, y)| x != y).unwrap_or(a.len().min(b.len()));
    let around = |s: &str| s.get(i.saturating_sub(100)..(i + 100).min(s.len())).unwrap_or("").to_string();
    format!("at byte {i} of {} and {}:\n  restyled: {}\n  new:      {}", a.len(), b.len(), around(a), around(b))
}

fn same_style(name: &str, a: &Value, b: &Value) {
    let restyled = live(&look(a)).style_for(&look(b)).unwrap();
    let new = live(&look(b)).style().to_string();
    assert!(restyled == new, "{name}: not the style of a new map, {}", first_difference(&restyled, &new));
}

#[test]
fn the_same_look_restyles_to_the_same_style() {
    let a = look_json("liberty");
    same_style("same look", &a, &a);
}

#[test]
fn every_colour_changed_restyles_to_the_style_of_a_new_map() {
    let a = look_json("liberty");
    let mut swapped = a.clone();
    recolour(&mut swapped, &|[r, g, b]| [b, r, g]);
    same_style("channels swapped", &a, &swapped);
    let mut dark = a.clone();
    recolour(&mut dark, &|c| c.map(|x| x / 2));
    same_style("darker", &a, &dark);
}

#[test]
fn the_base_map_colours_restyle_to_the_style_of_a_new_map() {
    let a = look_json("liberty");
    let mut b = a.clone();
    recolour(&mut b["base_map"], &|[r, g, b]| [255 - r, 255 - g, 255 - b]);
    same_style("base map inverted", &a, &b);
}

/// All the class fills of one colour: the classes that had other colours share one (a table of distinct colours would change its places).
#[test]
fn classes_of_one_colour_restyle_to_the_style_of_a_new_map() {
    let a = look_json("liberty");
    let mut b = a.clone();
    fn fills(v: &mut Value) {
        match v {
            Value::Object(o) => {
                if o.get("fill").is_some_and(Value::is_string) {
                    o.insert("fill".into(), json!("#888888"));
                }
                o.values_mut().for_each(fills);
            }
            Value::Array(a) => a.iter_mut().for_each(fills),
            _ => {}
        }
    }
    fills(&mut b["settings"]["palettes"]);
    fills(&mut b["roads"]["styles"]);
    same_style("one class colour", &a, &b);
}

/// The tiles of a map at zooms 12 to 16 around Monaco's centre (3 x 3 at each zoom).
fn some_tiles(live: &mut roadstyle_rs::relevel::LiveTiles) -> Vec<Vec<u8>> {
    let (lon, lat) = (7.4246_f64, 43.7384_f64);
    let mut out = Vec::new();
    for z in 12..=16u32 {
        let n = f64::from(1u32 << z);
        let x = ((lon + 180.0) / 360.0 * n) as u32;
        let y = ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n) as u32;
        for (dx, dy) in (0..3).flat_map(|a| (0..3).map(move |b| (a, b))) {
            out.push(live.tile(z, x + dx - 1, y + dy - 1));
        }
    }
    out
}

/// Every base-map theme over the stage 1 of the theme liberty: when the two make the same tiles, the restyled style is the new map's. A theme
/// that changes the tiles needs a new map, and the key of phase 3 refuses it (D2). On 2026-11-04 every theme but liberty itself changed the tiles:
/// a theme sets structure too (the first zoom of the base-map layers, the dash patterns of the roads), not only colours.
#[test]
fn a_base_map_theme_restyles_to_the_style_of_a_new_map() {
    let a = look_json("liberty");
    let tiles_a = some_tiles(&mut live(&look(&a)));
    let (mut same, mut other) = (Vec::new(), Vec::new());
    for theme in roadstyle_rs::look::basemap::themes() {
        let b = look_json(theme);
        if some_tiles(&mut live(&look(&b))) == tiles_a {
            same_style(theme, &a, &b);
            same.push(theme);
        } else {
            other.push(theme);
        }
    }
    println!("themes with the same tiles as liberty: {same:?}; with other tiles (a new map): {other:?}");
    assert!(same.contains(&"liberty"), "liberty makes its own tiles");
}

/// The held map is not changed: its style is the same before and after a style for another look.
#[test]
fn the_held_map_does_not_change() {
    let a = look_json("liberty");
    let mut held = live(&look(&a));
    let before = held.style().to_string();
    let mut b = a.clone();
    recolour(&mut b, &|[r, g, b]| [b, r, g]);
    held.style_for(&look(&b)).unwrap();
    assert!(held.style() == before);
}
