//! The browser's front-end of roadstyle-rs (docs/design/rust_engine.md): `makeStyle`, `Tiler` and `memoryBytes` through
//! wasm-bindgen, and the allocator that grows the memory in large steps. Natively the crate is empty.

/// The allocator in the browser: the standard one (dlmalloc), but when it grows the memory, the memory grows once more by its size (16 to
/// 256 MB) in one step, and the allocator keeps that block free for the next allocations. dlmalloc alone grows the memory 64 KB at a time,
/// thousands of steps for Monaco, and in Edge on Windows each step is slow: the first style took 14 to 21 s there, 3 s with the memory grown first.
#[cfg(target_arch = "wasm32")]
mod grow {
    use core::arch::wasm32::memory_size;
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};

    static PAGES: AtomicUsize = AtomicUsize::new(0); // the memory's size (64 KB pages) after the last step ahead

    fn ahead() {
        let now = memory_size(0);
        if now != PAGES.load(Relaxed) {
            let l = Layout::from_size_align((now << 16).clamp(16 << 20, 256 << 20), 16).unwrap();
            unsafe {
                let p = System.alloc(l); // null when the memory cannot grow: then nothing is taken ahead
                if !p.is_null() {
                    System.dealloc(p, l);
                }
            }
            PAGES.store(memory_size(0), Relaxed);
        }
    }

    struct Ahead;

    unsafe impl GlobalAlloc for Ahead {
        unsafe fn alloc(&self, l: Layout) -> *mut u8 {
            let p = System.alloc(l);
            ahead();
            p
        }
        unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
            let p = System.alloc_zeroed(l);
            ahead();
            p
        }
        unsafe fn realloc(&self, p: *mut u8, l: Layout, size: usize) -> *mut u8 {
            let q = System.realloc(p, l, size);
            ahead();
            q
        }
        unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
            System.dealloc(p, l)
        }
    }

    #[global_allocator]
    static ALLOC: Ahead = Ahead;
}

#[cfg(target_arch = "wasm32")]
mod wasm {
    use wasm_bindgen::prelude::*;

    /// makeStyle(roads: Uint8Array, look: string, features?: Uint8Array, planner?: Uint8Array, name?: string) -> string; an error is a thrown Error.
    #[wasm_bindgen(js_name = makeStyle)]
    pub fn make_style(parquet: Vec<u8>, look: &str, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<String, JsError> {
        roadstyle_rs::make_style(parquet, look, features, planner, name).map_err(|e| JsError::new(&e))
    }

    /// A map with vector tiles: `new Tiler(roads, look, features?, name?, prefix, keep)`, then `style()` (the style's JSON text) and
    /// `tile(source, z, x, y)` (a vector tile, empty when nothing is in it) for each request of the map, and `props(layer, id)` (the
    /// tile layer, for example `roads`).
    #[wasm_bindgen]
    pub struct Tiler {
        style: String,
        tiles: roadstyle_rs::tiles::Tiles,
    }

    #[wasm_bindgen]
    impl Tiler {
        #[wasm_bindgen(constructor)]
        pub fn new(parquet: Vec<u8>, look: &str, features: Option<Vec<u8>>, name: Option<String>, prefix: &str, keep: Vec<String>)
                   -> Result<Tiler, JsError> {
            let (style, tiles) = roadstyle_rs::make_tiled(parquet, look, features, name, prefix, &keep).map_err(|e| JsError::new(&e))?;
            Ok(Tiler { style, tiles })
        }

        pub fn style(&self) -> String {
            self.style.clone()
        }

        /// `source` is the style's one source, `roads`: the tile has a layer for each of the old sources.
        pub fn tile(&self, source: &str, z: u32, x: u32, y: u32) -> Vec<u8> {
            if source == roadstyle_rs::tiles::SOURCE { self.tiles.tile(z, x, y) } else { Vec::new() }
        }

        /// The properties of the feature `id` of a source, as JSON (`null` when there is none).
        pub fn props(&self, source: &str, id: u32) -> String {
            self.tiles.props(source, id as u64)
        }
    }

    /// makeLook(options: string) -> string: the look (look.json) of render_edges' palette, profile and settings (roadstyle-rs look.rs);
    /// options: {"palette", "profile", "settings", "args", "features"} as JSON text. An error is a thrown Error.
    #[wasm_bindgen(js_name = makeLook)]
    pub fn make_look(options: &str) -> Result<String, JsError> {
        let o: serde_json::Value = serde_json::from_str(options).map_err(|e| JsError::new(&format!("options: not JSON: {e}")))?;
        roadstyle_rs::look::make_look(&o).map(|l| l.to_string()).map_err(|e| JsError::new(&e))
    }

        /// The size of the module's memory, in bytes.
    #[wasm_bindgen(js_name = memoryBytes)]
    pub fn memory_bytes() -> usize {
        core::arch::wasm32::memory_size(0) * 65536
    }
}
