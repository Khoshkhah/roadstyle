//! roadstyle's look (docs/design/rust_library.md, "The config: the look"): the one typed, versioned value that the engine draws a map
//! with. `Look::resolve` makes it from render_edges' palette, profile, settings and keywords (`resolve.rs`, the port of `_settings.py`);
//! `Look::from_json` reads a saved look of version 2 (the typed sections and the map options, `sections.rs`), 1 or 0 (0.25.0's
//! `look.json`, with no `schema_version`), and `Look::to_json` writes version 2. A look file is the style: it has no page key. The look
//! is parsed
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
pub use widths::{round_to, RoadModel};

/// The pixels of an 8-bit PNG: (width, height, channels, the rows), for the tests of the textures.
pub use png::decode as png_pixels;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::{HashMap, HashSet};

/// The version of the look that this crate writes. It reads this version, 1 and 0 (0.25.0's `look.json`; until the frozen hosts move, T6).
pub const VERSION: u32 = 2;

/// A look of version 1 (as a look of version 1 or 0 is written, and as the resolution makes it): the resolved theme and settings, the
/// class styles, the road tables and render_edges' keywords. `Look::new` makes the typed look of it.
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
    /// road tables
    pub roads_model: Value,
    /// mapstyle's base-map part, as given (null: none)
    #[serde(default, skip_serializing_if = "Value::is_null")]
    pub features: Value,
    /// the one-way arrow image
    pub oneway_image: Value,
    /// the road popup's fields and the hover delay
    pub interaction: Value,
}

/// The look: the typed sections, the map options and the typed parts that the stages read, made one time from them.
#[derive(Clone, Debug)]
pub struct Look {
    /// the palette's name (render_edges' palette)
    pub palette: String,
    /// the settings sources as given (a mapping, a list of them, or null)
    pub settings: Value,
    /// the typed sections
    pub sections: Sections,
    /// the road width model (widths by zoom, draw order, the two-way split)
    pub model: RoadModel,
    /// the values of the roads' stages (the class styles, the twins, the access colours)
    pub road: RoadLook,
    /// the values of the names and arrows (the slots)
    pub slot: SlotLook,
    /// the values of the 3D bridge decks
    pub deck: DeckLook,
    /// the map options (what the caller chooses for one map)
    pub map: MapOptions,
    /// the call's keywords that are not map options, with their values: the page's, the writer's (export, data_maxzoom, data_tolerance,
    /// tile_keep, tile_layers: SourceMode and TileOptions in T4), the host's, a misspelt one. In memory only: never in the file. The
    /// caller checks them (`roadstyle::options::unknown`); the page takes its keys from its own caller (`given`), not from here.
    pub other: Map<String, Value>,
    /// the base map's page defaults (box_layout, basemap, basemaps, copy_field), for the page under the caller's keys. In memory only.
    pub base_map_page: Map<String, Value>,
}

impl Look {
    /// The look of render_edges' palette, profile, settings and keywords (`Options`).
    pub fn resolve(o: &Options) -> Result<Look, Error> {
        let (mut data, bm) = resolve::resolve(o)?;
        let (_, page) = MapOptions::from_args(&Value::Object(bm.clone()))?;
        let base_map_page = bm.into_iter().filter(|(k, _)| page.contains(k)).collect();
        // the call's own keywords only: the resolution's `args` has the base map's too (its map options where the call gives none)
        let call = o.args.as_object().cloned().unwrap_or_default();
        no_keys(&mut data);
        let mut look = Look::new(data)?;
        let (_, rest) = MapOptions::from_args(&Value::Object(call.clone()))?;
        look.other = call.into_iter().filter(|(k, _)| rest.contains(k) && !KEY_ARGS.contains(&k.as_str())).collect();
        look.base_map_page = base_map_page;
        Ok(look)
    }

    /// The version-1 look that the resolution makes of `o` (its JSON value): the parity goldens are a summary of it.
    pub fn resolution_value(o: &Options) -> Result<Value, Error> {
        let (mut data, _) = resolve::resolve(o)?;
        no_keys(&mut data);
        Ok(serde_json::to_value(&data).expect("a look is JSON"))
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
        let (map, rest) = MapOptions::from_args(&data.args)?;
        let other = data.args.as_object().into_iter().flatten().filter(|(k, _)| rest.contains(k)).map(|(k, v)| (k.clone(), v.clone())).collect();
        let mut look = Look::with(data.palette, data.settings, sections, map)?;
        look.other = other;
        Ok(look)
    }

