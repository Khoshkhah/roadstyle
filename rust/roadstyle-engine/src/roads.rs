//! The "roads" source: the stages of roadstyle's render_web.render that bake the `__rs_*` properties of each road, in the same
//! order. Each function names the Python function it ports; the columns are the ones mapstyle passes (docs/design/rust-spike.md, S2).

use crate::draw::Cap;
use crate::road::Roads;
use roadstyle_model::Cell;
use serde_json::Value;
use std::collections::{HashMap, HashSet};

/// The look data the stages read (look.json: the resolved class styles and the render's defaults).
pub struct Look {
    /// the theme's data.* values (the data stylers' widths, opacities and no-data colours) and the palette's name
    pub(crate) data: Value,
    pub(crate) palette: String,
    classes: HashMap<String, [Value; 2]>,
    fallback: [Value; 2],
    single_line: HashSet<String>,
    twin_one: bool,
    /// the heads' default length (render's head_m)
    pub head_m: f64,
    /// config bridge_shadow: a bridge's main casing piece casts a shadow (simple source)
    pub bridge_shadow: bool,
    /// the theme's access colours (render's access_col: the palette's `access`)
    access: serde_json::Map<String, Value>,
    /// the theme's casing.m: a metre-wide road's casing in metres (render's casing_m)
    casing_m: f64,
}

impl Look {
    pub fn from_json(look: &Value) -> Result<Look, String> {
        let pair = |v: &Value| -> Result<[Value; 2], String> {
            match v.as_array().map(|a| a.as_slice()) {
                Some([a, b]) => Ok([a.clone(), b.clone()]),
                _ => Err("look.json: a class style is not [plain, link]".into()),
            }
        };
        let styles = &look["styles"];
        let classes = styles["classes"].as_object().ok_or("look.json: no styles.classes")?;
        Ok(Look {
            data: look["theme"]["data"].clone(),
            palette: look["palette"].as_str().unwrap_or_default().to_string(),
            classes: classes.iter().map(|(k, v)| Ok((k.clone(), pair(v)?))).collect::<Result<_, String>>()?,
            fallback: pair(&styles["fallback"])?,
            single_line: look["config"]["single_line_classes"].as_array().into_iter().flatten()
                .filter_map(|v| v.as_str().map(String::from)).collect(),
            twin_one: look["config"]["twin_casing"] == "one",
            // render's head_m keyword, else its default in the look
            head_m: look["args"]["head_m"].as_f64().map_or_else(|| look["head_m"].as_f64().ok_or("look.json: no head_m"), Ok)?,
            bridge_shadow: truthy(look["config"].get("bridge_shadow").map(Cell::Json)),
            access: look["theme"]["access"].as_object().cloned().unwrap_or_default(),
            casing_m: look["theme"]["casing"]["m"].as_f64().unwrap_or(0.0),
        })
    }
}

// the columns of the roads, as mapstyle names them (render_map's kw)
const HIGHWAY: &str = "highway";
const DIRECTED: &str = "is_directed";
const DRIVING: &str = "has_arrows";
const LAYER: &str = "layer";
const BRIDGE: &str = "bridge";
const TUNNEL: &str = "tunnel";
const CAP_START: &str = "cap_start";
const CAP_END: &str = "cap_end";

impl Look {
    /// ClassStyler: a class's style (plain or link, resolved at build time) and its base class (normalize_highway).
    pub(crate) fn class_style(&self, highway: Option<Cell>) -> (&Value, String) {
        let h = match highway {
            None => String::new(),
            Some(c) if c.is_null() => String::new(),
            Some(c) => match c.as_str() { Some(s) => s.trim().to_lowercase(), None => c.to_value().to_string().trim().to_lowercase() },
        };
        let (base, link) = match h.strip_suffix("_link") { Some(b) => (b.to_string(), 1), None => (h, 0) };
        (&self.classes.get(&base).unwrap_or(&self.fallback)[link], base)
    }
}

/// The stages of render_web.render on the roads, in its order; each road gets `__rs_edge`, its position. `args`: look["args"], with the
/// options of the colours (colors.rs).
/// render's access_col: the kinds that have their own colour and row (_ACCESS); any other value is null.
const ACCESS_KINDS: [&str; 4] = ["private", "bus", "pedestrian", "delivery"];

