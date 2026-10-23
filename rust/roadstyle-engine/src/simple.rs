//! The "simple" source: simple mode's one road layer, every casing piece and every fill (render_web._casing_parts, _halves, _end_stub,
//! _simple_pieces), from the roads after their stages (roads::mark_roads). The geometry is computed as numpy computes it: a flat
//! projection at the line's first point, sequential sums, `hypot`, and numpy's rounding (`rint(x * 10^d) / 10^d`).
//! _mitre_ends is ported for the roads with metre widths (`__rs_wm`); its part for the items waits for the items (phase P4).

use crate::read::Feature;
use crate::roads::truthy;
use crate::props::{Feat, Props, Source};
use serde_json::Value;
use std::collections::HashMap;

const SEAM_M: f64 = 0.5; // a seam reaches this far each way from its cut, at most a quarter of either piece
const LAP_M: f64 = 2.0; // a lap (the flat seam below zoom 17) reaches this far each way, at most half of either piece
const PIECES: usize = 24; // the most pieces of one edge (the feature id is edge * PIECES + n)
const TIE: f64 = 1e-8; // the line-sort-key's tie-breaker per edge
const MAX_EDGES: usize = 1_000_000;
const ITEM_STEP: f64 = 0.01; // an item's step above its edge's fill, by its rank on the edge
const MAX_ITEMS: usize = 38; // the most items of one edge between its fill and the next casings

pub type Pt = [f64; 2];

pub struct Piece {
    pub props: Props,
    pub coords: Option<Vec<Pt>>,
}

/// np.round(x, d) for d > 0: rint(x * 10^d) / 10^d.
fn np_round(x: f64, scale: f64) -> f64 {
    (x * scale).round_ties_even() / scale
}

/// A line in metres from its first point (as _casing_parts and _halves project it), with its cumulative lengths.
pub(crate) struct Line {
    pub(crate) xy: Vec<Pt>,
    pub(crate) cum: Vec<f64>,
    pub(crate) lon0: f64,
    pub(crate) lat0: f64,
    pub(crate) kx: f64,
}

pub(crate) const KY: f64 = 111320.0;

impl Line {
    pub(crate) fn new(c: &[Pt]) -> Line {
        let (lon0, lat0) = (c[0][0], c[0][1]);
        let kx = 111320.0 * lat0.to_radians().cos();
        let xy: Vec<Pt> = c.iter().map(|p| [(p[0] - lon0) * kx, (p[1] - lat0) * KY]).collect();
        let mut cum = Vec::with_capacity(xy.len());
        let mut s = 0.0;
        cum.push(0.0);
        for w in xy.windows(2) {
            s += (w[1][0] - w[0][0]).hypot(w[1][1] - w[0][1]);
            cum.push(s);
        }
        Line { xy, cum, lon0, lat0, kx }
    }

    pub(crate) fn len(&self) -> f64 {
        self.cum[self.cum.len() - 1]
    }

    // np.searchsorted(cum, d, side="right") / side="left"
    fn right(&self, d: f64) -> usize {
        self.cum.partition_point(|&x| x <= d)
    }
    fn left(&self, d: f64) -> usize {
        self.cum.partition_point(|&x| x < d)
    }

    /// _at: the point at the distance d.
    pub(crate) fn at(&self, d: f64) -> Pt {
        let j = (self.right(d) as isize - 1).clamp(0, self.cum.len() as isize - 2) as usize;
        let w = self.cum[j + 1] - self.cum[j];
        let t = if w > 0.0 { (d - self.cum[j]) / w } else { 0.0 };
        let (p, q) = (self.xy[j], self.xy[j + 1]);
        [p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])]
    }

    /// _part: the cut points at a and b and the vertices between them.
    pub(crate) fn part(&self, a: f64, b: f64) -> Vec<Pt> {
        let mut out = vec![self.at(a)];
        let (i, j) = (self.right(a), self.left(b));
        if i < j {
            out.extend_from_slice(&self.xy[i..j]);
        }
        out.push(self.at(b));
        out
    }

    /// Back to lon / lat, rounded as numpy rounds (scale 1e7 or 1e8).
    pub(crate) fn lonlat(&self, pts: &[Pt], scale: f64) -> Vec<Pt> {
        pts.iter().map(|p| [np_round(p[0] / self.kx + self.lon0, scale), np_round(p[1] / KY + self.lat0, scale)]).collect()
    }
}

