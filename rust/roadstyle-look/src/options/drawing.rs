//! How the roads, their names, arrows, tunnels and bridges are drawn.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// The width of a road by data.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct Width {
    /// the column of the value (the data styler's column, when it is not given)
    pub by: Option<String>,
    /// (min, max) in px
    pub range: Option<(f64, f64)>,
    /// roads in metres: the zoom where a metre width is the class width
    pub m_zoom: Option<f64>,
}

/// The drawing of the roads.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct Roads {
    /// false: the casing of each road, not its fill (the fill layers stay, for the clicks)
    pub fill: bool,
    /// the length of a road's head in metres
    pub head_m: Option<f64>,
    /// roads in metres: the casing in metres
    pub casing_m: Option<f64>,
    /// roads in metres: a casing is never thinner than this many pixels each side
    pub casing_min_px: Option<f64>,
    /// two-way roads: each direction this part of the road width aside
    pub offset_frac: Option<f64>,
    /// two-way roads: each direction this part of the road width
    pub width_frac: Option<f64>,
    /// two-way roads: the zoom where the two directions separate
    pub offset_zoom: Option<f64>,
    /// the first zoom of each class
    pub minzoom: ClassMinzoom,
}

impl Default for Roads {
    fn default() -> Roads {
        Roads { fill: true, head_m: None, casing_m: None, casing_min_px: None, offset_frac: None, width_frac: None, offset_zoom: None,
                minzoom: ClassMinzoom::default() }
    }
}

/// The first zoom of each class: the profile's table, none (every class at every zoom), or the profile's table with these changes.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "snake_case", deny_unknown_fields)]
pub enum ClassMinzoom {
    #[default]
    Profile,
    Off,
    Table(Map<String, Value>),
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct Labels {
    /// the street names
    pub on: bool,
}

impl Default for Labels {
    fn default() -> Labels {
        Labels { on: true }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct Arrows {
    /// the one-way arrows
    pub on: bool,
}

impl Default for Arrows {
    fn default() -> Arrows {
        Arrows { on: true }
    }
}

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct Tunnels {
    /// the "Tunnels" box (a tool for choosing the tunnel look)
    pub control: bool,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct Bridges {
    /// the raised 3D bridge decks, and the page opens tilted
    pub decks_3d: bool,
}
