//! Data-driven colour and width (docs/design/rust_engine.md): render_edges' color_by, colors, cmap, vmin, vmax, width_by, color_table,
//! color_key, color_options, color_active and legend, read from look["args"]. Ports of roadstyle's stylers.py (ClassStyler,
//! CategoricalStyler, NumericStyler, ColorTableStyler, bake_props, bake_color_options, build_styler), of render_edges' color_table step,
//! and of render_web.render's colouring. The ramps (colors.py's ColorRamp) are the look's (roadstyle-look `Ramp`).

use roadstyle_model::mark::Mark;
use crate::road::Roads;
use crate::roads::Look;
use roadstyle_model::Cell;
use serde_json::{json, Map, Value};
use std::collections::{HashMap, HashSet};

/// The colouring of a map: the baked fill property of each colour option (option 0: __rs_fill), the active option (state rs_co) and the
/// legend data, the page's COLOR_OPTIONS ({name, prop, legend} for each option; empty for class colours).
pub struct Colors {
    pub props: Vec<String>,
    pub active: usize,
    pub meta: Vec<Value>,
}

/// ResolvedFrame: each edge's style values, as roadstyle writes them (a value given by the caller keeps its JSON form).
struct Frame {
    fill: Vec<Value>,
    width: Vec<Value>,
    opacity: Vec<Value>,
    dash: Vec<Value>,
    casing: Vec<Value>,
    casing_width: Vec<Value>,
    casing_opacity: Vec<Value>,
    klass: Vec<Value>,
    legend: Option<Value>,
    /// the edges a data styler has no value for (colour options fall back to the base option's fill there)
    missing: Option<Vec<bool>>,
    /// missing="self": keep the styler's own no-data colour
    missing_self: bool,
}

fn get<'a>(o: &'a Value, k: &str) -> Option<&'a Value> {
    o.get(k).filter(|v| !v.is_null())
}

/// Python's str() of a column value (pandas: integers stay integers with integer_object_nulls).
/// ponytail: a float is written as Python writes it only without an exponent (no 1e-05 or 1e+16); add it if a categorical column has such floats.
fn py_str(c: Cell) -> String {
    let v = match c {
        Cell::Null => return "None".into(),
        Cell::Bool(b) => return if b { "True" } else { "False" }.into(),
        Cell::Str(s) => return s.to_string(),
        Cell::Int(i) => return i.to_string(),
        Cell::Float(f) if f.is_nan() => return "None".into(),
        Cell::Float(f) if f.fract() == 0.0 && f.abs() < 1e16 => return format!("{f:.1}"),
        Cell::Float(f) => return format!("{f}"),
        Cell::Json(v) => v,
    };
    match v {
        Value::Null => "None".into(),
        Value::Bool(b) => if *b { "True" } else { "False" }.into(),
        Value::String(s) => s.clone(),
        Value::Number(n) => match (n.as_i64(), n.as_u64(), n.as_f64()) {
            (Some(i), _, _) => i.to_string(),
            (_, Some(u), _) => u.to_string(),
            (_, _, Some(f)) if f.fract() == 0.0 && f.abs() < 1e16 => format!("{f:.1}"),
            (_, _, Some(f)) => format!("{f}"),
            _ => n.to_string(),
        },
        other => other.to_string(),
    }
}

/// _keystr: a categorical value as a key (str, stripped, lower case). A missing value is "" (2026-10-24): pandas holds it as None or
/// as NaN by its version (Python 3.10's pandas gave "", newer ones "nan"), so both engines say so explicitly.
fn keystr(v: Option<Cell>) -> String {
    match v {
        None => String::new(),
        Some(c) if c.is_null() => String::new(),        // a missing value is "" (stylers._keystr), on every pandas version
        Some(c) => py_str(c).trim().to_lowercase(),
    }
}

/// _as_float: a number, or None for missing, NaN and what float() does not take.
fn as_float(v: Option<Cell>) -> Option<f64> {
    let f = match v? {
        Cell::Bool(b) | Cell::Json(&Value::Bool(b)) => b as u8 as f64,
        Cell::Str(s) => s.trim().parse::<f64>().ok()?,
        Cell::Json(Value::String(s)) => s.trim().parse::<f64>().ok()?,
        c => c.as_f64()?,
    };
    (!f.is_nan()).then_some(f)
}

fn num(v: f64) -> Value {
    serde_json::Number::from_f64(v).map_or(Value::Null, Value::Number)
}

/// float(x) of a theme or option value.
fn float(v: &Value) -> Result<f64, crate::Error> {
    as_float(Some(Cell::Json(v))).ok_or_else(|| crate::error::options(format!("not a number: {v}")))
}

