//! The time of each step that a change of the look repeats: stage 1 (`style_sources`), the live map (`LiveTiles::new`) and `restyle` (the roads of stage 1, the new look, no read).
//!
//!     cargo run --release -p roadstyle --example time_restyle -- <roads.parquet> <features.parquet> <levels.json> <look.json>
use std::time::Instant;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let read = |p: &str| std::fs::read(p).unwrap_or_else(|e| panic!("{p}: {e}"));
    let look = roadstyle::Look::from_json(&String::from_utf8(read(&a[3])).unwrap()).unwrap()
        .with_arg("levels", serde_json::from_slice(&read(&a[2])).unwrap()).unwrap();
    let (roads, features) = (read(&a[0]), read(&a[1]));
    for round in 0..2 {
        let t = Instant::now();
        let s = roadstyle::style_sources(roads.clone(), &look, Some(features.clone()), None, None).unwrap();
        println!("round {round}: style_sources {:>6.0} ms", t.elapsed().as_secs_f64() * 1e3);
        let t = Instant::now();
        let r = roadstyle_engine::restyle(&s, &look).unwrap();
        println!("          restyle       {:>6.0} ms  ({} layers, {} sources)", t.elapsed().as_secs_f64() * 1e3, r.layers.len(), r.sources.len());
        let t = Instant::now();
        let live = roadstyle::relevel::LiveTiles::new(s, look.clone(), "rs://1/", &[]).unwrap();
        println!("          LiveTiles::new {:>5.0} ms  (style {} bytes)", t.elapsed().as_secs_f64() * 1e3, live.style().len());
    }
}