fn int(p: &Props, k: &str) -> i64 {
    p.get(k).and_then(Value::as_i64).unwrap_or(0)
}

fn is_true(v: Option<&Value>) -> bool {
    v == Some(&Value::Bool(true))
}

/// _casing_parts: the casing of every edge as pieces. An edge whose three casing numbers differ (or with two different ends) is cut into
/// its start head, its main part and its end head, with a seam (and a lap, not on a dashed or tunnel casing) at each cut inside it.
pub(crate) fn casing_parts(roads: &[Feature], head_m: f64, width_col: Option<&str>) -> Vec<Piece> {
    let fcol = crate::cls_col();
    let fcol = fcol.as_str();
    let mut out = Vec::new();
    for (i, f) in roads.iter().enumerate() {
        let p = &f.props;
        if truthy(p.get("__rs_dup")) {
            continue; // one line for a reverse pair: its twin draws it
        }
        let mut base: Props = p.iter()
            .filter(|(k, _)| *k == "highway" || *k == fcol || *k == "lvl" || Some(*k) == width_col || (k.starts_with("__rs_") && !k.starts_with("__rs_fill")))
            .map(|(k, v)| (k, v.clone())).collect();
        let edge = p.get("__rs_edge").and_then(Value::as_i64).unwrap_or(i as i64);
        base.insert("__rs_edge", edge.into());
        if let Some(tw) = p.get("__rs_twin").and_then(Value::as_i64) {
            if tw < edge {
                continue; // a two-way pair's one casing: the first edge's pieces
            }
            base.insert("__rs_pair", true.into());
            base.insert("__rs_edge2", tw.into());
        }
        let (cs, cm, ce) = (int(p, "__rs_cs"), int(p, "__rs_cl"), int(p, "__rs_ce"));
        let split = truthy(p.get("__rs_split"));
        let c = match &f.coords {
            Some(c) if c.len() >= 2 && !(cs == cm && cm == ce && !split) => c,
            _ => {
                out.push(Piece { props: base, coords: f.coords.clone() });
                continue;
            }
        };
        let line = Line::new(c);
        let n = line.len();
        let (h0, h1) = (p.get("__rs_hs").and_then(Value::as_f64).unwrap_or(head_m), p.get("__rs_he").and_then(Value::as_f64).unwrap_or(head_m));
        // k: 0 the start head, 1 the main part, 2 the end head. A short road is cut once, in the heads' ratio (roadstyle after 0.24.2,
        // short_road_heads.md "One cut"): two cuts at h0 and n - h1 are one point only in exact arithmetic
        let cuts: Vec<(f64, f64, i64, usize)> = if h0 + h1 >= n - 0.05 {
            let h0 = n * h0 / (h0 + h1);
            vec![(0.0, h0, cs, 0), (h0, n, ce, 2)]
        } else {
            vec![(0.0, h0, cs, 0), (h0, n - h1, cm, 1), (n - h1, n, ce, 2)]
        };
        for &(a, b, num, k) in &cuts {
            let pts = line.part(a, b);
            if pts.len() < 2 || !pts.windows(2).any(|w| w[0] != w[1]) {
                continue;
            }
            let mut q = base.clone();
            q.insert("__rs_cl", num.into());
            if k == 1 {
                // the main piece ends at two cuts: flat ends
                q.insert("__rs_cap", true.into());
                q.insert("__rs_main", true.into());
            } else if split {
                // a head of an edge with two different ends: that end's cap
                q.insert("__rs_cap", p.get(if k == 0 { "__rs_cap0" } else { "__rs_cap1" }).cloned().unwrap_or(Value::Null));
            }
            if q.get("__rs_cap").is_none_or(Value::is_null) {
                q.shift_remove("__rs_cap");
            }
            out.push(Piece { props: q, coords: Some(line.lonlat(&pts, 1e7)) });
        }
        // a seam at each cut inside the edge, at the lower of the two pieces' numbers; below zoom 17 a flat lap instead
        let mut cut_at: Vec<f64> = cuts[1..].iter().map(|c| c.0).collect();
        cut_at.retain(|&x| x != 0.0 && x != n);
        cut_at.sort_by(f64::total_cmp);
        cut_at.dedup_by(|a, b| a == b);
        for &cut in &cut_at {
            let near: Vec<&(f64, f64, i64, usize)> = cuts.iter().filter(|(a, b, _, _)| b - a > 1e-9 && ((b - cut).abs() < 1e-9 || (a - cut).abs() < 1e-9)).collect();
            let half = near.iter().map(|(a, b, _, _)| (b - a) / 4.0).fold(SEAM_M, f64::min);
            let pts = line.part((cut - half).max(0.0), (cut + half).min(n));
            if near.len() < 2 || pts.len() < 2 {
                continue;
            }
            let mut q = base.clone();
            q.insert("__rs_cl", near.iter().map(|x| x.2).min().unwrap().into());
            q.insert("__rs_seam", true.into());
            q.shift_remove("__rs_cap");
            out.push(Piece { props: q.clone(), coords: Some(line.lonlat(&pts, 1e8)) });
            if truthy(base.get("__rs_dash")) || truthy(base.get("__rs_tunnel")) {
                continue; // a solid lap would fill a dashed casing's gaps
            }
            let half = near.iter().map(|(a, b, _, _)| (b - a) / 2.0).fold(LAP_M, f64::min);
            let pts = line.part((cut - half).max(0.0), (cut + half).min(n));
            q.insert("__rs_cap", true.into());
            q.insert("__rs_lap", true.into());
            out.push(Piece { props: q, coords: Some(line.lonlat(&pts, 1e7)) });
        }
    }
    out
}

