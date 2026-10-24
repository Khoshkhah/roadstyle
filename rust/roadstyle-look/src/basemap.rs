//! The base map's half of the look (mapstyle's styles, merged into roadstyle on 2026-10-23): a duckOSM map's travel mode, its theme and
//! its path style give the roads' palette and settings (mapstyle's `mode_settings`) and the base map's part of the look (`features`: the
//! layers of layers.yaml, the 3D heights, the base map's style in the theme's colours and its images). Ports of mapstyle's style.py
//! (`load_theme`, `recolor`, `_merge`, `_walk`), map.py (`mode_settings`, `_mix`, `_darker`, the images of `feature_overlays`) and
//! patterns.py (the textures: their masks are drawn one time, in data/basemap/patterns/). The files are roadstyle's own:
//! src/roadstyle/data/basemap/, read at build time, so there is one copy of them.

use crate::resolve::{carto_entries, yaml};
use base64::Engine;
use serde::Deserialize;
use serde_json::{json, Map, Value};

const LAYERS: &str = include_str!("../../../src/roadstyle/data/basemap/layers.yaml");
const MODES: &str = include_str!("../../../src/roadstyle/data/basemap/modes.yaml");
const PATHS: &str = include_str!("../../../src/roadstyle/data/basemap/paths.yaml");
const CARTO: &str = include_str!("../../../src/roadstyle/data/basemap/osm_carto.yaml");
/// the themes other than "osm" (osm_carto.yaml as it is), by name
const THEMES: [(&str, &str); 3] = [
    ("google", include_str!("../../../src/roadstyle/data/basemap/themes/google.yaml")),
    ("grey", include_str!("../../../src/roadstyle/data/basemap/themes/grey.yaml")),
    ("roadstyle", include_str!("../../../src/roadstyle/data/basemap/themes/roadstyle.yaml")),
];
const ICONS: [(&str, &str); 6] = [
    ("bicycle.svg", include_str!("../../../src/roadstyle/data/basemap/icons/bicycle.svg")),
    ("bus.svg", include_str!("../../../src/roadstyle/data/basemap/icons/bus.svg")),
    ("crossing.svg", include_str!("../../../src/roadstyle/data/basemap/icons/crossing.svg")),
    ("parking_p.svg", include_str!("../../../src/roadstyle/data/basemap/icons/parking_p.svg")),
    ("traffic_light.svg", include_str!("../../../src/roadstyle/data/basemap/icons/traffic_light.svg")),
    ("train.svg", include_str!("../../../src/roadstyle/data/basemap/icons/train.svg")),
];
/// the textures' masks (patterns.py drawn with PIL: the alpha of each pixel)
const PATTERNS: [(&str, &[u8]); 7] = [
    ("dots", include_bytes!("../../../src/roadstyle/data/basemap/patterns/dots.png")),
    ("graves", include_bytes!("../../../src/roadstyle/data/basemap/patterns/graves.png")),
    ("hatch", include_bytes!("../../../src/roadstyle/data/basemap/patterns/hatch.png")),
    ("rows", include_bytes!("../../../src/roadstyle/data/basemap/patterns/rows.png")),
    ("sand", include_bytes!("../../../src/roadstyle/data/basemap/patterns/sand.png")),
    ("trees", include_bytes!("../../../src/roadstyle/data/basemap/patterns/trees.png")),
    ("waves", include_bytes!("../../../src/roadstyle/data/basemap/patterns/waves.png")),
];

/// The travel modes of a map (render_map(mode=)): "all" emphasises none.
pub const LOOKS: [&str; 4] = ["all", "driving", "walking", "cycling"];

/// One choice of a base map's look: the travel mode that stands out, the theme (the whole map's colours) and the path style (how
/// walking and cycling paths look).
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields, default)]
pub struct BaseMap {
    pub mode: String,
    pub theme: String,
    pub paths: String,
}

impl Default for BaseMap {
    fn default() -> BaseMap {
        BaseMap { mode: "all".into(), theme: "osm".into(), paths: "google".into() }
    }
}