pub fn mark_roads(fs: &mut Roads, look: &Look, args: &Value) -> Result<crate::colors::Colors, String> {
    let access_col = args["access_col"].as_str().filter(|c| !c.is_empty());
    if let Some(col) = access_col {
        if fs.table.col(col).is_none() && !fs.is_empty() {
            return Err(format!("access_col {col:?} is not a column of the edges"));
        }
        for i in 0..fs.len() {
            let kind = fs.get(i, col).and_then(Cell::as_str).and_then(|k| ACCESS_KINDS.iter().find(|a| **a == k).copied());
            fs.draw[i].access = Some(kind);
        }
    }
    let colors = crate::colors::bake(fs, look, args)?;
    // render: the direction columns are read only when they are named (directed_col, driving_col: None by default)
    let named = |k: &str| args[k].as_str().is_some_and(|c| !c.is_empty());
    mark_twoway(fs, named("directed_col"), named("driving_col"));
    // a road with an access kind has its kind's colour in every colour option (the palette's `access`)
    for i in (0..fs.len()).filter(|_| access_col.is_some()) {
        let Some(c) = fs.draw[i].access.flatten().and_then(|k| look.access.get(k)).filter(|c| !c.is_null()) else { continue };
        let c = fs.values.id(c);
        let d = &mut fs.draw[i];
        if let Some(s) = d.style.as_mut() {
            s[0] = c;
        }
        d.fills.iter_mut().for_each(|f| *f = c);
    }
    if !look.single_line.is_empty() {
        mark_single_line(fs, &look.single_line);
    }
    mark_lvl(fs);
    let caps = CapCols::from_args(args);
    mark_caps(fs, &caps);
    mark_heads(fs);
    let named = |k: &str| args[k].as_str().is_some_and(|c| !c.is_empty());
    let computed = !named("casing_level_col") && !named("fill_level_col");      // render computes all four (compute_levels)
    mark_levels(fs, ["casing_level_col", "fill_level_col", "casing_start_col", "casing_end_col"].map(|k| computed || named(k)));
    if look.twin_one && mark_twin_casing(fs, look.head_m, Some("edge_id")) {        // render passes its edge_id_col (the engine's edge_id)
        mark_twin_dead_ends(fs, &caps);
    }
    // render's width_m_col: metre widths (docs/design/metre_widths.md); casing_m, else the theme's casing.m
    if let Some(col) = args["width_m_col"].as_str().filter(|c| !c.is_empty()) {
        mark_width_m(fs, col, args["casing_m"].as_f64().unwrap_or(look.casing_m));
    }
    stringify_unsafe_ints(fs);
    for (i, d) in fs.draw.iter_mut().enumerate() {
        d.edge = Some(i as u32);
    }
    Ok(colors)
}

/// The "roads" source of the style, from the marked roads (with __rs_cls, _mark_cls: filter_col is highway_col). It takes the roads:
/// their properties move into the source, not a copy (Tartu: 0.5 GB).
pub fn roads_source(mut fs: Roads) -> crate::road::RoadsSource {
    for i in 0..fs.len() {
        let cls = crate::cls_of(fs.road(i));
        fs.draw[i].cls = Some(fs.values.id(&cls));
    }
    crate::road::RoadsSource { roads: fs, tolerance: 0.05, maxzoom: None, names: Vec::new(), in_style: true }
}

// --- helpers: Python's values ---

fn missing(v: Option<Cell>) -> bool {
    v.is_none_or(Cell::is_null)
}

/// render_web._truthy: not missing and not "", "no", "false", "0", 0 or False.
pub(crate) fn truthy<'a, C: Into<Cell<'a>>>(v: Option<C>) -> bool {
    match v.map(Into::into) {
        None => false,
        Some(c) if c.is_null() => false,
        Some(Cell::Bool(b)) => b,
        Some(Cell::Int(i)) => i != 0,
        Some(Cell::Float(f)) => f != 0.0,
        Some(Cell::Str(s)) => !matches!(s, "" | "no" | "false" | "0"),
        Some(Cell::IntText(_)) => true,
        Some(Cell::Json(v)) => match v {
            Value::Bool(b) => *b,
            Value::Number(n) => n.as_f64() != Some(0.0),
            Value::String(s) => !matches!(s.as_str(), "" | "no" | "false" | "0"),
            _ => true,
        },
        Some(Cell::Null) => false,
    }
}

