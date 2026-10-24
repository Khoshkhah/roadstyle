//! The resolution of the look (look.json): what roadstyle renders a map with, made from render_edges' palette, profile and settings, as
//! Python makes it (docs/design/rust_engine.md). Ports of roadstyle's _settings.py (theme, style, roads: the profile and the palette merged, the palettes
//! of all classes, the settings in the older layout), of config.StyleConfig, of palettes.RoadStyle.from_dict with style._apply, and of the
//! parts geolibre-roadstyle's look_of adds (the class styles, the slots' tables, the arrow image, the popup). The data is roadstyle's own:
//! src/roadstyle/data/ (profiles, palettes, defaults.json, sprite.png), read at build time, so there is one copy of it.
//!
//! The settings are given (a mapping, or a list of them), not read from roadstyle.json files or $ROADSTYLE_CONFIG: the browser has none.
//! The user's own profiles and palettes are given too (`Options::files`), and they are passed through the calls (`Own`), not kept.

use crate::{LookData, RoadModel};
use base64::Engine;
use serde::Deserialize;
use serde_json::{json, Map, Value};

const PROFILES: [(&str, &str); 2] = [
    ("default", include_str!("../../../src/roadstyle/data/profiles/default.yaml")),
    ("highsat", include_str!("../../../src/roadstyle/data/profiles/highsat.yaml")),
];
const PALETTES: [(&str, &str); 4] = [
    ("amber", include_str!("../../../src/roadstyle/data/palettes/amber.yaml")),
    ("carto", include_str!("../../../src/roadstyle/data/palettes/carto.yaml")),
    ("highsat", include_str!("../../../src/roadstyle/data/palettes/highsat.yaml")),
    ("mono", include_str!("../../../src/roadstyle/data/palettes/mono.yaml")),
];
const DEFAULTS: &str = include_str!("../../../src/roadstyle/data/defaults.json");
const SPRITE: &[u8] = include_bytes!("../../../src/roadstyle/data/sprite.png");

/// render_web.render's defaults that the look holds, and DEFAULT_ROAD_POPUP.
const HEAD_M: f64 = 5.0;
const HOVER_DELAY_MS: i64 = 300;
const ROAD_POPUP: [&str; 7] = ["name", "edge_id", "edge_ref", "highway", "lanes", "bridge", "tunnel"];
/// what an own profile / palette merges over, and the names of each kind (bundled, in file order)
const BASE: [(&str, &str); 2] = [("profiles", "default"), ("palettes", "amber")];

// the older layout of a settings source (_settings._OLD_CONFIG, ...): its key -> the theme path
const OLD_CONFIG: [(&str, &str); 28] = [
    ("fill_opacity", "roads.fill_opacity"), ("casing_opacity", "casing.opacity"), ("casing_extra", "casing.extra"),
    ("link_scale", "roads.links.width"), ("twin_end_caps", "roads.twin_end_caps"), ("twin_casing", "roads.twin_casing"),
    ("tunnel_opacity_scale", "tunnels.opacity_scale"), ("tunnel_casing_dash", "tunnels.casing_dash"), ("tunnel_fill_dash", "tunnels.fill_dash"),
    ("tunnel_fill_dash_color", "tunnels.fill_dash_color"), ("tunnel_strength", "tunnels.strength"), ("tunnel_toward", "tunnels.toward"),
    ("tunnel_towards", "tunnels.towards"), ("tunnel_palette", "tunnels.palette"), ("tunnel_palettes", "tunnels.palettes"),
    ("bridge_casing_color", "bridges.casing_color"), ("bridge_casing_extra", "bridges.casing_extra"), ("bridge_casing_m", "bridges.casing_m"),
    ("bridge_casing_px", "bridges.casing_px"), ("bridge_shadow", "bridges.shadow.show"), ("bridge_shadow_color", "bridges.shadow.color"),
    ("bridge_shadow_blur", "bridges.shadow.blur"), ("bridge_shadow_offset", "bridges.shadow.offset"),
    ("bridge_shadow_trim_m", "bridges.shadow.trim_m"), ("bridge_decks", "bridges.decks"),
    ("labels", "labels"), ("arrows", "arrows"), ("overlays", "overlays"),
];
const OLD_CLASS_LISTS: [(&str, &str); 2] = [("minor_no_casing", "no_casing"), ("single_line_classes", "single_line")];
const OLD_CLASS_TABLES: [(&str, &str); 1] = [("minzoom", "minzoom")];
const OLD_ROAD_TABLES: [(&str, &str); 2] = [("group", "group"), ("z_order", "order")];
const OLD_SELECTION: [(&str, &str); 4] = [("core", "select"), ("glow", "hover"), ("glow_opacity", "glow_opacity"), ("casing", "casing")];

