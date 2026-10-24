//! roadstyle's look (docs/design/rust_library.md, "The config: the look"): the one typed, versioned value that the engine draws a map
//! with. `Look::resolve` makes it from render_edges' palette, profile, settings and keywords (`resolve.rs`, the port of `_settings.py`);
//! `Look::from_json` reads a saved look, of version 1 or of version 0 (today's `look.json`, with no `schema_version`). The look is parsed
//! one time: the typed parts that the stages read (`model`, `road`, `slot`, `deck`) are made when the look is made, not in each stage.
//!
//! The look does not know the roads (rule 2 of the layers): the engine combines the two.

pub mod basemap;
mod png;
mod resolve;
pub mod widths;

pub use resolve::{make_look, theme, Options};
pub use widths::{py_round, RoadModel};

/// The pixels of an 8-bit PNG: (width, height, channels, the rows), for the tests of the textures.
pub use png::decode as png_pixels;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::{HashMap, HashSet};

/// The version of the look that this crate writes. It reads this version and the one before it (0: today's `look.json`).
pub const VERSION: u32 = 1;

/// The look as it is written (`look.json`): the resolved theme and settings, the class styles, the road tables and the map options.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LookData {
    /// 1 for this version; a look of version 0 has none
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
    /// the road width model (widths by zoom, draw order, the two-way split)
    pub model: RoadModel,
    /// the values of the roads' stages (the class styles, the twins, the access colours)
    pub road: RoadLook,
    /// the values of the names and arrows (the slots)
    pub slot: SlotLook,
    /// the values of the 3D bridge decks
    pub deck: DeckLook,
}

impl std::ops::Deref for Look {
    type Target = LookData;
    fn deref(&self) -> &LookData {
        &self.data
    }
}

impl Look {
    /// The look of render_edges' palette, profile, settings and keywords (`Options`).
    pub fn resolve(o: &Options) -> Result<Look, String> {
        Look::new(resolve::resolve(o)?)
    }

    /// A look from its data: the typed parts are made here. A version past `VERSION` is an error.
    pub fn new(mut data: LookData) -> Result<Look, String> {
        if data.schema_version > VERSION {
            return Err(format!("look version {}: this engine reads versions 0 and {VERSION}", data.schema_version));
        }
        data.schema_version = VERSION;
        Ok(Look { model: RoadModel::new(&data.roads_model, &data.theme["roads"], &data.args)?, road: RoadLook::new(&data)?,
                  slot: SlotLook::new(&data)?, deck: DeckLook::new(&data.config["bridge_decks"]), data })
    }

    /// A saved look (its JSON text), of version 1 or 0.
    pub fn from_json(text: &str) -> Result<Look, String> {
        Look::new(serde_json::from_str(text).map_err(|e| format!("look: {e}"))?)
    }

    /// A look from its JSON value, of version 1 or 0.
    pub fn from_value(v: Value) -> Result<Look, String> {
        Look::new(serde_json::from_value(v).map_err(|e| format!("look: {e}"))?)
    }

    /// The look as it is written: version 1.
    pub fn to_json(&self) -> String {
        serde_json::to_string(&self.data).expect("a look is JSON")
    }

    /// The look as a JSON value: version 1.
    pub fn to_value(&self) -> Value {
        serde_json::to_value(&self.data).expect("a look is JSON")
    }

    /// The data, to change it: give it to `Look::new` again (for example a map option that the caller adds after the resolution).
    pub fn into_data(self) -> LookData {
        self.data
    }

    /// The same look with the map option `key` set to `value`.
    pub fn with_arg(self, key: &str, value: Value) -> Result<Look, String> {
        let mut data = self.data;
        if !data.args.is_object() {
            data.args = Value::Object(Map::new());
        }
        data.args[key] = value;
        Look::new(data)
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
    fn new(look: &LookData) -> Result<RoadLook, String> {
        let pair = |v: &Value| -> Result<[Value; 2], String> {
            match v.as_array().map(|a| a.as_slice()) {
                Some([a, b]) => Ok([a.clone(), b.clone()]),
                _ => Err("look.json: a class style is not [plain, link]".into()),
            }
        };
        let styles = &look.styles;
        let classes = styles["classes"].as_object().ok_or("look.json: no styles.classes")?;
        Ok(RoadLook {
            data: look.theme["data"].clone(),
            palette: look.palette.clone(),
            classes: classes.iter().map(|(k, v)| Ok((k.clone(), pair(v)?))).collect::<Result<_, String>>()?,
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
    fn new(look: &LookData) -> Result<SlotLook, String> {
        let s = &look.slots;
        Ok(SlotLook {
            z_order: s["z_order"].as_object().cloned().ok_or("look.json: no slots.z_order")?,
            width_z20: s["width_z20"].as_object().ok_or("look.json: no slots.width_z20")?.iter()
                .filter_map(|(k, v)| v.as_f64().map(|w| (k.clone(), w))).collect(),
            width_fallback: s["width_z20_fallback"].as_f64().ok_or("look.json: no slots.width_z20_fallback")?,
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
