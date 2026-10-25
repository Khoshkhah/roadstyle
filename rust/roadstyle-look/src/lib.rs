//! roadstyle's look (docs/design/rust_library.md, "The config: the look"): the one typed, versioned value that the engine draws a map
//! with. `Look::resolve` makes it from render_edges' palette, profile, settings and keywords (`resolve.rs`, the port of `_settings.py`);
//! `Look::from_json` reads a saved look of version 2 (the typed sections, `sections.rs`), 1 or 0 (0.25.0's `look.json`, with no
//! `schema_version`), and `Look::to_json` writes version 2. The look is parsed
//! one time: the typed parts that the stages read (`model`, `road`, `slot`, `deck`) are made when the look is made, not in each stage.
//!
//! The look does not know the roads (rule 2 of the layers): the engine combines the two.

pub mod basemap;
pub mod color;
mod error;
pub mod options;
pub mod sections;
mod png;
mod ramp;
mod resolve;
pub mod widths;

pub use error::Error;
pub use options::MapOptions;
pub use sections::{LookFile, Sections};
pub use ramp::Ramp;
pub use resolve::{make_look, theme, Options};
pub use widths::{py_round, RoadModel};

/// The pixels of an 8-bit PNG: (width, height, channels, the rows), for the tests of the textures.
pub use png::decode as png_pixels;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::{HashMap, HashSet};

/// The version of the look that this crate writes. It reads this version, 1 and 0 (0.25.0's `look.json`; until the frozen hosts move, T6).
pub const VERSION: u32 = 2;

/// The look's JSON views of version 1 (as a look of version 1 or 0 is written): the resolved theme and settings, the class styles, the
/// road tables and the map options. The readers that have not moved to the typed sections read these.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LookData {
    /// 1 (the views are version 1's form); a look of version 0 has none
    #[serde(default)]
    pub schema_version: u32,
    /// the palette's name (render_edges' palette)
    pub palette: String,
    /// the settings sources as given (a mapping, a list of them, or null)
    pub settings: Value,
    /// the map options: render_edges' keywords
    pub args: Value,
    /// the profile and the palette merged, with the settings over them (_settings.theme())
    pub theme: Value,
    /// StyleConfig's values (_settings.style()["config"])
    pub config: Value,
    /// each class of the palette as ClassStyler resolves it, plain and as a link, and the fallback
    pub styles: Value,
    /// render's default head length in metres
    pub head_m: f64,
    /// the slots' tables: the class order and each class's width at zoom 20
    pub slots: Value,
    /// render_web's road tables (_settings.roads())
    pub roads_model: Value,
    /// mapstyle's base-map part, as given (null: none)
    #[serde(default, skip_serializing_if = "Value::is_null")]
    pub features: Value,
    /// the one-way arrow image
    pub oneway_image: Value,
    /// the road popup's fields and the hover delay
    pub interaction: Value,
}

/// The look: its data and the typed parts that the stages read, made one time from the data.
#[derive(Clone, Debug)]
pub struct Look {
    data: LookData,
    /// the typed sections (version 2)
    pub sections: Sections,
    /// the road width model (widths by zoom, draw order, the two-way split)
    pub model: RoadModel,
    /// the values of the roads' stages (the class styles, the twins, the access colours)
    pub road: RoadLook,
    /// the values of the names and arrows (the slots)
    pub slot: SlotLook,
    /// the values of the 3D bridge decks
    pub deck: DeckLook,
    /// the map options of `args` (MapOptions::from_args); the readers move to them in N32 step 2
    pub map: MapOptions,
    /// the keywords of `args` that are not map options (the page's, the host's, a misspelt one), for the caller that knows the page's keys
    pub other_args: Vec<String>,
}

impl std::ops::Deref for Look {
    type Target = LookData;
    fn deref(&self) -> &LookData {
        &self.data
    }
}

impl Look {
    /// The look of render_edges' palette, profile, settings and keywords (`Options`).
    pub fn resolve(o: &Options) -> Result<Look, Error> {
        Look::new(resolve::resolve(o)?)
    }

    /// A look from its views of version 1 (a look of version 1 or 0, or the resolution's): the sections and the typed parts are made
    /// here. A version past 1 is an error.
    pub fn new(mut data: LookData) -> Result<Look, Error> {
        if data.schema_version > 1 {
            return Err(Error::Version { found: data.schema_version });
        }
        data.schema_version = 1;
        no_keys(&mut data);
        let sections = sections::from_views(&data)?;
        Look::with(data, sections)
    }

