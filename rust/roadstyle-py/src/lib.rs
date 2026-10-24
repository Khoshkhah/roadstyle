//! The Python binding of roadstyle's Rust engine (docs/design/rust_library.md, phase P5): the module `roadstyle._rust`.
//! Python roadstyle calls it when the engine is "rust" (`roadstyle/_engine.py`). Each call releases the GIL while Rust works.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use std::cell::RefCell;

thread_local! {
    /// The engine's warnings of the calls since the last `take_warnings` (audit R17: the engine has no global state; it gives its
    /// warnings back with its output, and Python's warnings are global, so the binding keeps them for `take_warnings`).
    static PENDING: RefCell<Vec<String>> = const { RefCell::new(Vec::new()) };
}

fn warned(w: &[String]) {
    PENDING.with(|p| p.borrow_mut().extend_from_slice(w));
}

/// A resolved look (roadstyle-look), parsed one time: `resolve_look(options)` makes it, `Look.from_json(text)` reads a saved look
/// (version 1, or version 0: today's look.json). The calls below take it, not its text.
#[pyclass(frozen, name = "Look")]
struct PyLook(roadstyle::Look);

#[pymethods]
impl PyLook {
    /// Look.from_json(text) -> Look: a saved look (version 1 or 0). An error is a ValueError.
    #[staticmethod]
    fn from_json(text: &str) -> PyResult<Self> {
        roadstyle::Look::from_json(text).map(PyLook).map_err(|e| PyValueError::new_err(e.to_string()))
    }

    /// json() -> str: the look's text (version 1).
    fn json(&self) -> String {
        self.0.to_json()
    }

    /// part(key) -> str: the JSON text of one part of the look: "args" (the map options), "config", "theme", "palette" (its name),
    /// "settings" (the settings sources as given) or "features" (the base map's part).
    fn part(&self, key: &str) -> PyResult<String> {
        let l = &self.0;
        match key {
            "args" => Ok(l.args.to_string()),
            "config" => Ok(l.config.to_string()),
            "theme" => Ok(l.theme.to_string()),
            "palette" => Ok(serde_json::Value::from(l.palette.as_str()).to_string()),
            "settings" => Ok(l.settings.to_string()),
            "features" => Ok(l.features.to_string()),
            _ => Err(PyValueError::new_err(format!("part {key:?}: the parts are args, config, theme, palette, settings and features"))),
        }
    }

    /// with_arg(key, value) -> Look: the same look with the map option `key` set to `value` (JSON text).
    fn with_arg(&self, key: &str, value: &str) -> PyResult<Self> {
        let v: serde_json::Value = serde_json::from_str(value).map_err(|e| PyValueError::new_err(format!("{key}: not JSON: {e}")))?;
        self.0.clone().with_arg(key, v).map(PyLook).map_err(|e| PyValueError::new_err(e.to_string()))
    }
}

/// resolve_look(options) -> Look: the look of render_edges' palette, profile and settings. `options` is the JSON text of
/// {"palette", "profile", "settings", "args", "features", "files"}. An error is a ValueError.
#[pyfunction]
fn resolve_look(py: Python<'_>, options: String) -> PyResult<PyLook> {
    py.detach(|| {
        let o: serde_json::Value = serde_json::from_str(&options).map_err(|e| format!("options: not JSON: {e}"))?;
        Ok::<_, String>(roadstyle::Look::resolve(&roadstyle::look::Options::from_value(&o)?)?)
    })
    .map(PyLook)
    .map_err(PyValueError::new_err)
}

/// make_style(roads, look, features=None, planner=None, name=None) -> str: the style's JSON text (roadstyle.export_inline's
/// style). `roads` and `features` are GeoParquet bytes (the geometry as WKB), `planner` the planner's Parquet bytes, `look` a Look.
/// An error is a ValueError.
#[pyfunction]
#[pyo3(signature = (roads, look, features=None, planner=None, name=None))]
fn make_style(py: Python<'_>, roads: Vec<u8>, look: PyRef<'_, PyLook>, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>)
              -> PyResult<String> {
    let look = &look.0;
    let s = py.detach(|| roadstyle::make_sources(roads, look, features, planner, name)).map_err(PyValueError::new_err)?;
    warned(&s.warnings);
    let mut out = Vec::new();
    py.detach(|| s.write_style(&mut out)).expect("a Vec takes every byte");
    Ok(String::from_utf8(out).expect("serde_json writes UTF-8"))
}

