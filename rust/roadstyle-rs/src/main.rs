//! The native front-end of roadstyle-rs (docs/design/rust_engine.md): the style, natively, with the time of each step.
//!
//!     cargo run --release -- spike/data/look.json spike/data/roads.parquet spike/data/features.parquet spike/data/planner.parquet made.json
//!     (- for no features or no planner)
//!     cargo run --release -- --layers spike/data/look.json spike/data/layers/all/roads.parquet     # the road layers alone, as {"layers": [...]}
//!     cargo run --release -- --tiles look.json roads.parquet features.parquet     # the map with vector tiles: the times and the sizes
//!     cargo run --release -- --bench look.json roads.parquet features.parquet     # each stage: its time, the memory in use after it, its peak

use roadstyle_rs::{layers, read, roads, simple, slots};
use serde_json::{json, Value};
use std::time::Instant;
use std::{env, fs, process};

/// The roads of a table with the contract names (no column keywords): each role's column by its contract name.
fn with_roles(table: roadstyle_rs::RoadTable) -> roadstyle_rs::Roads {
    let roles = roadstyle_rs::Roles::resolve(&table, &[]).unwrap_or_else(|e| fail(e));
    roadstyle_rs::Roads::new(table, roles, None)
}

/// The native program counts its memory (--bench): the bytes in use, and the peak since the last stage.
struct Count;
static NOW: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
static PEAK: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);

unsafe impl std::alloc::GlobalAlloc for Count {
    unsafe fn alloc(&self, l: std::alloc::Layout) -> *mut u8 {
        let n = NOW.fetch_add(l.size(), std::sync::atomic::Ordering::Relaxed) + l.size();
        PEAK.fetch_max(n, std::sync::atomic::Ordering::Relaxed);
        std::alloc::System.alloc(l)
    }
    unsafe fn dealloc(&self, p: *mut u8, l: std::alloc::Layout) {
        NOW.fetch_sub(l.size(), std::sync::atomic::Ordering::Relaxed);
        std::alloc::System.dealloc(p, l)
    }
    unsafe fn realloc(&self, p: *mut u8, l: std::alloc::Layout, size: usize) -> *mut u8 {
        if size > l.size() {
            let n = NOW.fetch_add(size - l.size(), std::sync::atomic::Ordering::Relaxed) + size - l.size();
            PEAK.fetch_max(n, std::sync::atomic::Ordering::Relaxed);
        } else {
            NOW.fetch_sub(l.size() - size, std::sync::atomic::Ordering::Relaxed);
        }
        std::alloc::System.realloc(p, l, size)
    }
}

#[global_allocator]
static ALLOC: Count = Count;

/// --bench: the stages of make_parts one by one (as make_parts runs them), and the text, with the time and the memory of each.
fn bench(look_path: &str, roads_path: &str, features_path: &str) {
    use std::sync::atomic::Ordering::Relaxed;
    let mut t = Instant::now();
    println!("| Stage | Time (ms) | In use after (MB) | Peak in it (MB) |\n|---|---|---|---|");
    let mut mark = |stage: &str| {
        println!("| {stage} | {:.0} | {} | {} |", t.elapsed().as_secs_f64() * 1e3, NOW.load(Relaxed) >> 20, PEAK.load(Relaxed) >> 20);
        PEAK.store(NOW.load(Relaxed), Relaxed);
        t = Instant::now();
    };
    let look = look_file(look_path);
    let mut feats = with_roles(read::read_roads(fs::read(roads_path).unwrap(), "geometry").unwrap_or_else(|e| fail(e)));
    mark("read the roads");
    let colors = roads::mark_roads(&mut feats, &look.road, &look.map).unwrap_or_else(|e| fail(e));
    mark("mark the roads (colours, pairs, levels)");
    let simple = simple::simple_source(&feats, look.road.head_m, look.road.bridge_shadow, None, Vec::new()).unwrap_or_else(|e| fail(e));
    mark("pieces (simple)");
    let slots = slots::slots_source(&feats, &look.slot);
    mark("names and arrows (slots)");
    let mut ovs = Vec::new();
    if features_path != "-" {
        let t = roadstyle_rs::read_features(fs::read(features_path).unwrap()).unwrap_or_else(|e| fail(e));
        let mut tables = roadstyle_rs::features::feature_tables(&t, &look).unwrap_or_else(|e| fail(e));
        let attached = roadstyle_rs::overlays::edge_attach(&mut tables, &feats).unwrap_or_else(|e| fail(e));
        ovs = roadstyle_rs::overlays::feature_overlays(tables, &look, &attached, &mut Vec::new()).0;
    }
    mark("base map");
    let roads = roads::roads_source(feats);
    mark("roads source");
    let layers = layers::road_layers(&look, &roads.roads, &simple, features(&slots), false, &mut ovs, &colors.props, colors.active).unwrap_or_else(|e| fail(e)).0;
    mark("layers");
    let mut text = Vec::new();
    roads.write_json(&mut text).unwrap();
    simple.write_json(&mut text, &roads.roads).unwrap();
    serde_json::to_writer(&mut text, &slots).unwrap();
    mark(&format!("the text of the sources ({} MB, {} layers)", text.len() >> 20, layers.len()));
}

