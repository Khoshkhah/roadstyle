//! roadstyle's road model (docs/design/rust_library.md, "The crates"): the roads as features with typed properties (`props`), the
//! geometry helpers (`geom`), and `Feature`, the row that the readers make and the engine draws. No I/O: it builds for wasm32.

// Ported numeric code: index loops over parallel arrays and tuple types of the Python stages read as they are in Python.
#![allow(clippy::needless_range_loop, clippy::type_complexity)]

pub mod geom;
pub mod props;

use serde_json::Value;

/// One road: its properties and its line.
pub struct Feature {
    pub props: props::Props,
    /// None: not a LineString (the stages skip it, as roadstyle does)
    pub coords: Option<Vec<[f64; 2]>>,
}

/// A JSON object made by moving its values in. json!({..}) serializes each value by reference: a deep copy of a big tree (a source's features).
#[doc(hidden)]
pub fn obj<const N: usize>(kv: [(&str, Value); N]) -> Value {
    Value::Object(kv.into_iter().map(|(k, v)| (k.to_string(), v)).collect())
}
