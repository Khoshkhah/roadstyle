//! Stage 2 from stage 1's files (docs/rust/architecture.md, "The three stages and the one call"): the tiles that tile_files makes from
//! the saved GeoJSON files and from the saved GeoParquet files are the tiles of make_tiled (the one call), decoded: each tile layer's
//! features with their ids, properties and geometry, in every tile of the roads' box at zooms 12, 14 and 15.

mod common;

use std::path::PathBuf;

fn data(p: &str) -> Vec<u8> {
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p);
    std::fs::read(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

fn same_tiles(area: &str) {
    let mut look: serde_json::Value = serde_json::from_slice(&data("look.json")).unwrap();
    look["args"]["arrows"] = true.into();
    look["args"]["labels"] = true.into();
    look["args"]["export"] = true.into();        // export_style's two stages (audit N2)
    let look = look.to_string();
    let (roads, features) = (data(&format!("{area}/roads.parquet")), data(&format!("{area}/features.parquet")));
    let keep = ["osm_id".to_string(), "access".to_string()];
    let (_, one) = roadstyle_rs::make_tiled(roads.clone(), &look, Some(features.clone()), None, "rs://", &keep).unwrap();
    let s = roadstyle_rs::make_sources(roads.clone(), &look, Some(features), None, None).unwrap();
    let dir = std::env::temp_dir().join(format!("roadstyle-stages-{area}-{}", std::process::id()));
    let mut by_file = Vec::new();
    for (f, sub) in [(roadstyle_rs::Format::GeoJson, "geojson"), (roadstyle_rs::Format::GeoParquet, "geoparquet")] {
        roadstyle_rs::save_sources(&s, &dir.join(sub), f, &keep).unwrap();
        by_file.push((sub, roadstyle_rs::tile_files(&dir.join(sub), &keep, None, &roadstyle_rs::xyz_at("")).unwrap().1));
    }
    let t = roadstyle_rs::read::read_roads(roads, "geometry").unwrap();
    let (mut x0, mut y0, mut x1, mut y1) = (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY);
    for c in (0..t.len()).filter_map(|i| t.line(i)).flatten() {
        (x0, y0, x1, y1) = (x0.min(c[0]), y0.min(c[1]), x1.max(c[0]), y1.max(c[1]));
    }
    let mut n = 0;
    for z in [12u32, 14, 15] {
        let k = (1u64 << z) as f64;
        let tx = |lon: f64| ((lon + 180.0) / 360.0 * k) as u32;
        let ty = |lat: f64| ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * k) as u32;
        for x in tx(x0)..=tx(x1) {
            for y in ty(y1)..=ty(y0) {
                let want = common::decode_tile(&one.tile(z, x, y));
                n += want.values().map(Vec::len).sum::<usize>();
                for (sub, tiles) in &by_file {
                    assert!(common::decode_tile(&tiles.tile(z, x, y)) == want, "{area} {z}/{x}/{y}: the tiles from the {sub} files differ");
                }
            }
        }
    }
    assert!(n > 0, "{area}: no features in the tiles");
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn monaco_tiles_from_the_files() {
    same_tiles("monaco");
}

#[test]
#[ignore = "Tartu: about 30 s; CI runs it with the ignored goldens"]
fn tartu_tiles_from_the_files() {
    same_tiles("tartu");
}