/// _halves: the fill of every edge with two different ends (__rs_split) as two halves cut at the middle, each with its end's cap.
pub(crate) fn halves(roads: &[Feature]) -> HashMap<i64, Vec<Piece>> {
    let mut out: HashMap<i64, Vec<Piece>> = HashMap::new();
    for (i, f) in roads.iter().enumerate() {
        let p = &f.props;
        let Some(c) = f.coords.as_ref().filter(|c| c.len() >= 2) else { continue };
        if !truthy(p.get("__rs_split")) || truthy(p.get("__rs_dup")) {
            continue;
        }
        let line = Line::new(c);
        let n = line.len();
        let edge = p.get("__rs_edge").and_then(Value::as_i64).unwrap_or(i as i64);
        for (k, (a, b)) in [(0.0, n / 2.0), (n / 2.0, n)].into_iter().enumerate() {
            let mut q: Props = p.iter().filter(|(kk, _)| !matches!(*kk, "__rs_cap0" | "__rs_cap1" | "__rs_split"))
                .map(|(kk, v)| (kk, v.clone())).collect();
            q.insert("__rs_edge", edge.into());
            let cap = p.get(if k == 0 { "__rs_cap0" } else { "__rs_cap1" }).cloned().unwrap_or(Value::Null);
            if !cap.is_null() {
                q.insert("__rs_cap", cap);
            }
            out.entry(edge).or_default().push(Piece { props: q, coords: Some(line.lonlat(&line.part(a, b), 1e7)) });
        }
    }
    out
}

/// _end_stub: a piece with one road end and one cut whose road end is not flat is drawn flat, plus a short stub at the road end that
/// carries the end's shape (0.5 m for a square end, 5 cm for a round one). Any other piece as it is.
fn end_stub(q: Piece, line_of: &[Option<&Vec<Pt>>]) -> Vec<Piece> {
    let edge = q.props.get("__rs_edge").and_then(Value::as_i64).unwrap_or(-1);
    let e = usize::try_from(edge).ok().and_then(|e| line_of.get(e).copied().flatten());
    let at = |a: &Pt, b: &Pt| (a[0] - b[0]).abs() < 1e-6 && (a[1] - b[1]).abs() < 1e-6;
    let (Some(c), Some(e)) = (q.coords.as_ref(), e) else { return vec![q] };
    if c.len() < 2 || e.len() < 2 || at(&c[0], &e[0]) == at(&c[c.len() - 1], &e[e.len() - 1]) {
        return vec![q];
    }
    let first = at(&c[0], &e[0]);
    let (end, prev) = if first { (c[0], c[1]) } else { (c[c.len() - 1], c[c.len() - 2]) };
    let m = if q.props.get("__rs_cap") == Some(&Value::from("square")) { 0.5 } else { 0.05 };
    let d = ((prev[0] - end[0]) * 111320.0 * end[1].to_radians().cos()).hypot((prev[1] - end[1]) * 111320.0);
    let k = (m / d.max(1e-6)).min(1.0);
    let inner = [end[0] + (prev[0] - end[0]) * k, end[1] + (prev[1] - end[1]) * k];
    let stub = if first { vec![end, inner] } else { vec![inner, end] };
    let mut flat = q.props.clone();
    flat.insert("__rs_cap", true.into());
    let mut sp = q.props;
    sp.insert("__rs_stub", true.into());
    vec![Piece { props: flat, coords: q.coords }, Piece { props: sp, coords: Some(stub) }]
}

