//! The "roads" source: the stages of roadstyle's render_web.render that bake the `__rs_*` properties of each road, in the same
//! order. Each function names the Python function it ports; the columns are the ones mapstyle passes (docs/design/rust-spike.md, S2).

use crate::draw::Cap;
use crate::road::Roads;
use roadstyle_model::{flags, Cell};
use serde_json::Value;
use std::collections::{HashMap, HashSet};

/// The look values of the roads' stages (roadstyle-look: the resolved class styles and the render's defaults).
pub use roadstyle_look::RoadLook as Look;

// the columns of the roads, as mapstyle names them (render_map's kw)
const HIGHWAY: &str = "highway";
const DIRECTED: &str = "is_directed";
const DRIVING: &str = "has_arrows";
const LAYER: &str = "layer";
const BRIDGE: &str = "bridge";
const TUNNEL: &str = "tunnel";
const CAP_START: &str = "cap_start";
const CAP_END: &str = "cap_end";

/// ClassStyler: a class's style (plain or link, resolved at build time) and its base class (normalize_highway).
pub(crate) fn class_style<'a>(look: &'a Look, highway: Option<Cell>) -> (&'a Value, String) {
    let h = match highway {
        None => String::new(),
        Some(c) if c.is_null() => String::new(),
        Some(c) => c.as_str().map_or_else(|| c.to_value().to_string(), String::from),
    };
    look.class_style(&h)
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
    mark_heads(fs, [named("head_start_m_col"), named("head_end_m_col")]);
    let named = |k: &str| args[k].as_str().is_some_and(|c| !c.is_empty());
    let computed = !named("casing_level_col") && !named("fill_level_col");      // render computes all four (compute_levels)
    mark_levels(fs, ["casing_level_col", "fill_level_col", "casing_start_col", "casing_end_col"].map(|k| computed || named(k)));
    // render's width_m_col: metre widths (docs/design/metre_widths.md); casing_m, else the theme's casing.m
    let width_col = args["width_m_col"].as_str().filter(|c| !c.is_empty());
    let pairs = if look.twin_one || width_col.is_some() { twin_pairs(fs) } else { Vec::new() };       // one time for both stages
    if look.twin_one && mark_twin_casing(fs, &pairs, look.head_m, Some("edge_id")) {        // render passes its edge_id_col (the engine's edge_id)
        mark_twin_dead_ends(fs, &caps);
    }
    if let Some(col) = width_col {
        mark_width_m(fs, &pairs, col, args["casing_m"].as_f64().unwrap_or(look.casing_m));
    }
    for (i, d) in fs.draw.iter_mut().enumerate() {
        d.edge = Some(i as u32);
    }
    Ok(colors)
}

/// The "roads" source of the style, from the marked roads (with __rs_cls, _mark_cls: filter_col is highway_col). It takes the roads:
/// their properties move into the source, not a copy (Tartu: 0.5 GB).
pub fn roads_source(mut fs: Roads) -> crate::road::RoadsSource {
    for i in 0..fs.len() {
        let cls = fs.road(i).cls();
        fs.draw[i].cls = Some(fs.values.id(&cls));
    }
    crate::road::RoadsSource { roads: fs, tolerance: 0.05, maxzoom: None, names: Vec::new(), in_style: true, read: None }
}

// --- helpers: Python's values ---

fn missing(v: Option<Cell>) -> bool {
    v.is_none_or(Cell::is_null)
}

/// A yes/no value by the one road-flag rule (roadstyle_model::flags): not missing, not 0 or False, and not a text in `flags::NO`.
pub(crate) fn truthy<'a, C: Into<Cell<'a>>>(v: Option<C>) -> bool {
    match v.map(Into::into) {
        None => false,
        Some(c) if c.is_null() => false,        // NaN too
        Some(Cell::Bool(b)) => b,
        Some(Cell::Int(i)) => i != 0,
        Some(Cell::Float(f)) => f != 0.0,
        Some(Cell::Str(s)) => flags::yes_text(s),
        Some(Cell::Json(v)) => flags::yes(v),
        Some(Cell::Null) => false,
    }
}

/// Python's float(v): a number, or a text that is one; None where Python raises.
fn py_float(v: Cell) -> Option<f64> {
    match v {
        Cell::Bool(b) => Some(b as u8 as f64),
        Cell::Str(s) => s.trim().parse::<f64>().ok(),
        Cell::Json(Value::Bool(b)) => Some(*b as u8 as f64),
        Cell::Json(Value::String(s)) => s.trim().parse::<f64>().ok(),
        c => c.as_f64(),
    }
}

/// _class_key: a missing class is "".
fn class_key(v: Option<Cell>) -> String {
    match v {
        None => String::new(),
        Some(c) if c.is_null() => String::new(),
        Some(c) => c.as_str().map_or_else(|| c.to_value().to_string(), String::from),
    }
}

// --- the stages ---

type EndKey = Option<(u32, u32, String)>;