/// A map with vector tiles: Tiler(roads, look, features=None, name=None, prefix="", keep=[]), then `style` (the style's JSON text)
/// and `tile(z, x, y)` (a vector tile, empty when nothing is in it), and `props(layer, id)` (the properties as JSON, "null" when
/// there is none).
#[pyclass(frozen)]
struct Tiler {
    #[pyo3(get)]
    style: String,
    tiles: roadstyle::tiles::Tiles,
}

#[pymethods]
impl Tiler {
    #[new]
    #[pyo3(signature = (roads, look, features=None, name=None, prefix=String::new(), keep=Vec::new()))]
    fn new(py: Python<'_>, roads: Vec<u8>, look: PyRef<'_, PyLook>, features: Option<Vec<u8>>, name: Option<String>, prefix: String,
           keep: Vec<String>) -> PyResult<Self> {
        let look = &look.0;
        let (style, tiles, w) = py.detach(|| roadstyle::make_tiled(roads, look, features, name, &prefix, &keep)).map_err(PyValueError::new_err)?;
        warned(&w);
        Ok(Tiler { style, tiles })
    }

    fn tile<'py>(&self, py: Python<'py>, z: u32, x: u32, y: u32) -> Bound<'py, PyBytes> {
        let t = py.detach(|| self.tiles.tile(z, x, y));
        PyBytes::new(py, &t)
    }

    fn props(&self, layer: &str, id: u64) -> String {
        self.tiles.props(layer, id)
    }

    /// archive(bounds, layers) -> bytes: a PMTiles archive of every tile in bounds [min lon, min lat, max lon, max lat] (roadstyle_tiles::pmtiles).
    fn archive<'py>(&self, py: Python<'py>, bounds: [f64; 4], layers: Vec<String>) -> PyResult<Bound<'py, PyBytes>> {
        let a = py.detach(|| self.tiles.archive(bounds, &layers)).ok_or_else(|| PyValueError::new_err("the archive has no tile"))?;
        Ok(PyBytes::new(py, &a))
    }

    /// bounds() -> [min lon, min lat, max lon, max lat] | None: the box of every feature in the tiles.
    fn bounds(&self) -> Option<[f64; 4]> {
        self.tiles.bounds()
    }

    /// layers() -> list[str]: the tile layers, in their order.
    fn layers(&self) -> Vec<String> {
        self.tiles.layer_names()
    }

    /// zooms() -> (first, last): the zooms of the tiles.
    fn zooms(&self) -> (u32, u32) {
        self.tiles.zooms()
    }
}

/// Stage 1 (docs/rust/architecture.md, "The three stages and the one call"): the style and its sources in memory (make_sources).
#[pyclass]
struct Sources {
    inner: roadstyle::sources::Sources,
}

fn format(f: &str) -> PyResult<roadstyle::Format> {
    match f {
        "geojson" => Ok(roadstyle::Format::GeoJson),
        "geoparquet" => Ok(roadstyle::Format::GeoParquet),
        _ => Err(PyValueError::new_err(format!("format must be 'geojson' or 'geoparquet', not {f:?}"))),
    }
}

#[pymethods]
impl Sources {
    /// save(dir, format="geojson", keep=[]) -> list[(name, size)]: stage 1's files in dir: style.json, a file for each source and
    /// road_table.parquet (every field of each road; the roads' file has their drawing values and `keep`).
    #[pyo3(signature = (dir, format="geojson", keep=Vec::new()))]
    fn save(&self, py: Python<'_>, dir: String, format: &str, keep: Vec<String>) -> PyResult<Vec<(String, usize)>> {
        let f = self::format(format)?;
        py.detach(|| roadstyle::save_sources(&self.inner, std::path::Path::new(&dir), f, &keep)).map_err(PyValueError::new_err)
    }

    /// file_names(format="geojson") -> list[str]: the names of stage 1's files.
    #[pyo3(signature = (format="geojson"))]
    fn file_names(&self, format: &str) -> PyResult<Vec<String>> {
        Ok(roadstyle::file_names(&self.inner, self::format(format)?))
    }

