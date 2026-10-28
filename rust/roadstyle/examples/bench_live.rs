//! The level editor's map (relevel::LiveTiles, the wasm LiveMap) on a large area: the first tiles of each view on a new map, with
//! the memory that they take. `views.json`: [[name, [[z, x, y], ...]], ...].
//!
//!     cargo run --release -p roadstyle --example bench_live -- <roads.parquet> <levels.json> <look.json> <views.json>

use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};
use std::time::Instant;

struct Count;
static NOW: AtomicUsize = AtomicUsize::new(0);

unsafe impl std::alloc::GlobalAlloc for Count {
    unsafe fn alloc(&self, l: std::alloc::Layout) -> *mut u8 {
        NOW.fetch_add(l.size(), Relaxed);
        std::alloc::System.alloc(l)
    }
    unsafe fn dealloc(&self, p: *mut u8, l: std::alloc::Layout) {
        NOW.fetch_sub(l.size(), Relaxed);
        std::alloc::System.dealloc(p, l)
    }
}

#[global_allocator]
static ALLOC: Count = Count;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let read = |p: &str| std::fs::read(p).unwrap_or_else(|e| panic!("{p}: {e}"));
    let look = roadstyle::Look::from_json(&String::from_utf8(read(&a[2])).unwrap()).unwrap()
        .with_arg("levels", serde_json::from_slice(&read(&a[1])).unwrap()).unwrap();
    let views: Vec<(String, Vec<[u32; 3]>)> = serde_json::from_slice(&read(&a[3])).unwrap();
    let roads = read(&a[0]);
    for (name, tiles) in &views {
        let s = roadstyle::style_sources(roads.clone(), &look, None, None, None).unwrap();
        let mut live = roadstyle::relevel::LiveTiles::new(s, look.clone(), "", &[]).unwrap();
        let (before, t) = (NOW.load(Relaxed), Instant::now());
        let bytes: usize = tiles.iter().map(|&[z, x, y]| live.tile(z, x, y).len()).sum();
        println!("{name:<12} {:>3} tiles  {:>5.0} ms  {:.2} MB  (+{:.0} MB memory)", tiles.len(), t.elapsed().as_secs_f64() * 1e3, bytes as f64 / 1e6,
                 (NOW.load(Relaxed) as f64 - before as f64) / 1e6);
    }
}
