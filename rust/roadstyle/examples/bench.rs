//! The stages of roadstyle on Monaco and Tartu (review 4, D9): the time of each, the peak of the memory in use during it and the memory
//! in use after it, as docs/rust/parity.md gives them. Tartu's files come from rust/roadstyle-rs/tests/get_goldens.sh.
//!
//!     cargo run --release -p roadstyle --example bench [-- <data folder>]     # default: rust/roadstyle-rs/tests/data

use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
use std::time::Instant;

/// The bytes in use, and their peak since the last step.
struct Count;
static NOW: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);

unsafe impl std::alloc::GlobalAlloc for Count {
    unsafe fn alloc(&self, l: std::alloc::Layout) -> *mut u8 {
        PEAK.fetch_max(NOW.fetch_add(l.size(), Relaxed) + l.size(), Relaxed);
        std::alloc::System.alloc(l)
    }
    unsafe fn dealloc(&self, p: *mut u8, l: std::alloc::Layout) {
        NOW.fetch_sub(l.size(), Relaxed);
        std::alloc::System.dealloc(p, l)
    }
    unsafe fn realloc(&self, p: *mut u8, l: std::alloc::Layout, size: usize) -> *mut u8 {
        if size > l.size() {
            PEAK.fetch_max(NOW.fetch_add(size - l.size(), Relaxed) + size - l.size(), Relaxed);
        } else {
            NOW.fetch_sub(l.size() - size, Relaxed);
        }
        std::alloc::System.realloc(p, l, size)
    }
}

#[global_allocator]
static ALLOC: Count = Count;

/// Runs `f` as one step and prints its time, its peak and the memory in use after it.
fn step<T>(name: &str, f: impl FnOnce() -> T) -> T {
    PEAK.store(NOW.load(Relaxed), Relaxed);
    let t = Instant::now();
    let out = f();
    let mb = |b: usize| b as f64 / 1e6;
    println!("  {name:<28} {:>8.0} ms   peak {:>7.1} MB   after {:>7.1} MB", t.elapsed().as_secs_f64() * 1e3, mb(PEAK.load(Relaxed)),
             mb(NOW.load(Relaxed)));
    out
}

fn main() {
    let dir = std::path::PathBuf::from(std::env::args().nth(1).unwrap_or_else(|| {
        concat!(env!("CARGO_MANIFEST_DIR"), "/../roadstyle-rs/tests/data").into()
    }));
    let read = |p: std::path::PathBuf| std::fs::read(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    let look = roadstyle::Look::from_json(&String::from_utf8(read(dir.join("look.json"))).unwrap()).unwrap();
    for area in ["monaco", "tartu"] {
        let a = dir.join(area);
        if !a.join("roads.parquet").exists() {
            println!("{area}: no roads.parquet (tests/get_goldens.sh gets Tartu)");
            continue;
        }
        println!("{area}:");
        let (roads, features) = step("read the roads and base map", || {
            (roadstyle::read::read_roads(read(a.join("roads.parquet")), "geometry").unwrap(),
             roadstyle::read_features(read(a.join("features.parquet"))).unwrap())
        });
        println!("  ({} roads)", roads.len());
        let (page_roads, page_features) = (roads.clone(), features.clone());
        let s = step("stage 1 (sources_of)", || roadstyle::sources_of(roads, &look, Some(features), None, None).unwrap());
        let style = step("stage 1 as text (write_style)", || {
            let mut out = Vec::new();
            s.write_style(&mut out, roadstyle::sources::SourceMode::INLINE).unwrap();
            out.len()
        });
        println!("  (the style: {:.1} MB)", style as f64 / 1e6);
        let (tstyle, tiles) = step("stage 2 (tile_stage)", || {
            let o = roadstyle::tiles::stage::TileOptions::new(&s.layers, &s.metadata, &s.saved[roadstyle::tiles::stage::TILES],
                                                             &s.saved[roadstyle::tiles::stage::COLUMNS], &[]).unwrap();
            roadstyle::tile_stage(&s, &o, &roadstyle::xyz_at(""), roadstyle::sources::SourceMode::INLINE).unwrap()
        });
        let archive = step("stage 2's archive (PMTiles)", || tiles.archive(tiles.bounds().unwrap(), &tiles.layer_names()).unwrap().len());
        println!("  (the archive: {:.1} MB; the tiled style: {:.1} KB)", archive as f64 / 1e6, roadstyle::style_text(&s, &tstyle).len() as f64 / 1e3);
        drop((s, tiles));
        let live = look.clone().with_arg("state", "live".into()).unwrap();
        let options = roadstyle::look::Options::default();
        for compress in [false, true] {
            let given = serde_json::json!({"compress": compress}).as_object().unwrap().clone();
            let (r, f) = (page_roads.clone(), page_features.clone());
            let html = step(&format!("the page (compress={compress})"), || {
                roadstyle::page_options::page_from(r, Some(f), &live, &options, &given).unwrap().html.len()
            });
            println!("  (the page: {:.1} MB)", html as f64 / 1e6);
        }
    }
}