    /// style() -> str: the style as one JSON text with each source's GeoJSON in it (make_style's).
    fn style(&self, py: Python<'_>) -> String {
        let mut out = Vec::new();
        py.detach(|| self.inner.write_style(&mut out)).expect("a Vec takes every byte");
        String::from_utf8(out).expect("JSON text is UTF-8")
    }

    /// tile_stage(only=None, exact=None, keep=[], at=None) -> (style, Tiler): stage 2 from memory (roadstyle::tile_stage), with the
    /// look's tile settings (make_sources saves them): the style that draws the tiles (JSON text) and the tiles. `only`: the sources in
    /// the tiles (render(tiles=True)'s tile_layers; the others stay in the style), `exact`: the columns of the roads and the pieces
    /// (its tile_keep), `keep`: more columns, `at`: where the tiles are, as JSON text (`{"url": "pmtiles://roads"}`; None: a folder,
    /// `roads/{z}/{x}/{y}`). These Sources stay as they are.
    #[pyo3(signature = (only=None, exact=None, keep=Vec::new(), at=None))]
    fn tile_stage(&self, py: Python<'_>, only: Option<Vec<String>>, exact: Option<Vec<String>>, keep: Vec<String>, at: Option<String>) -> PyResult<(String, Tiler)> {
        use roadstyle::tiles::stage::{TileOptions, COLUMNS, TILES};
        let s = &self.inner;
        let mut o = TileOptions::new(&s.layers, &s.metadata, &s.saved[TILES], &s.saved[COLUMNS], &keep).map_err(PyValueError::new_err)?;
        (o.exact, o.only) = (exact.map(|e| e.into_iter().collect()), only);
        let at = match at {
            Some(t) => serde_json::from_str(&t).map_err(|e| PyValueError::new_err(format!("at: not JSON: {e}")))?,
            None => roadstyle::xyz_at(""),
        };
        let (style, tiles) = py.detach(|| roadstyle::tile_stage(s, &o, &at));
        let style = style.to_string();
        Ok((style.clone(), Tiler { style, tiles }))
    }

    /// page_arrows(): stage 3 of a page with inline data: its one-way arrows are points that the page puts itself (the source arrows).
    fn page_arrows(&mut self) {
        self.inner.page_arrows();
    }

    /// metadata() -> str: the style's metadata as JSON text (the controls, the interaction, the colour options), without the sources.
    fn metadata(&self) -> String {
        self.inner.metadata.to_string()
    }

    /// add_palettes(base, looks): a page's views with other palettes (looks: [(palette, Look)]), merged into these Sources (the
    /// palette `base`): each property that differs gets a copy for each palette, `<key>@<palette>`, read by the state rs_palette.
    fn add_palettes(&mut self, py: Python<'_>, base: String, looks: Vec<(String, PyRef<'_, PyLook>)>) -> PyResult<()> {
        let looks: Vec<(String, roadstyle::Look)> = looks.into_iter().map(|(n, l)| (n, l.0.clone())).collect();
        let s = &mut self.inner;
        let before = s.warnings.len();
        py.detach(|| roadstyle::palettes::add(s, &base, &looks)).map_err(PyValueError::new_err)?;
        warned(&s.warnings[before..]);
        Ok(())
    }

    /// road_table() -> str: the road table as the page loads it (tiles.sidecar's form: props, mids, bboxes, lines).
    fn road_table(&self, py: Python<'_>) -> String {
        let mut out = Vec::new();
        py.detach(|| roadstyle::write_road_table(&self.inner, &mut out)).expect("a Vec takes every byte");
        String::from_utf8(out).expect("JSON text is UTF-8")
    }

    /// file(name, format="geojson", keep=[]) -> bytes: one of stage 1's files.
    #[pyo3(signature = (name, format="geojson", keep=Vec::new()))]
    fn file<'py>(&self, py: Python<'py>, name: &str, format: &str, keep: Vec<String>) -> PyResult<Bound<'py, PyBytes>> {
        let f = self::format(format)?;
        let b = py.detach(|| roadstyle::source_file(&self.inner, name, f, &self.inner.drawn(&keep))).map_err(PyValueError::new_err)?;
        Ok(PyBytes::new(py, &b))
    }
}