fn fail(msg: impl std::fmt::Display) -> ! {
    eprintln!("{msg}");
    process::exit(1)
}

/// A saved look (version 1 or 0).
fn look_file(p: &str) -> roadstyle_rs::Look {
    roadstyle_rs::Look::from_value(json_file(p)).unwrap_or_else(|e| fail(e))
}

fn json_file(path: &str) -> Value {
    let text = fs::read_to_string(path).unwrap_or_else(|e| fail(format!("{path}: {e}")));
    serde_json::from_str(&text).unwrap_or_else(|e| fail(format!("{path}: not JSON: {e}")))
}

fn features(source: &Value) -> &[Value] {
    source["data"]["features"].as_array().map_or(&[][..], |v| v.as_slice())
}

/// --sources: stage 1.
fn sources_mode(args: &[String]) {
    // stage 1: the sources as files (geojson or geoparquet) in a folder, with the time and each file's size
    let opt = |p: &str| (p != "-").then(|| fs::read(p).unwrap_or_else(|e| fail(format!("{p}: {e}"))));
    let format = if args[6] == "geoparquet" { roadstyle_rs::Format::GeoParquet } else { roadstyle_rs::Format::GeoJson };
    let t = Instant::now();
    let s = roadstyle_rs::style_sources(fs::read(&args[3]).unwrap(), &look_file(&args[2]), opt(&args[4]), None, None)
        .unwrap_or_else(|e| fail(e));
    let made = t.elapsed();
    let files = roadstyle_rs::write_sources(&s, std::path::Path::new(&args[5]), format, &[]).unwrap_or_else(|e| fail(e));
    eprintln!("style_sources {:.0} ms, save {:.0} ms", made.as_secs_f64() * 1e3, (t.elapsed() - made).as_secs_f64() * 1e3);
    for (f, n) in &files {
        println!("{f}\t{n}");
    }
    println!("total\t{}", files.iter().map(|f| f.1).sum::<usize>());
}

/// --tile-files.
fn tile_files_mode(args: &[String]) {
    // stage 2 from stage 1's files: the time, and the tiles of zoom 15 around the roads (their number and size)
    let t = Instant::now();
    let (style, tiles) = roadstyle_rs::tiles_of_files(std::path::Path::new(&args[2]), &[], None, &roadstyle_rs::xyz_at("")).unwrap_or_else(|e| fail(e));
    let made = t.elapsed();
    let c = &style["center"];
    let (lon, lat) = (c[0].as_f64().unwrap_or(0.0), c[1].as_f64().unwrap_or(0.0));
    let n = (1u64 << 15) as f64;
    let (x, y) = (((lon + 180.0) / 360.0 * n) as i64, ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n) as i64);
    let t2 = Instant::now();
    let (mut count, mut bytes) = (0, 0);
    for dx in -8..=8 {
        for dy in -8..=8 {
            let b = tiles.tile(15, (x + dx) as u32, (y + dy) as u32);
            count += !b.is_empty() as usize;
            bytes += b.len();
        }
    }
    eprintln!("tiles_of_files {:.0} ms; z15 around the centre: {count} tiles, {:.1} MB, {:.0} ms", made.as_secs_f64() * 1e3,
              bytes as f64 / 1e6, t2.elapsed().as_secs_f64() * 1e3);
}

/// --features.
fn features_mode(args: &[String]) {
    // step 3 check: the base-map feature collections from the worker's features.parquet, as {name: FeatureCollection}
    let data = fs::read(&args[3]).unwrap_or_else(|e| fail(format!("{}: {e}", args[3])));
    let t = roadstyle_rs::read_features(data).unwrap_or_else(|e| fail(e));
    let tables = roadstyle_rs::features::feature_tables(&t, &look_file(&args[2])).unwrap_or_else(|e| fail(e));
    let fcs: serde_json::Map<String, serde_json::Value> = tables.iter().map(|(n, t)| (n.clone(), t.to_value())).collect();
    println!("{}", serde_json::to_string(&fcs).unwrap());
}