// the ramps: branca's LinearColormap (roadstyle-look: the ramps are look data)
pub use roadstyle_look::Ramp;

// --- the stylers ---

/// ClassStyler: each edge by its class through the look's palette (the classes resolved at build time).
fn class_frame(fs: &Roads, look: &Look) -> Frame {
    let mut f = Frame::empty(fs.len());
    for ft in fs.iter() {
        let (s, base) = crate::roads::class_style(look, ft.get("highway"));
        f.push(&s["fill"], &s["width"], &s["opacity"], &s["dash"], &s["casing"], &s["casing_width"], &s["casing_opacity"], &Value::from(base));
    }
    f
}

impl Frame {
    fn empty(n: usize) -> Frame {
        let v = || Vec::with_capacity(n);
        Frame { fill: v(), width: v(), opacity: v(), dash: v(), casing: v(), casing_width: v(), casing_opacity: v(), klass: v(), legend: None,
                missing: None, missing_self: false }
    }

    #[allow(clippy::too_many_arguments)]
    fn push(&mut self, fill: &Value, width: &Value, opacity: &Value, dash: &Value, casing: &Value, cw: &Value, cop: &Value, klass: &Value) {
        self.fill.push(fill.clone());
        self.width.push(width.clone());
        self.opacity.push(opacity.clone());
        self.dash.push(dash.clone());
        self.casing.push(casing.clone());
        self.casing_width.push(cw.clone());
        self.casing_opacity.push(cop.clone());
        self.klass.push(klass.clone());
    }
}

/// CategoricalStyler: a {value: colour} map on a column; an unmapped value gets the theme's data.nodata. No casing.
fn categorical(fs: &Roads, look: &Look, column: &str, colors: &Map<String, Value>, missing_self: bool) -> Result<Frame, crate::Error> {
    let d = &look.data;
    let fallback = &d["nodata"];
    let map: HashMap<String, &Value> = colors.iter().map(|(k, v)| (keystr(Some(Cell::Str(k))), v)).collect();
    let (width, zero, null) = (num(float(&d["width"])?), num(0.0), Value::Null);
    let mut f = Frame::empty(fs.len());
    let mut miss = Vec::with_capacity(fs.len());
    for ft in fs.iter() {
        let k = keystr(ft.get(column));
        f.push(map.get(&k).copied().unwrap_or(fallback), &width, &d["opacity"], &null, &null, &zero, &d["casing_opacity"], &Value::from(k.as_str()));
        miss.push(!map.contains_key(&k));
    }
    let present: HashSet<&Value> = f.klass.iter().collect();
    let entries: Vec<Value> = colors.iter().filter(|(k, _)| present.contains(&Value::from(keystr(Some(Cell::Str(k)))))).map(|(k, v)| json!([k, v])).collect();
    f.legend = Some(json!({"kind": "categorical", "title": column, "entries": entries}));
    f.missing = Some(miss);
    f.missing_self = missing_self;
    Ok(f)
}

/// NumericStyler: a continuous ramp over [vmin, vmax] (the data's range where not given); width_by (min_px, max_px) over the data's range.
fn numeric(fs: &Roads, look: &Look, column: &str, o: &Value) -> Result<Frame, crate::Error> {
    let d = &look.data;
    let nums: Vec<Option<f64>> = fs.iter().map(|ft| as_float(ft.get(column))).collect();
    let present: Vec<f64> = nums.iter().flatten().copied().collect();
    let low = present.iter().copied().reduce(f64::min);
    let high = present.iter().copied().reduce(f64::max);
    let vmin = get(o, "vmin").cloned().unwrap_or_else(|| num(low.unwrap_or(0.0)));
    let vmax = get(o, "vmax").cloned().unwrap_or_else(|| num(high.unwrap_or(1.0)));
    let ramp = Ramp::new(get(o, "cmap").unwrap_or(&json!("viridis")))?;
    let (lo_v, hi_v) = (float(&vmin)?, float(&vmax)?);
    let span = if hi_v - lo_v != 0.0 { hi_v - lo_v } else { 1.0 };
    let nodata = d["nodata"].as_str().unwrap_or("#cccccc");
    let color = |v: Option<f64>| match v {
        None => nodata.to_string(),
        Some(v) => ramp.hex(((v - lo_v) / span).clamp(0.0, 1.0)),
    };
    let widths: Vec<Value> = match get(o, "width_by") {
        Some(wb) => {
            let (lo, hi) = match wb.as_array().map(|a| a.as_slice()) {
                Some([lo, hi]) => (lo, hi),
                _ => return Err(crate::error::options(format!("width_by: (min_px, max_px), not {wb}"))),
            };
            let (wmin, wmax) = (low.unwrap_or(0.0), high.unwrap_or(1.0));
            let wspan = if wmax - wmin != 0.0 { wmax - wmin } else { 1.0 };
            let (lf, hf) = (float(lo)?, float(hi)?);
            nums.iter().map(|v| v.map_or_else(|| lo.clone(), |v| num(lf + (hf - lf) * ((v - wmin) / wspan).clamp(0.0, 1.0)))).collect()
        }
        None => vec![num(float(&d["width"])?); fs.len()],
    };
    let (zero, null) = (num(0.0), Value::Null);
    let mut f = Frame::empty(fs.len());
    for (v, w) in nums.iter().zip(&widths) {
        f.push(&Value::from(color(*v)), w, &d["opacity"], &null, &null, &zero, &d["casing_opacity"], &null);
    }
    let stops: Vec<Value> = ramp.stops(9).into_iter().map(Value::from).collect();
    f.legend = Some(json!({"kind": "continuous", "title": column, "vmin": vmin, "vmax": vmax, "ramp": stops}));
    f.missing = Some(nums.iter().map(Option::is_none).collect());
    f.missing_self = get(o, "missing").and_then(Value::as_str) == Some("self");
    Ok(f)
}