/// make_sources(roads, look, features=None, planner=None, name=None) -> Sources: stage 1, as make_style's arguments.
#[pyfunction]
#[pyo3(signature = (roads, look, features=None, planner=None, name=None))]
fn make_sources(py: Python<'_>, roads: Vec<u8>, look: PyRef<'_, PyLook>, features: Option<Vec<u8>>, planner: Option<Vec<u8>>,
                name: Option<String>) -> PyResult<Sources> {
    let look = &look.0;
    let inner = py.detach(|| roadstyle::make_sources(roads, look, features, planner, name)).map_err(PyValueError::new_err)?;
    warned(&inner.warnings);
    Ok(Sources { inner })
}

/// tile_files(dir, keep=[], prefix="") -> Tiler: stage 2 from stage 1's files in dir (GeoJSON or GeoParquet, as style.json names
/// them); the Tiler's style is the saved style with the one vector source.
#[pyfunction]
#[pyo3(signature = (dir, keep=Vec::new(), prefix=String::new()))]
fn tile_files(py: Python<'_>, dir: String, keep: Vec<String>, prefix: String) -> PyResult<Tiler> {
    let (style, tiles) = py.detach(|| roadstyle::tile_files(std::path::Path::new(&dir), &keep, None, &roadstyle::xyz_at(&prefix))).map_err(PyValueError::new_err)?;
    Ok(Tiler { style: style.to_string(), tiles })
}

/// compute_levels(roads, method, cols, ...) -> (rows, info): roadstyle's compute_levels on the roads in their order (GeoParquet bytes), with
/// its keywords. `method`: "tags" or "solve"; `cols`: the columns of the class, the layer, the bridge, the tunnel and the junction; `order`:
/// "priority", "class", a column of numbers or None. `rows`: for each road (casing_start, casing_level, casing_end, fill_level); `info`:
/// the counts of the solve.
#[pyfunction]
#[pyo3(signature = (roads, method, cols, band_col=None, order=None, band_dist=10.0, head_m=5.0, max_level=20, margin=1.0,
                    min_positions=true, near_rules=false))]
#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn compute_levels(py: Python<'_>, roads: Vec<u8>, method: String, cols: [String; 5], band_col: Option<String>, order: Option<String>,
                  band_dist: f64, head_m: f64, max_level: i64, margin: f64, min_positions: bool, near_rules: bool)
                  -> PyResult<(Vec<(i64, i64, i64, i64)>, String)> {
    use roadstyle::levels::{Method, Options, Order};
    let m = Method::parse(&method).filter(|m| *m != Method::None)
        .ok_or_else(|| PyValueError::new_err(format!("method must be 'tags' or 'solve', not {method:?}")))?;
    let (order, order_col) = match order.as_deref() {
        None => (Order::None, ""),
        Some("priority") => (Order::Priority, ""),
        Some("class") => (Order::Class, ""),
        Some(c) => (Order::Column, c),
    };
    let o = Options { method: m, band_col: band_col.is_some(), order, band_dist, head_m, max_level, margin, min_positions, near_rules,
                      ..Default::default() };
    py.detach(|| {
        let feats = roadstyle::read::read_roads(roads, "geometry")?;
        let edges = roadstyle::level_edges(&feats, [&cols[0], &cols[1], &cols[2], &cols[3], &cols[4], band_col.as_deref().unwrap_or(""), order_col]);
        let mut rows = vec![(0, 0, 0, 0); feats.len()];
        let Some(levels) = roadstyle::levels::levels(&edges, &o)? else { return Ok((rows, "{}".into())) };
        for r in &levels.rows {
            rows[r.edge_id as usize] = (r.casing_start, r.casing_level, r.casing_end, r.fill_level);
        }
        // the counts, and the pairs and parts (road numbers) that compute_levels gives as attrs
        // the names of Python's levels_info
        let info = serde_json::json!({"roads": levels.roads, "pairs": levels.pairs, "order_pairs": levels.order_pairs,
                                      "given_up": levels.given_up, "order_violations": levels.orders_not_kept,
                                      "given_up_pairs": levels.given_up_pairs, "orders_not_kept_pairs": levels.orders_not_kept_pairs,
                                      "near_not_kept": levels.near_not_kept});
        Ok((rows, info.to_string()))
    })
    .map_err(|e: String| PyValueError::new_err(e))
}

