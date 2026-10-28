//! The clicks, the popup and the hover tooltip of the roads.

use crate::color::Color;
use serde::{Deserialize, Serialize};

/// The clicks and the hover of the roads.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default, deny_unknown_fields)]
pub struct Interaction {
    pub popup: Popup,
    /// none: no tooltip
    pub tooltip: Option<Tooltip>,
    pub hover_color: Option<Color>,
    pub select_color: Option<Color>,
}

/// The road popup.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "snake_case", deny_unknown_fields)]
pub enum Popup {
    /// the look's fields
    #[default]
    Default,
    /// these columns
    Fields(Vec<String>),
    /// every column
    All,
    /// the look's fields, in the docked panel
    Panel,
    /// no popup (a click still selects)
    Off,
}

/// The hover tooltip of the roads.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "snake_case", deny_unknown_fields)]
pub enum Tooltip {
    /// every column
    All,
    /// these columns
    Fields(Vec<String>),
}