    fn with(data: LookData, sections: Sections) -> Result<Look, Error> {
        let (map, other_args) = MapOptions::from_args(&data.args)?;
        Ok(Look { model: RoadModel::new(&data.roads_model, &data.theme["roads"], &data.args)?, road: RoadLook::new(&data)?,
                  slot: SlotLook::new(&data)?, deck: DeckLook::new(&data.config["bridge_decks"]), map, other_args, sections, data })
    }

    /// A saved look (its JSON text), of version 2, 1 or 0.
    pub fn from_json(text: &str) -> Result<Look, Error> {
        Look::from_value(serde_json::from_str(text).map_err(|e| Error::Look(format!("look: {e}")))?)
    }

    /// A look from its JSON value, of version 2, 1 or 0.
    pub fn from_value(v: Value) -> Result<Look, Error> {
        match v.get("schema_version").and_then(Value::as_u64).unwrap_or(0) {
            n if n > VERSION as u64 => Err(Error::Version { found: n as u32 }),
            2 => {
                let f = LookFile::from_value(v)?;
                Look::with(sections::views(&f)?, f.sections)
            }
            _ => Look::new(serde_json::from_value(v).map_err(|e| Error::Look(format!("look: {e}")))?),
        }
    }

    /// The look as it is written: version 2.
    pub fn to_json(&self) -> String {
        self.to_value().to_string()     // through a Value: one serialiser of the sections in the binary, not two
    }

    /// The look as a JSON value: version 2.
    pub fn to_value(&self) -> Value {
        self.file().to_value()
    }

    /// The look's JSON views of version 1, as a JSON value (as a look of version 1 was written).
    pub fn views_value(&self) -> Value {
        serde_json::to_value(&self.data).expect("a look is JSON")
    }

    fn file(&self) -> LookFile {
        LookFile { schema_version: VERSION, palette: self.data.palette.clone(), settings: self.data.settings.clone(), args: self.data.args.clone(),
                   sections: self.sections.clone() }
    }

    /// The data, to change it: give it to `Look::new` again (for example a map option that the caller adds after the resolution).
    pub fn into_data(self) -> LookData {
        self.data
    }

    /// The same look with the map option `key` set to `value`.
    pub fn with_arg(self, key: &str, value: Value) -> Result<Look, Error> {
        let mut data = self.data;
        if !data.args.is_object() {
            data.args = Value::Object(Map::new());
        }
        data.args[key] = value;
        Look::new(data)
    }
}

/// The keywords and settings keys that hold an API key. A look is saved and published (look.json, a plugin, a page's metadata), so no key
/// is written into it: the caller gives the keys to the page (`given`).
const KEY_ARGS: [&str; 2] = ["api_key", "street_view_key"];
const KEY_CONFIG: [&str; 2] = ["api_key", "api_keys"];

/// `data` with no API key: none in the keywords, none in the settings sources' `config`, none in the config view.
fn no_keys(data: &mut LookData) {
    if let Some(a) = data.args.as_object_mut() {
        KEY_ARGS.iter().for_each(|k| { a.shift_remove(*k); });
    }
    let sources: Vec<&mut Value> = match &mut data.settings {
        Value::Array(l) => l.iter_mut().collect(),
        v => vec![v],
    };
    for c in sources.into_iter().filter_map(|s| s.get_mut("config")).filter_map(Value::as_object_mut) {
        KEY_CONFIG.iter().for_each(|k| { c.shift_remove(*k); });
    }
    if let Some(c) = data.config.as_object_mut().filter(|c| c.contains_key("api_key")) {
        c.insert("api_key".into(), Value::Null);
        c.insert("api_keys".into(), Value::Object(Map::new()));
    }
}

/// Python's truth of a look value, as the engine's settings read it (`truthy`): false for null, false, 0 and the texts "", "no",
/// "false" and "0"; true for the other values.
fn truthy(v: Option<&Value>) -> bool {
    match v {
        None | Some(Value::Null) => false,
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64() != Some(0.0),
        Some(Value::String(s)) => !matches!(s.as_str(), "" | "no" | "false" | "0"),
        Some(_) => true,
    }
}

/// The look values of the roads' stages: the resolved class styles and the render's defaults.
#[derive(Clone, Debug)]
pub struct RoadLook {
    /// the theme's data.* values (the data stylers' widths, opacities and no-data colours)
    pub data: Value,
    /// the palette's name
    pub palette: String,
    classes: HashMap<String, [Value; 2]>,
    fallback: [Value; 2],
    /// config single_line_classes
    pub single_line: HashSet<String>,
    /// config twin_casing == "one"
    pub twin_one: bool,
    /// the heads' default length (render's head_m keyword, else its default in the look)
    pub head_m: f64,
    /// config bridge_shadow: a bridge's main casing piece casts a shadow (simple source)
    pub bridge_shadow: bool,
    /// the theme's access colours (render's access_col: the palette's `access`)
    pub access: Map<String, Value>,
    /// the theme's casing.m: a metre-wide road's casing in metres (render's casing_m)
    pub casing_m: f64,
}