/// solve_rules(roads, meets, lifts, near, orders, fixed, steps, min_positions) -> (parts, given_up_parts, orders_not_kept, near_not_kept):
/// roadstyle's _solve_intervals by the Rust solver, on road indexes (solve_levels(engine="rust")). A meet is (x, x_end, y, y_end) with the
/// ends 0 (start) or 2 (end); a stack or near rule (upper, lower, part 0, 1 or 2); a fixed road (road, its four numbers in [0, steps]).
#[pyfunction]
#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn solve_rules(py: Python<'_>, roads: usize, meets: Vec<(usize, usize, usize, usize)>, lifts: Vec<(usize, usize, usize)>,
               near: Vec<(usize, usize, usize)>, orders: Vec<(usize, usize)>, fixed: Vec<(usize, [i64; 4])>, steps: i64, min_positions: bool)
               -> PyResult<(Vec<[i64; 4]>, Vec<(usize, usize, usize)>, Vec<(usize, usize)>, Vec<(usize, usize, usize)>)> {
    let rules = roadstyle::levels::solve::Rules { roads, meets, lifts, orders, near, fixed };
    let s = py.detach(|| roadstyle::levels::solve::solve(&rules, steps, min_positions)).map_err(PyValueError::new_err)?;
    Ok((s.parts, s.given_up_parts, s.orders_not_kept, s.near_not_kept))
}

/// render_web._page_html in Rust (roadstyle::page): the page of a live style with the dashboard's options. `parts`: name, cam, bounds,
/// side_panel_html, host_panel_width, compress, gz (the blobs, made by Python's zlib), side_b64, side, simple_js; `pmtiles`: a tiled page.
#[pyfunction]
#[pyo3(signature = (style, page, parts, pmtiles=None))]
fn make_page(style: String, page: String, parts: String, pmtiles: Option<Vec<u8>>) -> PyResult<String> {
    roadstyle::page::make_page(&style, &page, &parts, pmtiles.as_deref()).map_err(PyValueError::new_err)
}

/// export_look(look, cols, positions) -> str: the simple look for another app's data layer (roadstyle_engine::export_look); `cols`: the
/// columns [highway, oneway, tunnel, bridge, id].
#[pyfunction]
fn export_look(look: PyRef<'_, PyLook>, cols: [String; 5], positions: Vec<i64>) -> PyResult<String> {
    let c = roadstyle::export_look::LookCols { highway: &cols[0], oneway: &cols[1], tunnel: &cols[2], bridge: &cols[3], id: &cols[4] };
    roadstyle::export_look::export_look(&look.0, &c, &positions).map(|v| v.to_string()).map_err(PyValueError::new_err)
}

/// make_area(edges, folder, ...) -> (roads, pairs, warnings): roadstyle's make_area (level_input) in Rust (roadstyle::level_area): writes
/// roads.parquet, pairs.csv and, the first time, edits.csv in `folder`, from the edges (GeoParquet bytes); the keywords of level_input.
#[pyfunction]
#[pyo3(signature = (edges, folder, id_col="edge_id".to_string(), highway_col="highway".to_string(), layer_col="layer".to_string(),
                    bridge_col="bridge".to_string(), tunnel_col="tunnel".to_string(), junction_col="junction".to_string(), band_col=None,
                    order=Some("priority".to_string()), band_dist=10.0, head_m=5.0, near_rules=false))]
#[allow(clippy::too_many_arguments)]
fn make_area(py: Python<'_>, edges: Vec<u8>, folder: String, id_col: String, highway_col: String, layer_col: String, bridge_col: String,
             tunnel_col: String, junction_col: String, band_col: Option<String>, order: Option<String>, band_dist: f64, head_m: f64,
             near_rules: bool) -> PyResult<(usize, usize, Vec<String>)> {
    let o = roadstyle::level_area::MakeOptions { id_col, highway_col, layer_col, bridge_col, tunnel_col, junction_col, band_col, order, band_dist,
                                                 head_m, near_rules };
    py.detach(|| {
        let table = roadstyle::read::read_roads(edges, "geometry")?;
        roadstyle::level_area::make_area(&table, std::path::Path::new(&folder), &o).map(|m| (m.roads, m.pairs, m.warnings))
    }).map_err(|e: String| PyValueError::new_err(e))
}