fn with(mut p: Props, k: i64, s: f64) -> Props {
    p.insert("__rs_k", k.into());
    p.insert("__rs_s", s.into());
    p
}

/// The "simple" source: _simple_pieces (casing pieces __rs_k 0, bridge shadows 2, tunnel gap 3 and dashes 4, fills 1), the feature ids
/// (edge * PIECES + n), the tie-breaker per edge and __rs_cls (_mark_cls).
/// `width_col`: render's width_m_col, which the pieces keep (the layer's `cols`).
/// `items`: the line items on the edges (_item_pieces, `__rs_k` 5), each over its edge's fill, by its rank on the edge.
pub fn simple_source(roads: &[Feature], head_m: f64, shadows: bool, width_col: Option<&str>, items: Vec<Piece>) -> Result<Source, String> {
    let fcol = crate::cls_col();
    let fcol = fcol.as_str();
    let line_of: Vec<Option<&Vec<Pt>>> = roads.iter().map(|f| f.coords.as_ref()).collect();
    let mut halves = halves(roads);
    let mut out: Vec<Piece> = Vec::new();
    for q0 in casing_parts(roads, head_m, width_col) {
        let stub = !is_true(q0.props.get("__rs_cap")) && !truthy(q0.props.get("__rs_seam"));
        for q in if stub { end_stub(q0, &line_of) } else { vec![q0] } {
            let p = &q.props;
            if truthy(p.get("__rs_dash")) || (truthy(p.get("__rs_seam")) && truthy(p.get("__rs_tunnel"))) {
                continue; // a dashed class has no casing; a tunnel's casing is its dashes alone
            }
            let bridge = truthy(p.get("__rs_bridge"));
            let k = 2.0 * int(p, "__rs_cl") as f64 + if bridge { 0.25 } else { 0.0 };
            let whole = int(p, "__rs_cs") == int(p, "__rs_cl") && int(p, "__rs_cl") == int(p, "__rs_ce");
            if shadows && bridge && (truthy(p.get("__rs_main")) || whole) {
                out.push(Piece { props: with(p.clone(), 2, k - 0.1), coords: q.coords.clone() });
            }
            if truthy(p.get("__rs_tunnel")) && !bridge {
                out.push(Piece { props: with(p.clone(), 3, k), coords: q.coords.clone() });
                out.push(Piece { props: with(q.props, 4, k + 0.1), coords: q.coords });
            } else {
                out.push(Piece { props: with(q.props, 0, k), coords: q.coords });
            }
        }
    }
    for (i, f) in roads.iter().enumerate() {
        let p = &f.props;
        if truthy(p.get("__rs_dup")) {
            continue;
        }
        let edge = p.get("__rs_edge").and_then(Value::as_i64).unwrap_or(i as i64);
        let fills: Vec<Piece> = if truthy(p.get("__rs_split")) {
            halves.remove(&edge).unwrap_or_default().into_iter()
                .flat_map(|h| if is_true(h.props.get("__rs_cap")) { vec![h] } else { end_stub(h, &line_of) }).collect()
        } else {
            vec![Piece { props: p.clone(), coords: f.coords.clone() }]
        };
        for h in fills {
            let props: Props = h.props.into_iter().filter(|(k, _)| *k == "highway" || *k == fcol || *k == "lvl" || Some(*k) == width_col || k.starts_with("__rs_")).collect();
            let s = 2.0 * int(&props, "__rs_fl") as f64 + if truthy(props.get("__rs_dash")) { -0.5 } else { 1.0 };
            out.push(Piece { props: with(props, 1, s), coords: h.coords });
        }
    }
    let mut items = items;
    mitre_ends(&mut out, &line_of, roads, &mut items);
    let mut n: HashMap<i64, usize> = HashMap::new();
    let mut features = Vec::with_capacity(out.len());
    for mut f in out {
        let e = f.props.get("__rs_edge").and_then(Value::as_i64).unwrap_or(0);
        let c = n.entry(e).or_default();
        if *c == PIECES {
            return Err(format!("edge {e} has more than {PIECES} pieces"));
        }
        if e as usize >= MAX_EDGES {
            return Err(format!("more than {MAX_EDGES} edges"));
        }
        let id = e as usize * PIECES + *c;
        *c += 1;
        let s = f.props["__rs_s"].as_f64().unwrap_or(0.0) + e as f64 * TIE;
        f.props.insert("__rs_s", s.into());
        let cls = roads.get(e as usize).map(|r| crate::cls_of(&r.props)).unwrap_or(Value::Null);
        f.props.insert("__rs_cls", cls);
        features.push(Feat { id, props: f.props, coords: f.coords });
    }
    // the items, by edge, order, overlay and feature: an id per edge and rank, and a sort key over the edge's fill
    items.sort_by_key(|f| ["__rs_edge", "__rs_ord", "__rs_ov", "__rs_item"].map(|k| f.props.get(k).and_then(Value::as_i64).unwrap_or(0)));
    let mut rank: HashMap<i64, usize> = HashMap::new();
    for mut f in items {
        let e = f.props.get("__rs_edge").and_then(Value::as_i64).unwrap_or(0);
        let r = rank.entry(e).or_default();
        *r += 1;
        if *r > MAX_ITEMS {
            return Err(format!("simple=True: edge {e} has more than {MAX_ITEMS} items; they do not fit between its fill and the next casings"));
        }
        let id = MAX_EDGES * PIECES + e as usize * MAX_ITEMS + *r - 1;
        let s = 2.0 * int(&f.props, "__rs_fl") as f64 + 1.0 + *r as f64 * ITEM_STEP + e as f64 * TIE;
        f.props.insert("__rs_s", s.into());
        // _mark_cls: the class and the access of the item's road
        let road = roads.get(e as usize).map(|r| &r.props);
        f.props.insert("__rs_cls", road.map(crate::cls_of).unwrap_or(Value::Null));
        if let Some(a) = road.and_then(|p| p.get("__rs_access")).filter(|a| !a.is_null()) {
            f.props.insert("__rs_access", a.clone());
        }
        features.push(Feat { id, props: f.props, coords: f.coords });
    }
    Ok(Source { feats: features, id_first: false, tolerance: 0.05, maxzoom: None })
}

