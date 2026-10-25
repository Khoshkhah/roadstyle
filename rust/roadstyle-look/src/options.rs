//! The map options (docs/design/t3_map_options_and_look.md, audit N32): what a caller chooses for one map, the keys that change the output
//! of stage 1 (the style, its sources, the road table). The page's keys are `PageOptions` (the facade's page.rs); the style writer's are
//! `SourceMode`, the tiles' `TileOptions`.
//!
//! Two forms come in. `MapOptions::from_json` reads the nested form: an unknown key is an error with its path and the nearest known key.
//! `MapOptions::from_args` reads render_edges' flat keywords (`highway_col`, `color_by`, ...), the `args` of a look of version 1: it maps
//! each map keyword and gives the names of the other keywords (the page's, the host's, a misspelt one) to the caller, which knows the
//! page's keys.

use crate::color::Color;
use crate::Error;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};

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
    fn defaults() -> Overlay {
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

/// The fields of render_edges' flat keywords (`flat`).
struct Flat {
    /// the sparse options: the fields that the keywords set
    out: Map<String, Value>,
    /// the paths of those fields, in order
    paths: Vec<String>,
    /// the names of the keywords that are not map options
    rest: Vec<String>,
}

/// The fields of render_edges' flat keywords `args`.
fn flat(args: &Value) -> Result<Flat, Error> {
    let empty = Map::new();
    let a = match args {
        Value::Object(a) => a,
        Value::Null => &empty,
        other => return Err(Error::Options(format!("map options: a mapping of keywords, not {other}"))),
    };
    let mut out = Map::new();
    let mut paths: Vec<String> = Vec::new();
    let mut rest = Vec::new();
    for (k, v) in a {
        if v.is_null() && k != "minzoom" {
            continue;       // a keyword given as None: its default
        }
        if let Some(path) = FLAT.iter().find(|f| f.0 == k).map(|f| f.1) {
            put(&mut out, &mut paths, path, v.clone());
        } else if !SPECIAL.contains(&k.as_str()) {
            rest.push(k.clone());
        }
    }
    let get = |k: &str| a.get(k).filter(|v| !v.is_null());
    // the drawing positions: stored ({edge_hash, n_edges}), the tags rule ("tags"), solved whatever the input has ("solve", 2026-10-25:
    // the engine reads an input's contract columns casing_level / fill_level when no keyword is given), the caller's columns, else solved
    let levels = match (get("levels"), out.get("columns").and_then(|c| c.get("levels"))) {
        (Some(Value::Object(m)), _) => json!({"stored": m}),
        (Some(Value::String(s)), _) if s == "tags" || s == "solve" => json!(s),
        (Some(other), _) => return Err(Error::Options(format!("levels: {{edge_hash, n_edges}}, \"tags\" or \"solve\", not {other}"))),
        (None, Some(c)) if c.get("casing_level").is_some() || c.get("fill_level").is_some() => json!("given"),
        (None, _) => Value::Null,        // the default (auto)
    };
    if !levels.is_null() {
        put(&mut out, &mut paths, "levels", levels);
    }
    match a.get("minzoom") {
        None | Some(Value::Null) | Some(Value::Bool(true)) => {}
        Some(Value::Bool(false)) => put(&mut out, &mut paths, "roads.minzoom", json!("off")),
        Some(Value::Object(t)) => put(&mut out, &mut paths, "roads.minzoom", json!({"table": t})),
        Some(other) => return Err(Error::Options(format!("minzoom: True, False, None or a {{class: zoom}} mapping, not {other}"))),
    }
    if let Some(p) = get("road_popup") {
        put(&mut out, &mut paths, "interaction.popup", match p {
            Value::Bool(true) => json!("default"),
            Value::Bool(false) => json!("off"),
            Value::Array(f) => json!({"fields": f}),
            Value::String(s) if s == "panel" => json!("panel"),
            Value::String(_) => json!("all"),
            other => return Err(Error::Options(format!("road_popup: True, False, a list of columns, \"all\" or \"panel\", not {other}"))),
        });
    }
    // the hover tooltip: road_tooltip, else the folium name tooltip
    let given = |v: &&Value| !matches!(v, Value::Bool(false)) && *v != "" && v.as_array().is_none_or(|f| !f.is_empty());
    if let Some(t) = get("road_tooltip").filter(given).or_else(|| get("tooltip")).filter(given) {
        put(&mut out, &mut paths, "interaction.tooltip", match t {
            Value::Bool(true) => json!("all"),
            Value::Array(f) => json!({"fields": f}),
            Value::String(s) => json!({"fields": [s]}),
            other => return Err(Error::Options(format!("road_tooltip: True or a list of columns, not {other}"))),
        });
    }
    if let Some(t) = get("color_table") {
        put(&mut out, &mut paths, "color.table", json!({"colors": t, "key": get("color_key").cloned().unwrap_or_else(|| json!("edge_id"))}));
    }
    if let Some(o) = get("color_options") {
        let named: Vec<(String, Value)> = match o {
            Value::Object(m) => m.iter().map(|(k, v)| (k.clone(), v.clone())).collect(),
            Value::Array(l) => l.iter().map(|x| (x["name"].as_str().unwrap_or_default().to_string(), x.clone())).collect(),
            other => return Err(Error::Options(format!("color_options: a {{name: options}} mapping or a list, not {other}"))),
        };
        let opts = named.into_iter().map(|(name, o)| {
            let mut n = Map::new();
            n.insert("name".into(), name.into());
            for (k, v) in o.as_object().into_iter().flatten().filter(|(k, v)| *k != "name" && !v.is_null()) {
                let to = COLOR_OPTION.iter().find(|f| f.0 == k).map(|f| f.1)
                    .ok_or_else(|| Error::Options(format!("color_options: unknown key {k:?}{}", nearest(k, COLOR_OPTION.iter().map(|f| f.0)))))?;
                n.insert(to.into(), v.clone());
            }
            Ok(Value::Object(n))
        }).collect::<Result<Vec<_>, Error>>()?;
        put(&mut out, &mut paths, "color.options", Value::Array(opts));
    }
    if let Some(l) = get("overlays") {
        let l = l.as_array().ok_or_else(|| Error::Options(format!("overlays: a list, not {l}")))?;
        put(&mut out, &mut paths, "overlays", Value::Array(l.iter().map(overlay_from_flat).collect::<Result<_, _>>()?));
    }
    if let Some(d) = get("items") {
        put(&mut out, &mut paths, "items", json!({"data": d, "popup": get("items_popup")}));
    }
    let modes = get("modes");
    let layers = get("interaction");
    if modes.is_some() || layers.is_some() {
        put(&mut out, &mut paths, "base_map", json!({"modes": modes.cloned().unwrap_or(json!([])), "layers": layers.cloned().unwrap_or(json!({}))}));
    }
    Ok(Flat { out, paths, rest })
}

/// The flat keywords that are one field each: (keyword, the field's path).
const FLAT: &[(&str, &str)] = &[
    ("highway_col", "columns.class"), ("tunnel_col", "columns.tunnel"), ("bridge_col", "columns.bridge"), ("layer_col", "columns.layer"),
    ("edge_id_col", "columns.edge_id"), ("directed_col", "columns.directed"), ("driving_col", "columns.driving"),
    ("access_col", "columns.access"), ("filter_col", "columns.filter"), ("width_m_col", "columns.width_m"), ("cap_col", "columns.cap"),
    ("casing_start_col", "columns.levels.casing_start"), ("casing_level_col", "columns.levels.casing_level"),
    ("casing_end_col", "columns.levels.casing_end"), ("fill_level_col", "columns.levels.fill_level"),
    ("head_start_m_col", "columns.levels.head_start_m"), ("head_end_m_col", "columns.levels.head_end_m"),
    ("cap_start_col", "columns.levels.cap_start"), ("cap_end_col", "columns.levels.cap_end"),
    ("color_by", "color.by"), ("colors", "color.colors"), ("cmap", "color.cmap"), ("vmin", "color.vmin"), ("vmax", "color.vmax"),
    ("missing", "color.missing"), ("style", "color.style"), ("color_active", "color.active"),
    ("width_by", "width.range"), ("width_m_zoom", "width.m_zoom"),
    ("road_fill", "roads.fill"), ("head_m", "roads.head_m"), ("casing_m", "roads.casing_m"), ("casing_min_px", "roads.casing_min_px"),
    ("offset_frac", "roads.offset_frac"), ("width_frac", "roads.width_frac"), ("offset_zoom", "roads.offset_zoom"),
    ("hover_color", "interaction.hover_color"), ("select_color", "interaction.select_color"),
    ("labels", "labels.on"), ("arrows", "arrows.on"), ("tunnel_control", "tunnels.control"), ("view_3d", "bridges.decks_3d"),
    ("boundary", "boundary"), ("name", "output.name"), ("state", "output.state"), ("live_data", "output.live_data"),
];

/// The flat keywords of more than one field, or of a value in another form: `from_args` reads them itself.
const SPECIAL: &[&str] = &["levels", "minzoom", "road_popup", "road_tooltip", "tooltip", "color_table", "color_key", "color_options",
                           "overlays", "items", "items_popup", "modes", "interaction"];

/// The keys of a colour option (a data styler's keywords): (keyword, the field of `ColorOption`).
const COLOR_OPTION: &[(&str, &str)] = &[("color_by", "by"), ("colors", "colors"), ("cmap", "cmap"), ("vmin", "vmin"), ("vmax", "vmax"),
                                        ("width_by", "width"), ("missing", "missing"), ("palette", "palette"), ("style", "style")];

/// The fields of rs.Overlay that are one field each of `Overlay`: (field, the field's path).
const OVERLAY: &[(&str, &str)] = &[
    ("label", "label"), ("fc", "data"), ("kind", "kind"), ("placement", "placement"), ("color", "color"), ("color_col", "color_column"),
    ("outline", "outline"), ("opacity", "opacity"), ("width", "width"), ("width_m", "width_m"), ("radius", "radius"), ("dash", "dash"),
    ("popup", "popup"), ("popup_window", "popup_window"), ("tooltip", "tooltip"), ("visible", "visible"), ("min_zoom", "min_zoom"),
    ("max_zoom", "max_zoom"), ("select", "select"), ("style", "style"), ("edge_col", "edge.column"), ("order_col", "edge.order_column"),
    ("width_m_col", "edge.width_m_column"), ("offset_m_col", "edge.offset_m_column"), ("dash_col", "edge.dash_column"),
    ("text_col", "text.column"), ("text_size", "text.size"), ("text_color", "text.color"), ("text_halo", "text.halo"),
];

/// An overlay as the engine reads it today (rs.Overlay's fields, its data in `fc`) in the nested form.
fn overlay_from_flat(o: &Value) -> Result<Value, Error> {
    let o = o.as_object().ok_or_else(|| Error::Options(format!("overlays: each overlay is a mapping, not {o}")))?;
    let mut n = serde_json::to_value(Overlay::defaults()).expect("an overlay is JSON").as_object().cloned().unwrap_or_default();
    for (k, v) in o.iter().filter(|(_, v)| !v.is_null()) {
        let to = OVERLAY.iter().find(|f| f.0 == k).map(|f| f.1)
            .ok_or_else(|| Error::Options(format!("overlays: unknown field {k:?}{}", nearest(k, OVERLAY.iter().map(|f| f.0)))))?;
        set(&mut n, to, v.clone());
    }
    Ok(Value::Object(n))
}

/// `set`, and the path in `paths` (the fields that the flat keywords set, for `with_args`).
fn put(m: &mut Map<String, Value>, paths: &mut Vec<String>, path: &str, v: Value) {
    set(m, path, v);
    paths.push(path.into());
}

/// The value at the dotted `path` of `m`.
fn at<'a>(m: &'a Map<String, Value>, path: &str) -> Option<&'a Value> {
    match path.split_once('.') {
        None => m.get(path),
        Some((head, tail)) => at(m.get(head)?.as_object()?, tail),
    }
}