/// base_map_theme(theme) -> str: a base map's theme (roadstyle-look's basemap::load_theme) as JSON text: [osm_carto.yaml in the theme's
/// colours, the theme file itself, [saturation, lighten] of its transform]. An unknown theme is a ValueError that names the themes.
#[pyfunction]
fn base_map_theme(theme: &str) -> PyResult<String> {
    let (style, file, (s, l)) = roadstyle::look::basemap::load_theme(theme).map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(serde_json::json!([style, file, [s, l]]).to_string())
}

/// base_map_recolor(colour, saturation, lighten) -> str: a "#rrggbb" colour with a theme's transform (basemap::recolor); another
/// value (JSON text) as it is. Gives JSON text.
#[pyfunction]
fn base_map_recolor(colour: &str, saturation: f64, lighten: f64) -> PyResult<String> {
    let v: serde_json::Value = serde_json::from_str(colour).map_err(|e| PyValueError::new_err(format!("colour: not JSON: {e}")))?;
    Ok(roadstyle::look::basemap::recolor(&v, saturation, lighten).to_string())
}

/// duckosm_catalog_sql(catalog) -> [str, str]: the queries of the tables (schema, table) and the columns (schema, table, column) of a
/// duckOSM file, for duckosm_plan.
#[pyfunction]
fn duckosm_catalog_sql(catalog: &str) -> [String; 2] {
    roadstyle::duckosm::catalog_sql(catalog)
}

/// duckosm_plan(tables, columns, mode, tags, specs, only=False) -> str: the SQL that reads a duckOSM file (roadstyle_io::duckosm, the one
/// copy of it), as JSON text: {"roads": [3 statements] (null when the file has no network of `mode`: "roads_error" says why), "meta": the stored levels' query or null (tags), "select": the roads of `mode`,
/// "layers": [{"spec", "name", "sql": [the queries in order]}] for the base map (`specs`: layers.yaml's layers as JSON text), "subset":
/// with `only` (the map of `mode` alone), the queries of its roads with no stored levels and of its edge_ids}. `tables` and `columns`: the rows of the
/// catalog's information_schema.
#[pyfunction]
#[pyo3(signature = (tables, columns, mode, tags, specs, only=false))]
fn duckosm_plan(tables: Vec<(String, String)>, columns: Vec<(String, String, String)>, mode: &str, tags: bool, specs: &str, only: bool)
                -> PyResult<String> {
    use roadstyle::duckosm;
    let cat = duckosm::Catalog { tables, columns };
    let specs: Vec<serde_json::Value> = serde_json::from_str(specs).map_err(|e| PyValueError::new_err(format!("specs: {e}")))?;
    // the base map's queries also for a file with no network: then "roads" is null and "roads_error" says why
    let (roads, roads_error) = match duckosm::roads_sql(&cat, tags, only.then_some(mode)) {
        Ok(r) => (Some(r), None),
        Err(e) => (None, Some(e)),
    };
    let select = duckosm::roads_select(mode).map_err(PyValueError::new_err)?;
    let layers: Vec<serde_json::Value> = duckosm::features_sql(&cat, &specs).into_iter()
        .map(|l| serde_json::json!({"spec": l.spec, "name": l.name, "sql": l.sql})).collect();
    let meta = (!tags).then_some(duckosm::LEVELS_META_SQL);
    let subset = (only && !tags).then_some([duckosm::SUBSET_SQL, duckosm::IDS_SQL]);
    Ok(serde_json::json!({"roads": roads, "roads_error": roads_error, "meta": meta, "select": select, "layers": layers, "subset": subset}).to_string())
}

/// duckosm_levels(row) -> str: the look's keyword `levels` (JSON text) from the stored levels' metadata row (source, n_edges, edge_hash),
/// or a ValueError that says what to do.
#[pyfunction]
#[pyo3(signature = (row=None))]
fn duckosm_levels(row: Option<(String, i64, String)>) -> PyResult<String> {
    roadstyle::duckosm::levels_keyword(row.as_ref().map(|(s, n, h)| (s.as_str(), *n, h.as_str()))).map(|v| v.to_string()).map_err(PyValueError::new_err)
}

