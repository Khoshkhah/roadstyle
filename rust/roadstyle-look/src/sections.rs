//! The typed look (T3 step 2, docs/design/t3_map_options_and_look.md, audit R16): one struct for each section of the resolved look, in
//! place of the JSON values `theme` and `config` (StyleConfig's flat view, most of whose keys were a copy of a theme section) and of the
//! resolution's tables (`styles`, `slots`, `roads_model`, the arrow image, the road popup, the base map's part).
//!
//! A look of version 2 is written with these sections and the map options (`LookFile`); a look of version 1 gives its sections with
//! `from_views`. A number keeps its written form (`Num`: 15 stays 15, 2.0 stays 2.0) and a colour its text (`Color`), so the outputs of a
//! look of version 1 and of the same look as version 2 are the same, byte for byte.
//!
//! `look.schema.json` is made from these types with the feature `schema` (schemars; its tests turn it on).
//!
//! The big tables (the class tables, the zoom tables, the palettes, the base map's layers) stay JSON mappings here: the readers of step 3
//! type them.

use crate::color::Color;
use crate::{Error, LookData};
use indexmap::IndexMap;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};

/// A number of the look, in its written form: a whole number stays whole, a float stays a float.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(transparent)]
pub struct Num(pub serde_json::Number);

impl Num {
    /// The value as a float.
    pub fn f(&self) -> f64 {
        self.0.as_f64().unwrap_or(f64::NAN)
    }
}

impl From<f64> for Num {
    fn from(v: f64) -> Num {
        Num(serde_json::Number::from_f64(v).expect("a finite number"))
    }
}

#[cfg(feature = "schema")]
impl schemars::JsonSchema for Num {
    fn schema_name() -> std::borrow::Cow<'static, str> {
        "Num".into()
    }
    fn json_schema(_: &mut schemars::SchemaGenerator) -> schemars::Schema {
        schemars::json_schema!({"type": "number"})
    }
}

type Table = Map<String, Value>;

/// The sections of a look: the profile and the palette merged, the settings over them, with the values of the resolution.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct Sections {
    pub roads: RoadsLook,
    pub casing: CasingLook,
    pub labels: LabelLook,
    pub arrows: ArrowLook,
    pub bridges: BridgeLook,
    pub tunnels: TunnelLook,
    pub selection: SelectionLook,
    pub data: DataLook,
    pub overlays: OverlayLook,
    pub boundary: BoundaryLook,
    pub background: BackgroundLook,
    /// the dark theme of the style's layers (`rs_theme` "dark"): how each light colour is turned dark
    #[serde(default)]
    pub dark: DarkLook,
    /// the colour of each kind of restricted road
    pub access: IndexMap<String, Color>,
    pub camera: CameraLook,
    pub tiles: TileLook,
    /// the page's defaults of the settings: the base map (never a key: a look is saved and published)
    pub page: PageLook,
    /// every palette that the look can name (a view's palette), by its name
    pub palettes: Table,
    /// the names of the profile and the palette
    pub active: ActiveLook,
    /// the road popup's default fields and the hover delay
    pub interaction: InteractionLook,
    /// the base map's part (a duckOSM map's mode, theme and path style); none with no base map
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub base_map: Option<BaseMapLook>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct RoadsLook {
    /// each class: group, order, minzoom, width, casing_width, dash, no_casing, single_line, minor
    pub classes: Table,
    /// a class with no entry
    pub fallback: Table,
    /// the width of each group by zoom
    pub width: Table,
    pub width_zoom_rate: Table,
    /// the casing width of each group: the fill width times this
    pub casing_ratio: Table,
    pub zoom_stops: Vec<Num>,
    pub links: Links,
    pub cap: String,
    pub join: String,
    pub split: Split,
    pub width_m_zoom: Num,
    pub twin_end_caps: bool,
    /// "one" (one casing around a two-way road's two edges) or "each"
    pub twin_casing: String,
    pub fill_opacity: Num,
    /// each class of the palette as ClassStyler resolves it, plain and as a link, and the fallback
    pub styles: ClassStyles,
    /// road tables
    pub model: RoadsModel,
    /// render's default head length in metres
    pub head_m: f64,
}

