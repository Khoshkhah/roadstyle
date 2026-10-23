//! The Python binding of roadstyle's Rust engine (docs/design/rust_library.md, phase P5): the module `roadstyle._rust`.
//! Python roadstyle calls it when the engine is "rust" (`roadstyle/_engine.py`). Each call releases the GIL while Rust works.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

/// make_style(roads, look, features=None, planner=None, name=None) -> str: the style's JSON text (roadstyle.export_inline's
/// style). `roads` and `features` are GeoParquet bytes (the geometry as WKB), `planner` the planner's Parquet bytes, `look` the
/// look's JSON text. An error is a ValueError.
#[pyfunction]
#[pyo3(signature = (roads, look, features=None, planner=None, name=None))]
fn make_style(py: Python<'_>, roads: Vec<u8>, look: String, features: Option<Vec<u8>>, planner: Option<Vec<u8>>, name: Option<String>)
              -> PyResult<String> {
    py.detach(|| roadstyle::make_style(roads, &look, features, planner, name)).map_err(PyValueError::new_err)
}

/// make_look(options) -> str: the look (look.json) of render_edges' palette, profile and settings. `options` is the JSON text of
/// {"palette", "profile", "settings", "args", "features"}.
#[pyfunction]
fn make_look(py: Python<'_>, options: String) -> PyResult<String> {
    py.detach(|| {
        let o: serde_json::Value = serde_json::from_str(&options).map_err(|e| format!("options: not JSON: {e}"))?;
        roadstyle::look::make_look(&o).map(|l| l.to_string())
    })
    .map_err(PyValueError::new_err)
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
    fn new(py: Python<'_>, roads: Vec<u8>, look: String, features: Option<Vec<u8>>, name: Option<String>, prefix: String, keep: Vec<String>)
           -> PyResult<Self> {
        let (style, tiles) = py.detach(|| roadstyle::make_tiled(roads, &look, features, name, &prefix, &keep)).map_err(PyValueError::new_err)?;
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
}

/// compute_levels(roads, method, cols) -> (rows, info): roadstyle's compute_levels with its defaults, on the roads in their order (GeoParquet
/// bytes). `method`: "tags" or "solve"; `cols`: the columns of the class, the layer, the bridge, the tunnel and the junction. `rows`: for
/// each road (casing_start, casing_level, casing_end, fill_level); `info`: the counts of the solve.
#[pyfunction]
#[allow(clippy::type_complexity)]
fn compute_levels(py: Python<'_>, roads: Vec<u8>, method: String, cols: [String; 5])
                  -> PyResult<(Vec<(i64, i64, i64, i64)>, String)> {
    let m = roadstyle::levels::Method::parse(&method).filter(|m| *m != roadstyle::levels::Method::None)
        .ok_or_else(|| PyValueError::new_err(format!("method must be 'tags' or 'solve', not {method:?}")))?;
    py.detach(|| {
        let feats = roadstyle::read::read_roads(roads, "geometry")?;
        let c: [&str; 5] = [&cols[0], &cols[1], &cols[2], &cols[3], &cols[4]];
        let edges = roadstyle::level_edges(&feats, c);
        let mut rows = vec![(0, 0, 0, 0); feats.len()];
        let Some(levels) = roadstyle::levels::compute(&edges, m)? else { return Ok((rows, "{}".into())) };
        for r in &levels.rows {
            rows[r.edge_id as usize] = (r.casing_start, r.casing_level, r.casing_end, r.fill_level);
        }
        // the counts, and the pairs (road numbers) that compute_levels gives as attrs
        let info = serde_json::json!({"roads": levels.roads, "given_up": levels.given_up, "orders_not_kept": levels.orders_not_kept,
                                      "given_up_pairs": levels.given_up_pairs, "orders_not_kept_pairs": levels.orders_not_kept_pairs});
        Ok((rows, info.to_string()))
    })
    .map_err(|e: String| PyValueError::new_err(e))
}

/// render_web._page_html in Rust (roadstyle::page): the page of a live style with the dashboard's options. `parts`: name, cam, bounds,
/// side_panel_html, host_panel_width, compress, gz (the blobs, made by Python's zlib), side_b64, side, simple_js; `pmtiles`: a tiled page.
#[pyfunction]
#[pyo3(signature = (style, page, parts, pmtiles=None))]
fn make_page(style: String, page: String, parts: String, pmtiles: Option<Vec<u8>>) -> PyResult<String> {
    roadstyle::page::make_page(&style, &page, &parts, pmtiles.as_deref()).map_err(PyValueError::new_err)
}

/// The engine's warnings since the last call of this (render_web's warnings.warn): the binding gives them as Python warnings.
#[pyfunction]
fn take_warnings() -> Vec<String> {
    roadstyle::take_warnings()
}

#[pymodule]
fn _rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(take_warnings, m)?)?;
    m.add_function(wrap_pyfunction!(make_page, m)?)?;
    m.add_function(wrap_pyfunction!(make_style, m)?)?;
    m.add_function(wrap_pyfunction!(make_look, m)?)?;
    m.add_function(wrap_pyfunction!(compute_levels, m)?)?;
    m.add_class::<Tiler>()?;
    m.add("MAX_ROADS", roadstyle::MAX_ROADS)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
