//! The colours of a map coloured by data.

use crate::color::Color;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// The colours of a map coloured by data (render_edges' data styler, colour table and colour options).
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct DataColor {
    /// the column that gives each road its colour
    pub by: Option<String>,
    pub colors: Option<Colors>,
    pub cmap: Option<Cmap>,
    pub vmin: Option<f64>,
    pub vmax: Option<f64>,
    pub missing: Missing,
    /// a styler object (render_edges' `style`), as its JSON
    pub style: Option<Value>,
    /// a colour for each road, by the value of a column
    pub table: Option<ColorTable>,
    /// the "Colour by" menu: one colouring for each option
    pub options: Vec<ColorOption>,
    /// the option shown first: its number or its name
    pub active: Option<Active>,
}

/// Categorical colours: a colour for each value, or `"self"` (the value is the colour).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(untagged)]
pub enum Colors {
    Map(Map<String, Value>),
    Itself(Itself),
}

/// The text `"self"`.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
pub enum Itself {
    #[serde(rename = "self")]
    Itself,
}

/// A numeric ramp: a colour map's name, or a list of colours.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(untagged)]
pub enum Cmap {
    Name(String),
    Colors(Vec<Color>),
}

/// In a colour option: a road with no value keeps the first option's fill (`base`) or takes the no-data colour (`self`).
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "snake_case")]
pub enum Missing {
    #[default]
    Base,
    #[serde(rename = "self")]
    Itself,
}

/// A colour for each road: `colors` by the value of the column `key`.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct ColorTable {
    pub colors: Map<String, Value>,
    #[serde(default = "edge_id")]
    pub key: String,
}

fn edge_id() -> String {
    "edge_id".into()
}

/// One option of the "Colour by" menu: the keys of a data styler, all optional (none: the class style).
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct ColorOption {
    pub name: String,
    pub by: Option<String>,
    pub colors: Option<Colors>,
    pub cmap: Option<Cmap>,
    pub vmin: Option<f64>,
    pub vmax: Option<f64>,
    /// the width follows the value: (min, max) in px
    pub width: Option<(f64, f64)>,
    pub missing: Missing,
    pub palette: Option<String>,
    pub style: Option<Value>,
}

/// An option of the "Colour by" menu: its number or its name.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(untagged)]
pub enum Active {
    Index(usize),
    Name(String),
}