/// StyleConfig's fields, in order (dataclasses.asdict keeps it).
const CONFIG_FIELDS: [&str; 37] = [
    "fill_opacity", "casing_opacity", "casing_extra", "link_scale", "tunnel_opacity_scale", "bridge_casing_extra", "bridge_casing_m",
    "bridge_casing_px", "bridge_casing_color", "bridge_shadow", "bridge_shadow_color", "bridge_shadow_blur", "bridge_shadow_offset",
    "bridge_shadow_trim_m", "single_line_classes", "twin_end_caps", "twin_casing", "tunnel_casing_dash", "tunnel_fill_dash",
    "tunnel_fill_dash_color", "tunnel_strength", "tunnel_toward", "tunnel_towards", "tunnel_palette", "tunnel_palettes", "minor_no_casing",
    "minzoom", "basemap", "labels", "arrows", "camera", "bridge_decks", "overlays", "annotations", "tiles", "api_key", "api_keys",
];

fn lookup<'a>(t: &[(&'a str, &'a str)], k: &str) -> Option<&'a str> {
    t.iter().find(|(a, _)| *a == k).map(|(_, b)| *b)
}

// --- YAML (yaml.safe_load: the files use nothing of YAML 1.1 that 1.2 reads in another way; tests/look.rs checks the results) ---

fn yaml_value(y: &yaml_rust2::Yaml) -> Value {
    use yaml_rust2::Yaml;
    match y {
        Yaml::Real(s) => s.parse::<f64>().ok().and_then(serde_json::Number::from_f64).map_or(Value::Null, Value::Number),
        Yaml::Integer(i) => Value::from(*i),
        Yaml::String(s) => Value::from(s.as_str()),
        Yaml::Boolean(b) => Value::Bool(*b),
        Yaml::Array(a) => Value::Array(a.iter().map(yaml_value).collect()),
        Yaml::Hash(h) => Value::Object(h.iter().map(|(k, v)| (yaml_key(k), yaml_value(v))).collect()),
        _ => Value::Null,
    }
}

/// A mapping key as JSON writes it: a number's text (Python's json.dumps writes an int key 18 as "18").
fn yaml_key(k: &yaml_rust2::Yaml) -> String {
    use yaml_rust2::Yaml;
    match k {
        Yaml::String(s) | Yaml::Real(s) => s.clone(),
        Yaml::Integer(i) => i.to_string(),
        Yaml::Boolean(b) => if *b { "true" } else { "false" }.into(),
        other => format!("{other:?}"),
    }
}

pub(crate) fn yaml(text: &str) -> Result<Value, String> {
    let docs = yaml_rust2::YamlLoader::load_from_str(text).map_err(|e| e.to_string())?;
    let v = docs.first().map(yaml_value).unwrap_or(Value::Null);
    if v.is_object() { Ok(v) } else { Err("a settings file holds a mapping".into()) }
}

// --- _settings ---

/// _deep_merge: a mapping merges key by key, anything else (a list too) replaces.
fn deep_merge(dst: &mut Value, src: &Value) {
    if let (Some(d), Some(s)) = (dst.as_object_mut(), src.as_object()) {
        for (k, v) in s {
            match d.get_mut(k) {
                Some(dv) if dv.is_object() && v.is_object() => deep_merge(dv, v),
                _ => {
                    d.insert(k.clone(), v.clone());
                }
            }
        }
    }
}