/// What a base map's choice gives the look: the roads' palette name and settings (one settings source), the base map's part of the
/// look (`features`) and the map options of the mode (a mode with no lanes: one centred line for each road).
pub struct BaseMapLook {
    pub palette: String,
    pub settings: Value,
    pub features: Value,
    pub args: Map<String, Value>,
}

/// The theme names: "osm" (osm_carto.yaml as it is) and every theme file, in order.
pub fn themes() -> Vec<&'static str> {
    std::iter::once("osm").chain(THEMES.iter().map(|t| t.0)).collect()
}

fn pyrepr(names: &[&str]) -> String {
    format!("({})", names.iter().map(|n| format!("'{n}'")).collect::<Vec<_>>().join(", "))
}

/// The bundled file `name` of mapstyle's styles.
fn style(text: &str) -> Value {
    yaml(text).expect("a bundled base-map style is YAML")
}

/// Python's round() of a float to an integer (round half to even).
fn py_round(x: f64) -> i64 {
    x.round_ties_even() as i64
}

fn hex(c: &str) -> Option<[f64; 3]> {
    let ok = c.len() == 7 && c.starts_with('#') && c[1..].chars().all(|x| x.is_ascii_hexdigit());
    ok.then(|| [1, 3, 5].map(|i| u8::from_str_radix(&c[i..i + 2], 16).unwrap() as f64))
}

/// Python's x % 1.0 (the sign of the divisor).
fn frac(x: f64) -> f64 {
    let m = x % 1.0;
    if m < 0.0 { m + 1.0 } else { m }
}

/// colorsys.rgb_to_hls
fn rgb_to_hls(r: f64, g: f64, b: f64) -> (f64, f64, f64) {
    let (maxc, minc) = (r.max(g).max(b), r.min(g).min(b));
    let (sumc, rangec) = (maxc + minc, maxc - minc);
    let l = sumc / 2.0;
    if minc == maxc {
        return (0.0, l, 0.0);
    }
    let s = if l <= 0.5 { rangec / sumc } else { rangec / (2.0 - maxc - minc) };
    let (rc, gc, bc) = ((maxc - r) / rangec, (maxc - g) / rangec, (maxc - b) / rangec);
    let h = if r == maxc { bc - gc } else if g == maxc { 2.0 + rc - bc } else { 4.0 + gc - rc };
    (frac(h / 6.0), l, s)
}

/// colorsys.hls_to_rgb
fn hls_to_rgb(h: f64, l: f64, s: f64) -> [f64; 3] {
    if s == 0.0 {
        return [l, l, l];
    }
    let m2 = if l <= 0.5 { l * (1.0 + s) } else { l + s - (l * s) };
    let m1 = 2.0 * l - m2;
    let v = |hue: f64| {
        let hue = frac(hue);
        if hue < 1.0 / 6.0 {
            m1 + (m2 - m1) * hue * 6.0
        } else if hue < 0.5 {
            m2
        } else if hue < 2.0 / 3.0 {
            m1 + (m2 - m1) * (2.0 / 3.0 - hue) * 6.0
        } else {
            m1
        }
    };
    [v(h + 1.0 / 3.0), v(h), v(h - 1.0 / 3.0)]
}

/// recolor: a "#rrggbb" colour with `saturation` times its saturation, then `lighten` of the way to white; anything else as it is.
fn recolor(v: &Value, saturation: f64, lighten: f64) -> Value {
    let Some(c) = v.as_str().and_then(hex) else { return v.clone() };
    let (h, l, s) = rgb_to_hls(c[0] / 255.0, c[1] / 255.0, c[2] / 255.0);
    let rgb = hls_to_rgb(h, l, s * saturation).map(|x| x + (1.0 - x) * lighten);
    json!(format!("#{}", rgb.iter().map(|x| format!("{:02x}", py_round(x * 255.0))).collect::<String>()))
}