/// Python's float(v): a number, or a text that is one; None where Python raises.
fn py_float(v: Cell) -> Option<f64> {
    match v {
        Cell::Bool(b) => Some(b as u8 as f64),
        Cell::Str(s) => s.trim().parse::<f64>().ok(),
        Cell::IntText(i) => Some(i as f64),
        Cell::Json(Value::Bool(b)) => Some(*b as u8 as f64),
        Cell::Json(Value::String(s)) => s.trim().parse::<f64>().ok(),
        c => c.as_f64(),
    }
}

/// round(x, digits) as a key: the text of the correctly rounded decimal is the same as Python's round (a tie cannot occur at 6 or 7
/// places: half of 1e-6 has no exact binary value), and -0 is 0.
fn round_key(x: f64, digits: usize) -> String {
    let s = format!("{x:.digits$}");
    if s.starts_with('-') && s[1..].bytes().all(|c| c == b'0' || c == b'.') { s[1..].to_string() } else { s }
}

fn point_key(c: &[f64; 2]) -> (String, String) {
    (round_key(c[0], 6), round_key(c[1], 6))
}

/// _class_key: a missing class is "".
fn class_key(v: Option<Cell>) -> String {
    match v {
        None => String::new(),
        Some(c) if c.is_null() => String::new(),
        Some(c) => c.as_str().map_or_else(|| c.to_value().to_string(), String::from),
    }
}

/// The road's two end points, for a LineString of two points or more.
fn ends(c: Option<&[[f64; 2]]>) -> Option<([f64; 2], [f64; 2])> {
    let c = c?;
    (c.len() >= 2).then(|| (c[0], c[c.len() - 1]))
}

// --- the stages ---

type EndKey = Option<((String, String), (String, String), String)>;

/// _mark_twoway: __rs_twoway (a reverse twin of the same class, both directed) and __rs_oneway (the arrows).
fn mark_twoway(fs: &mut Roads, directed: bool, driving: bool) {
    let keys: Vec<EndKey> = fs.iter().map(|f| ends(f.line()).map(|(a, z)| (point_key(&a), point_key(&z), class_key(f.get(HIGHWAY))))).collect();
    let rev = |k: &EndKey| k.as_ref().map(|(a, z, c)| (z.clone(), a.clone(), c.clone()));
    let mut by: HashMap<EndKey, Vec<usize>> = HashMap::new();
    for (i, k) in keys.iter().enumerate() {
        if k.is_some() {        // not a line: a key of its own (Python: id(ft)), never a twin
            by.entry(k.clone()).or_default().push(i);
        }
    }
    let count = |k: &EndKey| if k.is_some() { by.get(k).map_or(0, |v| v.len()) } else { 0 };
    for (i, k) in keys.iter().enumerate() {
        let r = rev(k);
        let n = count(&r);
        let two = if k.is_some() && r == *k { n >= 2 } else { n >= 1 };
        let ow = if missing(fs.get(i, "oneway")) { !two } else { truthy(fs.get(i, "oneway")) };
        (fs.draw[i].twoway, fs.draw[i].oneway) = (Some(two), Some(ow));
    }
    if directed {
        // directed_col: a pair is two lanes only when neither edge is undirected (null = directed)
        let und = |f: crate::road::Road| !missing(f.get(DIRECTED)) && !truthy(f.get(DIRECTED));
        let undirected: Vec<bool> = fs.iter().map(und).collect();
        for (i, k) in keys.iter().enumerate() {
            if fs.draw[i].twoway != Some(true) {
                continue;
            }
            let others_und = by.get(&rev(k)).is_none_or(|v| v.iter().filter(|&&t| t != i).all(|&t| undirected[t]));
            if undirected[i] || others_und {
                let no_oneway = missing(fs.get(i, "oneway"));
                let d = &mut fs.draw[i];
                d.twoway = Some(false);
                if no_oneway {
                    d.oneway = Some(!undirected[i]);
                }
            }
        }
    }
    if driving {
        for i in 0..fs.len() {        // driving_col: no arrows where cars may not drive (null = driving)
            if !missing(fs.get(i, DRIVING)) && !truthy(fs.get(i, DRIVING)) {
                fs.draw[i].oneway = Some(false);
            }
        }
    }
}