// _mitre_ends: a flat end where another road with metre widths goes on is pushed on to close the corner with the road that goes on most
// straight, turning _MITRE_MAX degrees at most; an item's end where an item of its colour and dash goes on (within _ITEM_JOIN_M) too.
const MITRE_MAX: f64 = 60.0;
const ITEM_JOIN_M: f64 = 2.0;

/// _unit: the unit vector from a to b in metres east and north, and its length.
fn unit(a: &Pt, b: &Pt, lat: f64) -> ((f64, f64), f64) {
    let (x, y) = ((b[0] - a[0]) * 111320.0 * lat.to_radians().cos(), (b[1] - a[1]) * 111320.0);
    let n = x.hypot(y);
    (if n > 0.0 { (x / n, y / n) } else { (0.0, 0.0) }, n)
}

/// _heading: the way a line runs at its first or last point, from a point at least 0.5 m away.
fn heading(c: &[Pt], first: bool) -> (f64, f64) {
    let pts: Vec<&Pt> = if first { c.iter().rev().collect() } else { c.iter().collect() };
    let last = pts[pts.len() - 1];
    let flip = |u: (f64, f64)| if first { (-u.0, -u.1) } else { u };
    for q in pts[..pts.len() - 1].iter().rev() {
        let (u, n) = unit(q, last, last[1]);
        if n >= 0.5 {
            return flip(u);
        }
    }
    flip(unit(pts[0], last, last[1]).0)
}