/// _walk: `f` on every value of `o` that is not a mapping or a list.
fn walk(o: &Value, f: &dyn Fn(&Value) -> Value) -> Value {
    match o {
        Value::Object(m) => Value::Object(m.iter().map(|(k, v)| (k.clone(), walk(v, f))).collect()),
        Value::Array(a) => Value::Array(a.iter().map(|v| walk(v, f)).collect()),
        v => f(v),
    }
}

/// _merge: `b` over `a`, mappings merged key by key; anything else, or an empty mapping (no textures), replaces.
fn merge(a: Option<&Value>, b: &Value) -> Value {
    match (a.and_then(Value::as_object), b.as_object()) {
        (Some(a), Some(bm)) if !bm.is_empty() => {
            let mut out = a.clone();
            for (k, v) in bm {
                out.insert(k.clone(), merge(a.get(k), v));
            }
            Value::Object(out)
        }
        _ => b.clone(),
    }
}

/// A theme: osm_carto.yaml in its colours (its transform on every colour, then its own colours), the theme file itself (empty for
/// "osm") and its transform (saturation, lighten), for the colours that come from elsewhere.
fn load_theme(theme: &str) -> Result<(Value, Value, (f64, f64)), String> {
    let base = style(CARTO);
    if theme == "osm" {
        return Ok((base, json!({}), (1.0, 0.0)));
    }
    let text = THEMES.iter().find(|t| t.0 == theme).map(|t| t.1)
        .ok_or_else(|| format!("unknown theme '{theme}'; choose from {}", pyrepr(&themes())))?;
    let t = style(text);
    let tr = &t["transform"];
    let tr = (tr["saturation"].as_f64().unwrap_or(1.0), tr["lighten"].as_f64().unwrap_or(0.0));
    let colored = walk(&base, &|v| recolor(v, tr.0, tr.1));
    let own: Map<String, Value> = ["roads", "features"].iter().filter_map(|k| Some((k.to_string(), t.get(*k)?.clone()))).collect();
    Ok((merge(Some(&colored), &Value::Object(own)), t, tr))
}

/// _mix: "#rrggbb" `a` moved `t` of the way to `b`.
fn mix(a: &str, b: &str, t: f64) -> String {
    let (x, y) = (hex(a).unwrap_or([0.0; 3]), hex(b).unwrap_or([0.0; 3]));
    format!("#{}", (0..3).map(|i| format!("{:02x}", py_round(x[i] + (y[i] - x[i]) * t))).collect::<String>())
}

/// _darker: each channel of "#rrggbb" times `f`, the fraction cut off.
fn darker(c: &str, f: f64) -> String {
    let x = hex(c).unwrap_or([0.0; 3]);
    format!("#{}", x.iter().map(|v| format!("{:02x}", (v * f) as i64)).collect::<String>())
}

fn data_url(mime: &str, data: &[u8]) -> String {
    format!("data:{mime};base64,{}", base64::engine::general_purpose::STANDARD.encode(data))
}

/// pattern_png: one 64 px tile of the texture `name` in `color` on transparent (MapLibre's fill-pattern cannot tint an image, so each
/// colour is an image of its own).
fn pattern_png(name: &str, color: &str) -> Result<Vec<u8>, String> {
    let mask = PATTERNS.iter().find(|p| p.0 == name).ok_or_else(|| format!("no texture named '{name}'"))?.1;
    let (w, h, ch, px) = crate::png::decode(mask)?;
    let c = hex(color).ok_or_else(|| format!("texture {name}: {color} is not a '#rrggbb' colour"))?;
    let rgba: Vec<u8> = px.chunks(ch).flat_map(|p| [c[0] as u8, c[1] as u8, c[2] as u8, p[ch - 1]]).collect();
    Ok(crate::png::encode_rgba(w, h, &rgba))
}

fn kind_of<'a>(specs: &'a [Value], name: &str) -> &'a str {
    specs.iter().find(|s| s["name"] == name).and_then(|s| s["kind"].as_str()).unwrap_or("")
}

