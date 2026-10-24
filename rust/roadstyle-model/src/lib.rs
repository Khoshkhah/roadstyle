//! roadstyle's road model (docs/design/rust_library.md, "The crates"): the roads as features with typed properties (`props`), the
//! geometry helpers (`geom`), `Feature`, the road that the readers make and the engine draws, and `Row`, a row of another table. No I/O: it builds for wasm32.

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

/// One row of another table (the base map's features, the route planner's parts): its columns, and the bytes of its blob column (the
/// WKB geometry of a base-map feature; None in a table with no blob).
pub struct Row {
    pub cols: serde_json::Map<String, Value>,
    pub blob: Option<Vec<u8>>,
}

/// A JSON object made by moving its values in. json!({..}) serializes each value by reference: a deep copy of a big tree (a source's features).
#[doc(hidden)]
pub fn obj<const N: usize>(kv: [(&str, Value); N]) -> Value {
    Value::Object(kv.into_iter().map(|(k, v)| (k.to_string(), v)).collect())
}
