//! The caller's overlays and the road's own line items.

use crate::color::Color;
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// An overlay (rs.Overlay): a layer of the caller's features over or under the roads. `None`: the overlays settings' value.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct Overlay {
    pub label: Option<String>,
    /// a FeatureCollection
    pub data: Value,
    /// none: from the geometries
    pub kind: Option<OverlayKind>,
    pub placement: Placement,
    pub color: Option<Color>,
    /// the property with a colour for each feature (null: `color`)
    pub color_column: Option<String>,
    pub outline: Option<Color>,
    pub opacity: Option<f64>,
    pub width: Option<f64>,
    /// a line's width in metres, exact from `min_zoom` on (in place of `width`)
    pub width_m: Option<f64>,
    pub radius: Option<f64>,
    /// a line's dash pattern, in line widths
    pub dash: Option<Vec<f64>>,
    pub popup: Option<Vec<String>>,
    /// false: a click selects it, with no floating popup
    pub popup_window: bool,
    pub tooltip: Option<Vec<String>>,
    pub visible: bool,
    pub min_zoom: Option<f64>,
    pub max_zoom: Option<f64>,
    /// a click picks its road or the item itself (with `edge`)
    pub select: Select,
    /// the features are items of the roads: drawn at their road's fill number
    pub edge: Option<EdgeLink>,
    /// `kind: text`: the text and its paint
    pub text: Option<TextStyle>,
    /// the name of a style of the theme's `overlays.styles`, whose fields fill what the overlay does not give
    pub style: Option<String>,
}

impl Overlay {
    pub(super) fn defaults() -> Overlay {
        Overlay { popup_window: true, visible: true, ..Overlay::default() }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "snake_case")]
pub enum OverlayKind {
    Fill,
    Line,
    Circle,
    Text,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "snake_case")]
pub enum Placement {
    #[default]
    Over,
    Under,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "snake_case")]
pub enum Select {
    #[default]
    Road,
    Item,
}

/// The road of each feature of an overlay (rs.Overlay's edge_col and the columns that go with it).
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct EdgeLink {
    /// the property with the id of the feature's road
    pub column: String,
    /// the property with the feature's order (lower first; null: 0)
    pub order_column: Option<String>,
    /// lines, simple mode: the property with each item's width in metres (else `width_m`)
    pub width_m_column: Option<String>,
    /// lines, simple mode: the property with each item's offset in metres (right of the line's direction; null: 0)
    pub offset_m_column: Option<String>,
    /// lines, simple mode: the property with each item's dash pattern (null: `dash`)
    pub dash_column: Option<String>,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct TextStyle {
    /// the property that holds the text
    pub column: Option<String>,
    /// px
    pub size: Option<f64>,
    pub color: Option<Color>,
    /// the halo's colour (none: no halo)
    pub halo: Option<Color>,
}

/// The road's own line items (lanes, lane lines, marks).
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct Items {
    /// a FeatureCollection whose features name their road
    pub data: Value,
    /// the fields that a clicked item shows (none: all its fields)
    pub popup: Option<Vec<String>>,
}