/// _mark_twoway: __rs_twoway (a reverse twin of the same class, both directed) and __rs_oneway (the arrows).
fn mark_twoway(fs: &mut Roads, directed: bool, driving: bool) {
    let topo = fs.topo();
    let keys: Vec<EndKey> = fs.iter().map(|f| topo.ends[f.i].map(|[a, z]| (a, z, class_key(f.get(HIGHWAY))))).collect();
    let rev = |k: &EndKey| k.as_ref().map(|(a, z, c)| (*z, *a, c.clone()));
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
    let mut first: HashMap<(u32, u32, String), usize> = HashMap::new();
    for i in 0..fs.len() {
        let kind = match fs.get(i, HIGHWAY).and_then(Cell::as_str) { Some(s) if classes.contains(s) => s.to_string(), _ => continue };
        let Some([a, z]) = fs.topo().ends[i] else { continue };
        match first.remove(&(z, a, kind.clone())) {
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
/// `named`: render's head_start_m_col and head_end_m_col name the columns (as render, a column is read only when its keyword names it).
fn mark_heads(fs: &mut Roads, named: [bool; 2]) {
    if named == [false, false] {
        return;
    }
    for i in 0..fs.len() {
        let head = |on: bool, col: &str| if on { fs.get(i, col).and_then(py_float).filter(|v| *v > 0.0) } else { None };
        (fs.draw[i].head_start, fs.draw[i].head_end) = (head(named[0], "head_start_m"), head(named[1], "head_end_m"));
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
fn mark_twin_casing(fs: &mut Roads, pairs: &[(usize, usize)], head_m: f64, id_col: Option<&str>) -> bool {
    let mut bad = Vec::new();
    for &(j, i) in pairs {
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
        fs.warnings.push(format!("twin_casing: {} two-way pair(s) whose two directions disagree on their casing numbers, heads or end shapes (reversed); \
                             the first edge of each is drawn: {}{}", bad.len(), bad[..bad.len().min(10)].join(", "), if bad.len() > 10 { " ..." } else { "" }));
    }
    !pairs.is_empty()
}

/// _twin_pairs: a two-way edge and a reverse edge of its class on the same line backwards, as (first, second).
fn twin_pairs(fs: &Roads) -> Vec<(usize, usize)> {
    let mut first: HashMap<(Vec<(u64, u64)>, String), usize> = HashMap::new();
    let mut pairs = Vec::new();
    for i in 0..fs.len() {
        if fs.draw[i].twoway != Some(true) {
            continue;
        }
        let Some(c) = fs.line(i).filter(|c| c.len() >= 2) else { continue };
        // each point rounded to 7 places (the correctly rounded decimal, as Python's round; -0 is 0), as the bits of its float
        let r7 = |x: f64| { let v: f64 = format!("{x:.7}").parse().unwrap(); if v == 0.0 { 0u64 } else { v.to_bits() } };
        let line: Vec<(u64, u64)> = c.iter().map(|x| (r7(x[0]), r7(x[1]))).collect();
        let back: Vec<(u64, u64)> = line.iter().rev().copied().collect();
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
fn mark_width_m(fs: &mut Roads, pairs: &[(usize, usize)], col: &str, casing_m: f64) {
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
    for &(i, j) in pairs {
        if let (Some(a), Some(b)) = (fs.draw[i].width_m, fs.draw[j].width_m) {
            fs.draw[i].twin_width_m = Some(b);
            fs.draw[j].twin_width_m = Some(a);
        }
    }
}

/// _mark_twin_dead_ends: a twin pair's dead end (no other edge ends there) without a given cap is square.
fn mark_twin_dead_ends(fs: &mut Roads, caps: &CapCols) {
    let cs = fs.topo().ends.clone();
    let count = fs.topo().degree.clone();
    for i in 0..fs.len() {
        let Some([a, z]) = &cs[i] else { continue };
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
            if a != z && count[*pnt as usize] == 2 && !end_given[k] && !whole_given {
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


#[cfg(test)]
mod tests {
    use super::*;

    /// Roads of these lines and classes (whole numbers in `highway`), `twoway` as given.
    fn roads(rows: &[(&[[f64; 2]], i64, bool)]) -> Roads {
        let mut lines = roadstyle_model::table::Lines::default();
        rows.iter().for_each(|(l, _, _)| lines.push(Some(l)));
        let mut t = roadstyle_model::RoadTable::new(Vec::new(), Vec::new(), lines).unwrap();
        t.set_ints(HIGHWAY, rows.iter().map(|r| r.1).collect());
        let mut fs = Roads::new(t);
        for (d, r) in fs.draw.iter_mut().zip(rows) {
            d.twoway = Some(r.2);
        }
        fs
    }

    #[test]
    fn twin_pairs_are_two_way_roads_of_one_class_on_the_same_line_backwards() {
        let fs = roads(&[
            (&[[0.0, 0.0], [1.0, 0.0]], 5, true),
            (&[[1.0, 0.0], [0.0, 0.0]], 5, true),           // the twin of 0
            (&[[1.0, 0.0], [0.0, 0.0]], 6, true),           // the same line backwards, another class: no twin
            (&[[0.0, 1.0], [1.0, 1.0]], 5, false),          // not two-way
            (&[[1.0, 1.0], [0.0, 1.0]], 5, true),           // its line's other way is not two-way: no twin
            (&[[0.0, 2.0], [1.0, 2.000_000_01]], 5, true),  // the points rounded to 7 places, as Python's round
            (&[[1.0, 2.0], [0.0, 2.0]], 5, true),
        ]);
        assert_eq!(twin_pairs(&fs), vec![(0, 1), (5, 6)]);
    }
}