/// _reach: how far a flat end goes on to close the corner with the line that goes on (None: not a corner to close).
fn reach(own: ((f64, f64), (f64, f64), f64, f64), oth: ((f64, f64), (f64, f64), f64, f64)) -> Option<f64> {
    let ((p, u, h, o), (q, v, k, w)) = (own, oth);
    let cos = (u.0 * v.0 + u.1 * v.1).clamp(-1.0, 1.0);
    let turn = cos.acos().to_degrees();
    if !(0.5..=MITRE_MAX).contains(&turn) {
        return None;
    }
    let rn = |d: (f64, f64), x: f64| (d.1 * x, -d.0 * x);
    let (pa, pb) = ((p.0 + rn(u, o).0, p.1 + rn(u, o).1), (q.0 + rn(v, w).0, q.1 + rn(v, w).1));
    let det = u.0 * v.1 - u.1 * v.0;
    let (dx, dy) = (pb.0 - pa.0, pb.1 - pa.1);
    let (s, t) = ((dx * v.1 - dy * v.0) / det, (u.0 * dy - u.1 * dx) / det);
    if s.abs().max(t.abs()) > ITEM_JOIN_M {
        return None;
    }
    let sin = turn.to_radians().sin();
    Some(s.max(0.0) + ((k - h * cos) / sin).max(0.0).min(h * (turn.to_radians() / 2.0).tan()))
}

/// _push: the line with its first or last point pushed `m` metres straight on.
fn push(c: &mut Vec<Pt>, first: bool, m: f64) {
    let u = heading(c, first);
    let u = if first { (-u.0, -u.1) } else { u };
    let end = if first { c[0] } else { c[c.len() - 1] };
    let pt = [crate::layers::py_round(end[0] + u.0 * m / (111320.0 * end[1].to_radians().cos()), 7), crate::layers::py_round(end[1] + u.1 * m / 111320.0, 7)];
    if first { c.insert(0, pt) } else { c.push(pt) }
}