/// `v` at the dotted `path` of `m`, with the mappings on the way.
fn set(m: &mut Map<String, Value>, path: &str, v: Value) {
    match path.split_once('.') {
        None => {
            m.insert(path.into(), v);
        }
        Some((head, tail)) => {
            let e = m.entry(head).or_insert_with(|| Value::Object(Map::new()));
            if !e.is_object() {
                *e = Value::Object(Map::new());
            }
            set(e.as_object_mut().expect("a mapping"), tail, v);
        }
    }
}

/// `"; did you mean \"x\"?"` with the known name nearest `k` (`nearest_name`), or "".
pub fn nearest<'a>(k: &str, known: impl IntoIterator<Item = &'a str>) -> String {
    nearest_name(k, known).map_or_else(String::new, |n| format!("; did you mean \"{n}\"?"))
}

/// The known name nearest `k` (Jaro-Winkler 0.75 or more: a common start counts more, so "by_column" finds "by"), or none.
pub fn nearest_name<'a>(k: &str, known: impl IntoIterator<Item = &'a str>) -> Option<&'a str> {
    known.into_iter().map(|n| (strsim::jaro_winkler(k, n), n)).filter(|(s, _)| *s >= 0.75).max_by(|a, b| a.0.total_cmp(&b.0)).map(|(_, n)| n)
}