/// _set_path: set a dotted path, merging a mapping into a mapping.
fn set_path(dst: &mut Value, path: &str, value: &Value) {
    let parts: Vec<&str> = path.split('.').collect();
    let mut d = dst;
    for k in &parts[..parts.len() - 1] {
        let m = d.as_object_mut().unwrap();
        if !m.contains_key(*k) {
            m.insert(k.to_string(), json!({}));
        }
        d = m.get_mut(*k).unwrap();
    }
    let last = parts[parts.len() - 1];
    match d.get_mut(last) {
        Some(x) if x.is_object() && value.is_object() => deep_merge(x, value),
        _ => {
            d.as_object_mut().unwrap().insert(last.to_string(), value.clone());
        }
    }
}

/// The user's own profiles and palettes of one resolution (render's ./profiles, ./palettes, ~/.config/roadstyle/...): (kind, name, text).
type Own = [(String, String, String)];

fn own(o: &Own, kind: &str, name: &str) -> Option<String> {
    o.iter().find(|(k, n, _)| k == kind && n == name).map(|(_, _, t)| t.clone())
}

/// style_names: the bundled names, then the user's own ones.
fn names(o: &Own, kind: &str) -> Vec<String> {
    let mut out: Vec<String> = if kind == "profiles" { PROFILES.iter().map(|p| p.0.to_string()).collect() }
                               else { PALETTES.iter().map(|p| p.0.to_string()).collect() };
    for (k, n, _) in o {
        if k == kind && !out.contains(n) {
            out.push(n.clone());
        }
    }
    out
}

/// _style_file: one profile or palette by name, merged over the base (default / amber) unless it is the base.
fn style_file(o: &Own, kind: &str, name: &str) -> Result<Value, String> {
    let files: &[(&str, &str)] = if kind == "profiles" { &PROFILES } else { &PALETTES };
    let mine = own(o, kind, name);        // the user's own file first, as _style_dirs
    let text = mine.clone().or_else(|| files.iter().find(|f| f.0 == name).map(|f| f.1.to_string()))
        .ok_or_else(|| format!("no {} named '{name}'; there are: {}", &kind[..kind.len() - 1], names(o, kind).join(", ")))?;     // Python's repr
    let data = yaml(&text).map_err(|e| format!("{} {name}: {e}", &kind[..kind.len() - 1]))?;
    let base = lookup(&BASE, kind).unwrap();
    if name == base && mine.is_none() {
        return Ok(data);
    }
    if name == base {        // an own file with the base's name: over the bundled base
        let text = files.iter().find(|f| f.0 == name).map(|f| f.1).unwrap_or_default();
        let mut out = yaml(text).map_err(|e| format!("{} {name}: {e}", &kind[..kind.len() - 1]))?;
        deep_merge(&mut out, &data);
        return Ok(out);
    }
    let mut out = style_file(o, kind, base)?;
    deep_merge(&mut out, &data);
    Ok(out)
}

/// _class_entries: a palette's road classes at the profile's widths (a class with no width in the profile is left out).
fn class_entries(colors: &Value, classes: &Value) -> Value {
    let mut out = Map::new();
    for (c, col) in colors.as_object().into_iter().flatten() {
        let Some(cl) = classes.get(c).filter(|e| e.get("width").is_some()) else { continue };
        out.insert(c.clone(), json!({"fill": col["fill"], "width": cl["width"], "casing_width": cl["casing_width"],
                                     "dash": cl.get("dash").cloned().unwrap_or(Value::Null), "opacity": col.get("opacity").cloned().unwrap_or(json!(1.0)),
                                     "casing": col.get("casing").cloned().unwrap_or(Value::Null)}));
    }
    Value::Object(out)
}

