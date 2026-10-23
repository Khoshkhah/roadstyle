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
}

#[pymodule]
fn _rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(make_style, m)?)?;
    m.add_function(wrap_pyfunction!(make_look, m)?)?;
    m.add_class::<Tiler>()?;
    m.add("MAX_ROADS", roadstyle::MAX_ROADS)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