    /// The look of its parts: the typed parts that the stages read are made here.
    pub fn with(palette: String, settings: Value, sections: Sections, map: MapOptions) -> Result<Look, Error> {
        let r = &sections.roads;
        Ok(Look { model: RoadModel::new(&r.model, &r.links, &r.split, &r.fallback, &map)?, road: RoadLook::new(&sections, &palette, &map),
                  slot: SlotLook::new(&sections), deck: DeckLook::new(&sections.bridges.decks), map, sections, palette, settings,
                  other: Map::new(), base_map_page: Map::new() })
    }

    /// The same look with other map options (a view's palette resolved again keeps the page's map options); `other` stays.
    pub fn with_map(self, map: MapOptions) -> Result<Look, Error> {
        let (other, page) = (self.other, self.base_map_page);
        let mut look = Look::with(self.palette, self.settings, self.sections, map)?;
        (look.other, look.base_map_page) = (other, page);
        Ok(look)
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
                Look::with(f.palette, f.settings, f.sections, f.map)
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

    fn file(&self) -> LookFile {
        LookFile { schema_version: VERSION, palette: self.palette.clone(), settings: self.settings.clone(), map: self.map.clone(),
                   sections: self.sections.clone() }
    }

    /// The same look with the keyword `key` (render_edges' flat keyword) set to `value`: a map option changes the map options, another
    /// keyword goes to `other`. A keyword that is read with another one (`items` with `items_popup`, `color_table` with `color_key`)
    /// takes the other one from this call only: give both to the resolution.
    pub fn with_arg(self, key: &str, value: Value) -> Result<Look, Error> {
        let mut one = Map::new();
        one.insert(key.into(), value.clone());
        let (map, rest) = self.map.with_args(&Value::Object(one))?;
        let mut look = self.with_map(map)?;
        if rest.iter().any(|k| k == key) && !KEY_ARGS.contains(&key) {
            look.other.insert(key.into(), value);
        }
        Ok(look)
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

/// A flag of a look value: false for null, false, 0 and the texts "", "no", "false" and "0"; true for the other values.
fn flag(v: Option<&Value>) -> bool {
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
    /// the classes flagged single_line
    pub single_line: HashSet<String>,
    /// roads.twin_casing == "one"
    pub twin_one: bool,
    /// the heads' default length (render's head_m keyword, else its default in the look)
    pub head_m: f64,
    /// bridges.shadow.show: a bridge's main casing piece casts a shadow (simple source)
    pub bridge_shadow: bool,
    /// the theme's access colours (render's access_col: the palette's `access`)
    pub access: Map<String, Value>,
    /// the theme's casing.m: a metre-wide road's casing in metres (render's casing_m)
    pub casing_m: f64,
}

impl RoadLook {
    fn new(s: &Sections, palette: &str, map: &MapOptions) -> RoadLook {
        let r = &s.roads;
        RoadLook {
            data: serde_json::to_value(&s.data).expect("a section is JSON"),
            palette: palette.to_string(),
            classes: r.styles.classes.iter().map(|(k, v)| (k.clone(), v.clone())).collect(),
            fallback: r.styles.fallback.clone(),
            // the classes flagged single_line (config single_line_classes)
            single_line: r.classes.iter().filter(|(_, e)| flag(e.get("single_line"))).map(|(c, _)| c.clone()).collect(),
            twin_one: r.twin_casing == "one",
            head_m: map.roads.head_m.unwrap_or(r.head_m),
            bridge_shadow: s.bridges.shadow.show,
            access: s.access.iter().map(|(k, c)| (k.clone(), Value::from(c.css()))).collect(),
            casing_m: s.casing.m.f(),
        }
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
    /// labels.slot_m: the length of one slot in metres
    pub slot_m: f64,
}

impl SlotLook {
    fn new(s: &Sections) -> SlotLook {
        let t = &s.labels.slots;
        SlotLook {
            z_order: t.z_order.clone(),
            width_z20: t.width_z20.iter().map(|(k, w)| (k.clone(), w.f())).collect(),
            width_fallback: t.width_z20_fallback.f(),
            slot_m: s.labels.slot_m.f(),
        }
    }
}

/// The look values of the 3D bridge decks (the section bridges.decks).
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
    fn new(d: &sections::Decks) -> DeckLook {
        DeckLook { base_m: d.base_m.f(), thickness_m: d.thickness_m.f(), ramp_m: d.ramp_m.f(), step_m: d.step_m.f(), match_zoom: d.match_zoom.f(),
                   width_scale: d.width_scale.f(), casing_px: d.casing_px.f(), flat_below: d.flat_below.f(), opacity: d.opacity.f() }
    }
}
