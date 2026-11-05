//! The time of `LiveTiles::style_for` and `set_look` (docs/design/restyle_without_retile.md, phases 2 and 3) against a new map, for a look with every
//! colour of a theme changed.
//!
//!     cargo run --release -p roadstyle --example time_style_for -- <roads.parquet> <features.parquet> <levels.json> <look.json>
use serde_json::Value;
use std::time::Instant;

fn recolour(v: &mut Value) {
    match v {
        Value::String(s) if s.len() == 7 && s.starts_with('#') && s[1..].chars().all(|c| c.is_ascii_hexdigit()) => {
            *s = format!("#{}{}{}", &s[5..7], &s[1..3], &s[3..5]);
        }
        Value::Array(a) => a.iter_mut().for_each(recolour),
        Value::Object(o) => o.values_mut().for_each(recolour),
        _ => {}
    }
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let read = |p: &str| std::fs::read(p).unwrap_or_else(|e| panic!("{p}: {e}"));
    let levels: Value = serde_json::from_slice(&read(&a[2])).unwrap();
    let text = String::from_utf8(read(&a[3])).unwrap();
    let look_a = roadstyle::Look::from_json(&text).unwrap().with_arg("levels", levels.clone()).unwrap();
    // every colour as a theme changes them: not the user's data colours (`map`, `data`, `overlays`), which the stage-1 key counts
    let mut j: Value = serde_json::from_str(&text).unwrap();
    j.as_object_mut().unwrap().iter_mut().filter(|(k, _)| !matches!(k.as_str(), "map" | "data" | "overlays")).for_each(|(_, v)| recolour(v));
    let look_b = roadstyle::Look::from_json(&j.to_string()).unwrap().with_arg("levels", levels).unwrap();
    let (roads, features) = (read(&a[0]), read(&a[1]));
    let new = |l: &roadstyle::Look| {
        let s = roadstyle::style_sources(roads.clone(), l, Some(features.clone()), None, None).unwrap();
        roadstyle::relevel::LiveTiles::new(s, l.clone(), "rs://1/", &[]).unwrap()
    };
    let t = Instant::now();
    let mut held = new(&look_a);
    println!("new map (stage 1 and LiveTiles): {:>6.0} ms", t.elapsed().as_secs_f64() * 1e3);
    let mut text_b = String::new();
    for round in 0..3 {
        let t = Instant::now();
        text_b = held.style_for(&look_b).unwrap();
        println!("style_for, round {round}:          {:>6.0} ms  ({} bytes)", t.elapsed().as_secs_f64() * 1e3, text_b.len());
    }
    for round in 0..3 {
        let look = if round % 2 == 0 { &look_b } else { &look_a };
        let t = Instant::now();
        let kept = held.set_look(look).unwrap();
        println!("set_look, round {round}:           {:>6.0} ms  (tiles kept: {kept})", t.elapsed().as_secs_f64() * 1e3);
    }
    let t = Instant::now();
    let fresh = new(&look_b);
    println!("new map of the new look:          {:>6.0} ms; the same style: {}", t.elapsed().as_secs_f64() * 1e3, fresh.style() == text_b);
}