fn mitre_ends(out: &mut [Piece], line_of: &[Option<&Vec<Pt>>], roads: &[Feature], items: &mut [Piece]) {
    let snap = |p: &Pt| (format!("{:.6}", p[0]), format!("{:.6}", p[1]));
    let mut wide: indexmap::IndexMap<i64, (f64, f64)> = indexmap::IndexMap::new();
    for (i, f) in roads.iter().enumerate() {
        let p = &f.props;
        let (Some(wm), Some(c)) = (p.get("__rs_wm").and_then(Value::as_f64), f.coords.as_ref().filter(|c| c.len() >= 2)) else { continue };
        if truthy(p.get("__rs_dup")) {
            continue;
        }
        let k = c[0][1].to_radians().cos();
        let cm = p.get("__rs_cm").and_then(Value::as_f64).unwrap_or(0.0);
        wide.insert(p.get("__rs_edge").and_then(Value::as_i64).unwrap_or(i as i64), (wm * k, (wm - 2.0 * cm) * k));
    }
    let line = |e: i64| line_of.get(e as usize).copied().flatten();
    let mut ends: HashMap<(String, String), Vec<(i64, bool)>> = HashMap::new();
    for &e in wide.keys() {
        let Some(c) = line(e) else { continue };
        ends.entry(snap(&c[0])).or_default().push((e, true));
        ends.entry(snap(&c[c.len() - 1])).or_default().push((e, false));
    }
    let at = |a: &Pt, b: &Pt| (a[0] - b[0]).abs() < 1e-6 && (a[1] - b[1]).abs() < 1e-6;
    // one latitude for all the metres (two points' own ones put them metres apart): the first item's, else the first road's
    let lat0 = items.first().and_then(|f| f.coords.as_ref()).and_then(|c| c.first()).map(|p| p[1])
        .or_else(|| line_of.iter().flatten().find(|c| !c.is_empty()).map(|c| c[0][1])).unwrap_or(0.0);
    let k0 = 111320.0 * lat0.to_radians().cos();
    let xy = |pt: &Pt| (pt[0] * k0, pt[1] * 111320.0);
    for f in out.iter_mut() {
        let p = &f.props;
        let Some(edge) = p.get("__rs_edge").and_then(Value::as_i64) else { continue };
        if p.get("__rs_cap") != Some(&Value::Bool(true)) || truthy(p.get("__rs_seam")) || truthy(p.get("__rs_lap")) || !wide.contains_key(&edge) {
            continue;
        }
        let (Some(c), Some(e)) = (f.coords.as_mut().filter(|c| c.len() >= 2), line(edge)) else { continue };
        let j = if int(p, "__rs_k") == 1 { 1 } else { 0 };
        for first in [true, false] {
            let (cp, ep) = if first { (&c[0], &e[0]) } else { (&c[c.len() - 1], &e[e.len() - 1]) };
            if !at(cp, ep) {
                continue;
            }
            let node = *ep;
            let u = heading(e, first);
            let u = if first { (-u.0, -u.1) } else { u };
            let mut best: Option<(f64, f64)> = None;
            for &(o, ofirst) in ends.get(&snap(&node)).into_iter().flatten() {
                if o == edge {
                    continue;
                }
                let Some(oc) = line(o) else { continue };
                let v = heading(oc, ofirst);
                let v = if ofirst { v } else { (-v.0, -v.1) };
                let pick = |x: (f64, f64)| if j == 1 { x.1 } else { x.0 };
                let m = reach((xy(&node), u, pick(wide[&edge]) / 2.0, 0.0), (xy(&node), v, pick(wide[&o]) / 2.0, 0.0));
                let dot = u.0 * v.0 + u.1 * v.1;
                if let Some(m) = m {
                    if best.is_none_or(|b| dot > b.0) {
                        best = Some((dot, m));
                    }
                }
            }
            if let Some((_, m)) = best.filter(|b| b.1 > 0.0) {
                push(c, first, m);
            }
        }
    }
    // the items: an end with the items of its colour and dash that start within ITEM_JOIN_M (and a start with those that end there)
    let lines: Vec<usize> = (0..items.len()).filter(|&k| items[k].coords.as_ref().is_some_and(|c| c.len() >= 2)).collect();
    let text = |f: &Piece, k: &str| f.props.get(k).filter(|v| !v.is_null()).map(Value::to_string);     // Python's None: missing or null
    let key = |f: &Piece| (text(f, "__rs_ic"), text(f, "__rs_dash"));
    let cell = |p: &Pt| ((p[0] / 3e-5).floor() as i64, (p[1] / 3e-5).floor() as i64);
    let end_of = |c: &Vec<Pt>, first: bool| if first { c[0] } else { c[c.len() - 1] };
    let mut by: HashMap<_, Vec<usize>> = HashMap::new();
    for &k in &lines {
        let c = items[k].coords.as_ref().unwrap();
        for first in [true, false] {
            by.entry((key(&items[k]), first, cell(&end_of(c, first)))).or_default().push(k);
        }
    }
    let num = |p: &Props, k: &str| p.get(k).and_then(Value::as_f64).unwrap_or(0.0);
    let side = |f: &Piece, first: bool| {
        let c = f.coords.as_ref().unwrap();
        let cl = c[0][1].to_radians().cos();
        let u = heading(c, first);
        let out_u = if first { (-u.0, -u.1) } else { u };
        let o = num(&f.props, "__rs_iom") * cl;
        (xy(&end_of(c, first)), out_u, num(&f.props, "__rs_iwm") * cl / 2.0, if first { -o } else { o })
    };
    let mut pushes = Vec::new();
    for &k in &lines {
        for first in [true, false] {
            let (p, u, h, o) = side(&items[k], first);
            let (x, y) = cell(&end_of(items[k].coords.as_ref().unwrap(), first));
            let mut best: Option<(f64, f64)> = None;
            for dx in [-1, 0, 1] {
                for dy in [-1, 0, 1] {
                    for &j in by.get(&(key(&items[k]), !first, (x + dx, y + dy))).into_iter().flatten() {
                        if j == k {
                            continue;
                        }
                        let (q, v, kk, w) = side(&items[j], !first);
                        let (v, w) = ((-v.0, -v.1), -w);
                        if (q.0 - p.0).hypot(q.1 - p.1) > ITEM_JOIN_M {
                            continue;
                        }
                        let dot = u.0 * v.0 + u.1 * v.1;
                        if let Some(m) = reach((p, u, h, o), (q, v, kk, w)) {
                            if best.is_none_or(|b| dot > b.0) {
                                best = Some((dot, m));
                            }
                        }
                    }
                }
            }
            if let Some((_, m)) = best.filter(|b| b.1 > 0.0) {
                pushes.push((k, first, m));
            }
        }
    }
    for (k, first, m) in pushes {
        push(items[k].coords.as_mut().unwrap(), first, m);
    }
}