/// palette_to_dict("carto"): the bundled palette carto at the default profile's widths, as RoadStyle.to_dict writes each class (the widths
/// and the opacity as floats).
pub(crate) fn carto_entries() -> Result<Value, String> {
    let th = theme(&[], &[])?;
    let float = |v: &Value| v.as_f64().map_or(Value::Null, |f| json!(f));
    Ok(Value::Object(th["palettes"]["carto"].as_object().into_iter().flatten().map(|(c, e)| {
        (c.clone(), json!({"fill": e["fill"], "width": float(&e["width"]), "casing_width": float(&e["casing_width"]), "casing": e["casing"],
                           "dash": e["dash"], "opacity": float(&e["opacity"])}))
    }).collect()))
}

fn truthy(v: Option<&Value>) -> bool {
    match v {
        None | Some(Value::Null) => false,
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64() != Some(0.0),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
    }
}

/// `data.get(k) or {}` for a mapping.
fn items(v: Option<&Value>) -> Vec<(String, Value)> {
    v.and_then(Value::as_object).map(|m| m.iter().map(|(k, v)| (k.clone(), v.clone())).collect()).unwrap_or_default()
}

/// _old_style_keys: a settings source's style values in the older layout, as a theme, and the class flags whose lists replace the theme's.
fn old_style_keys(data: &Value) -> (Value, Vec<String>) {
    let mut out = json!({});
    let mut flags = Vec::new();
    if truthy(data.get("palettes")) {
        let pals: Map<String, Value> = items(data.get("palettes")).into_iter()
            .map(|(n, v)| { let r = if v.is_object() { v.get("roads").cloned().unwrap_or(v) } else { v }; (n, r) }).collect();
        out["palettes"] = Value::Object(pals);
    }
    for (k, v) in items(data.get("config")) {
        if let Some(path) = OLD_CONFIG.into_iter().find(|(a, _)| *a == k).map(|(_, b)| b) {
            set_path(&mut out, path, &v);
        } else if let Some(flag) = lookup(&OLD_CLASS_LISTS, &k) {
            for cls in v.as_array().into_iter().flatten() {
                set_path(&mut out, &format!("roads.classes.{}.{flag}", cls.as_str().unwrap_or_default()), &json!(true));
            }
            flags.push(flag.to_string());
        } else if let Some(field) = lookup(&OLD_CLASS_TABLES, &k) {
            for (cls, z) in items(Some(&v)) {
                set_path(&mut out, &format!("roads.classes.{cls}.{field}"), &z);
            }
        }
    }
    for (k, v) in items(data.get("selection")) {
        set_path(&mut out, &format!("selection.{}", lookup(&OLD_SELECTION, &k).unwrap_or(&k)), &v);
    }
    for (table, value) in items(data.get("roads")) {
        if let Some(field) = lookup(&OLD_ROAD_TABLES, &table) {
            for (cls, x) in items(Some(&value)) {
                set_path(&mut out, &format!("roads.classes.{cls}.{field}"), &x);
            }
        } else if table == "links" && value.is_array() {
            set_path(&mut out, "roads.links.classes", &value);
        } else {
            set_path(&mut out, &format!("roads.{table}"), &value);
        }
    }
    (out, flags)
}

/// _settings.theme(): the profile and the palette that the sources name (default and amber when none does), merged; "palettes": every
/// palette's road classes at this profile's widths; then each source's style values of the older layout; "active": the two names.
pub fn theme(sources: &[Value], o: &Own) -> Result<Value, String> {
    let (mut profile, mut palette) = (Value::from("default"), Value::from("amber"));
    for d in sources {
        if truthy(d.get("profile")) {
            profile = d["profile"].clone();
        }
        if truthy(d.get("palette")) {
            palette = d["palette"].clone();
        }
    }
    let name = |v: &Value| v.as_str().map(String::from).ok_or_else(|| format!("a profile or palette name, not {v}"));
    let mut out = style_file(o, "profiles", &name(&profile)?)?;
    let mut pal = style_file(o, "palettes", &name(&palette)?)?;
    pal.as_object_mut().unwrap().shift_remove("classes");
    deep_merge(&mut out, &pal);
    let classes = out["roads"]["classes"].clone();
    let mut pals = Map::new();
    for n in names(o, "palettes") {
        pals.insert(n.to_string(), class_entries(&style_file(o, "palettes", &n)?["classes"], &classes));
    }
    out["palettes"] = Value::Object(pals);
    for d in sources {
        let (old, flags) = old_style_keys(d);
        for flag in flags {
            for e in out["roads"]["classes"].as_object_mut().into_iter().flat_map(|m| m.values_mut()) {
                e.as_object_mut().map(|m| m.shift_remove(&flag));
            }
        }
        deep_merge(&mut out, &old);
    }
    out["active"] = json!({"profile": profile, "palette": palette});
    Ok(out)
}

