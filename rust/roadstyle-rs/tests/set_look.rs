//! `LiveTiles::set_look` (docs/design/restyle_without_retile.md, D2, D3 and D5): when it says that the map keeps its tiles, its style is the
//! style of a new map of the new look, and every tile of the map (the tiles made before the new look and the tiles first made after it) is the
//! tile of a new map of the new look cut with the held map's buffers (`LiveTiles::with_buffers`), byte for byte. A change of colours only is kept; a change of structure is refused. Random changes of the look's values (colours, numbers, flags) check
//! the rule where the key could be wrong: a wrong "kept" fails, a refusal does not (it costs time, not a wrong map). On Monaco with its base map
//! and the duckOSM page's options.

use serde_json::{json, Value};
use std::path::PathBuf;

fn data(p: &str) -> Vec<u8> {
    std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)).unwrap()
}

/// The saved look (JSON) of the theme liberty, with the page's options.
fn look_json() -> Value {
    let args = json!({"color_options": {"Road class": {}}, "access_col": "access", "arrows": true, "labels": true, "state": "live"});
    let l = roadstyle_rs::Look::resolve(&roadstyle_rs::look::Options::from_value(&json!({"args": args,
        "base_map": {"mode": "all", "theme": "liberty", "paths": "google"}})).unwrap()).unwrap();
    serde_json::from_str(&l.to_json()).unwrap()
}

fn live(look: &roadstyle_rs::Look) -> Option<roadstyle_rs::relevel::LiveTiles> {
    cut(look, None)
}

/// A new map of `look`, its tiles cut with `buffers` (None: the style's).
fn cut(look: &roadstyle_rs::Look, buffers: Option<Vec<f64>>) -> Option<roadstyle_rs::relevel::LiveTiles> {
    let s = roadstyle_rs::style_sources(data("monaco/roads.parquet"), look, Some(data("monaco/features.parquet")), None, None).ok()?;
    roadstyle_rs::relevel::LiveTiles::with_buffers(s, look.clone(), "rs://1/", &["osm_id".to_string()], buffers).ok()
}

/// Every tile of Monaco's roads at zooms 12 to 16.
fn tile_numbers() -> Vec<(u32, u32, u32)> {
    let t = roadstyle_rs::read::read_roads(data("monaco/roads.parquet"), "geometry").unwrap();
    let (mut x0, mut y0, mut x1, mut y1) = (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY);
    for c in (0..t.len()).filter_map(|i| t.line(i)).flatten() {
        (x0, y0, x1, y1) = (x0.min(c[0]), y0.min(c[1]), x1.max(c[0]), y1.max(c[1]));
    }
    let mut out = Vec::new();
    for z in 12..=16u32 {
        let n = (1u64 << z) as f64;
        let tx = |lon: f64| ((lon + 180.0) / 360.0 * n) as u32;
        let ty = |lat: f64| ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n) as u32;
        for x in tx(x0)..=tx(x1) {
            for y in ty(y1)..=ty(y0) {
                out.push((z, x, y));
            }
        }
    }
    out
}

/// `set_look(b)` on the map of `a`, with half of the tiles made before it. The answer, and (when it keeps the tiles) the check that every tile
/// and the style are those of a new map of `b`.
fn set_and_check(name: &str, a: &Value, b: &Value) -> bool {
    let (Ok(la), Ok(lb)) = (roadstyle_rs::Look::from_json(&a.to_string()), roadstyle_rs::Look::from_json(&b.to_string())) else { return false };
    let mut held = live(&la).expect("the map of look a");
    let numbers = tile_numbers();
    for &(z, x, y) in numbers.iter().step_by(2) {
        held.tile(z, x, y);         // made with look a, before the new look
    }
    if !held.set_look(&lb).unwrap() {
        return false;
    }
    let new_style = live(&lb).unwrap_or_else(|| panic!("{name}: set_look kept the tiles of a look that makes no map")).style().to_string();
    assert!(held.style() == new_style, "{name}: set_look kept the tiles, but the style is not the new map's");
    let mut new = cut(&lb, Some(held.options().buffers.clone())).unwrap();
    for &(z, x, y) in &numbers {
        assert!(held.tile(z, x, y) == new.tile(z, x, y), "{name}: set_look kept the tiles, but tile {z}/{x}/{y} is not the new map's");
    }
    true
}

/// Each colour `#rrggbb` in `v`, changed by `f`.
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

#[test]
fn a_change_of_colours_keeps_the_tiles() {
    let a = look_json();
    // every colour of the look as a theme has them: not the user's data colours (`map`, `data`, `overlays`), which the key counts
    let mut swapped = a.clone();
    swapped.as_object_mut().unwrap().iter_mut().filter(|(k, _)| !matches!(k.as_str(), "map" | "data" | "overlays"))
        .for_each(|(_, v)| recolour(v, &|[r, g, b]| [b, r, g]));
    assert!(set_and_check("every colour", &a, &swapped), "a change of colours only keeps the tiles");
    // the data colours count: a change of them makes a new map (a data colour can be a place in the pieces' colour table)
    let mut data_colours = a.clone();
    recolour(&mut data_colours["data"], &|[r, g, b]| [b, r, g]);
    assert!(!set_and_check("data colours", &a, &data_colours), "a change of the data colours makes a new map");
    let mut base = a.clone();
    recolour(&mut base["base_map"], &|c| c.map(|x| 255 - x));
    assert!(set_and_check("base-map colours", &a, &base), "a change of the base map's colours keeps the tiles");
}