/// The images of the base map that feature_overlays puts in roadstyle:images, for each layer of layers.yaml that is drawn on its own:
/// the landcover textures (`ms-pat-<kind>`) and the point layers' icons (`ms-icon-<layer>`), as data URLs.
fn images(st: &Value, specs: &[Value]) -> Result<Map<String, Value>, String> {
    let f = &st["features"];
    let mut out = Map::new();
    for s in specs.iter().filter(|s| s["show"] != false && s.get("merge_into").is_none()) {
        let name = s["name"].as_str().unwrap_or_default();
        if name == "landcover" {
            let fills = &f["areas"]["landcover"];
            let default = fills["default"].as_str().unwrap_or("#000000");
            for (k, pat) in f["landcover_pattern"].as_object().into_iter().flatten() {
                let fill = fills.get(k).filter(|_| k != "default").and_then(Value::as_str).unwrap_or(default);
                let png = pattern_png(pat.as_str().unwrap_or_default(), &darker(fill, 0.6))?;
                out.insert(format!("ms-pat-{k}"), data_url("image/png", &png).into());
            }
        } else if kind_of(specs, name) == "point" {
            let mut p = f["points"]["default"].as_object().cloned().unwrap_or_default();
            p.extend(f["points"][name].as_object().cloned().unwrap_or_default());
            if let Some(icon) = p.get("icon").and_then(Value::as_str).filter(|i| !i.is_empty()) {
                let svg = ICONS.iter().find(|i| i.0 == icon).ok_or_else(|| format!("no icon named '{icon}'"))?.1;
                let color = p.get("color").and_then(Value::as_str).unwrap_or_default();
                let svg = svg.replacen("<svg ", &format!("<svg fill=\"{color}\" "), 1);
                out.insert(format!("ms-icon-{name}"), data_url("image/svg+xml", svg.as_bytes()).into());
            }
        }
    }
    Ok(out)
}

