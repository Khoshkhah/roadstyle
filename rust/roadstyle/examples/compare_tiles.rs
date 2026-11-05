//! Do the tiles of two looks differ? Stage 1 and the live map of each look, the tiles around a point at some zooms, compared byte by byte.
//!
//!     cargo run --release -p roadstyle --example compare_tiles -- <roads.parquet> <features.parquet> <levels.json> <lookA.json> <lookB.json> <lon> <lat>
fn tile_of(lon: f64, lat: f64, z: u32) -> (u32, u32) {
    let n = f64::from(1u32 << z);
    let x = ((lon + 180.0) / 360.0 * n).floor() as u32;
    let y = ((1.0 - (lat.to_radians().tan() + 1.0 / lat.to_radians().cos()).ln() / std::f64::consts::PI) / 2.0 * n).floor() as u32;
    (x, y)
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let read = |p: &str| std::fs::read(p).unwrap_or_else(|e| panic!("{p}: {e}"));
    let levels: serde_json::Value = serde_json::from_slice(&read(&a[2])).unwrap();
    let look = |p: &str| roadstyle::Look::from_json(&String::from_utf8(read(p)).unwrap()).unwrap().with_arg("levels", levels.clone()).unwrap();
    let (roads, features) = (read(&a[0]), read(&a[1]));
    let (lon, lat): (f64, f64) = (a[5].parse().unwrap(), a[6].parse().unwrap());
    let mut maps = Vec::new();
    for p in [&a[3], &a[4]] {
        let l = look(p);
        let s = roadstyle::style_sources(roads.clone(), &l, Some(features.clone()), None, None).unwrap();
        maps.push(roadstyle::relevel::LiveTiles::new(s, l, "rs://1/", &[]).unwrap());
    }
    println!("style text: A {} bytes, B {} bytes, equal: {}", maps[0].style().len(), maps[1].style().len(), maps[0].style() == maps[1].style());
    for z in [6u32, 9, 11, 13, 14, 15, 16] {
        let (cx, cy) = tile_of(lon, lat, z);
        let (mut same, mut total, mut bytes) = (0, 0, 0);
        for dx in 0..3u32 {
            for dy in 0..3u32 {
                let (x, y) = (cx + dx - 1, cy + dy - 1);
                let t0 = maps[0].tile(z, x, y);
                let t1 = maps[1].tile(z, x, y);
                total += 1;
                bytes += t0.len();
                if t0 == t1 { same += 1; }
            }
        }
        println!("z{z:<2}  {same}/{total} tiles are the same  ({bytes} bytes in A)");
    }
}