#[test]
fn a_change_of_structure_makes_a_new_map() {
    let a = look_json();
    let mut b = a.clone();
    for c in b["roads"]["classes"].as_object_mut().unwrap().values_mut() {
        c["minzoom"] = json!(c["minzoom"].as_f64().unwrap_or(0.0) + 2.0);
    }
    assert!(!set_and_check("class minzoom", &a, &b), "another first zoom of the classes changes the tiles: set_look refuses it");
}

/// The leaves of a JSON value that a random change can change: colours, numbers and flags, with their paths.
fn leaves(v: &Value, path: &mut Vec<String>, out: &mut Vec<Vec<String>>) {
    match v {
        Value::Object(o) => for (k, x) in o {
            path.push(k.clone());
            leaves(x, path, out);
            path.pop();
        },
        Value::Array(a) => for (i, x) in a.iter().enumerate() {
            path.push(i.to_string());
            leaves(x, path, out);
            path.pop();
        },
        Value::Number(_) | Value::Bool(_) => out.push(path.clone()),
        Value::String(s) if s.starts_with('#') => out.push(path.clone()),
        _ => {}
    }
}

fn at<'a>(v: &'a mut Value, path: &[String]) -> &'a mut Value {
    path.iter().fold(v, |v, k| match v { Value::Array(a) => &mut a[k.parse::<usize>().unwrap()], _ => &mut v[k.as_str()] })
}

/// Random changes of one to three values of the look (a fixed seed: the same changes on each run). A change that `set_look` keeps must give
/// the new map's tiles and style.
#[test]
fn random_changes_keep_the_tiles_only_when_they_are_the_same() {
    let a = look_json();
    let mut paths = Vec::new();
    leaves(&a, &mut Vec::new(), &mut paths);
    // the dock colours (the data dock's objects) are out of the pool: they are not in the map, and their leaves would move the seeded choices
    paths.retain(|p| p[0] != "schema_version" && p[0] != "dock");
    let mut seed: u64 = 20261104;
    let mut next = |n: usize| {
        seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        ((seed >> 33) as usize) % n
    };
    let (mut kept, mut refused) = (0, 0);
    for trial in 0..40 {
        let mut b = a.clone();
        let mut what = Vec::new();
        for _ in 0..(1 + next(3)) {
            let p = &paths[next(paths.len())];
            let v = at(&mut b, p);
            *v = match v.clone() {
                Value::Bool(x) => json!(!x),
                Value::Number(n) if n.is_i64() => json!(n.as_i64().unwrap() + 1),
                Value::Number(n) => json!((n.as_f64().unwrap() * 1.37 * 1000.0).round() / 1000.0),
                Value::String(_) => json!(format!("#{:06x}", next(0xffffff))),
                x => x,
            };
            what.push(p.join("."));
        }
        if set_and_check(&format!("trial {trial} ({})", what.join(", ")), &a, &b) { kept += 1 } else { refused += 1 }
    }
    println!("random changes: {kept} kept the tiles (and gave the new map's tiles and style), {refused} needed a new map");
}

/// Each value of the sections that the stage-1 key leaves out (`arrows`, and `labels` but its `slots` and `slot_m`), changed one at a time: a change
/// that `set_look` keeps gives the new map's tiles and style. Most of them must be kept: they are the values that the themes change (the halo, the
/// sizes of the names and arrows).
#[test]
fn each_label_and_arrow_value_keeps_the_tiles_only_when_they_are_the_same() {
    let a = look_json();
    let mut paths = Vec::new();
    for s in ["labels", "arrows"] {
        leaves(&a[s], &mut vec![s.to_string()], &mut paths);
    }
    paths.retain(|p| !(p[0] == "labels" && p.get(1).is_some_and(|k| k == "slots" || k == "slot_m")));
    let (mut kept, mut refused) = (0, 0);
    for p in &paths {
        let mut b = a.clone();
        let v = at(&mut b, p);
        *v = match v.clone() {
            Value::Bool(x) => json!(!x),
            Value::Number(n) if n.is_i64() => json!(n.as_i64().unwrap() + 1),
            Value::Number(n) => json!((n.as_f64().unwrap() * 1.37 * 1000.0).round() / 1000.0),
            _ => json!("#123456"),
        };
        if set_and_check(&p.join("."), &a, &b) { kept += 1 } else { refused += 1 }
    }
    println!("label and arrow values: {kept} kept the tiles, {refused} needed a new map, of {}", paths.len());
    assert!(kept > refused, "most label and arrow values are style only");
}
