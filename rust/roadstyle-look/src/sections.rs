//! The typed look (T3 step 2, docs/design/t3_map_options_and_look.md, audit R16): one struct for each section of the resolved look, in
//! place of the JSON values `theme` and `config` (StyleConfig's flat view, most of whose keys were a copy of a theme section) and of the
//! resolution's tables (`styles`, `slots`, `roads_model`, the arrow image, the road popup, the base map's part).
//!
//! A look of version 2 is written with these sections (`LookFile`). The readers that have not moved to them read the JSON views of
//! version 1 (`LookData`), which `views` makes from the sections. A number keeps its written form (`Num`: 15 stays 15, 2.0 stays 2.0)
//! and a colour its text (`Color`), so a look of version 1 that goes to version 2 and back gives the same views, byte for byte.
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
    pub styles: Value,
    /// render_web's road tables (width, width_zoom_rate, casing_ratio, group, links, zoom_stops, z_order)
    pub model: Value,
    /// render's default head length in metres
    pub head_m: f64,
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
    pub opacity: Num,
    /// no casing where it is narrower than this many pixels at a zoom (0: always a casing)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub drop_below_px: Option<Num>,
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
    pub slots: Value,
    /// the length of one slot in metres (config annotations.slot_m)
    pub slot_m: Num,
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

/// A look as it is written, version 2: the typed sections, with the map options as render_edges' keywords (`args`, until N32 step 2). Its
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
    /// the map options: render_edges' keywords
    pub args: Value,
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
        let (settings, args) = (take("settings")?, take("args")?);
        let sections = serde_json::from_value(Value::Object(m)).map_err(|e| bad("a look of version 2", e))?;
        Ok(LookFile { schema_version, palette, settings, args, sections })
    }

    /// The file as a JSON value: the four keys, then the sections' keys.
    pub fn to_value(&self) -> Value {
        let mut m = Map::new();
        m.insert("schema_version".into(), self.schema_version.into());
        m.insert("palette".into(), self.palette.clone().into());
        m.insert("settings".into(), self.settings.clone());
        m.insert("args".into(), self.args.clone());
        if let Value::Object(s) = serde_json::to_value(&self.sections).expect("the sections are JSON") {
            m.extend(s);
        }
        Value::Object(m)
    }
}

/// The theme sections that are written as they are in version 1 (the others: `access`, `palettes`, `active`, `background`).
const THEME: [&str; 14] = ["roads", "casing", "labels", "arrows", "bridges", "tunnels", "selection", "data", "overlays", "boundary",
                           "background", "access", "palettes", "active"];

/// The keys of a version-2 section that are not keys of the version-1 theme section: (section, key).
const NOT_THEME: [(&str, &str); 5] = [("roads", "styles"), ("roads", "model"), ("roads", "head_m"), ("labels", "slots"), ("labels", "slot_m")];

fn bad(what: &str, e: impl std::fmt::Display) -> Error {
    Error::Look(format!("look: {what}: {e}"))
}

/// The sections of a version-1 look (its JSON views).
pub fn from_views(d: &LookData) -> Result<Sections, Error> {
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

/// The JSON views of version 1 (`theme`, `config`, `styles`, `slots`, `roads_model`, `head_m`, `features`, `oneway_image`,
/// `interaction`) of the sections, for the readers that have not moved to the sections.
pub fn views(f: &LookFile) -> Result<LookData, Error> {
    let s = serde_json::to_value(&f.sections).expect("the sections are JSON");
    let mut theme = Map::new();
    for k in THEME {
        let mut v = s[k].clone();
        if let Some(m) = v.as_object_mut() {
            for (_, key) in NOT_THEME.iter().filter(|(sec, _)| *sec == k) {
                m.shift_remove(*key);
            }
            if k == "arrows" {
                m.shift_remove("image");
            }
        }
        theme.insert(k.into(), v);
    }
    let theme = Value::Object(theme);
    let mut extra = Map::new();
    extra.insert("camera".into(), s["camera"].clone());
    extra.insert("tiles".into(), s["tiles"].clone());
    extra.insert("annotations".into(), json!({"slot_m": s["labels"]["slot_m"]}));
    extra.insert("basemap".into(), s["page"]["basemap"].clone());
    let config = crate::resolve::config_of(&theme, extra)?;
    Ok(LookData {
        schema_version: 1,
        palette: f.palette.clone(),
        settings: f.settings.clone(),
        args: f.args.clone(),
        theme,
        config,
        styles: s["roads"]["styles"].clone(),
        head_m: f.sections.roads.head_m,
        slots: s["labels"]["slots"].clone(),
        roads_model: s["roads"]["model"].clone(),
        features: s.get("base_map").cloned().unwrap_or(Value::Null),
        oneway_image: s["arrows"]["image"].clone(),
        interaction: s["interaction"].clone(),
    })
}

/// The JSON Schema of a look of version 2 (look.schema.json; the feature `schema`).
#[cfg(feature = "schema")]
pub fn schema() -> Value {
    serde_json::to_value(schemars::schema_for!(LookFile)).expect("a schema is JSON")
}