/// duckosm_subset_levels(row, missing, example, ids) -> str: the look's keyword `levels` (JSON text) of the stored levels for a map of one
/// mode: `row` the stored levels' metadata, `missing` and `example` the row of the plan's "subset" query, `ids` the map's edge_ids.
#[pyfunction]
#[pyo3(signature = (row, missing, example, ids))]
fn duckosm_subset_levels(row: Option<(String, i64, String)>, missing: i64, example: Option<i64>, ids: Vec<i64>) -> PyResult<String> {
    roadstyle::duckosm::subset_levels_keyword(row.as_ref().map(|(s, n, h)| (s.as_str(), *n, h.as_str())), missing, example, &ids)
        .map(|v| v.to_string()).map_err(PyValueError::new_err)
}

/// duckosm_features_select(specs) -> str | None: the base map's rows from the tables f<spec> that were made.
#[pyfunction]
fn duckosm_features_select(specs: Vec<usize>) -> Option<String> {
    roadstyle::duckosm::features_select(&specs)
}

/// serve(area, port, page=None): roadstyle serve (roadstyle-cli) in a thread of its own: the level editor's page files (in the extension,
/// or the folder `page`) at / and the area folder at /area/, on 127.0.0.1. Returns at once; the server stops with the Python process
/// (roadstyle-levels edit waits for Ctrl+C). An error when the extension has no editor WebAssembly package (build_editor.sh, then build).
#[pyfunction]
#[pyo3(signature = (area, port, page=None))]
fn serve(area: String, port: u16, page: Option<String>) -> PyResult<()> {
    let page = page.map_or(roadstyle_cli::Page::Embedded, |p| roadstyle_cli::Page::Dir(p.into()));
    if matches!(page, roadstyle_cli::Page::Embedded) && !roadstyle_cli::EMBEDDED.iter().any(|(n, _)| n.ends_with("_bg.wasm")) {
        return Err(PyValueError::new_err("this build has no WebAssembly package of the level editor: run rust/roadstyle-wasm/build_editor.sh, \
                                          then build the extension again (python rust/roadstyle-py/build.py), or use --engine python"));
    }
    // bind here, so an error (the port in use) comes back to Python
    std::net::TcpListener::bind(("127.0.0.1", port)).map_err(|e| PyValueError::new_err(format!("127.0.0.1:{port}: {e}")))?;
    std::thread::spawn(move || roadstyle_cli::serve(std::path::Path::new(&area), page, port));
    Ok(())
}

/// The engine's warnings since the last call of this (render_web's warnings.warn): the binding gives them as Python warnings.
#[pyfunction]
fn take_warnings() -> Vec<String> {
    PENDING.with(|p| std::mem::take(&mut *p.borrow_mut()))
}

#[pymodule]
fn _rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(take_warnings, m)?)?;
    m.add_function(wrap_pyfunction!(make_page, m)?)?;
    m.add_function(wrap_pyfunction!(export_look, m)?)?;
    m.add_function(wrap_pyfunction!(make_style, m)?)?;
    m.add_function(wrap_pyfunction!(resolve_look, m)?)?;
    m.add_class::<PyLook>()?;
    m.add_function(wrap_pyfunction!(compute_levels, m)?)?;
    m.add_function(wrap_pyfunction!(solve_rules, m)?)?;
    m.add_function(wrap_pyfunction!(serve, m)?)?;
    m.add_function(wrap_pyfunction!(make_area, m)?)?;
    m.add_function(wrap_pyfunction!(base_map_theme, m)?)?;
    m.add_function(wrap_pyfunction!(base_map_recolor, m)?)?;
    m.add_function(wrap_pyfunction!(duckosm_catalog_sql, m)?)?;
    m.add_function(wrap_pyfunction!(duckosm_plan, m)?)?;
    m.add_function(wrap_pyfunction!(duckosm_levels, m)?)?;
    m.add_function(wrap_pyfunction!(duckosm_subset_levels, m)?)?;
    m.add_function(wrap_pyfunction!(duckosm_features_select, m)?)?;
    m.add_class::<Tiler>()?;
    m.add_class::<Sources>()?;
    m.add_function(wrap_pyfunction!(make_sources, m)?)?;
    m.add_function(wrap_pyfunction!(tile_files, m)?)?;
    m.add("MAX_ROADS", roadstyle::MAX_ROADS)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
