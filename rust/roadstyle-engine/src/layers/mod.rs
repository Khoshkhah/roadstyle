//! The road layers (full port step 2, docs/design/rust-spike.md): the expression builders, over the road tables of
//! `_load_road_model` (look.json "roads_model" and "theme"). `exprs`: the width and offset expressions and the filters; `eval`: the
//! evaluator that finds the layers no feature can draw; `build`: the road layers of a style; `restyle`: the overlays' second pass;
//! `labels`: the names' size and filter.

mod build;
mod eval;
mod exprs;
mod labels;
mod restyle;

use roadstyle_model::mark::Mark;
use crate::overlays::{edge_overlay, overlay_layers, Overlay};
use crate::props::{Get, Props};
use roadstyle_model::Cell;
use roadstyle_look::sections::{LabelLook, Num};
use indexmap::IndexMap;
use serde_json::{json, Map, Value};
use std::collections::{HashMap, HashSet};

/// Round x to n decimals (roadstyle-look's: one copy).
pub(crate) use roadstyle_look::round_to;

/// The road width model of the look (roadstyle-look), made one time with the look.
pub use roadstyle_look::RoadModel as Model;

pub use build::{road_layers, PageInfo};
pub use exprs::*;
pub(crate) use eval::swap;
pub(crate) use labels::{label_readable_filter, label_size_expr};
use eval::*;
use restyle::*;