/// mode_settings and the base map's part of the look for one choice (render_map's mode, theme and paths).
pub fn base_map(b: &BaseMap) -> Result<BaseMapLook, String> {
    if !LOOKS.contains(&b.mode.as_str()) {
        return Err(format!("unknown mode '{}'; choose from {}", b.mode, pyrepr(&LOOKS)));
    }
    let styles = style(PATHS);
    let st = styles.get(&b.paths).ok_or_else(|| {
        let names: Vec<&str> = styles.as_object().into_iter().flatten().map(|(k, _)| k.as_str()).collect();
        format!("unknown path style '{}'; choose from {}", b.paths, pyrepr(&names))
    })?;
    let modes = style(MODES);
    let spec = modes.get(&b.mode).filter(|s| !s.is_null()).cloned().unwrap_or_else(|| json!({}));
    let (themed, th, tr) = load_theme(&b.theme)?;
    let color = |v: &Value| recolor(v, tr.0, tr.1);
    let base = walk(&carto_entries()?, &color);
    let colors = &themed["roads"]["colors"];
    let theme_paths = th.get("paths").filter(|p| p.is_object()).cloned().unwrap_or_else(|| json!({}));
    let over: Map<String, Value> = walk(st.get("palette").filter(|p| !p.is_null()).unwrap_or(&json!({})), &color).as_object().cloned()
        .unwrap_or_default().into_iter().map(|(c, v)| {
            let mut e = v.as_object().cloned().unwrap_or_default();
            e.extend(theme_paths.get(&c).and_then(Value::as_object).cloned().unwrap_or_default());
            (c, Value::Object(e))
        }).collect();
    // a class the base lacks (pedestrian, steps, platform, ...) starts from footway's entry without its dash: osm_carto.yaml gives the dash
    // where a class has one. The classes in their first-seen order (Python makes them a set, whose order changes with each run)
    let mut new = base["footway"].as_object().cloned().unwrap_or_default();
    new.insert("dash".into(), Value::Null);
    let mut palette = Map::new();
    let keys = |v: &Value| v.as_object().map(|m| m.keys().cloned().collect::<Vec<_>>()).unwrap_or_default();
    for c in keys(&base).into_iter().chain(keys(colors)).chain(over.keys().cloned()) {
        if palette.contains_key(&c) {
            continue;
        }
        let mut e = base.get(&c).and_then(Value::as_object).cloned().unwrap_or_else(|| new.clone());
        e.extend(colors.get(&c).and_then(Value::as_object).cloned().unwrap_or_default());
        e.extend(over.get(&c).and_then(Value::as_object).cloned().unwrap_or_default());
        palette.insert(c, Value::Object(e));
    }
    let truthy = |v: Option<&Value>| v.is_some_and(|v| !matches!(v, Value::Null | Value::Bool(false)) && v.as_f64() != Some(0.0));
    if truthy(spec.get("fade")) && truthy(st.get("fade")) {
        let fade = st["fade"].as_f64().unwrap_or(0.0);
        for c in modes["cars"].as_array().into_iter().flatten().filter_map(Value::as_str) {
            for k in ["fill", "casing"] {
                if let Some(x) = palette.get_mut(c).and_then(|e| e.get_mut(k)).filter(|x| x.as_str().is_some_and(|s| !s.is_empty())) {
                    *x = mix(x.as_str().unwrap(), "#ffffff", fade).into();
                }
            }
        }
    }
    let mut roads = spec.get("roads").and_then(Value::as_object).cloned().unwrap_or_default();
    let mut group = Map::new();
    group.insert("ferry".into(), "path".into());     // a ferry line: path width
    for c in spec.get("em").and_then(Value::as_array).into_iter().flatten().filter_map(Value::as_str) {
        group.insert(c.into(), "em".into());
    }
    group.extend(st.get("group").and_then(Value::as_object).cloned().unwrap_or_default());
    for (k, v) in [("width", json!({"em": st["em"]["width"]})), ("width_zoom_rate", json!({"em": 1.3})),
                   ("casing_ratio", json!({"em": st["em"]["casing_ratio"]})), ("group", Value::Object(group))] {
        let e = roads.entry(k).or_insert_with(|| json!({}));
        if let (Some(e), Some(v)) = (e.as_object_mut(), v.as_object()) {
            e.extend(v.clone());
        }
    }
    let mut config = Map::new();
    if let Some(m) = st.get("minor_no_casing") {
        config.insert("minor_no_casing".into(), m.clone());
    }
    config.extend(th.get("roadstyle").and_then(Value::as_object).cloned().unwrap_or_default());
    let name = format!("ms_{}_{}{}", b.mode, b.paths, if b.theme == "osm" { String::new() } else { format!("_{}", b.theme) });
    let mut pals = Map::new();
    pals.insert(name.clone(), Value::Object(palette));
    let settings = json!({"palettes": pals, "roads": roads, "config": config});
    let layers = style(LAYERS);
    let specs = layers["layers"].as_array().cloned().unwrap_or_default();
    let features = json!({"layers_yaml": layers, "buildings_3d": style(CARTO)["features"]["buildings_3d"], "style": themed["features"],
                          "images": images(&themed, &specs)?});
    let mut args = Map::new();
    if spec.get("lanes") == Some(&Value::Bool(false)) {          // one centred line for each road
        args.insert("offset_frac".into(), 0.into());
        args.insert("width_frac".into(), 1.into());
    }
    Ok(BaseMapLook { palette: name, settings, features, args })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn colours_as_python_makes_them() {
        // the values of mapstyle's recolor, _mix and _darker
        assert_eq!(recolor(&json!("#add19e"), 0.55, 0.2), json!("#c1d1bb"));
        assert_eq!(recolor(&json!("#c24e6b"), 0.55, 0.2), json!("#b98693"));
        assert_eq!(recolor(&json!("#123456"), 1.0, 0.0), json!("#123456"));
        assert_eq!(recolor(&json!(3), 0.55, 0.2), json!(3));
        assert_eq!(mix("#000000", "#ffffff", 0.5), "#808080");
        assert_eq!(mix("#e892a2", "#ffffff", 0.3), "#efb3be");
        assert_eq!(darker("#add19e", 0.6), "#677d5e");
    }
}
