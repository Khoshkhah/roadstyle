//! The tile buffer of each zoom for each look of a folder, against the buffer of the first look (`base`): the largest ratio over the zooms.
//!
//!     cargo run --release -p roadstyle --example theme_buffers -- <roads.parquet> <features.parquet> <levels.json> <base look> <folder>
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let read = |p: &str| std::fs::read(p).unwrap_or_else(|e| panic!("{p}: {e}"));
    let levels: serde_json::Value = serde_json::from_slice(&read(&a[2])).unwrap();
    let look = |p: &str| roadstyle::Look::from_json(&String::from_utf8(read(p)).unwrap()).unwrap().with_arg("levels", levels.clone()).unwrap();
    let (roads, features) = (read(&a[0]), read(&a[1]));
    let buffers = |l: &roadstyle::Look| {
        let s = roadstyle::style_sources(roads.clone(), l, Some(features.clone()), None, None).unwrap();
        roadstyle::relevel::LiveTiles::new(s, l.clone(), "rs://1/", &[]).unwrap().options().buffers.clone()
    };
    let base = buffers(&look(&a[3]));
    println!("base buffers (px, zoom 0 to max): {:?}", base.iter().map(|b| (b * 10.0).round() / 10.0).collect::<Vec<_>>());
    let mut names: Vec<_> = std::fs::read_dir(&a[4]).unwrap().map(|e| e.unwrap().path()).collect();
    names.sort();
    for p in names {
        let b = buffers(&look(p.to_str().unwrap()));
        let ratio = b.iter().zip(&base).map(|(x, y)| x / y).fold(0.0f64, f64::max);
        println!("{:<14} largest ratio {:.3}", p.file_stem().unwrap().to_str().unwrap(), ratio);
    }
}