/// --tiles.
fn tiles_mode(args: &[String]) {
    // the map with vector tiles (tiled_from_parquet), then every tile around the centre at zooms 12, 14 and 15: the times and sizes
    let read = |p: &str| if p == "-" { None } else { Some(fs::read(p).unwrap_or_else(|e| fail(format!("{p}: {e}")))) };
    let t = Instant::now();
    let (style, tiles, _) = roadstyle_rs::tiled_from_parquet(read(&args[3]).unwrap(), &look_file(&args[2]), read(&args[4]), None,
                                                    "rs://", &["osm_id".into(), "access".into()]).unwrap_or_else(|e| fail(e));
    eprintln!("tiled_from_parquet {:.0} ms (style {:.1} KB)", t.elapsed().as_secs_f64() * 1e3, style.len() as f64 / 1e3);
    let style: Value = serde_json::from_str(&style).unwrap();
    let c = &style["center"];
    let (lon, lat) = (c[0].as_f64().unwrap(), c[1].as_f64().unwrap());
    for z in [12u32, 14, 15] {
        let n = (1u64 << z) as f64;
        let (x, y) = ((lon + 180.0) / 360.0 * n, (1.0 - (lat.to_radians().tan() + 1.0 / lat.to_radians().cos()).ln() / std::f64::consts::PI) / 2.0 * n);
        let r = (8u32 << (z - 12)) / 2; // about 8 km around the centre
        let t = Instant::now();
        let (mut count, mut bytes, mut most) = (0, 0usize, 0usize);
        for tx in (x as u32).saturating_sub(r)..=(x as u32 + r) {
            for ty in (y as u32).saturating_sub(r)..=(y as u32 + r) {
                let all = tiles.tile(z, tx, ty).len();
                if all > 0 {
                    count += 1;
                    bytes += all;
                    most = most.max(all);
                }
            }
        }
        eprintln!("z{z}: {count} tiles with data, {:.1} MB, the largest {:.0} KB, {:.2} ms a tile", bytes as f64 / 1e6, most as f64 / 1e3,
                  t.elapsed().as_secs_f64() * 1e3 / count.max(1) as f64);
    }
}

/// --layers: the road layers alone, for the 12 subsets of tools/make_layer_goldens.py (no base map).
fn layers_mode(args: &[String]) {
    let (look_path, roads_path) = (&args[2], &args[3]);
    let look = look_file(look_path);
    let data = fs::read(roads_path).unwrap_or_else(|e| fail(format!("{roads_path}: {e}")));
    let mut feats = with_roles(read::read_roads(data, "geometry").unwrap_or_else(|e| fail(format!("{roads_path}: {e}"))));
    let colors = roads::mark_roads(&mut feats, &look.road, &look.map).unwrap_or_else(|e| fail(e));
    let simple = simple::simple_source(&feats, look.road.head_m, look.road.bridge_shadow, None, Vec::new()).unwrap_or_else(|e| fail(e));
    let slots = slots::slots_source(&feats, &look.slot);
    let roads = roads::roads_source(feats);
    let layers = layers::road_layers(&look, &roads.roads, &simple, features(&slots), false, &mut [], &colors.props, colors.active).unwrap_or_else(|e| fail(e)).0;
    println!("{}", json!({"layers": layers}));
}

/// The whole style, as the worker makes it (inline_style), with the total time.
fn style_mode(args: &[String]) {
    let look = look_file(&args[1]);
    let data = fs::read(&args[2]).unwrap_or_else(|e| fail(format!("{}: {e}", args[2])));
    let opt = |i: usize| if args[i] == "-" { None } else { Some(fs::read(&args[i]).unwrap_or_else(|e| fail(format!("{}: {e}", args[i])))) };
    let (fdata, pdata) = (opt(3), opt(4));
    let t = Instant::now();
    let text = roadstyle_rs::inline_style(data, &look, fdata, pdata, None).unwrap_or_else(|e| fail(e));
    let dt = t.elapsed();
    fs::write(&args[5], &text).unwrap_or_else(|e| fail(format!("{}: {e}", args[5])));
    eprintln!("inline_style {:.0} ms ({:.1} MB)", dt.as_secs_f64() * 1e3, text.len() as f64 / 1e6);
}

fn main() {
    let args: Vec<String> = env::args().collect();
    match (args.len(), args.get(1).map(String::as_str)) {
        (5, Some("--bench")) => bench(&args[2], &args[3], &args[4]),
        (7, Some("--sources")) => sources_mode(&args),
        (3, Some("--tile-files")) => tile_files_mode(&args),
        (4, Some("--features")) => features_mode(&args),
        (5, Some("--tiles")) => tiles_mode(&args),
        (4, Some("--layers")) => layers_mode(&args),
        (6, _) => style_mode(&args),
        _ => fail("usage: roadstyle-rs <look.json> <roads.parquet> <features.parquet | -> <planner.parquet | -> <out.json>  |  \
                   roadstyle-rs --layers <look.json> <roads.parquet>"),
    }
}