/// ColorTableStyler: the class widths and casing, and each edge's own colour from `column` (a colour text; else the theme's
/// data.color_table). No legend.
fn color_table(fs: &Roads, look: &Look, column: &str) -> Frame {
    let mut f = class_frame(fs, look);
    let fallback = &look.data["color_table"];
    let mut miss = Vec::with_capacity(fs.len());
    for (i, ft) in fs.iter().enumerate() {
        let c = ft.get(column).and_then(Cell::as_str).map(str::trim).filter(|s| !s.is_empty());
        f.fill[i] = c.map_or_else(|| fallback.clone(), Value::from);
        miss.push(c.is_none());
    }
    f.missing = Some(miss);
    f
}

/// build_styler (option_styler for a colour option): `o` holds color_by, colors, cmap, vmin, vmax, width_by, missing, palette.
fn resolve(fs: &Roads, look: &Look, o: &Value) -> Result<Frame, crate::Error> {
    if get(o, "style").is_some() {
        return Err(crate::Error::Unsupported(crate::Unsupported::Styler));
    }
    if let Some(p) = get(o, "palette").and_then(Value::as_str).filter(|p| *p != look.palette) {
        return Err(crate::Error::Unsupported(crate::Unsupported::Palette { palette: p.to_string(), look: look.palette.to_string() }));
    }
    let Some(column) = get(o, "color_by") else { return Ok(class_frame(fs, look)) };
    let column = column.as_str().ok_or_else(|| crate::error::options("color_by: a column name"))?;
    if fs.at(0).is_some_and(|f| !f.contains_key(column)) {
        return Err(crate::error::column(column, "color_by names it, and the roads do not have it"));
    }
    match get(o, "colors") {
        Some(Value::String(s)) if s == "self" => Ok(color_table(fs, look, column)),
        Some(Value::Object(colors)) => categorical(fs, look, column, colors, get(o, "missing").and_then(Value::as_str) == Some("self")),
        Some(other) => Err(crate::error::options(format!("colors: a {{value: colour}} map or \"self\", not {other}"))),
        None => numeric(fs, look, column, o),
    }
}

/// bake_props: each edge's __rs_fill, __rs_w, __rs_op, __rs_dash, __rs_casing, __rs_cw, __rs_cop and __rs_class.
fn bake_props(fs: &mut Roads, f: &Frame) {
    for i in 0..fs.len() {
        let style = [&f.fill, &f.width, &f.opacity, &f.dash, &f.casing, &f.casing_width, &f.casing_opacity, &f.klass].map(|v| fs.values.id(&v[i]));
        fs.draw[i].style = Some(fs.values.style_ix(style));
    }
}

