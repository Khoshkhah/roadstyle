//! The browser's front-end of roadstyle-rs (docs/design/rust_engine.md): `Look`, `inlineStyle`, `pageFrom`, `Tiler` and `memoryBytes` through
//! wasm-bindgen, and the allocator that grows the memory in large steps. Natively the crate is empty.

/// The allocator in the browser: the standard one (dlmalloc), but when it grows the memory, the memory grows once more by a quarter of its
/// size (16 to 64 MB) in one step, and the allocator keeps that block free for the next allocations. dlmalloc alone grows the memory 64 KB
/// at a time, thousands of steps for Monaco, and in Edge on Windows each step is slow: the first style took 14 to 21 s there, 3 s with the
/// memory grown first. The step was the whole size (16 to 256 MB) until 2026-10-25; the quarter keeps the memory near what is held (Monaco
/// 110 to 68 MiB, Tartu 221 to 197 MiB) with few steps. Edge's first-style time on Windows must be checked again with the quarter step.
#[cfg(target_arch = "wasm32")]
mod grow {
    use core::arch::wasm32::memory_size;
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicUsize, Ordering::Relaxed};

    static PAGES: AtomicUsize = AtomicUsize::new(0); // the memory's size (64 KB pages) after the last step ahead
    /// the times that the memory grew (dlmalloc's own steps and the steps ahead)
    pub static STEPS: AtomicUsize = AtomicUsize::new(0);
    /// the bytes that the program holds now, and their most since `peak_reset` (the memory's size grows in steps ahead, so it does not
    /// show these: parity.md, "The drawing values of a road")
    pub static LIVE: AtomicUsize = AtomicUsize::new(0);
    pub static PEAK: AtomicUsize = AtomicUsize::new(0);

    #[inline(never)]
    fn took(n: usize) {
        let live = LIVE.fetch_add(n, Relaxed) + n;
        PEAK.fetch_max(live, Relaxed);
    }

    #[inline(never)]
    fn ahead() {
        let now = memory_size(0);
        if now != PAGES.load(Relaxed) {
            STEPS.fetch_add(1, Relaxed);
            let l = Layout::from_size_align(((now << 16) / 4).clamp(16 << 20, 64 << 20), 16).unwrap();
            unsafe {
                let p = System.alloc(l); // null when the memory cannot grow: then nothing is taken ahead
                if !p.is_null() {
                    System.dealloc(p, l);
                }
            }
            if memory_size(0) != now {
                STEPS.fetch_add(1, Relaxed);
            }
            PAGES.store(memory_size(0), Relaxed);
        }
    }

    struct Ahead;

    // Every function of the allocator is out of line (#[inline(never)]): with fat LTO they were inlined at each allocation site, thousands of
    // copies, 1.31 MB of the package (12,312,335 to 11,006,948 bytes; parity.md, "Size"). The cost is one call for each allocation:
    // Tartu's styleSources and tilesOfSources in Node took about 2 % longer, about the noise between runs.

    unsafe impl GlobalAlloc for Ahead {
        #[inline(never)]
        unsafe fn alloc(&self, l: Layout) -> *mut u8 {
            let p = System.alloc(l);
            if !p.is_null() {
                took(l.size());
            }
            ahead();
            p
        }
        #[inline(never)]
        unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
            let p = System.alloc_zeroed(l);
            if !p.is_null() {
                took(l.size());
            }
            ahead();
            p
        }
        #[inline(never)]
        unsafe fn realloc(&self, p: *mut u8, l: Layout, size: usize) -> *mut u8 {
            let q = System.realloc(p, l, size);
            if !q.is_null() {
                LIVE.fetch_sub(l.size(), Relaxed);
                took(size);
            }
            ahead();
            q
        }
        #[inline(never)]
        unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
            LIVE.fetch_sub(l.size(), Relaxed);
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
    /// (version 2, 1, or 0: the look.json of 0.25.0), `toJson()` gives its text (version 2). The calls below take it, not its text.
    #[wasm_bindgen(js_name = Look)]
    pub struct JsLook(roadstyle::Look);

    #[wasm_bindgen(js_class = Look)]
    impl JsLook {
        /// Look.fromJson(text): a saved look (version 2, 1 or 0). An error is a thrown Error.
        #[wasm_bindgen(js_name = fromJson)]
        pub fn from_json(text: &str) -> Result<JsLook, JsError> {
            roadstyle::Look::from_json(text).map(JsLook).map_err(|e| JsError::new(&e.to_string()))
        }

        /// toJson(): the look's text (version 2), to save and load it. It is not an API: read no field of it.
        #[wasm_bindgen(js_name = toJson)]
        pub fn to_json(&self) -> String {
            self.0.to_json()
        }

        /// withArg(key: string, value: string) -> Look: the same look with the map option `key` (a render_edges keyword: color_by, state,
        /// live_data, levels, ...) set to `value` (JSON text) binding's Look.with_arg. An error is a thrown Error.
        #[wasm_bindgen(js_name = withArg)]
        pub fn with_arg(&self, key: &str, value: &str) -> Result<JsLook, JsError> {
            let v: serde_json::Value = serde_json::from_str(value).map_err(|e| JsError::new(&format!("{key}: not JSON: {e}")))?;
            self.0.clone().with_arg(key, v).map(JsLook).map_err(|e| JsError::new(&e.to_string()))
        }
    }

    /// resolveLook(options: string) -> Look: the look of render_edges' palette, profile and settings; options: {"palette", "profile",
    /// "settings", "args", "features", "files"} as JSON text. An error is a thrown Error.
    #[wasm_bindgen(js_name = resolveLook)]
    pub fn resolve_look(options: &str) -> Result<JsLook, JsError> {
        let o: serde_json::Value = serde_json::from_str(options).map_err(|e| JsError::new(&format!("options: not JSON: {e}")))?;
        roadstyle::look::Options::from_value(&o).and_then(|o| roadstyle::Look::resolve(&o)).map(JsLook).map_err(|e| JsError::new(&e.to_string()))
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
        roadstyle::look::Ramp::new(&c).map(|r| r.stops(n)).map_err(|e| JsError::new(&e.to_string()))
    }

    /// inlineStyle(roads: Uint8Array, look: Look, features?: Uint8Array, planner?: Uint8Array, name?: string) -> string; an error is a thrown Error.
    #[wasm_bindgen(js_name = inlineStyle)]
    pub fn inline_style(parquet: Vec<u8>, look: &JsLook, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<String, JsError> {
        roadstyle::inline_style(parquet, &look.0, features, planner, name).map_err(|e| JsError::new(&e.to_string()))
    }

    /// makeArea(edges: Uint8Array, options?: string) -> AreaFiles: a level area's files in memory (roadstyle::level_area::make_files), for
    /// a page with no server: `edges` is GeoParquet of the area's edges (the line in `geometry`, longitude and latitude; a duckOSM file's:
    /// duckosmPlan's "level_edges"); `options` the JSON text of {"id_col", "highway_col", "layer_col", "bridge_col", "tunnel_col",
    /// "junction_col", "band_col", "order" ("priority", "class", a column, or null), "band_dist", "head_m", "near_rules", "heads" (heads.csv
    /// text)}, each optional (make_area's defaults).
    #[wasm_bindgen(js_name = makeArea)]
    pub fn make_area(edges: Vec<u8>, options: Option<String>) -> Result<AreaFiles, JsError> {
        let o: serde_json::Value = serde_json::from_str(options.as_deref().unwrap_or("{}")).map_err(|e| JsError::new(&format!("options: {e}")))?;
        let d = roadstyle::level_area::MakeOptions::default();
        let text = |k: &str, d: String| o[k].as_str().map_or(d, String::from);
        let num = |k: &str, d: f64| o[k].as_f64().unwrap_or(d);
        let m = roadstyle::level_area::MakeOptions {
            id_col: text("id_col", d.id_col), highway_col: text("highway_col", d.highway_col), layer_col: text("layer_col", d.layer_col),
            bridge_col: text("bridge_col", d.bridge_col), tunnel_col: text("tunnel_col", d.tunnel_col), junction_col: text("junction_col", d.junction_col),
            band_col: o["band_col"].as_str().map(String::from),
            order: if o.get("order").is_some() { o["order"].as_str().filter(|v| *v != "none").map(String::from) } else { d.order },
            band_dist: num("band_dist", d.band_dist), head_m: num("head_m", d.head_m), near_rules: o["near_rules"].as_bool().unwrap_or(d.near_rules),
        };
        let table = roadstyle::read::read_roads(edges, "geometry").map_err(|e| JsError::new(&e.to_string()))?;
        roadstyle::level_area::make_files(&table, &m, o["heads"].as_str().unwrap_or("")).map(AreaFiles).map_err(|e| JsError::new(&e.to_string()))
    }

    /// A level area's files (makeArea): `roads` (roads.parquet's bytes, for new LevelArea), `pairs` and `edits` (pairs.csv and an empty
    /// edits.csv), the numbers of roads and pairs, and the warnings.
    #[wasm_bindgen]
    pub struct AreaFiles(roadstyle::level_area::AreaFiles);

    #[wasm_bindgen]
    impl AreaFiles {
        #[wasm_bindgen(getter)]
        pub fn roads(&self) -> Vec<u8> {
            self.0.roads.clone()
        }
        #[wasm_bindgen(getter)]
        pub fn pairs(&self) -> String {
            self.0.pairs.clone()
        }
        #[wasm_bindgen(getter)]
        pub fn edits(&self) -> String {
            self.0.edits.clone()
        }
        #[wasm_bindgen(getter, js_name = roadCount)]
        pub fn road_count(&self) -> usize {
            self.0.made.roads
        }
        #[wasm_bindgen(getter, js_name = pairCount)]
        pub fn pair_count(&self) -> usize {
            self.0.made.pairs
        }
        #[wasm_bindgen(getter)]
        pub fn warnings(&self) -> Vec<String> {
            self.0.made.warnings.clone()
        }
    }

    /// The level editor in the page (roadstyle::level_editor): new LevelArea(roads.parquet of the area, pairs.csv text). Each answer is JSON
    /// text: the numbers of each road in the roads' order, the rules not kept (by road id) and the counts.
    #[wasm_bindgen]
    pub struct LevelArea(roadstyle::level_editor::Editor);

    #[wasm_bindgen]
    impl LevelArea {
        #[wasm_bindgen(constructor)]
        pub fn new(roads: Vec<u8>, pairs: &str) -> Result<LevelArea, JsError> {
            roadstyle::level_editor::Editor::new(roads, pairs).map(LevelArea).map_err(|e| JsError::new(&e.to_string()))
        }
        /// The whole solve with the edits (edits.csv text).
        pub fn solve(&mut self, edits: &str) -> Result<String, JsError> {
            self.0.solve(edits).map(|a| a.to_json().to_string()).map_err(|e| JsError::new(&e.to_string()))
        }
        /// The solve after a change that names the roads of `changed` (edge ids): the roads around it, else the whole area.
        #[wasm_bindgen(js_name = solveLocal)]
        pub fn solve_local(&mut self, edits: &str, changed: Vec<String>) -> Result<String, JsError> {
            self.0.solve_local(edits, &changed).map(|a| a.to_json().to_string()).map_err(|e| JsError::new(&e.to_string()))
        }
        /// The answer to start from (levels.csv, levels_info.json): 4 numbers for each road; the given-up parts as "upper|lower|part"; the
        /// numbers of order wishes not kept, near warnings and crossings not kept.
        #[wasm_bindgen(js_name = startFrom)]
        pub fn start_from(&mut self, levels: Vec<i32>, given_up_parts: Vec<String>, orders_not_kept: usize, near: usize, crossings: usize) -> Result<(), JsError> {
            let parts: Vec<(String, String, String)> = given_up_parts.iter().map(|p| {
                let mut f = p.split('|').map(String::from);
                (f.next().unwrap_or_default(), f.next().unwrap_or_default(), f.next().unwrap_or_default())
            }).collect();
            let levels: Vec<i64> = levels.into_iter().map(i64::from).collect();
            self.0.start_from(&levels, &parts, orders_not_kept, near, crossings).map_err(|e| JsError::new(&e.to_string()))
        }
        /// The check before rules are added (rows: CSV text with a header): [[index, why, [rule rows]]].
        pub fn check(&self, edits: &str, rows: &str) -> Result<String, JsError> {
            self.0.check(edits, rows).map(|c| roadstyle::level_editor::conflicts_json(&c).to_string()).map_err(|e| JsError::new(&e.to_string()))
        }
        /// What the panel shows of each road, a list in the roads' order.
        pub fn facts(&self) -> String {
            self.0.facts()
        }
        /// The road ids, in the roads' order.
        #[wasm_bindgen(js_name = roadIds)]
        pub fn road_ids(&self) -> Vec<String> {
            self.0.road_ids()
        }
        /// The road of each id (any edge id or road id; "" when it names none).
        #[wasm_bindgen(js_name = roadOf)]
        pub fn road_of(&self, ids: Vec<String>) -> Vec<String> {
            self.0.road_of(&ids)
        }
        /// What the panel shows of the roads of `ids` (any edge or road id), each with its place `i` and its ends (heads.csv, caps.csv).
        #[wasm_bindgen(js_name = factsOf)]
        pub fn facts_of(&self, ids: Vec<String>, heads: &str, caps: &str) -> Result<String, JsError> {
            self.0.facts_of(&ids, heads, caps).map_err(|e| JsError::new(&e.to_string()))
        }
        /// Your heads and caps of each road that has one: {road: [[head start, head end], [cap start, cap end]]}.
        #[wasm_bindgen(js_name = ownEnds)]
        pub fn own_ends(&self, heads: &str, caps: &str) -> Result<String, JsError> {
            self.0.own_ends_json(heads, caps).map_err(|e| JsError::new(&e.to_string()))
        }
        /// The roads whose edge_ref (or an edge's) has `q` in it: [[road, edge_ref, exact]].
        pub fn find(&self, q: &str) -> String {
            self.0.find(q)
        }
        /// The 4 numbers of each road from a levels.csv text; undefined when a road has no row.
        #[wasm_bindgen(js_name = levelsOf)]
        pub fn levels_of(&self, csv: &str) -> Option<Vec<i32>> {
            self.0.levels_of(csv)
        }
        /// The area's edge_hash (every edge both ways), as the host's levels name it.
        #[wasm_bindgen(js_name = edgeHash)]
        pub fn edge_hash(&self) -> String {
            self.0.edge_hash()
        }
        /// Each road end as drawn, a list in the roads' order: heads, caps, and yours (heads.csv, caps.csv).
        pub fn ends(&self, heads: &str, caps: &str) -> Result<String, JsError> {
            self.0.ends_json(heads, caps).map_err(|e| JsError::new(&e.to_string()))
        }
        /// levels.csv: one row for each edge with its four numbers and its ends as drawn (4 numbers for each road).
        #[wasm_bindgen(js_name = levelsCsv)]
        pub fn levels_csv(&self, levels: Vec<i32>, heads: &str, caps: &str) -> Result<String, JsError> {
            let levels: Vec<i64> = levels.into_iter().map(i64::from).collect();
            self.0.levels_csv(&levels, heads, caps).map_err(|e| JsError::new(&e.to_string()))
        }
        /// The map's table (GeoParquet, one row for each edge) for inlineStyle: 4 numbers for each road.
        pub fn draw(&self, levels: Vec<i32>, heads: &str, caps: &str) -> Result<Vec<u8>, JsError> {
            let levels: Vec<i64> = levels.into_iter().map(i64::from).collect();
            self.0.draw(&levels, heads, caps).map_err(|e| JsError::new(&e.to_string()))
        }
    }

    /// pageFrom(roads: Uint8Array, look: Look, options: string, given?: string) -> string: the page of the roads (GeoParquet) in one
    /// call, as render_edges(backend="web") (roadstyle::page_options::page_from; MapLibre stays a placeholder). `look`: resolveLook's of
    /// `options` (its JSON text, which a view's palette resolves again), with "state": "live" in its args. The page's keys (template,
    /// popup_mode, ...) come from the call's args (page_options::given_of: the keywords that are not map options, name, road_popup);
    /// `given`: the caller's values over them (JSON text: api_key, street_view_key, resolved_basemaps); `features`: a duckOSM map's base
    /// map (Parquet bytes).
    #[wasm_bindgen(js_name = pageFrom)]
    pub fn page_html(roads: Vec<u8>, look: &JsLook, options: &str, given: Option<String>, features: Option<Vec<u8>>) -> Result<String, JsError> {
        page_of(roadstyle::read::read_roads(roads, "geometry").map_err(|e| JsError::new(&e.to_string()))?, features, look, options, given)
    }

    /// pageFrom and Roads.page: the page of read roads.
    fn page_of(roads: roadstyle::RoadTable, features: Option<Vec<u8>>, look: &JsLook, options: &str, given: Option<String>) -> Result<String, JsError> {
        let o: roadstyle::look::Options = serde_json::from_str(options).map_err(|e| JsError::new(&format!("options: {e}")))?;
        // the page's keys of the call (the look's other keywords, name, road_popup: page_options::given_of), under the caller's
        let mut all = roadstyle::page_options::given_of(&look.0, &o.args);
        if let Some(g) = given {
            let g: serde_json::Map<String, serde_json::Value> = serde_json::from_str(&g).map_err(|e| JsError::new(&format!("given: {e}")))?;
            all.extend(g);
        }
        let given = all;
        let features = features.map(roadstyle::read_features).transpose().map_err(|e| JsError::new(&e.to_string()))?;
        let page = roadstyle::page_options::page_from(roads, features, &look.0, &o, &given).map_err(|e| JsError::new(&e.to_string()))?;
        page.warnings.iter().for_each(|w| console_warn(w));
        Ok(page.html)
    }

    #[wasm_bindgen]
    extern "C" {
        /// console.warn: the warnings of a call's stages (warnings of the host)
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
        roadstyle::export_look::export_look(&look.0, &lc, &ps).map(|v| v.to_string()).map_err(|e| JsError::new(&e.to_string()))
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
            let (style, tiles, _) = roadstyle::tiled_from_parquet(parquet, &look.0, features, name, prefix, &keep).map_err(|e| JsError::new(&e.to_string()))?;
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
            self.tiles.archive(b, &layers).map_err(|e| JsError::new(&e.to_string()))
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
        inner: roadstyle::sources::Styled,
    }

    #[wasm_bindgen]
    impl Sources {
        /// style(): the style's JSON text with its sources inline binding's `style()`.
        pub fn style(&self) -> String {
            let mut out = Vec::new();
            self.inner.write_style(&mut out, roadstyle::sources::SourceMode::INLINE).expect("a Vec takes every byte");
            String::from_utf8(out).expect("JSON text is UTF-8")
        }

        /// fileNames(format): the names of stage 1's files (style.json, a file for each source, road_table.parquet).
        #[wasm_bindgen(js_name = fileNames)]
        pub fn source_file_names(&self, format: &str) -> Result<Vec<String>, JsError> {
            Ok(roadstyle::source_file_names(&self.inner, self::format(format)?))
        }

        /// roadTable(fields?, lines?): the road table as the page loads it, JSON text (props, mids, bboxes, and with `lines` the
        /// lines: one item for each road); `fields`: only these fields of each road. Without lines, roadLines gives a road's line.
        #[wasm_bindgen(js_name = roadTable)]
        pub fn road_table(&self, fields: Option<Vec<String>>, lines: Option<bool>) -> Vec<u8> {
            let mut out = Vec::new();
            roadstyle::write_road_table(&self.inner, fields.as_deref(), lines.unwrap_or(false), &mut out).expect("a Vec takes every byte");
            out
        }

        /// roadLines(ids): the lines of these rows of the road table, JSON text: a list with one item for each id (null: no line).
        #[wasm_bindgen(js_name = roadLines)]
        pub fn road_lines(&self, ids: Vec<u32>) -> Vec<u8> {
            let mut out = Vec::new();
            roadstyle::write_road_lines(&self.inner, &ids, &mut out).expect("a Vec takes every byte");
            out
        }

        /// file(name, format, keep): one of stage 1's files ("geojson" or "geoparquet"; the roads' file has their drawing values and
        /// `keep`, the road table every field of each road).
        pub fn file(&self, name: &str, format: &str, keep: Vec<String>) -> Result<Vec<u8>, JsError> {
            roadstyle::source_file(&self.inner, name, self::format(format)?, &self.inner.drawn(&keep)).map_err(|e| JsError::new(&e.to_string()))
        }
    }

    /// styleSources(parquet, look, features, planner, name): stage 1, with inlineStyle's arguments.
    #[wasm_bindgen(js_name = styleSources)]
    pub fn style_sources(parquet: Vec<u8>, look: &JsLook, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>)
                        -> Result<Sources, JsError> {
        roadstyle::style_sources(parquet, &look.0, features, planner, name).map(|inner| Sources { inner }).map_err(|e| JsError::new(&e.to_string()))
    }

    /// Roads that a reader of a road file gave (roadstyle-io: a RoadTable, one row for each road): `readGeoJson(bytes)` makes them. `length`
    /// and `columns()` describe them; `sources(look, features?, planner?, name?)` is stage 1 of them (styleSources' arguments after the roads).
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

        /// page(look, options, given?, features?): the page of these roads in one call, as pageFrom (its arguments after the roads).
        pub fn page(&self, look: &JsLook, options: &str, given: Option<String>, features: Option<Vec<u8>>) -> Result<String, JsError> {
            page_of(self.0.clone(), features, look, options, given)
        }

        /// sources(look, features?, planner?, name?): stage 1 of these roads, as styleSources; `features` and `planner` are Parquet bytes.
        pub fn sources(&self, look: &JsLook, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>) -> Result<Sources, JsError> {
            let err = |e: roadstyle::Error| JsError::new(&e.to_string());
            let features = features.map(roadstyle::read_features).transpose().map_err(err)?;
            let planner = planner.map(|p| roadstyle::read::read_table(p, "")).transpose().map_err(roadstyle::Error::from).map_err(err)?;
            roadstyle::sources_of(self.0.clone(), &look.0, features, planner, name).map(|inner| Sources { inner }).map_err(err)
        }
    }

    /// duckosmPlan(catalog, mode, tags, specs, only?, run?) -> string: the SQL that reads a duckOSM file (roadstyle-io's duckosm.rs, the one copy that
    /// The Python binding runs too), as JSON text: {"catalog": the 2 queries of the catalog, "roads": 3 statements, "meta": the stored levels' query or
    /// null, "select": the roads of `mode` ("roads" is null when the file has no network of `mode`: "roads_error" says why), "layers": [{spec, name, sql: the
    /// queries in order}]}. `catalog`: the JSON text of {"name", "tables":
    /// [[schema, table]], "columns": [[schema, table, column]]} (with no tables: only "catalog" is in the answer); `specs`: layers.yaml's
    /// layers as JSON text. `only`: the map of `mode` alone; then "subset" has the queries of its roads with no stored levels and
    /// of its edge_ids (for duckosmSubsetLevels). "level_edges": the edges of the file's level area (duckosm::level_edges_sql), for makeArea.
    /// `run`: the id of this reading of the file: its tables have their own names (each layer's "table"; "drop" drops them), so two
    /// readings at the same time on one connection do not meet. With no `run`, a new one; "run" gives it, for the next calls of the same
    /// reading.
    #[wasm_bindgen(js_name = duckosmPlan)]
    pub fn duckosm_plan(catalog: &str, mode: &str, tags: bool, specs: &str, only: Option<bool>, run: Option<String>) -> Result<String, JsError> {
        let only = only.unwrap_or(false);
        let run = roadstyle::duckosm::Run::new(&run.unwrap_or_else(|| {
            static N: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
            format!("w{}", N.fetch_add(1, std::sync::atomic::Ordering::Relaxed))
        })).map_err(|e| JsError::new(&e.to_string()))?;
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
        let made = duckosm::features_sql(&cat, &specs);
        let drop = run.drop_sql(&made.iter().map(|l| l.spec).collect::<Vec<_>>());
        let layers: Vec<serde_json::Value> = made.into_iter()
            .map(|l| serde_json::json!({"spec": l.spec, "name": l.name, "table": run.feature(l.spec), "sql": l.sql})).collect();
        // the base map's queries also for a file with no network: then "roads" is null and "roads_error" says why
        let (roads, roads_error) = match duckosm::roads_sql(&cat, tags, only.then_some(mode), &run) {
            Ok(r) => (Some(r), None),
            Err(e) => (None, Some(e)),
        };
        Ok(serde_json::json!({"catalog": queries, "run": run.id(), "roads": roads, "roads_error": roads_error,
                              "meta": (!tags).then_some(duckosm::LEVELS_META_SQL),
                              "select": duckosm::roads_select(mode, &run).map_err(String::from).map_err(err)?, "layers": layers,
                              "subset": (only && !tags).then(|| [duckosm::subset_sql(&run), duckosm::ids_sql(&run)]), "drop": drop,
                              "level_edges": duckosm::level_edges_sql(&cat).ok()}).to_string())
    }

    /// duckosmLevels(source?, nEdges?, edgeHash?) -> string: the look's keyword `levels` (JSON text) from the stored levels' metadata row
    /// (none: the file has no such row); an error says what to do.
    #[wasm_bindgen(js_name = duckosmLevels)]
    pub fn duckosm_levels(source: Option<String>, n_edges: Option<f64>, edge_hash: Option<String>) -> Result<String, JsError> {
        let row = match (&source, n_edges, &edge_hash) {
            (Some(s), Some(n), Some(h)) => Some((s.as_str(), n as i64, h.as_str())),
            _ => None,
        };
        roadstyle::duckosm::levels_keyword(row).map(|v| v.to_string()).map_err(|e| JsError::new(&e.to_string()))
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
        roadstyle::duckosm::subset_levels_keyword(row, missing as i64, example, &ids).map(|v| v.to_string()).map_err(|e| JsError::new(&e.to_string()))
    }

    /// duckosmFeaturesSelect(specs: number[], run: string) -> string | undefined: the base map's rows from the run's tables of the layers
    /// `specs` that were made.
    #[wasm_bindgen(js_name = duckosmFeaturesSelect)]
    pub fn duckosm_features_select(specs: Vec<u32>, run: &str) -> Result<Option<String>, JsError> {
        let run = roadstyle::duckosm::Run::new(run).map_err(|e| JsError::new(&e.to_string()))?;
        Ok(roadstyle::duckosm::features_select(&specs.into_iter().map(|i| i as usize).collect::<Vec<_>>(), &run))
    }

    /// readGeoParquet(bytes: Uint8Array) -> Roads: the roads of a GeoParquet file (the geometry in the column `geometry`, as styleSources
    /// reads it). An error is a thrown Error.
    #[wasm_bindgen(js_name = readGeoParquet)]
    pub fn read_geoparquet(bytes: Vec<u8>) -> Result<Roads, JsError> {
        roadstyle::read::read_roads(bytes, "geometry").map(Roads).map_err(|e| JsError::new(&e.to_string()))
    }

    /// readGeoJson(bytes: Uint8Array) -> Roads: the roads of a GeoJSON file (a FeatureCollection in EPSG:4326; roadstyle-io's geojson.rs
    /// says how each property becomes a column). An error is a thrown Error.
    #[wasm_bindgen(js_name = readGeoJson)]
    pub fn read_geojson(bytes: &[u8]) -> Result<Roads, JsError> {
        roadstyle::geojson::read_roads(bytes).map(Roads).map_err(|e| JsError::new(&e.to_string()))
    }

    /// readShp(shp: Uint8Array, dbf: Uint8Array, prj?: string, name?: string) -> Roads: the roads of a Shapefile, in EPSG:4326 (roadstyle-io's
    /// shp.rs; no prj: no CRS, an error). A GeoPackage is not read here: SQLite is C (the native programs read it). An error is a thrown Error.
    #[wasm_bindgen(js_name = readShp)]
    pub fn read_shp(shp: &[u8], dbf: &[u8], prj: Option<String>, name: Option<String>) -> Result<Roads, JsError> {
        roadstyle::shp::read_roads(shp, dbf, prj.as_deref(), name.as_deref().unwrap_or("the Shapefile")).map(Roads).map_err(|e| JsError::new(&e.to_string()))
    }

    /// tilesOfSources(sources, prefix, keep): stage 2 from memory (the typed pieces, no GeoJSON text; the sources stay as they are). The
    /// Tiler's style has the one vector source `<prefix>roads/{z}/{x}/{y}`, with the pieces' promoteId (roadstyle::tile_stage).
    #[wasm_bindgen(js_name = tilesOfSources)]
    pub fn tile_sources(sources: &Sources, prefix: &str, keep: Vec<String>) -> Result<Tiler, JsError> {
        let (style, tiles) = roadstyle::tiles_of_sources(&sources.inner, prefix, &keep).map_err(|e| JsError::new(&e.to_string()))?;
        Ok(Tiler { style, tiles })
    }

    /// A tiled map that the level editor redraws (roadstyle::relevel): `new LiveMap(sources, look, prefix, keep)` takes stage 1 (the
    /// Sources are used up) and the look that made it; `style()` and `tile(source, z, x, y)` as a Tiler's; `relevel(rows)` gives the edges
    /// new values. `rows`: JSON text, an array of levels.csv rows (`edge`, `casing_start`, `casing_level`, `casing_end`, `fill_level`,
    /// `head_start_m`, `head_end_m`, `cap_start`, `cap_end`; numbers or their text, "" or null for none); the answer is JSON text
    /// `{edges, pieces_gone, sources, style_changed}`. Then reload the map's tiles (with `style_changed`: set the style again).
    #[wasm_bindgen]
    pub struct LiveMap(roadstyle::relevel::LiveTiles);

    #[wasm_bindgen]
    impl LiveMap {
        #[wasm_bindgen(constructor)]
        pub fn new(sources: Sources, look: &JsLook, prefix: &str, keep: Vec<String>) -> Result<LiveMap, JsError> {
            roadstyle::relevel::LiveTiles::new(sources.inner, look.0.clone(), prefix, &keep).map(LiveMap).map_err(|e| JsError::new(&e.to_string()))
        }

        pub fn style(&self) -> String {
            self.0.style().to_string()
        }

        pub fn tile(&mut self, source: &str, z: u32, x: u32, y: u32) -> Vec<u8> {
            if source == roadstyle::tiles::SOURCE { self.0.tile(z, x, y) } else { Vec::new() }
        }

        /// roadLines(rows): as Sources.roadLines, from the stage 1 that the map holds.
        #[wasm_bindgen(js_name = roadLines)]
        pub fn road_lines(&self, ids: Vec<u32>) -> Vec<u8> {
            let mut out = Vec::new();
            roadstyle::write_road_lines(self.0.sources(), &ids, &mut out).expect("a Vec takes every byte");
            out
        }

        /// roadEnds(): the two end points of each row's line, 4 numbers for each row (start lon, lat, end lon, lat; NaN: no line).
        #[wasm_bindgen(js_name = roadEnds)]
        pub fn road_ends(&self) -> Vec<f64> {
            roadstyle::road_ends(self.0.sources())
        }

        pub fn relevel(&mut self, rows: &str) -> Result<String, JsError> {
            let err = |m: String| JsError::new(&format!("relevel: {m}"));
            let rows: Vec<serde_json::Value> = serde_json::from_str(rows).map_err(|e| err(e.to_string()))?;
            let text = |v: &serde_json::Value| v.as_str().map(str::trim).filter(|t| !t.is_empty()).map(String::from)
                .or_else(|| v.as_f64().map(|n| n.to_string()));
            let num = |r: &serde_json::Value, k: &str| -> Result<Option<f64>, JsError> {
                text(&r[k]).map(|t| t.parse::<f64>().map_err(|_| err(format!("{k} is not a number: {t}")))).transpose()
            };
            let int = |r: &serde_json::Value, k: &str| -> Result<i64, JsError> {
                num(r, k)?.filter(|n| n.fract() == 0.0).map(|n| n as i64).ok_or_else(|| err(format!("{k} is not a whole number")))
            };
            let rows = rows.iter().map(|r| Ok(roadstyle::relevel::LevelRow {
                edge_id: text(&r["edge"]).and_then(|t| t.parse().ok()).ok_or_else(|| err(format!("an edge id: {}", r["edge"])))?,
                levels: [int(r, "casing_start")?, int(r, "casing_level")?, int(r, "casing_end")?, int(r, "fill_level")?],
                heads: [num(r, "head_start_m")?, num(r, "head_end_m")?],
                caps: [text(&r["cap_start"]), text(&r["cap_end"])],
            })).collect::<Result<Vec<_>, JsError>>()?;
            let done = self.0.relevel(&rows).map_err(|e| JsError::new(&e.to_string()))?;
            Ok(serde_json::to_string(&done).expect("JSON of counts"))
        }
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

    /// tilesOfFiles(files, prefix, keep): stage 2 from stage 1's files (GeoJSON or GeoParquet, as style.json names them); the Tiler's
    /// style is the saved style with the one vector source (roadstyle::tiled_style).
    #[wasm_bindgen(js_name = tilesOfFiles)]
    pub fn tiles_of_files(files: &FileSet, prefix: &str, keep: Vec<String>) -> Result<Tiler, JsError> {
        let read = |n: &str| files.files.get(n).cloned().ok_or_else(|| format!("{n}: not in the files"));
        let (style, tiles) = roadstyle::tiles_of_files_with(read, &keep, None, &roadstyle::xyz_at(prefix)).map_err(|e| JsError::new(&e.to_string()))?;
        Ok(Tiler { style: style.to_string(), tiles })
    }

    /// The size of the module's memory, in bytes (it grows in steps ahead and never gets smaller: `liveBytes` gives what is held).
    #[wasm_bindgen(js_name = memoryBytes)]
    pub fn memory_bytes() -> usize {
        core::arch::wasm32::memory_size(0) * 65536
    }

    /// liveBytes() -> [now, peak]: the bytes that the program holds now, and the most it held since the last `liveBytesReset()`.
    #[wasm_bindgen(js_name = liveBytes)]
    pub fn live_bytes() -> Vec<f64> {
        use std::sync::atomic::Ordering::Relaxed;
        vec![crate::grow::LIVE.load(Relaxed) as f64, crate::grow::PEAK.load(Relaxed) as f64]
    }

    /// The times that the memory grew since the module started (dlmalloc's own steps and the allocator's steps ahead).
    #[wasm_bindgen(js_name = growSteps)]
    pub fn grow_steps() -> usize {
        crate::grow::STEPS.load(std::sync::atomic::Ordering::Relaxed)
    }

    /// The peak of `liveBytes` starts again from the bytes held now.
    #[wasm_bindgen(js_name = liveBytesReset)]
    pub fn live_bytes_reset() {
        use std::sync::atomic::Ordering::Relaxed;
        crate::grow::PEAK.store(crate::grow::LIVE.load(Relaxed), Relaxed);
    }
}
