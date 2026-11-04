//! For each look file of a folder: does its map make the same tiles as the map of the first look (`base`), and does `set_look` keep the tiles?
//! The tiles: 3 x 3 around a point at zooms 9 to 16.
//!
//!     cargo run --release -p roadstyle --example theme_tiles -- <roads.parquet> <features.parquet> <levels.json> <base look> <folder> <lon> <lat>
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let read = |p: &str| std::fs::read(p).unwrap_or_else(|e| panic!("{p}: {e}"));
    let levels: serde_json::Value = serde_json::from_slice(&read(&a[2])).unwrap();
    let look = |p: &str| roadstyle::Look::from_json(&String::from_utf8(read(p)).unwrap()).unwrap().with_arg("levels", levels.clone()).unwrap();
    let (roads, features) = (read(&a[0]), read(&a[1]));
    let (lon, lat): (f64, f64) = (a[5].parse().unwrap(), a[6].parse().unwrap());
    let new = |l: &roadstyle::Look| {
        let s = roadstyle::style_sources(roads.clone(), l, Some(features.clone()), None, None).unwrap();
        roadstyle::relevel::LiveTiles::new(s, l.clone(), "rs://1/", &[]).unwrap()
    };
    let tiles = |m: &mut roadstyle::relevel::LiveTiles| -> Vec<Vec<u8>> {
        let mut out = Vec::new();
        for z in 9..=16u32 {
            let n = f64::from(1u32 << z);
            let x = ((lon + 180.0) / 360.0 * n) as u32;
            let y = ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n) as u32;
            for (dx, dy) in (0..3u32).flat_map(|a| (0..3u32).map(move |b| (a, b))) {
                out.push(m.tile(z, x + dx - 1, y + dy - 1));
            }
        }
        out
    };
    let base = look(&a[3]);
    let base_tiles = tiles(&mut new(&base));
    let mut names: Vec<_> = std::fs::read_dir(&a[4]).unwrap().map(|e| e.unwrap().path()).collect();
    names.sort();
    for p in names {
        let l = look(p.to_str().unwrap());
        let these = tiles(&mut new(&l));
        let same = these == base_tiles;
        let bytes = |t: &[Vec<u8>]| t.iter().map(Vec::len).sum::<usize>();
        print!("{:>+6.1}% bytes  ", 100.0 * (bytes(&these) as f64 / bytes(&base_tiles) as f64 - 1.0));
        let mut held = new(&base);
        let why = held.set_look_why(&l).unwrap();
        let kept = why.is_none();
        // a kept look: the held tiles must be the new look's tiles cut with the held buffers
        let wrong = kept && {
            let s = roadstyle::style_sources(roads.clone(), &l, Some(features.clone()), None, None).unwrap();
            let mut oracle = roadstyle::relevel::LiveTiles::with_buffers(s, l.clone(), "rs://1/", &[], Some(held.options().buffers.clone())).unwrap();
            tiles(&mut held) != tiles(&mut oracle)
        };
        println!("{:<14} same tiles: {:<5} set_look kept: {:<5} {} {}", p.file_stem().unwrap().to_str().unwrap(), same, kept,
                 if wrong { "WRONG" } else if same && !kept { "(a refusal that was not needed)" } else { "" }, why.unwrap_or_default());
    }
}