impl RoadLook {
    fn new(look: &LookData) -> Result<RoadLook, Error> {
        let pair = |v: &Value| -> Result<[Value; 2], Error> {
            match v.as_array().map(|a| a.as_slice()) {
                Some([a, b]) => Ok([a.clone(), b.clone()]),
                _ => Err(Error::Look("look.json: a class style is not [plain, link]".into())),
            }
        };
        let styles = &look.styles;
        let classes = styles["classes"].as_object().ok_or_else(|| Error::Look("look.json: no styles.classes".into()))?;
        Ok(RoadLook {
            data: look.theme["data"].clone(),
            palette: look.palette.clone(),
            classes: classes.iter().map(|(k, v)| Ok((k.clone(), pair(v)?))).collect::<Result<_, Error>>()?,
            fallback: pair(&styles["fallback"])?,
            single_line: look.config["single_line_classes"].as_array().into_iter().flatten()
                .filter_map(|v| v.as_str().map(String::from)).collect(),
            twin_one: look.config["twin_casing"] == "one",
            head_m: look.args["head_m"].as_f64().unwrap_or(look.head_m),
            bridge_shadow: truthy(look.config.get("bridge_shadow")),
            access: look.theme["access"].as_object().cloned().unwrap_or_default(),
            casing_m: look.theme["casing"]["m"].as_f64().unwrap_or(0.0),
        })
    }

    /// ClassStyler: the style of a class value `h` (as text; plain or link, resolved at build time) and its base class
    /// (normalize_highway: trimmed, lower case, without `_link`).
    pub fn class_style(&self, h: &str) -> (&Value, String) {
        let h = h.trim().to_lowercase();
        let (base, link) = match h.strip_suffix("_link") { Some(b) => (b.to_string(), 1), None => (h, 0) };
        (&self.classes.get(&base).unwrap_or(&self.fallback)[link], base)
    }
}

/// The look values of the slots (the names and the arrows).
#[derive(Clone, Debug)]
pub struct SlotLook {
    /// the class order of the slots
    pub z_order: Map<String, Value>,
    /// each class's casing width at zoom 20 in px
    pub width_z20: HashMap<String, f64>,
    /// the fallback's casing width at zoom 20 in px
    pub width_fallback: f64,
    /// config annotations.slot_m: the length of one slot in metres
    pub slot_m: f64,
}

impl SlotLook {
    fn new(look: &LookData) -> Result<SlotLook, Error> {
        let s = &look.slots;
        Ok(SlotLook {
            z_order: s["z_order"].as_object().cloned().ok_or_else(|| Error::Look("look.json: no slots.z_order".into()))?,
            width_z20: s["width_z20"].as_object().ok_or_else(|| Error::Look("look.json: no slots.width_z20".into()))?.iter()
                .filter_map(|(k, v)| v.as_f64().map(|w| (k.clone(), w))).collect(),
            width_fallback: s["width_z20_fallback"].as_f64().ok_or_else(|| Error::Look("look.json: no slots.width_z20_fallback".into()))?,
            slot_m: look.config["annotations"]["slot_m"].as_f64().unwrap_or(100.0),
        })
    }
}

/// The look values of the 3D bridge decks (config bridge_decks, each with its default).
#[derive(Clone, Debug)]
pub struct DeckLook {
    pub base_m: f64,
    pub thickness_m: f64,
    pub ramp_m: f64,
    pub step_m: f64,
    pub match_zoom: f64,
    pub width_scale: f64,
    pub casing_px: f64,
    pub flat_below: f64,
    pub opacity: f64,
}

impl DeckLook {
    fn new(cfg: &Value) -> DeckLook {
        let f = |k: &str, d: f64| cfg[k].as_f64().unwrap_or(d);
        DeckLook { base_m: f("base_m", 5.0), thickness_m: f("thickness_m", 1.0), ramp_m: f("ramp_m", 40.0), step_m: f("step_m", 2.5),
                   match_zoom: f("match_zoom", 18.0), width_scale: f("width_scale", 1.0), casing_px: f("casing_px", 2.0),
                   flat_below: f("flat_below", 16.0), opacity: f("opacity", 0.7) }
    }
}
