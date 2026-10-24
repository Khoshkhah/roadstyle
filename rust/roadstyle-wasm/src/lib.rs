//! The browser's front-end of roadstyle-rs (docs/design/rust_engine.md): `makeStyle`, `makePage`, `Tiler` and `memoryBytes` through
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
        roadstyle::make_style(parquet, look, features, planner, name).map_err(|e| JsError::new(&e))
    }

    /// makePage(style: string, page: string, parts: string, pmtiles?: Uint8Array) -> string: the page of a live style (state "live") with
    /// the dashboard's options (roadstyle::page; MapLibre stays a placeholder).
    #[wasm_bindgen(js_name = makePage)]
    pub fn make_page(style: &str, page: &str, parts: &str, pmtiles: Option<Vec<u8>>) -> Result<String, JsError> {
        roadstyle::page::make_page(style, page, parts, pmtiles.as_deref()).map_err(|e| JsError::new(&e))
    }

    /// exportLook(look: string, cols: string[] (highway, oneway, tunnel, bridge, id), positions: number[]) -> string: the simple look
    /// for another app's data layer (roadstyle's export_look) from a resolved look.
    #[wasm_bindgen(js_name = exportLook)]
    pub fn export_look(look: &str, cols: Vec<String>, positions: Vec<i32>) -> Result<String, JsError> {
        let look: serde_json::Value = serde_json::from_str(look).map_err(|e| JsError::new(&e.to_string()))?;
        let c = |i: usize| cols.get(i).map(String::as_str).unwrap_or(["highway", "oneway", "tunnel", "bridge", "edge_id"][i]);
        let lc = roadstyle::export_look::LookCols { highway: c(0), oneway: c(1), tunnel: c(2), bridge: c(3), id: c(4) };
        let ps: Vec<i64> = positions.into_iter().map(i64::from).collect();
        roadstyle::export_look::export_look(&look, &lc, &ps).map(|v| v.to_string()).map_err(|e| JsError::new(&e))
    }

    /// A map with vector tiles: `new Tiler(roads, look, features?, name?, prefix, keep)`, then `style()` (the style's JSON text) and
    /// `tile(source, z, x, y)` (a vector tile, empty when nothing is in it) for each request of the map, and `props(layer, id)` (the
    /// tile layer, for example `roads`).
    #[wasm_bindgen]
    pub struct Tiler {
        style: String,
        tiles: roadstyle::tiles::Tiles,
    }

    #[wasm_bindgen]
    impl Tiler {
        #[wasm_bindgen(constructor)]
        pub fn new(parquet: Vec<u8>, look: &str, features: Option<Vec<u8>>, name: Option<String>, prefix: &str, keep: Vec<String>)
                   -> Result<Tiler, JsError> {
            let (style, tiles) = roadstyle::make_tiled(parquet, look, features, name, prefix, &keep).map_err(|e| JsError::new(&e))?;
            Ok(Tiler { style, tiles })
        }

        pub fn style(&self) -> String {
            self.style.clone()
        }

        /// `source` is the style's one source, `roads`: the tile has a layer for each of the old sources.
        pub fn tile(&self, source: &str, z: u32, x: u32, y: u32) -> Vec<u8> {
            if source == roadstyle::tiles::SOURCE { self.tiles.tile(z, x, y) } else { Vec::new() }
        }

        /// archive(bounds, layers): a PMTiles archive of every tile in bounds [min lon, min lat, max lon, max lat] (one file of the map).
        pub fn archive(&self, bounds: Vec<f64>, layers: Vec<String>) -> Result<Vec<u8>, JsError> {
            let b: [f64; 4] = bounds.try_into().map_err(|_| JsError::new("bounds: four numbers"))?;
            self.tiles.archive(b, &layers).ok_or_else(|| JsError::new("the archive has no tile"))
        }

        /// The properties of the feature `id` of a source, as JSON (`null` when there is none).
        pub fn props(&self, source: &str, id: u32) -> String {
            self.tiles.props(source, id as u64)
        }
    }

    fn format(f: &str) -> Result<roadstyle::Format, JsError> {
        match f {
            "geojson" => Ok(roadstyle::Format::GeoJson),
            "geoparquet" => Ok(roadstyle::Format::GeoParquet),
            _ => Err(JsError::new(&format!("format must be 'geojson' or 'geoparquet', not {f:?}"))),
        }
    }

    /// Stage 1 (docs/rust/architecture.md, "The three stages and the one call"): the style and its sources in memory.
    #[wasm_bindgen]
    pub struct Sources {
        inner: roadstyle::sources::Sources,
    }

    #[wasm_bindgen]
    impl Sources {
        /// fileNames(format): the names of stage 1's files (style.json, a file for each source, road_table.parquet).
        #[wasm_bindgen(js_name = fileNames)]
        pub fn file_names(&self, format: &str) -> Result<Vec<String>, JsError> {
            Ok(roadstyle::file_names(&self.inner, self::format(format)?))
        }

        /// file(name, format, keep): one of stage 1's files ("geojson" or "geoparquet"; the roads' file has their drawing values and
        /// `keep`, the road table every field of each road).
        pub fn file(&self, name: &str, format: &str, keep: Vec<String>) -> Result<Vec<u8>, JsError> {
            roadstyle::source_file(&self.inner, name, self::format(format)?, &self.inner.drawn(&keep)).map_err(|e| JsError::new(&e))
        }
    }

    /// makeSources(parquet, look, features, planner, name): stage 1, with makeStyle's arguments.
    #[wasm_bindgen(js_name = makeSources)]
    pub fn make_sources(parquet: Vec<u8>, look: &str, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>)
                        -> Result<Sources, JsError> {
        roadstyle::make_sources(parquet, look, features, planner, name).map(|inner| Sources { inner }).map_err(|e| JsError::new(&e))
    }

    /// tileSources(sources, prefix, keep): stage 2 from memory (the typed pieces, no GeoJSON text); it takes the sources. The Tiler's
    /// style has the one vector source `<prefix>roads/{z}/{x}/{y}`.
    #[wasm_bindgen(js_name = tileSources)]
    pub fn tile_sources(sources: Sources, prefix: &str, keep: Vec<String>) -> Result<Tiler, JsError> {
        let (style, tiles) = roadstyle::tile_made(sources.inner, prefix, &keep).map_err(|e| JsError::new(&e))?;
        Ok(Tiler { style, tiles })
    }

    /// Stage 1's files for stage 2: each file's name and bytes (style.json and the files that it names).
    #[wasm_bindgen]
    #[derive(Default)]
    pub struct FileSet {
        files: std::collections::HashMap<String, Vec<u8>>,
    }

    #[wasm_bindgen]
    impl FileSet {
        #[wasm_bindgen(constructor)]
        pub fn new() -> FileSet {
            FileSet::default()
        }

        pub fn add(&mut self, name: &str, bytes: Vec<u8>) {
            self.files.insert(name.to_string(), bytes);
        }
    }

    /// tileFiles(files, prefix, keep): stage 2 from stage 1's files (GeoJSON or GeoParquet, as style.json names them); the Tiler's
    /// style is the saved style with the one vector source.
    #[wasm_bindgen(js_name = tileFiles)]
    pub fn tile_files(files: &FileSet, prefix: &str, keep: Vec<String>) -> Result<Tiler, JsError> {
        let read = |n: &str| files.files.get(n).cloned().ok_or_else(|| format!("{n}: not in the files"));
        let (style, tiles) = roadstyle::tile_files_with(read, &keep, None).map_err(|e| JsError::new(&e))?;
        Ok(Tiler { style: roadstyle::vector_style(&style, prefix, tiles.zooms()).to_string(), tiles })
    }

    /// makeLook(options: string) -> string: the look (look.json) of render_edges' palette, profile and settings (roadstyle-rs look.rs);
    /// options: {"palette", "profile", "settings", "args", "features"} as JSON text. An error is a thrown Error.
    #[wasm_bindgen(js_name = makeLook)]
    pub fn make_look(options: &str) -> Result<String, JsError> {
        let o: serde_json::Value = serde_json::from_str(options).map_err(|e| JsError::new(&format!("options: not JSON: {e}")))?;
        roadstyle::look::make_look(&o).map(|l| l.to_string()).map_err(|e| JsError::new(&e))
    }

        /// The size of the module's memory, in bytes.
    #[wasm_bindgen(js_name = memoryBytes)]
    pub fn memory_bytes() -> usize {
        core::arch::wasm32::memory_size(0) * 65536
    }
}