/// render_edges' colouring and render_web.render's: the per-edge props of the class styles, of a data styler (color_by, color_table), or
/// of colour options (color_options: one fill per option, the shared width and casing from the class styles or the data styler).
pub fn bake(fs: &mut Roads, look: &Look, args: &Value) -> Result<Colors, crate::Error> {
    // render_edges: color_table, an edge_id -> colour map, as the column __rs_color (keys as text, as str(id) in Python)
    let main = if let Some(t) = get(args, "color_table") {
        let key = get(args, "color_key").and_then(Value::as_str).unwrap_or("edge_id");
        let t = t.as_object().ok_or_else(|| crate::error::options("color_table: a {edge_id: colour} map"))?;
        if fs.at(0).is_some_and(|f| !f.contains_key(key)) {
            return Err(crate::error::column(key, "color_key names it, and the edges do not have it"));
        }
        for i in 0..fs.len() {
            let c = fs.get(i, key).and_then(|k| t.get(&py_str(k))).cloned().unwrap_or(Value::Null);
            fs.draw[i].color = Some(fs.values.ix(&c));
        }
        Some(color_table(fs, look, Mark::Color.name()))
    } else if get(args, "style").is_some() || get(args, "color_by").is_some() {
        Some(resolve(fs, look, &json!({"color_by": get(args, "color_by"), "colors": get(args, "colors"), "cmap": get(args, "cmap"),
                                         "vmin": get(args, "vmin"), "vmax": get(args, "vmax"), "width_by": get(args, "width_by"),
                                         "style": get(args, "style")}))?)
    } else {
        None
    };
    if let Some(opts) = get(args, "color_options") {
        // one fill per option; the width, casing and dash from the main styler or the class styles
        let named: Vec<(String, Value)> = match opts {
            Value::Object(m) => m.iter().map(|(k, v)| (k.clone(), v.clone())).collect(),
            Value::Array(a) => a.iter().map(|o| {
                let name = o["name"].as_str().map(String::from).ok_or_else(|| crate::error::options("color_options: each item needs a name"))?;
                let rest: Map<String, Value> = o.as_object().unwrap().iter().filter(|(k, _)| *k != "name").map(|(k, v)| (k.clone(), v.clone())).collect();
                Ok((name, Value::Object(rest)))
            }).collect::<Result<_, crate::Error>>()?,
            other => return Err(crate::error::options(format!("color_options: a {{name: options}} map or a list, not {other}"))),
        };
        let frames = named.iter().map(|(n, o)| Ok((n.clone(), resolve(fs, look, o)?))).collect::<Result<Vec<_>, crate::Error>>()?;
        bake_props(fs, &main.unwrap_or_else(|| class_frame(fs, look)));
        let base = &frames[0].1.fill;
        let mut meta = Vec::new();
        let mut props = Vec::new();
        for (idx, (name, f)) in frames.iter().enumerate() {
            let prop = roadstyle_model::mark::option_fill(idx).into_owned();
            let miss = if idx == 0 || f.missing_self { None } else { f.missing.as_ref() };
            for i in 0..fs.len() {
                let fill = fs.values.id(if miss.is_some_and(|m| m[i]) { &base[i] } else { &f.fill[i] });
                match fs.draw[i].style {
                    Some(s) if idx == 0 => {
                        let mut s = fs.values.style(s);
                        s[0] = fill;
                        fs.draw[i].style = Some(fs.values.style_ix(s));
                    }
                    _ => fs.draw[i].fills = fs.draw[i].fills.iter().copied().chain([fill]).collect(),
                }
            }
            meta.push(json!({"name": name, "prop": prop, "legend": f.legend.clone()}));
            props.push(prop);
        }
        fs.values.fill_names = props.clone();
        let active = match get(args, "color_active") {
            Some(Value::Number(n)) => n.as_u64().ok_or_else(|| crate::error::options("color_active: an option's number or name"))? as usize,
            Some(Value::String(s)) => named.iter().position(|(n, _)| n == s).unwrap_or(0),
            _ => 0,
        };
        return Ok(Colors { props, active, meta });
    }
    let f = main.unwrap_or_else(|| class_frame(fs, look));
    bake_props(fs, &f);
    // a data styler's legend as the one "colour by" entry (no menu, only the key); legend=False: none
    let meta = match &f.legend {
        Some(l) if get(args, "legend") != Some(&Value::Bool(false)) => {
            vec![json!({"name": get(l, "title").cloned().unwrap_or_else(|| json!("data")), "prop": Mark::Fill.name(), "legend": l})]
        }
        _ => Vec::new(),
    };
    Ok(Colors { props: vec![Mark::Fill.name().into()], active: 0, meta })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_missing_category_is_empty_text() {
        let nan = json!(null);
        assert_eq!((keystr(None), keystr(Some(Cell::Null)), keystr(Some(Cell::Float(f64::NAN))), keystr(Some(Cell::Json(&nan)))), ("".into(), "".into(), "".into(), "".into()));
        assert_eq!(keystr(Some(Cell::Str(" Primary "))), "primary");
    }
}