/// _mark_single_line: a reverse pair of a single-line class is one line; the later edge is __rs_dup, both name the other in __rs_edge2.
fn mark_single_line(fs: &mut Roads, classes: &HashSet<String>) {
    let mut first: HashMap<((String, String), (String, String), String), usize> = HashMap::new();
    for i in 0..fs.len() {
        let kind = match fs.get(i, HIGHWAY).and_then(Cell::as_str) { Some(s) if classes.contains(s) => s.to_string(), _ => continue };
        let Some((a, z)) = ends(fs.line(i)) else { continue };
        let (a, z) = (point_key(&a), point_key(&z));
        match first.remove(&(z.clone(), a.clone(), kind.clone())) {
            None => {
                first.entry((a, z, kind)).or_insert(i);
            }
            Some(j) => {
                fs.draw[i].dup = true;
                fs.draw[i].edge2 = Some(j as u32);
                fs.draw[j].edge2 = Some(i as u32);
                for r in [i, j] {
                    (fs.draw[r].twoway, fs.draw[r].oneway) = (Some(false), Some(false));
                }
            }
        }
    }
}

/// _mark_lvl: lvl from the OSM layer (else 1 for a bridge, -1 for a tunnel), and the bridge and tunnel looks.
fn mark_lvl(fs: &mut Roads) {
    for i in 0..fs.len() {
        let ly = fs.get(i, LAYER).and_then(py_float).filter(|v| v.is_finite()).map_or(0, |v| v.trunc() as i64);
        let (br, tu) = (truthy(fs.get(i, BRIDGE)), truthy(fs.get(i, TUNNEL)));
        let lvl = if ly != 0 { ly } else if br { 1 } else if tu { -1 } else { 0 };
        let d = &mut fs.draw[i];
        (d.lvl, d.bridge, d.tunnel) = (Some(lvl), Some(br), Some(tu));
    }
}

/// _cap_value: "square", true (flat at the end point) or null (round).
fn cap_value(v: Cell) -> Value {
    if let Some(s) = v.as_str() {
        match s.trim().to_lowercase().as_str() {
            "square" => return "square".into(),
            "round" => return Value::Null,
            _ => {}
        }
    }
    if truthy(Some(v)) { true.into() } else { Value::Null }
}

/// _mark_caps (no cap_col; cap_start_col / cap_end_col): __rs_cap when the two ends agree, else __rs_cap0 / __rs_cap1 / __rs_split.
/// render's cap columns: `cap_col` (both ends; the user's name) and `cap_start_col` / `cap_end_col` (one end each; the engine's names
/// cap_start / cap_end after ColumnMap). Only the named ones are read.
pub(crate) struct CapCols {
    whole: Option<String>,
    start: bool,
    end: bool,
}

impl CapCols {
    fn from_args(args: &Value) -> CapCols {
        let named = |k: &str| args[k].as_str().is_some_and(|c| !c.is_empty());
        CapCols { whole: args["cap_col"].as_str().filter(|c| !c.is_empty()).map(String::from), start: named("cap_start_col"), end: named("cap_end_col") }
    }
}

/// A value is given: set, and not NaN (Python: not None and equal to itself).
fn given(v: Option<Cell>) -> bool {
    !missing(v) && v.and_then(Cell::as_f64).is_none_or(|x| !x.is_nan())
}

fn mark_caps(fs: &mut Roads, caps: &CapCols) {
    for i in 0..fs.len() {
        let r = fs.road(i);
        let whole = caps.whole.as_deref().and_then(|c| r.get(c)).filter(|v| given(Some(*v))).map_or(Value::Null, cap_value);
        let end = |on: bool, col: &str| if on && given(r.get(col)) { cap_value(r.get(col).unwrap()) } else { whole.clone() };
        let (s0, s1) = (Cap::from_value(&end(caps.start, CAP_START)), Cap::from_value(&end(caps.end, CAP_END)));
        let d = &mut fs.draw[i];
        if s0 == s1 {
            if s0 != Cap::Round {
                d.cap = Some(s0);
            }
        } else {
            d.split = Some([s0, s1]);
        }
    }
}

