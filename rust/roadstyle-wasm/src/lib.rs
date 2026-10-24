//! The browser's front-end of roadstyle-rs (docs/design/rust_engine.md): `Look`, `makeStyle`, `makePage`, `Tiler` and `memoryBytes` through
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

    /// A resolved look (roadstyle-look), parsed one time: `resolveLook(options)` makes it, `Look.fromJson(text)` reads a saved look
    /// (version 1, or version 0: today's look.json), `toJson()` gives its text (version 1). The calls below take it, not its text.
    #[wasm_bindgen(js_name = Look)]
    pub struct JsLook(roadstyle::Look);

    #[wasm_bindgen(js_class = Look)]
    impl JsLook {
        /// Look.fromJson(text): a saved look (version 1 or 0). An error is a thrown Error.
        #[wasm_bindgen(js_name = fromJson)]
        pub fn from_json(text: &str) -> Result<JsLook, JsError> {
            roadstyle::Look::from_json(text).map(JsLook).map_err(|e| JsError::new(&e))
        }

        /// toJson(): the look's text (version 1).
        #[wasm_bindgen(js_name = toJson)]
        pub fn to_json(&self) -> String {
            self.0.to_json()
        }
    }

    /// resolveLook(options: string) -> Look: the look of render_edges' palette, profile and settings; options: {"palette", "profile",
    /// "settings", "args", "features", "files"} as JSON text. An error is a thrown Error.
    #[wasm_bindgen(js_name = resolveLook)]
    pub fn resolve_look(options: &str) -> Result<JsLook, JsError> {
        let o: serde_json::Value = serde_json::from_str(options).map_err(|e| JsError::new(&format!("options: not JSON: {e}")))?;
        roadstyle::look::Options::from_value(&o).and_then(|o| roadstyle::Look::resolve(&o)).map(JsLook).map_err(|e| JsError::new(&e))
    }

    /// makeLook(options: string) -> Look: the old name of resolveLook, for one version.
    #[wasm_bindgen(js_name = makeLook)]
    pub fn make_look(options: &str) -> Result<JsLook, JsError> {
        resolve_look(options)
    }

    /// rampStops(cmap: string, n: number) -> string[]: `n` colours ("#rrggbb") at even steps along a ramp (render_edges' cmap: a branca
    /// scheme or a matplotlib colormap name, or the JSON text of a list of colours), from the first colour to the last (at least 2), as
    /// roadstyle's ColorRamp.stops: for example a colour for each category of a column. An error is a thrown Error.
    #[wasm_bindgen(js_name = rampStops)]
    pub fn ramp_stops(cmap: &str, n: usize) -> Result<Vec<String>, JsError> {
        let c: serde_json::Value = if cmap.trim_start().starts_with('[') {
            serde_json::from_str(cmap).map_err(|e| JsError::new(&format!("cmap: not a JSON list: {e}")))?
        } else {
            cmap.into()
        };
        roadstyle::look::Ramp::new(&c).map(|r| r.stops(n)).map_err(|e| JsError::new(&e))
    }

    /// makeStyle(roads: Uint8Array, look: Look, features?: Uint8Array, planner?: Uint8Array, name?: string) -> string; an error is a thrown Error.
    #[wasm_bindgen(js_name = makeStyle)]
    pub fn make_style(parquet: Vec<u8>, look: &JsLook, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<String, JsError> {
        roadstyle::make_style(parquet, &look.0, features, planner, name).map_err(|e| JsError::new(&e))
    }

    /// The level editor in the page (roadstyle::level_editor): new LevelArea(roads.parquet of the area, pairs.csv text). Each answer is JSON
    /// text: the numbers of each road in the roads' order, the rules not kept (by road id) and the counts.
    #[wasm_bindgen]
    pub struct LevelArea(roadstyle::level_editor::Editor);

    #[wasm_bindgen]
    impl LevelArea {
        #[wasm_bindgen(constructor)]
        pub fn new(roads: Vec<u8>, pairs: &str) -> Result<LevelArea, JsError> {
            roadstyle::level_editor::Editor::new(roads, pairs).map(LevelArea).map_err(|e| JsError::new(&e))
        }
        /// The whole solve with the edits (edits.csv text).
        pub fn solve(&mut self, edits: &str) -> Result<String, JsError> {
            self.0.solve(edits).map_err(|e| JsError::new(&e))
        }
        /// The solve after a change that names the roads of `changed` (edge ids): the roads around it, else the whole area.
        #[wasm_bindgen(js_name = solveLocal)]
        pub fn solve_local(&mut self, edits: &str, changed: Vec<String>) -> Result<String, JsError> {
            self.0.solve_local(edits, &changed).map_err(|e| JsError::new(&e))
        }
        /// The answer to start from (levels.csv, levels_info.json): 4 numbers for each road; the given-up parts as "upper|lower|part".
        #[wasm_bindgen(js_name = startFrom)]
        pub fn start_from(&mut self, levels: Vec<i32>, given_up_parts: Vec<String>, orders_not_kept: usize, near: usize) -> Result<(), JsError> {
            let parts: Vec<(String, String, String)> = given_up_parts.iter().map(|p| {
                let mut f = p.split('|').map(String::from);
                (f.next().unwrap_or_default(), f.next().unwrap_or_default(), f.next().unwrap_or_default())
            }).collect();
            let levels: Vec<i64> = levels.into_iter().map(i64::from).collect();
            self.0.start_from(&levels, &parts, orders_not_kept, near).map_err(|e| JsError::new(&e))
        }
        /// The check before rules are added (rows: CSV text with a header): [[index, why, [rule rows]]].
        pub fn check(&self, edits: &str, rows: &str) -> Result<String, JsError> {
            self.0.check(edits, rows).map_err(|e| JsError::new(&e))
        }
        /// What the panel shows of each road, a list in the roads' order.
        pub fn facts(&self) -> String {
            self.0.facts()
        }
        /// Each road end as drawn, a list in the roads' order: heads, caps, and yours (heads.csv, caps.csv).
        pub fn ends(&self, heads: &str, caps: &str) -> Result<String, JsError> {
            self.0.ends_json(heads, caps).map_err(|e| JsError::new(&e))
        }
        /// levels.csv: one row for each edge with its four numbers and its ends as drawn (4 numbers for each road).
        #[wasm_bindgen(js_name = levelsCsv)]
        pub fn levels_csv(&self, levels: Vec<i32>, heads: &str, caps: &str) -> Result<String, JsError> {
            let levels: Vec<i64> = levels.into_iter().map(i64::from).collect();
            self.0.levels_csv(&levels, heads, caps).map_err(|e| JsError::new(&e))
        }
        /// The map's table (GeoParquet, one row for each edge) for makeStyle: 4 numbers for each road.
        pub fn draw(&self, levels: Vec<i32>, heads: &str, caps: &str) -> Result<Vec<u8>, JsError> {
            let levels: Vec<i64> = levels.into_iter().map(i64::from).collect();
            self.0.draw(&levels, heads, caps).map_err(|e| JsError::new(&e))
        }
    }

    /// makePage(roads: Uint8Array, look: Look, options: string, given?: string) -> string: the page of the roads (GeoParquet) in one
    /// call, as render_edges(backend="web") (roadstyle::page_options::page_from; MapLibre stays a placeholder). `look`: makeLook's of
    /// `options` (its JSON text, which a view's palette resolves again), with "state": "live" in its args; `given`: the caller's values
    /// over the look's args (JSON text: api_key, street_view_key, resolved_basemaps).
    #[wasm_bindgen(js_name = makePage)]
    pub fn make_page(roads: Vec<u8>, look: &JsLook, options: &str, given: Option<String>) -> Result<String, JsError> {
        let o: roadstyle::look::Options = serde_json::from_str(options).map_err(|e| JsError::new(&format!("options: {e}")))?;
        let given: serde_json::Map<String, serde_json::Value> = match given {
            Some(g) => serde_json::from_str(&g).map_err(|e| JsError::new(&format!("given: {e}")))?,
            None => serde_json::Map::new(),
        };
        let roads = roadstyle::read::read_roads(roads, "geometry").map_err(|e| JsError::new(&e))?;
        let page = roadstyle::page_options::page_from(roads, &look.0, &o, &given).map_err(|e| JsError::new(&e))?;
        page.warnings.iter().for_each(|w| console_warn(w));
        Ok(page.html)
    }

    #[wasm_bindgen]
    extern "C" {
        /// console.warn: the warnings of a call's stages (Python's warnings.warn)
        #[wasm_bindgen(js_namespace = console, js_name = warn)]
        fn console_warn(s: &str);
    }

    /// exportLook(look: Look, cols: string[] (highway, oneway, tunnel, bridge, id), positions: number[]) -> string: the simple look
    /// for another app's data layer (roadstyle's export_look) from a resolved look.
    #[wasm_bindgen(js_name = exportLook)]
    pub fn export_look(look: &JsLook, cols: Vec<String>, positions: Vec<i32>) -> Result<String, JsError> {
        let c = |i: usize| cols.get(i).map(String::as_str).unwrap_or(["highway", "oneway", "tunnel", "bridge", "edge_id"][i]);
        let lc = roadstyle::export_look::LookCols { highway: c(0), oneway: c(1), tunnel: c(2), bridge: c(3), id: c(4) };
        let ps: Vec<i64> = positions.into_iter().map(i64::from).collect();
        roadstyle::export_look::export_look(&look.0, &lc, &ps).map(|v| v.to_string()).map_err(|e| JsError::new(&e))
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
        pub fn new(parquet: Vec<u8>, look: &JsLook, features: Option<Vec<u8>>, name: Option<String>, prefix: &str, keep: Vec<String>)
                   -> Result<Tiler, JsError> {
            let (style, tiles, _) = roadstyle::make_tiled(parquet, &look.0, features, name, prefix, &keep).map_err(|e| JsError::new(&e))?;
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

        /// roadTable(): the road table as the page loads it, JSON text (props, mids, bboxes, lines: one item for each road).
        #[wasm_bindgen(js_name = roadTable)]
        pub fn road_table(&self) -> Vec<u8> {
            let mut out = Vec::new();
            roadstyle::write_road_table(&self.inner, &mut out).expect("a Vec takes every byte");
            out
        }

        /// file(name, format, keep): one of stage 1's files ("geojson" or "geoparquet"; the roads' file has their drawing values and
        /// `keep`, the road table every field of each road).
        pub fn file(&self, name: &str, format: &str, keep: Vec<String>) -> Result<Vec<u8>, JsError> {
            roadstyle::source_file(&self.inner, name, self::format(format)?, &self.inner.drawn(&keep)).map_err(|e| JsError::new(&e))
        }
    }

    /// makeSources(parquet, look, features, planner, name): stage 1, with makeStyle's arguments.
    #[wasm_bindgen(js_name = makeSources)]
    pub fn make_sources(parquet: Vec<u8>, look: &JsLook, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>)
                        -> Result<Sources, JsError> {
        roadstyle::make_sources(parquet, &look.0, features, planner, name).map(|inner| Sources { inner }).map_err(|e| JsError::new(&e))
    }

    /// Roads that a reader of a road file gave (roadstyle-io: a RoadTable, one row for each road): `readGeoJson(bytes)` makes them. `length`
    /// and `columns()` describe them; `sources(look, features?, planner?, name?)` is stage 1 of them (makeSources' arguments after the roads).
    #[wasm_bindgen]
    pub struct Roads(roadstyle::RoadTable);

    #[wasm_bindgen]
    impl Roads {
        /// The number of roads (the file's features).
        #[wasm_bindgen(getter)]
        pub fn length(&self) -> usize {
            self.0.len()
        }

        /// The names of the roads' columns (the file's properties), in order.
        pub fn columns(&self) -> Vec<String> {
            self.0.names().to_vec()
        }

        /// sources(look, features?, planner?, name?): stage 1 of these roads, as makeSources; `features` and `planner` are Parquet bytes.
        pub fn sources(&self, look: &JsLook, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<Sources, JsError> {
            let err = |e: String| JsError::new(&e);
            let features = features.map(roadstyle::read_features).transpose().map_err(err)?;
            let planner = planner.map(|p| roadstyle::read::read_table(p, "")).transpose().map_err(err)?;
            roadstyle::sources_of(self.0.clone(), &look.0, features, planner, name).map(|inner| Sources { inner }).map_err(err)
        }
    }

    /// duckosmPlan(catalog, mode, tags, specs) -> string: the SQL that reads a duckOSM file (roadstyle-io's duckosm.rs, the one copy that
    /// Python runs too), as JSON text: {"catalog": the 2 queries of the catalog, "roads": 3 statements, "meta": the stored levels' query or
    /// null, "select": the roads of `mode`, "layers": [{spec, name, sql: the
    /// queries in order}]}. `catalog`: the JSON text of {"name", "tables":
    /// [[schema, table]], "columns": [[schema, table, column]]} (with no tables: only "catalog" is in the answer); `specs`: layers.yaml's
    /// layers as JSON text. `only`: the map of `mode` alone; then "subset" has the queries of its roads with no stored levels and
    /// of its edge_ids (for duckosmSubsetLevels).
    #[wasm_bindgen(js_name = duckosmPlan)]
    pub fn duckosm_plan(catalog: &str, mode: &str, tags: bool, specs: &str, only: Option<bool>) -> Result<String, JsError> {
        let only = only.unwrap_or(false);
        use roadstyle::duckosm;
        let err = |e: String| JsError::new(&e);
        let c: serde_json::Value = serde_json::from_str(catalog).map_err(|e| err(format!("catalog: {e}")))?;
        let text = |v: &serde_json::Value| v.as_str().unwrap_or_default().to_string();
        let rows = |k: &str| c[k].as_array().cloned().unwrap_or_default();
        let queries = duckosm::catalog_sql(c["name"].as_str().unwrap_or_default());
        if rows("tables").is_empty() {
            return Ok(serde_json::json!({"catalog": queries}).to_string());
        }
        let cat = duckosm::Catalog { tables: rows("tables").iter().map(|r| (text(&r[0]), text(&r[1]))).collect(),
                                     columns: rows("columns").iter().map(|r| (text(&r[0]), text(&r[1]), text(&r[2]))).collect() };
        let specs: Vec<serde_json::Value> = serde_json::from_str(specs).map_err(|e| err(format!("specs: {e}")))?;
        let layers: Vec<serde_json::Value> = duckosm::features_sql(&cat, &specs).into_iter()
            .map(|l| serde_json::json!({"spec": l.spec, "name": l.name, "sql": l.sql})).collect();
        Ok(serde_json::json!({"catalog": queries, "roads": duckosm::roads_sql(&cat, tags, only.then_some(mode)).map_err(err)?, "meta": (!tags).then_some(duckosm::LEVELS_META_SQL),
                              "select": duckosm::roads_select(mode).map_err(err)?, "layers": layers,
                              "subset": (only && !tags).then_some([duckosm::SUBSET_SQL, duckosm::IDS_SQL])}).to_string())
    }

    /// duckosmLevels(source?, nEdges?, edgeHash?) -> string: the look's keyword `levels` (JSON text) from the stored levels' metadata row
    /// (none: the file has no such row); an error says what to do.
    #[wasm_bindgen(js_name = duckosmLevels)]
    pub fn duckosm_levels(source: Option<String>, n_edges: Option<f64>, edge_hash: Option<String>) -> Result<String, JsError> {
        let row = match (&source, n_edges, &edge_hash) {
            (Some(s), Some(n), Some(h)) => Some((s.as_str(), n as i64, h.as_str())),
            _ => None,
        };
        roadstyle::duckosm::levels_keyword(row).map(|v| v.to_string()).map_err(|e| JsError::new(&e))
    }

    /// duckosmSubsetLevels(source?, nEdges?, edgeHash?, missing, example?, ids) -> string: the look's keyword `levels` (JSON text) for a map
    /// of one mode: the stored levels' metadata row, the row of the plan's "subset" query, and the map's edge_ids (a BigInt64Array).
    #[wasm_bindgen(js_name = duckosmSubsetLevels)]
    pub fn duckosm_subset_levels(source: Option<String>, n_edges: Option<f64>, edge_hash: Option<String>, missing: f64, example: Option<i64>,
                                 ids: Vec<i64>) -> Result<String, JsError> {
        let row = match (&source, n_edges, &edge_hash) {
            (Some(s), Some(n), Some(h)) => Some((s.as_str(), n as i64, h.as_str())),
            _ => None,
        };
        roadstyle::duckosm::subset_levels_keyword(row, missing as i64, example, &ids).map(|v| v.to_string()).map_err(|e| JsError::new(&e))
    }

    /// duckosmFeaturesSelect(specs: number[]) -> string | undefined: the base map's rows from the tables f<spec> that were made.
    #[wasm_bindgen(js_name = duckosmFeaturesSelect)]
    pub fn duckosm_features_select(specs: Vec<u32>) -> Option<String> {
        roadstyle::duckosm::features_select(&specs.into_iter().map(|i| i as usize).collect::<Vec<_>>())
    }

    /// readGeoJson(bytes: Uint8Array) -> Roads: the roads of a GeoJSON file (a FeatureCollection in EPSG:4326; roadstyle-io's geojson.rs
    /// says how each property becomes a column). An error is a thrown Error.
    #[wasm_bindgen(js_name = readGeoJson)]
    pub fn read_geojson(bytes: &[u8]) -> Result<Roads, JsError> {
        roadstyle::geojson::read_roads(bytes).map(Roads).map_err(|e| JsError::new(&e))
    }

    /// tileSources(sources, prefix, keep): stage 2 from memory (the typed pieces, no GeoJSON text; the sources stay as they are). The
    /// Tiler's style has the one vector source `<prefix>roads/{z}/{x}/{y}`, with the pieces' promoteId (roadstyle::tile_stage).
    #[wasm_bindgen(js_name = tileSources)]
    pub fn tile_sources(sources: &Sources, prefix: &str, keep: Vec<String>) -> Result<Tiler, JsError> {
        let (style, tiles) = roadstyle::tile_made(&sources.inner, prefix, &keep).map_err(|e| JsError::new(&e))?;
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
    /// style is the saved style with the one vector source (roadstyle::tiled_style).
    #[wasm_bindgen(js_name = tileFiles)]
    pub fn tile_files(files: &FileSet, prefix: &str, keep: Vec<String>) -> Result<Tiler, JsError> {
        let read = |n: &str| files.files.get(n).cloned().ok_or_else(|| format!("{n}: not in the files"));
        let (style, tiles) = roadstyle::tile_files_with(read, &keep, None, &roadstyle::xyz_at(prefix)).map_err(|e| JsError::new(&e))?;
        Ok(Tiler { style: style.to_string(), tiles })
    }

    /// The size of the module's memory, in bytes.
    #[wasm_bindgen(js_name = memoryBytes)]
    pub fn memory_bytes() -> usize {
        core::arch::wasm32::memory_size(0) * 65536
    }
}