/// render_edges' flat keywords that are map options (`from_args` reads them).
pub fn keywords() -> impl Iterator<Item = &'static str> {
    FLAT.iter().map(|f| f.0).chain(SPECIAL.iter().copied())
}

/// serde's error of the nested options, explained: an unknown key with its path and the nearest known key; another error as it is.
fn explain(v: &Value, e: &str) -> String {
    let unknown = e.strip_prefix("unknown field `").or_else(|| e.strip_prefix("unknown variant `"));
    let Some((key, expected)) = unknown.and_then(|r| r.split_once('`')) else { return format!("map options: {e}") };
    // the known names: the ones that serde names after "expected"
    let known: Vec<&str> = expected.split('`').skip(1).step_by(2).collect();
    let path = find(v, key, &known, "").unwrap_or_else(|| key.to_string());
    format!("\"{path}\": unknown key{}", nearest(key, known.iter().copied()))
}

/// The path of the first mapping in `v` that has the key `key` beside keys that are all `known` (the struct that serde read), or of the
/// first text `key` (a variant).
fn find(v: &Value, key: &str, known: &[&str], at: &str) -> Option<String> {
    let join = |k: &str| if at.is_empty() { k.to_string() } else { format!("{at}.{k}") };
    match v {
        Value::Object(m) => {
            if m.contains_key(key) && m.keys().all(|k| k == key || known.contains(&k.as_str())) {
                return Some(join(key));
            }
            m.iter().find_map(|(k, x)| find(x, key, known, &join(k)))
        }
        Value::Array(l) => l.iter().enumerate().find_map(|(i, x)| find(x, key, known, &format!("{at}[{i}]"))),
        Value::String(s) if s == key => Some(at.to_string()),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_misspelt_key_is_an_error_with_its_path_and_the_nearest_key() {
        let e = MapOptions::from_json(r#"{"color": {"by_column": "speed"}}"#).unwrap_err().to_string();
        assert_eq!(e, r#""color.by_column": unknown key; did you mean "by"?"#);
        let e = MapOptions::from_json(r#"{"roads": {"fill": false, "casing_minpx": 1}}"#).unwrap_err().to_string();
        assert_eq!(e, r#""roads.casing_minpx": unknown key; did you mean "casing_min_px"?"#);
        let e = MapOptions::from_json(r#"{"overlays": [{"label": "a"}, {"lable": "b"}]}"#).unwrap_err().to_string();
        assert_eq!(e, r#""overlays[1].lable": unknown key; did you mean "label"?"#);
        let e = MapOptions::from_json(r#"{"levels": "solved"}"#).unwrap_err().to_string();
        assert_eq!(e, r#""levels": unknown key; did you mean "solve"?"#);
        let e = MapOptions::from_json(r#"{"colour": {}}"#).unwrap_err().to_string();
        assert_eq!(e, r#""colour": unknown key; did you mean "color"?"#);
    }

    #[test]
    fn the_defaults() {
        let m = MapOptions::from_json("{}").unwrap();
        assert_eq!(m, MapOptions::default());
        assert_eq!((m.columns.class.as_str(), m.roads.fill, m.labels.on, m.arrows.on), ("highway", true, true, true));
        assert_eq!((&m.levels, &m.roads.minzoom, &m.interaction.popup, m.output.state), (&Levels::Auto, &ClassMinzoom::Profile, &Popup::Default, State::Static));
        // the JSON form reads back as the same options
        assert_eq!(MapOptions::from_json(&serde_json::to_string(&m).unwrap()).unwrap(), m);
    }

    #[test]
    fn the_flat_keywords() {
        let (m, rest) = MapOptions::from_args(&json!({
            "highway_col": "klass", "casing_level_col": "cl", "fill_level_col": "fl", "color_by": "speed", "cmap": ["#000", "red"],
            "width_by": [1, 4], "road_popup": "panel", "road_tooltip": false, "tooltip": ["name"], "minzoom": {"service": 16},
            "color_table": {"1": "#ff0000"}, "color_key": "id", "view_3d": true, "state": "live", "basemap": "blank", "sidebar": null,
            "levels": {"edge_hash": "ab", "n_edges": 2}, "modes": ["driving"], "interaction": {"landcover": {"clickable": true}},
            "color_options": {"Speed": {"color_by": "speed", "missing": "self"}, "Class": {}},
            "overlays": [{"fc": {"type": "FeatureCollection", "features": []}, "kind": "line", "edge_col": "eid", "text_col": null,
                          "popup_window": true, "visible": false}]})).unwrap();
        assert_eq!(rest, ["basemap"]);
        assert_eq!(m.columns.class, "klass");
        assert_eq!(m.columns.levels.as_ref().unwrap().casing_level.as_deref(), Some("cl"));
        assert_eq!(m.levels, Levels::Stored { edge_hash: "ab".into(), n_edges: 2 });
        assert_eq!(m.color.by.as_deref(), Some("speed"));
        assert_eq!(m.color.cmap, Some(Cmap::Colors(vec![Color::parse("#000000").unwrap(), Color::parse("#ff0000").unwrap()])));
        assert_eq!(m.width.range, Some((1.0, 4.0)));
        assert_eq!(m.interaction.popup, Popup::Panel);
        assert_eq!(m.interaction.tooltip, Some(Tooltip::Fields(vec!["name".into()])));
        assert_eq!(m.roads.minzoom, ClassMinzoom::Table(json!({"service": 16}).as_object().unwrap().clone()));
        assert_eq!(m.color.table.as_ref().unwrap().key, "id");
        assert_eq!(m.color.options.iter().map(|o| (o.name.as_str(), o.by.as_deref(), o.missing)).collect::<Vec<_>>(),
                   [("Speed", Some("speed"), Missing::Itself), ("Class", None, Missing::Base)]);
        assert!(m.bridges.decks_3d && m.output.state == State::Live);
        let ov = &m.overlays[0];
        assert_eq!((ov.kind, ov.edge.as_ref().map(|e| e.column.as_str()), ov.visible, ov.popup_window), (Some(OverlayKind::Line), Some("eid"), false, true));
        assert_eq!(m.base_map.as_ref().unwrap().modes, ["driving"]);
        // no level columns and no `levels`: solved; the columns alone: given; minzoom False: off
        assert_eq!(MapOptions::from_args(&json!({})).unwrap().0.levels, Levels::Auto);
        assert_eq!(MapOptions::from_args(&json!({"levels": "solve"})).unwrap().0.levels, Levels::Solve);
        assert_eq!(MapOptions::from_args(&json!({"fill_level_col": "f"})).unwrap().0.levels, Levels::Given);
        assert_eq!(MapOptions::from_args(&json!({"minzoom": false})).unwrap().0.roads.minzoom, ClassMinzoom::Off);
        assert_eq!(MapOptions::from_args(&json!({"levels": "tags"})).unwrap().0.levels, Levels::Tags);
    }

    #[test]
    fn a_flat_keyword_of_the_wrong_kind_is_an_error_that_names_it() {
        let e = |a: Value| MapOptions::from_args(&a).unwrap_err().to_string();
        assert_eq!(e(json!({"road_popup": 3})), "road_popup: True, False, a list of columns, \"all\" or \"panel\", not 3");
        assert_eq!(e(json!({"minzoom": "yes"})), "minzoom: True, False, None or a {class: zoom} mapping, not \"yes\"");
        assert_eq!(e(json!({"overlays": [{"fc": {}, "lable": "x"}]})), "overlays: unknown field \"lable\"; did you mean \"label\"?");
        assert!(e(json!({"hover_color": "#zzz"})).contains("\"#zzz\" is not a colour"), "{}", e(json!({"hover_color": "#zzz"})));
        assert!(e(json!({"road_fill": "no"})).starts_with("map options: invalid type"), "{}", e(json!({"road_fill": "no"})));
    }
}