/// The head lengths of each edge (head_start_m_col / head_end_m_col): __rs_hs / __rs_he where the value is a number above 0.
fn mark_heads(fs: &mut Roads) {
    for i in 0..fs.len() {
        let head = |col: &str| fs.get(i, col).and_then(py_float).filter(|v| *v > 0.0);
        (fs.draw[i].head_start, fs.draw[i].head_end) = (head("head_start_m"), head("head_end_m"));
    }
}

/// _mark_levels: __rs_cl / __rs_fl (casing at most the fill), the heads' casing numbers __rs_cs / __rs_ce, band 0.
/// _mark_levels: `named` says which of the columns casing_level, fill_level, casing_start and casing_end render reads (a keyword names it,
/// or render computed the levels); a head that has none takes the main casing number.
fn mark_levels(fs: &mut Roads, named: [bool; 4]) {
    let num = |v: Option<Cell>| v.and_then(py_float).filter(|x| !x.is_nan()).map_or(0, |x| x.round_ties_even() as i64);
    for i in 0..fs.len() {
        let r = fs.road(i);
        let col = |k: usize, c: &str| if named[k] { num(r.get(c)) } else { 0 };
        let (c, fl) = (col(0, "casing_level"), col(1, "fill_level"));
        let (c, fl) = (c.min(fl), c.max(fl));
        let cs = if named[2] { num(r.get("casing_start")).min(fl) } else { c };
        let ce = if named[3] { num(r.get("casing_end")).min(fl) } else { c };
        fs.draw[i].levels = Some([c, fl, cs, ce]);
    }
}

/// _twin_pairs + _mark_twin_casing: a two-way edge and a reverse edge of its class on the same line backwards share one casing
/// (__rs_twin: the other's position). Returns whether any pair was found. The two must agree, reversed (casing numbers, heads and end
/// shapes); a pair that does not is named in a warning, by `id_col` (render's edge_id_col), else by position.
fn mark_twin_casing(fs: &mut Roads, head_m: f64, id_col: Option<&str>) -> bool {
    let pairs = twin_pairs(fs);
    let mut bad = Vec::new();
    for &(j, i) in &pairs {
        fs.draw[i].twin = Some(j as u32);
        fs.draw[j].twin = Some(i as u32);
        // each end: its casing number, its head length and its cap
        let ends = |d: &crate::draw::Draw| {
            let whole = d.cap.unwrap_or(Cap::Round);
            let [s0, s1] = d.split.unwrap_or([whole, whole]);
            let lv = |k: usize| d.levels.map(|l| l[k]);
            ((lv(2), d.head_start.unwrap_or(head_m), s0), (lv(3), d.head_end.unwrap_or(head_m), s1))
        };
        let (p, q) = (&fs.draw[i], &fs.draw[j]);
        let (ep, eq) = (ends(p), ends(q));
        if (eq.0 != ep.1 || eq.1 != ep.0) || q.levels.map(|l| l[0]) != p.levels.map(|l| l[0]) {
            let name = |k: usize| match id_col.and_then(|c| fs.get(k, c)) {
                Some(c) => c.as_str().map_or_else(|| c.to_value().to_string(), String::from),
                None => k.to_string(),
            };
            bad.push(format!("{} / {}", name(j), name(i)));
        }
    }
    if !bad.is_empty() {
        crate::warn(format!("twin_casing: {} two-way pair(s) whose two directions disagree on their casing numbers, heads or end shapes (reversed); \
                             the first edge of each is drawn: {}{}", bad.len(), bad[..bad.len().min(10)].join(", "), if bad.len() > 10 { " ..." } else { "" }));
    }
    !pairs.is_empty()
}