impl RoadsLook {
    /// Each class's value of `key` in the class table, for the classes that give it (`minzoom`: the classes' first zooms).
    pub fn class_values(&self, key: &str) -> Table {
        self.classes.iter().filter_map(|(c, e)| Some((c.clone(), e.get(key)?.clone()))).collect()
    }

    /// The classes whose flag `key` is true (`no_casing`, `single_line`, `minor`), in the table's order.
    pub fn flagged(&self, key: &str) -> Vec<String> {
        self.classes.iter().filter(|(_, e)| crate::resolve::is_set(e.get(key))).map(|(c, _)| c.clone()).collect()
    }
}

/// Each class's style as ClassStyler resolves it: [plain, as a link] (fill, width, casing, casing_width, dash, opacity, casing_opacity).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct ClassStyles {
    pub classes: IndexMap<String, [Value; 2]>,
    pub fallback: [Value; 2],
}

/// road tables: the widths of each group by zoom, the zoom rate above the last stop, the casing ratio,
/// each class's group, the link classes, the zoom stops and each class's drawing order.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct RoadsModel {
    /// group -> zoom (as text) -> px
    pub width: IndexMap<String, IndexMap<String, Num>>,
    pub width_zoom_rate: IndexMap<String, Num>,
    pub casing_ratio: IndexMap<String, Num>,
    /// class -> its width group
    pub group: IndexMap<String, String>,
    pub links: Vec<String>,
    pub zoom_stops: Vec<Num>,
    pub z_order: Table,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct Links {
    pub classes: Vec<String>,
    /// a link's width: this part of its class's width
    pub width: Num,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct Split {
    pub offset_frac: Num,
    pub width_frac: Num,
    pub offset_zoom: Num,
    pub ramp_zooms: Num,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct CasingLook {
    pub extra: Num,
    /// roads in metres: the casing in metres
    pub m: Num,
    /// roads in metres: a casing is never thinner than this many pixels each side
    pub min_px: Num,
    /// no casing piece (a bridge's keeps it) at a zoom where the whole casing line is narrower than this many px (0: always a casing).
    /// Before `opacity`: the profile gives it, the palette gives `opacity`, and the theme keeps that order.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub drop_below_px: Option<Num>,
    pub opacity: Num,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct LabelLook {
    pub halo_width: Num,
    pub font: Vec<String>,
    pub glyphs: String,
    pub minzoom: Num,
    pub minor_minzoom: Num,
    pub fraction: Num,
    pub min_px: Num,
    /// the size of the names by zoom: [[zoom, px], ...]
    pub base_size: Vec<[Num; 2]>,
    pub max_angle: Num,
    pub padding: Num,
    pub color: Color,
    /// none: no halo
    pub halo_color: Option<Color>,
    /// roads in metres: the names' size by zoom for every class
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub size: Option<Value>,
    /// the slots' tables: the class order and each class's width at zoom 20
    pub slots: Slots,
    /// the length of one slot in metres (config annotations.slot_m)
    pub slot_m: Num,
}

/// The slots' tables (the names and the arrows): the class order, and each class's casing width at zoom 20 in px.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct Slots {
    pub z_order: Table,
    pub width_z20: IndexMap<String, Num>,
    pub width_z20_fallback: Num,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct ArrowLook {
    pub minzoom: Num,
    pub minor_minzoom: Num,
    pub main_below: Num,
    pub size: Value,
    pub spacing: Value,
    pub icon: Value,
    /// the classes of the main arrows
    pub main: Vec<String>,
    pub place: Value,
    pub color: Color,
    pub opacity: Num,
    /// the one-way arrow image
    pub image: Value,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct BridgeLook {
    pub cap: String,
    pub wing_scale: Num,
    pub ramp: Vec<Num>,
    pub casing_extra: Num,
    pub casing_m: Num,
    pub casing_px: Num,
    pub shadow: Shadow,
    pub decks: Decks,
    pub casing_color: Color,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct Shadow {
    pub show: bool,
    pub blur: Num,
    pub offset: Vec<Num>,
    pub trim_m: Num,
    pub width_scale: Num,
    pub color: Color,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct Decks {
    pub base_m: Num,
    pub thickness_m: Num,
    pub ramp_m: Num,
    pub step_m: Num,
    pub match_zoom: Num,
    pub width_scale: Num,
    pub flat_below: Num,
    pub casing_px: Num,
    pub underlay: Color,
    pub opacity: Num,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct TunnelLook {
    pub opacity_scale: Num,
    pub cap: String,
    /// folium's dash (goes with folium, P7)
    pub folium_dash: Vec<Num>,
    pub casing_dash: Vec<Num>,
    pub fill_dash: Vec<Num>,
    pub strength: Num,
    pub dash_extra_px: Num,
    pub steps: Vec<Num>,
    pub ratios: Value,
    pub fill_dash_color: Color,
    pub toward: String,
    pub towards: IndexMap<String, Color>,
    pub palette: String,
    pub palettes: Table,
    pub to: Table,
}

impl TunnelLook {
    /// The colour that a tunnel moves toward: the colour of the name `toward` in `towards`, else `toward` itself (a "#rrggbb").
    pub fn toward_color(&self) -> &str {
        self.towards.get(&self.toward).map_or(&self.toward, Color::css)
    }

    /// The pair of colours of the tunnel palette `palette` (none: the palette is not given).
    pub fn pair(&self) -> Option<&Value> {
        self.palettes.get(&self.palette).filter(|v| !v.is_null())
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct SelectionLook {
    /// folium's highlight (goes with folium, P7)
    pub folium: Value,
    pub hover: Color,
    pub select: Color,
    pub casing: Color,
    pub opacity: Num,
    pub glow_opacity: Num,
    /// folium's hover colour (goes with folium, P7)
    pub folium_hover: Color,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct DataLook {
    pub width: Num,
    pub casing_width: Num,
    pub nodata: Color,
    pub color_table: Color,
    /// the ramp of live data (rs.setData) when the call has no cmap: colours of a medium brightness, so they show on a light and on a dark map
    pub live_ramp: Vec<Color>,
    pub opacity: Num,
    pub casing_opacity: Num,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct OverlayLook {
    pub radius: Num,
    pub width: Num,
    pub circle_stroke_width: Num,
    pub text_size: Num,
    pub text_max_angle: Num,
    pub text_padding: Num,
    pub text_halo_width: Num,
    pub item_overlap_px: Num,
    pub color: Color,
    pub circle_stroke: Color,
    pub fill_opacity: Num,
    pub circle_opacity: Num,
    pub line_opacity: Num,
    pub outline_opacity: Num,
    /// an overlay's style by its name (the settings' `overlays.styles`)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub styles: Option<Table>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct BoundaryLook {
    pub width: Num,
    pub dash: Vec<Num>,
    pub color: Color,
    pub opacity: Num,
}

/// One kind of colour in the dark theme: the lightness of the light colour (0 to 1) is placed between `lightness[0]` (for black) and `lightness[1]` (for
/// white), and the saturation is multiplied by `saturation`. The hue stays. A first number above the second turns the lightness over (the labels).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct DarkBand {
    pub lightness: [f64; 2],
    pub saturation: f64,
}

/// The dark theme (profile `dark`): a band for each kind of colour of the style. `area`: the fills and the 3D buildings of the base map's layers; `line`: their
/// lines and outlines; `point`: their points and icons; `casing`: the casing of the roads (the fill of a road keeps its colour); `label`: the names, the
/// arrows and their halos. The textures of the land are made again in the `area` band.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct DarkLook {
    pub area: DarkBand,
    pub line: DarkBand,
    pub point: DarkBand,
    pub casing: DarkBand,
    pub label: DarkBand,
}

impl Default for DarkLook {
    /// the values of the default profile, so that a look file made before the dark theme has them
    fn default() -> DarkLook {
        let band = |l0: f64, l1: f64, s: f64| DarkBand { lightness: [l0, l1], saturation: s };
        DarkLook { area: band(0.10, 0.30, 0.85), line: band(0.30, 0.65, 0.9), point: band(0.30, 0.80, 1.0), casing: band(0.12, 0.42, 0.85), label: band(0.92, 0.30, 1.0) }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct BackgroundLook {
    pub light: Color,
    pub dark: Color,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct CameraLook {
    pub pitch: Num,
    pub bearing: Num,
    pub pitch_3d: Num,
    pub max_pitch: Num,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct TileLook {
    pub minzoom: Num,
    pub maxzoom: Num,
    pub extent: Num,
    pub buffer_px: Num,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct PageLook {
    /// the base map's name
    pub basemap: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct ActiveLook {
    pub profile: String,
    pub palette: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct InteractionLook {
    pub popup: Vec<String>,
    pub hover_delay_ms: Num,
}

/// mapstyle's base-map part: the layers of layers.yaml, the 3D buildings, the base map's style and its images.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct BaseMapLook {
    pub layers_yaml: Value,
    pub buildings_3d: Value,
    pub style: Value,
    pub images: Value,
}

/// A look as it is written, version 2: the typed sections and the typed map options. It has no page key: a look file is the style. Its
/// JSON is one mapping: these four keys and the sections' keys.
// Read and written by hand, not with serde's `flatten`: `flatten` reads the sections a second time through serde's buffer, which put a
// second reader of each section into the binary (113 KB of the wasm package for `Sections` alone), and it does not go with
// `deny_unknown_fields`.
#[derive(Clone, Debug, PartialEq)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
pub struct LookFile {
    /// 2
    pub schema_version: u32,
    /// the palette's name
    pub palette: String,
    /// the settings sources as given (a mapping, a list of them, or null)
    pub settings: Value,
    /// the map options
    pub map: crate::MapOptions,
    #[cfg_attr(feature = "schema", schemars(flatten))]
    pub sections: Sections,
}

impl LookFile {
    /// The file of a JSON value. An unknown key is an error of `Sections` (`deny_unknown_fields`).
    pub fn from_value(v: Value) -> Result<LookFile, Error> {
        let Value::Object(mut m) = v else { return Err(bad("a look of version 2", "not a mapping")) };
        let mut take = |k: &str| m.shift_remove(k).ok_or_else(|| bad("a look of version 2", format!("missing field `{k}`")));
        let schema_version = take("schema_version")?.as_u64().ok_or_else(|| bad("a look of version 2", "schema_version is not a number"))? as u32;
        let palette = take("palette")?.as_str().ok_or_else(|| bad("a look of version 2", "palette is not a text"))?.to_string();
        let (settings, map) = (take("settings")?, take("map")?);
        let map = crate::MapOptions::from_value(map)?;
        check_tunnels(m.get("tunnels").unwrap_or(&Value::Null))?;
        let sections = serde_json::from_value(Value::Object(m)).map_err(|e| bad("a look of version 2", e))?;
        Ok(LookFile { schema_version, palette, settings, map, sections })
    }

    /// The file as a JSON value: the four keys, then the sections' keys.
    pub fn to_value(&self) -> Value {
        let mut m = Map::new();
        m.insert("schema_version".into(), self.schema_version.into());
        m.insert("palette".into(), self.palette.clone().into());
        m.insert("settings".into(), self.settings.clone());
        m.insert("map".into(), serde_json::to_value(&self.map).expect("the map options are JSON"));
        if let Value::Object(s) = serde_json::to_value(&self.sections).expect("the sections are JSON") {
            m.extend(s);
        }
        Value::Object(m)
    }
}

/// The theme sections of a look of version 1 that are sections of version 2 as they are.
const THEME: [&str; 14] = ["roads", "casing", "labels", "arrows", "bridges", "tunnels", "selection", "data", "overlays", "boundary",
                           "background", "access", "palettes", "active"];

fn bad(what: &str, e: impl std::fmt::Display) -> Error {
    Error::Look(format!("look: {what}: {e}"))
}

/// the name in quotes of a JSON value, for the messages that name a value
fn repr(v: &Value) -> String {
    match v {
        Value::Null => "None".into(),
        Value::Bool(b) => (if *b { "True" } else { "False" }).into(),
        Value::String(s) => format!("'{s}'"),
        Value::Array(a) => format!("[{}]", a.iter().map(repr).collect::<Vec<_>>().join(", ")),
        Value::Object(o) => format!("{{{}}}", o.iter().map(|(k, v)| format!("'{k}': {}", repr(v))).collect::<Vec<_>>().join(", ")),
        Value::Number(_) => v.to_string(),
    }
}

/// The tunnel look's rule: each colour of `towards` a "#rrggbb", `toward` one of their names or a "#rrggbb".
/// It runs before the typed reader, so a value of another type has this message too (the texts of the tunnel checks).
fn check_tunnels(t: &Value) -> Result<(), Error> {
    let hex = |v: &Value| v.as_str().is_some_and(|c| c.len() == 7 && crate::color::hex_rgb(c).is_some());
    let empty = Map::new();
    let towards = t.get("towards").and_then(Value::as_object).unwrap_or(&empty);
    if let Some((n, c)) = towards.iter().find(|(_, c)| !hex(c)) {
        return Err(Error::Options(format!("tunnel_towards '{n}': {} is not a '#rrggbb' colour", repr(c))));
    }
    let toward = t.get("toward").unwrap_or(&Value::Null);
    if !toward.as_str().is_some_and(|n| towards.contains_key(n)) && !hex(toward) {
        let names = Value::Array(towards.keys().map(|k| Value::from(k.as_str())).collect());
        return Err(Error::Options(format!("tunnel_toward {} is not a colour name in {} or a '#rrggbb' colour", repr(toward), repr(&names))));
    }
    Ok(())
}

/// The sections of a version-1 look (its JSON views).
pub fn from_views(d: &LookData) -> Result<Sections, Error> {
    check_tunnels(&d.theme["tunnels"])?;
    let mut s = Map::new();
    for k in THEME {
        s.insert(k.into(), d.theme.get(k).cloned().unwrap_or(Value::Null));
    }
    let set = |s: &mut Map<String, Value>, sec: &str, k: &str, v: Value| {
        if let Some(m) = s.get_mut(sec).and_then(Value::as_object_mut) {
            m.insert(k.into(), v);
        }
    };
    set(&mut s, "roads", "styles", d.styles.clone());
    set(&mut s, "roads", "model", d.roads_model.clone());
    set(&mut s, "roads", "head_m", json!(d.head_m));
    set(&mut s, "labels", "slots", d.slots.clone());
    set(&mut s, "labels", "slot_m", d.config["annotations"]["slot_m"].clone());
    set(&mut s, "arrows", "image", d.oneway_image.clone());
    for k in ["camera", "tiles"] {
        s.insert(k.into(), d.config[k].clone());
    }
    s.insert("page".into(), json!({"basemap": d.config["basemap"]}));
    s.insert("interaction".into(), d.interaction.clone());
    if !d.features.is_null() {
        s.insert("base_map".into(), d.features.clone());
    }
    serde_json::from_value(Value::Object(s)).map_err(|e| bad("the sections of a version-1 look", e))
}

/// The JSON Schema of a look of version 2 (look.schema.json; the feature `schema`).
#[cfg(feature = "schema")]
pub fn schema() -> Value {
    serde_json::to_value(schemars::schema_for!(LookFile)).expect("a schema is JSON")
}
