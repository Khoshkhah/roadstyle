//! The map options (docs/design/t3_map_options_and_look.md, audit N32): what a caller chooses for one map, the keys that change the output
//! of stage 1 (the style, its sources, the road table). The page's keys are `PageOptions` (the facade's page.rs); the style writer's are
//! `SourceMode`, the tiles' `TileOptions`.
//!
//! Two forms come in. `MapOptions::from_json` reads the nested form: an unknown key is an error with its path and the nearest known key.
//! `MapOptions::from_args` reads render_edges' flat keywords (`highway_col`, `color_by`, ...), the `args` of a look of version 1: it maps
//! each map keyword and gives the names of the other keywords (the page's, the host's, a misspelt one) to the caller, which knows the
//! page's keys.

mod colour;
mod drawing;
mod flat;
mod names;
mod overlay;
mod popup;
#[cfg(test)]
mod tests;

pub use colour::*;
pub use drawing::*;
pub use flat::keywords;
pub use names::{nearest, nearest_name};
pub use overlay::*;
pub use popup::*;

use crate::Error;
use flat::{at, flat, set};
use names::explain;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// The map options. Each group has its default; a value that the profile gives is an `Option`: `None` is the profile's value.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
#[non_exhaustive]
pub struct MapOptions {
    pub columns: Columns,
    pub levels: Levels,
    /// the data colours
    pub color: DataColor,
    pub width: Width,
    pub roads: Roads,
    pub interaction: Interaction,
    pub labels: Labels,
    pub arrows: Arrows,
    pub tunnels: Tunnels,
    pub bridges: Bridges,
    pub overlays: Vec<Overlay>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub items: Option<Items>,
    /// GeoJSON: a geometry, a Feature or a FeatureCollection
    #[serde(skip_serializing_if = "Option::is_none")]
    pub boundary: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub base_map: Option<BaseMapOptions>,
    pub output: Output,
}

/// The columns of the roads that the engine reads, by their names in the caller's table (the engine's own name when none is given).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct Columns {
    /// the road class (OSM's `highway`)
    pub class: String,
    pub tunnel: Option<String>,
    pub bridge: Option<String>,
    pub layer: Option<String>,
    pub edge_id: Option<String>,
    /// a two-way road as one edge (true) or as two
    pub directed: Option<String>,
    pub driving: Option<String>,
    pub access: Option<String>,
    /// the column that the filter panel lists, when it is not the class
    pub filter: Option<String>,
    /// each road's width in metres
    pub width_m: Option<String>,
    /// the cap of each road's ends
    pub cap: Option<String>,
    /// the drawing positions, when the caller gives them (`Levels::Given` or `Levels::Stored`)
    pub levels: Option<LevelColumns>,
}

impl Default for Columns {
    fn default() -> Columns {
        Columns { class: "highway".into(), tunnel: None, bridge: None, layer: None, edge_id: None, directed: None, driving: None,
                  access: None, filter: None, width_m: None, cap: None, levels: None }
    }
}

/// The columns of the drawing positions (compute_levels' output columns).
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct LevelColumns {
    pub casing_start: Option<String>,
    pub casing_level: Option<String>,
    pub casing_end: Option<String>,
    pub fill_level: Option<String>,
    pub head_start_m: Option<String>,
    pub head_end_m: Option<String>,
    pub cap_start: Option<String>,
    pub cap_end: Option<String>,
}

/// Where the drawing positions come from.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "snake_case", deny_unknown_fields)]
pub enum Levels {
    /// the given columns, else the input's contract columns casing_level / fill_level (duckOSM's stored levels), else solved
    /// (docs/reference/contract.md, "The drawing positions"; duckosm.read(levels="auto"))
    #[default]
    Auto,
    /// the engine solves them (compute_levels(method="solve")), whatever the input has
    Solve,
    /// the engine computes them with the tags rule
    Tags,
    /// a duckOSM file's stored levels (`columns.levels`), solved for these edges: the engine checks that the edges are the same
    Stored { edge_hash: String, n_edges: u64 },
    /// the caller's columns (`columns.levels`)
    Given,
}

/// A duckOSM map's base map: its modes and the start values of its layers.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct BaseMapOptions {
    /// the mode columns of the road table (driving, walking, cycling, ...)
    pub modes: Vec<String>,
    /// a layer's start values
    pub layers: Map<String, Value>,
}

/// The output: its name and its state.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct Output {
    pub name: Option<String>,
    pub state: State,
    /// the feature states that a page's dashboard colours the roads with (rs.setData)
    pub live_data: bool,
    /// a style for an app with no road table (export_inline, export_style): the source `roads` with its pick and highlight layers, and
    /// the export's arrows (fewer, one in the middle of each slot, and the slots' numbers). A map option because it changes stage 1: its
    /// layers go through every pass, and they change the arrows layer and the controls (2026-10-25).
    pub export: bool,
}

/// A style with its state baked in, or one that keeps MapLibre's global state (a page with the dashboard).
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "snake_case")]
pub enum State {
    #[default]
    Static,
    Live,
}

impl MapOptions {
    /// The options from their nested JSON text. An unknown key is an error with its path and the nearest known key.
    pub fn from_json(text: &str) -> Result<MapOptions, Error> {
        MapOptions::from_value(serde_json::from_str(text).map_err(|e| Error::Options(format!("map options: {e}")))?)
    }

    /// The options from their nested JSON value. An unknown key is an error with its path and the nearest known key.
    pub fn from_value(v: Value) -> Result<MapOptions, Error> {
        serde_json::from_value::<MapOptions>(v.clone()).map_err(|e| Error::Options(explain(&v, &e.to_string())))
    }

    /// The options of render_edges' flat keywords (the `args` of a look of version 1), and the names of the keywords that are not map
    /// options (the page's, the host's, a misspelt one), in their order: the caller knows the page's keys and checks them. A map keyword
    /// with a value of the wrong kind is an error that names it.
    pub fn from_args(args: &Value) -> Result<(MapOptions, Vec<String>), Error> {
        let f = flat(args)?;
        Ok((MapOptions::from_value(Value::Object(f.out))?, f.rest))
    }

    /// These options with the flat keywords `args` over them: each field that a keyword sets changes, the others stay. The names of the
    /// keywords that are not map options, as `from_args`.
    pub fn with_args(&self, args: &Value) -> Result<(MapOptions, Vec<String>), Error> {
        let f = flat(args)?;
        let Value::Object(mut base) = serde_json::to_value(self).expect("the map options are JSON") else { unreachable!("a mapping") };
        for p in &f.paths {
            set(&mut base, p, at(&f.out, p).cloned().unwrap_or(Value::Null));
        }
        Ok((MapOptions::from_value(Value::Object(base))?, f.rest))
    }
}