fn path<'a>(t: &'a Value, p: &str) -> Result<&'a Value, String> {
    p.split('.').try_fold(t, |v, k| v.get(k).ok_or_else(|| format!("the theme has no {p}")))
}

/// _settings.style()["config"]: the StyleConfig values from the theme, defaults.json and the sources' other config keys.
fn style_config(theme: &Value, sources: &[Value]) -> Result<Map<String, Value>, String> {
    let mut cfg = Map::new();
    for (k, p) in OLD_CONFIG.into_iter() {
        cfg.insert(k.into(), path(theme, p)?.clone());
    }
    let classes = theme["roads"]["classes"].as_object().cloned().unwrap_or_default();
    let flagged = |f: &str| Value::Array(classes.iter().filter(|(_, e)| truthy(e.get(f))).map(|(c, _)| Value::from(c.as_str())).collect());
    cfg.insert("minor_no_casing".into(), flagged("no_casing"));
    cfg.insert("single_line_classes".into(), flagged("single_line"));
    cfg.insert("minzoom".into(), Value::Object(classes.iter().filter_map(|(c, e)| Some((c.clone(), e.get("minzoom")?.clone()))).collect()));
    let defaults: Value = serde_json::from_str(DEFAULTS).map_err(|e| e.to_string())?;
    for (k, v) in items(defaults.get("config")) {
        cfg.insert(k, v);
    }
    let old: Vec<&str> = OLD_CONFIG.into_iter().map(|(k, _)| k).chain(OLD_CLASS_LISTS.iter().map(|x| x.0)).chain(OLD_CLASS_TABLES.iter().map(|x| x.0)).collect();
    for d in sources {
        for (k, v) in items(d.get("config")) {
            if !old.contains(&k.as_str()) {
                cfg.insert(k, v);
            }
        }
    }
    Ok(cfg)
}

/// dataclasses.asdict(StyleConfig(...)): the fields in order, each from the settings, else its default (api_key, api_keys); the set
/// minor_no_casing as a sorted list (as the look is written).
fn config(cfg: &Map<String, Value>) -> Value {
    let mut out = Map::new();
    for f in CONFIG_FIELDS {
        let v = match (f, cfg.get(f)) {
            (_, Some(v)) => v.clone(),
            ("api_key", None) => Value::Null,
            ("api_keys", None) => json!({}),
            ("basemap", None) => json!("voyager"),
            (_, None) => Value::Null,
        };
        let v = if f == "minor_no_casing" {
            let mut s: Vec<String> = v.as_array().into_iter().flatten().filter_map(|x| x.as_str().map(String::from)).collect();
            s.sort();
            s.dedup();
            json!(s)
        } else {
            v
        };
        out.insert(f.into(), v);
    }
    Value::Object(out)
}

fn float(v: &Value, what: &str) -> Result<f64, String> {
    v.as_f64().ok_or_else(|| format!("{what}: not a number: {v}"))
}

/// Python's str() of a number in a dash pattern (_dash_str: "4,4").
fn py_num(v: &Value) -> String {
    match v.as_i64() {
        Some(i) => i.to_string(),
        None => {
            let f = v.as_f64().unwrap_or(f64::NAN);
            if f.fract() == 0.0 && f.abs() < 1e16 { format!("{f:.1}") } else { format!("{f}") }
        }
    }
}