/// _twin_pairs: a two-way edge and a reverse edge of its class on the same line backwards, as (first, second).
fn twin_pairs(fs: &Roads) -> Vec<(usize, usize)> {
    let mut first: HashMap<(String, String), usize> = HashMap::new();
    let mut pairs = Vec::new();
    for i in 0..fs.len() {
        if fs.draw[i].twoway != Some(true) {
            continue;
        }
        let Some(c) = fs.line(i).filter(|c| c.len() >= 2) else { continue };
        let pts: Vec<String> = c.iter().map(|x| format!("{},{}", round_key(x[0], 7), round_key(x[1], 7))).collect();
        let line = pts.join(";");
        let back = pts.iter().rev().cloned().collect::<Vec<_>>().join(";");
        let ck = class_key(fs.get(i, HIGHWAY));
        match first.remove(&(back, ck.clone())) {
            None => {
                first.entry((line, ck)).or_insert(i);
            }
            Some(j) => pairs.push((j, i)),
        }
    }
    pairs
}

/// _mark_width_m: __rs_wm / __rs_cm, the line's width and casing in metres over cos(latitude) at its mean latitude, for a finite width
/// above 0 (any other value keeps the class width). Then a pair with metres on both gets the other direction's in __rs_twm.
fn mark_width_m(fs: &mut Roads, col: &str, casing_m: f64) {
    for i in 0..fs.len() {
        let Some(w) = fs.get(i, col).and_then(py_float) else { continue };
        let pts = fs.line(i).unwrap_or(&[]);
        if !(w > 0.0 && w.is_finite()) || pts.is_empty() {
            continue;
        }
        let sec = 1.0 / (pts.iter().map(|c| c[1]).sum::<f64>() / pts.len() as f64).to_radians().cos();
        fs.draw[i].width_m = Some(crate::layers::py_round(w * sec, 4));
        fs.draw[i].casing_m = Some(crate::layers::py_round(casing_m * sec, 4));
    }
    for (i, j) in twin_pairs(fs) {
        if let (Some(a), Some(b)) = (fs.draw[i].width_m, fs.draw[j].width_m) {
            fs.draw[i].twin_width_m = Some(b);
            fs.draw[j].twin_width_m = Some(a);
        }
    }
}

/// _mark_twin_dead_ends: a twin pair's dead end (no other edge ends there) without a given cap is square.
fn mark_twin_dead_ends(fs: &mut Roads, caps: &CapCols) {
    let mut count: HashMap<(String, String), usize> = HashMap::new();
    let cs: Vec<Option<((String, String), (String, String))>> = fs.iter().map(|f| ends(f.line()).map(|(a, z)| (point_key(&a), point_key(&z)))).collect();
    for (a, z) in cs.iter().flatten() {
        *count.entry(a.clone()).or_default() += 1;
        *count.entry(z.clone()).or_default() += 1;
    }
    for i in 0..fs.len() {
        let Some((a, z)) = &cs[i] else { continue };
        if fs.draw[i].twin.is_none() {
            continue;
        }
        let r = fs.road(i);
        let whole_given = caps.whole.as_deref().is_some_and(|c| given(r.get(c)));
        let end_given = [(caps.start, CAP_START), (caps.end, CAP_END)].map(|(on, col)| on && given(r.get(col)));
        let d = &mut fs.draw[i];
        let whole = d.cap.unwrap_or(Cap::Round);
        let split = d.split.is_some();
        let old = d.split.unwrap_or([whole, whole]);
        let mut new = old;
        for (k, pnt) in [a, z].into_iter().enumerate() {
            if a != z && count.get(pnt) == Some(&2) && !end_given[k] && !whole_given {
                new[k] = Cap::Square;
            }
        }
        // a cap property set new comes after the twin's (Python's dict: a key put back goes to the end)
        if new[0] == new[1] {
            d.split = None;
            if new[0] != Cap::Round {
                d.caps_late |= d.cap.is_none();
                d.cap = Some(new[0]);
            }
        } else if new != old || split {
            d.cap = None;
            d.caps_late |= !split;
            d.split = Some(new);
        }
    }
}

/// _stringify_unsafe_ints: an integer past 2**53 - 1 as text (JavaScript would round it). The marks have none.
fn stringify_unsafe_ints(fs: &mut Roads) {
    fs.table.stringify_unsafe_ints();
}