/// The class styles (look_of's _class_styles): each class of the palette as ClassStyler resolves it, plain and as a link
/// (RoadStyle.from_dict, then style._apply with no tunnel and no bridge).
fn class_styles(theme: &Value, palette: &str, config: &Value) -> Result<Value, String> {
    let table = theme["palettes"].get(palette).and_then(Value::as_object)
        .ok_or_else(|| format!("unknown palette {palette:?}; choose from {:?}", theme["palettes"].as_object().map(|m| m.keys().collect::<Vec<_>>())))?;
    let fb_casing = &theme["roads"]["fallback"]["palette_casing"];
    let (link_scale, fill_opacity) = (float(&config["link_scale"], "link_scale")?, float(&config["fill_opacity"], "fill_opacity")?);
    let res = |d: &Value| -> Result<Value, String> {
        for k in ["fill", "width", "casing_width"] {
            if d.get(k).is_none() {
                return Err(format!("RoadStyle dict is missing required keys: [{k:?}]"));
            }
        }
        let (width, casing_width) = (float(&d["width"], "width")?, float(&d["casing_width"], "casing_width")?);
        let casing = d.get("casing").or_else(|| d.get("casing_dark")).unwrap_or(fb_casing);
        let dash = d.get("dash").and_then(Value::as_array).filter(|a| !a.is_empty())
            .map_or(Value::Null, |a| Value::from(a.iter().map(py_num).collect::<Vec<_>>().join(",")));
        let opacity = d.get("opacity").map_or(Ok(1.0), |o| float(o, "opacity"))?;
        let one = |scale: f64| json!({"fill": d["fill"], "width": width * scale, "casing": casing, "casing_width": casing_width * scale,
                                      "dash": dash, "opacity": fill_opacity * opacity, "casing_opacity": config["casing_opacity"]});
        Ok(json!([one(1.0), one(link_scale)]))
    };
    let classes: Map<String, Value> = table.iter().map(|(c, d)| Ok((c.clone(), res(d)?))).collect::<Result<_, String>>()?;
    let fallback = res(table.get("unclassified").or_else(|| table.values().next()).ok_or("an empty palette")?)?;
    Ok(json!({"classes": classes, "fallback": fallback}))
}

/// _settings.roads(): the road model tables of the web renderer.
fn roads(theme: &Value) -> Value {
    let r = &theme["roads"];
    let classes = r["classes"].as_object().cloned().unwrap_or_default();
    let field = |f: &str| Value::Object(classes.iter().filter_map(|(c, e)| Some((c.clone(), e.get(f)?.clone()))).collect());
    json!({"width": r["width"], "width_zoom_rate": r["width_zoom_rate"], "casing_ratio": r["casing_ratio"], "group": field("group"),
           "links": r["links"]["classes"], "zoom_stops": r["zoom_stops"], "z_order": field("order")})
}

/// What a look is made from: render_edges' palette (default "amber"), profile and settings (a mapping, or a list of them; none: null),
/// its keywords (`args`), the base map's look (`base_map`: a duckOSM map's mode, theme and path style; it gives the palette, a settings
/// source after the given ones, the base map's part `features` and the mode's map options), or mapstyle's base-map part as given
/// (`features`), and the user's own profiles and palettes as text (`files`: {"profiles": {name: text}, "palettes": {...}}).
#[derive(Clone, Debug, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Options {
    #[serde(default)]
    pub palette: Option<String>,
    #[serde(default)]
    pub profile: Value,
    #[serde(default)]
    pub settings: Value,
    #[serde(default)]
    pub args: Value,
    #[serde(default)]
    pub features: Option<Value>,
    #[serde(default)]
    pub base_map: Option<crate::basemap::BaseMap>,
    #[serde(default)]
    pub files: Map<String, Value>,
}

impl Options {
    /// The options from their JSON value (today's makeLook options).
    pub fn from_value(v: &Value) -> Result<Options, String> {
        Options::deserialize(v).map_err(|e| format!("look options: {e}"))
    }
}

/// The look of render_edges(palette=, profile=, settings=, **args) as a JSON value (version 1): `options` as `Options` reads them.
pub fn make_look(options: &Value) -> Result<Value, String> {
    Ok(crate::Look::resolve(&Options::from_value(options)?)?.to_value())
}

pub(crate) fn resolve(options: &Options) -> Result<LookData, String> {
    let own: Vec<(String, String, String)> = ["profiles", "palettes"].iter().flat_map(|k| {
        options.files.get(*k).and_then(Value::as_object).into_iter().flatten()
            .filter_map(move |(n, t)| Some((k.to_string(), n.clone(), t.as_str()?.to_string())))
    }).collect();
    let bm = options.base_map.as_ref().map(crate::basemap::base_map).transpose()?;
    if bm.is_some() && (options.palette.is_some() || options.features.is_some()) {
        return Err("look options: base_map gives the palette and the base map's part (features): give none of them with it".into());
    }
    let palette = bm.as_ref().map_or_else(|| options.palette.as_deref().unwrap_or("amber"), |b| b.palette.as_str());
    let profile = Some(&options.profile).filter(|v| !v.is_null());
    let settings = match (&bm, &options.settings) {
        (None, s) => s.clone(),
        (Some(b), Value::Null) => b.settings.clone(),
        (Some(b), Value::Array(a)) => Value::Array(a.iter().cloned().chain([b.settings.clone()]).collect()),
        (Some(b), s) => json!([s, b.settings]),
    };
    // render_edges: a profile, and a bundled palette, other than the default, is a settings source after settings=
    let mut pick = Map::new();
    if let Some(p) = profile.filter(|p| p.as_str() != Some("default")) {
        pick.insert("profile".into(), p.clone());
    }
    if palette != "amber" && names(&own, "palettes").iter().any(|n| n == palette) {
        pick.insert("palette".into(), palette.into());
    }
    let mut sources: Vec<Value> = match &settings {
        Value::Null => vec![],
        Value::Array(a) => a.clone(),
        Value::Object(_) => vec![settings.clone()],
        other => return Err(format!("settings: a mapping or a list of them, not {other}")),
    };
    if !pick.is_empty() {
        sources.push(Value::Object(pick));
    }
    let th = theme(&sources, &own)?;
    let config = config(&style_config(&th, &sources)?);
    let styles = class_styles(&th, palette, &config)?;
    let roads_model = roads(&th);
    let mut args = if options.args.is_null() { json!({}) } else { options.args.clone() };
    let stored = bm.is_some() && args["levels"].is_object();       // the stored levels of a duckOSM file: their columns
    let level_cols = crate::basemap::LEVEL_COLS.iter().filter(|_| stored).map(|c| (format!("{c}_col"), Value::from(*c)));
    for (k, v) in bm.iter().flat_map(|b| b.args.clone()).chain(level_cols) {      // the base map's map options, where the caller gives none
        if let Some(a) = args.as_object_mut().filter(|a| !a.contains_key(&k)) {
            a.insert(k, v);
        }
    }
    let model = RoadModel::new(&roads_model, &th["roads"], &args)?;
    let mut width_z20 = Map::new();
    for c in &model.classes {
        width_z20.insert(c.clone(), json!(model.class_width_px(Some(c), 20.0, true)));
    }
    let slots = json!({"z_order": roads_model["z_order"], "width_z20": width_z20, "width_z20_fallback": model.class_width_px(None, 20.0, true)});
    let png = base64::engine::general_purpose::STANDARD.encode(SPRITE);
    let oneway = json!({"url": format!("data:image/png;base64,{png}"), "sdf": true, "pixelRatio": path(&th, "arrows.icon.pixel_ratio")?});
    Ok(LookData {
        schema_version: crate::VERSION,
        palette: palette.into(),
        settings,
        args,
        theme: th,
        config,
        styles,
        head_m: HEAD_M,
        slots,
        roads_model,
        features: bm.map(|b| b.features).or_else(|| options.features.clone()).unwrap_or(Value::Null),
        oneway_image: oneway,
        interaction: json!({"popup": ROAD_POPUP, "hover_delay_ms": HOVER_DELAY_MS}),
    })
}
