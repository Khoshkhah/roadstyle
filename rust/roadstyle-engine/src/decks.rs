//! render_web._bridge_decks: the bridges as ramped deck ribbons for the 3D view (the fill-extrusion source `decks`). Python makes the ribbons
//! with shapely (GEOS buffers and offset curves); this module makes the same strips with its own mitre offsets, so a polygon can have
//! other vertices than GEOS gives, but it covers the same ground (tests/test_engine_parity.py compares them by shape).

use crate::layers::{py_round, py_truth, Model};
use crate::road::Roads;
use roadstyle_model::Cell;
use serde_json::{json, Map, Value};
use std::collections::HashMap;

type P = [f64; 2];
type Node = (f64, f64);

/// The deck settings (render's dk: the defaults, then the config's bridge_decks).
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
    pub fn from_config(cfg: &Value) -> DeckLook {
        let f = |k: &str, d: f64| cfg[k].as_f64().unwrap_or(d);
        DeckLook { base_m: f("base_m", 5.0), thickness_m: f("thickness_m", 1.0), ramp_m: f("ramp_m", 40.0), step_m: f("step_m", 2.5),
                   match_zoom: f("match_zoom", 18.0), width_scale: f("width_scale", 1.0), casing_px: f("casing_px", 2.0),
                   flat_below: f("flat_below", 16.0), opacity: f("opacity", 0.7) }
    }
}

/// A node as a hash key (the rounded floats' bits: py_round gives no -0.0).
fn hk(n: Node) -> (u64, u64) {
    (n.0.to_bits(), n.1.to_bits())
}

fn lt(a: (Node, Node), b: (Node, Node)) -> bool {
    a.partial_cmp(&b) == Some(std::cmp::Ordering::Less)
}

fn key(a: Node, z: Node) -> ((u64, u64), (u64, u64)) {
    let (p, q) = if lt((z, a), (a, z)) { (z, a) } else { (a, z) };
    (hk(p), hk(q))
}

fn len(a: &P, b: &P) -> f64 {
    ((b[0] - a[0]).powi(2) + (b[1] - a[1]).powi(2)).sqrt()
}

/// shapely's interpolate: the point at distance d along the line.
fn at_dist(pts: &[P], d: f64) -> P {
    let mut run = 0.0;
    for w in pts.windows(2) {
        let l = len(&w[0], &w[1]);
        if run + l >= d && l > 0.0 {
            let f = (d - run) / l;
            return [w[0][0] + (w[1][0] - w[0][0]) * f, w[0][1] + (w[1][1] - w[0][1]) * f];
        }
        run += l;
    }
    pts[pts.len() - 1]
}

/// shapely.ops.substring for d0 < d1: the start point, the vertices strictly between, the end point.
fn substring(pts: &[P], d0: f64, d1: f64) -> Vec<P> {
    let mut out = vec![at_dist(pts, d0)];
    let mut run = 0.0;
    for w in pts.windows(2) {
        if d0 < run && run < d1 {
            out.push(w[0]);
        } else if run >= d1 {
            break;
        }
        run += len(&w[0], &w[1]);
    }
    out.push(at_dist(pts, d1));
    out
}

/// The line offset by d (positive: to the left), with mitre joins; a join sharper than the mitre limit (5, shapely's) is bevelled.
// ponytail: no clean-up of an inner side that folds over itself (a turn tighter than the deck's width); GEOS unions it away
fn offset(pts: &[P], d: f64) -> Vec<P> {
    let mut p: Vec<P> = Vec::with_capacity(pts.len());
    for q in pts {
        if p.last().is_none_or(|l| l != q) {
            p.push(*q);
        }
    }
    if p.len() < 2 {
        return Vec::new();
    }
    let normal = |a: &P, b: &P| {
        let l = len(a, b);
        [-(b[1] - a[1]) / l, (b[0] - a[0]) / l]
    };
    let ns: Vec<P> = p.windows(2).map(|w| normal(&w[0], &w[1])).collect();
    let mut out = vec![[p[0][0] + ns[0][0] * d, p[0][1] + ns[0][1] * d]];
    for i in 1..p.len() - 1 {
        let (a, b) = (ns[i - 1], ns[i]);
        let s = [a[0] + b[0], a[1] + b[1]];
        let sl = (s[0] * s[0] + s[1] * s[1]).sqrt();
        let cos = if sl > 1e-12 { (s[0] * a[0] + s[1] * a[1]) / sl } else { 0.0 };
        if cos > 1.0 / 5.0 {
            let k = d / (cos * sl);
            out.push([p[i][0] + s[0] * k, p[i][1] + s[1] * k]);
        } else {
            out.push([p[i][0] + a[0] * d, p[i][1] + a[1] * d]);
            out.push([p[i][0] + b[0] * d, p[i][1] + b[1] * d]);
        }
    }
    let (q, n) = (p[p.len() - 1], ns[ns.len() - 1]);
    out.push([q[0] + n[0] * d, q[1] + n[1] * d]);
    out
}

/// The strip between the offsets a and b of the line (flat ends): shapely's buffer of an offset curve, with flat caps and mitre joins.
fn strip(pts: &[P], a: f64, b: f64) -> Vec<P> {
    let mut ring = offset(pts, a);
    if ring.is_empty() {
        return ring;
    }
    ring.extend(offset(pts, b).into_iter().rev());
    ring.push(ring[0]);
    ring
}

struct Rep<'a> {
    a: Node,
    z: Node,
    c: &'a [P],
    fi: usize,
}

/// _bridge_decks: the deck features of the roads (the roads source's features, in its order: a feature's index is its id).
/// `hw`: the property that has the user's `highway` column (a casing slab's `highway`).
pub fn bridge_decks(roads: &Roads, dk: &DeckLook, m: &Model, hw: &str) -> Vec<Value> {
    let mut reps: Vec<Rep> = Vec::new();
    let mut pair_edges: HashMap<((u64, u64), (u64, u64)), Vec<usize>> = HashMap::new();
    for (fi, p) in roads.iter().enumerate() {
        let Some(c) = p.line() else { continue };
        let lvl = p.get("lvl").and_then(Cell::as_f64).unwrap_or(0.0);
        if !p.get("__rs_bridge").is_some_and(py_truth) || lvl < 1.0 || c.len() < 2 {
            continue;
        }
        let [a, z] = roads.topo().ends[fi].expect("a line of two points or more").map(|n| { let q = roads.topo().points[n as usize]; (q[0], q[1]) });
        pair_edges.entry(key(a, z)).or_default().push(fi);
        if (p.get("__rs_twoway").is_some_and(py_truth) && lt((z, a), (a, z))) || p.get("__rs_dup").is_some_and(py_truth) {
            continue;
        }
        reps.push(Rep { a, z, c, fi });
    }
    let twin_of = |fi: usize, a: Node, z: Node| pair_edges.get(&key(a, z)).and_then(|v| v.iter().copied().find(|&f| f != fi));
    let n = reps.len();
    let mut used = vec![false; n];
    let mut at: HashMap<(u64, u64), Vec<usize>> = HashMap::new();
    for (i, r) in reps.iter().enumerate() {
        at.entry(hk(r.a)).or_default().push(i);
        at.entry(hk(r.z)).or_default().push(i);
    }
    // a span: (the chain's last point index of the edge, its feature, the edge with the chain's direction, its reverse twin)
    type Span = (usize, usize, Option<usize>, Option<usize>);
    let walk = |start: usize, used: &mut [bool]| -> (Vec<P>, Vec<Span>, bool, bool) {
        let r = &reps[start];
        used[start] = true;
        let mut chain: Vec<P> = r.c.to_vec();
        let mut spans: Vec<Span> = vec![(chain.len() - 1, r.fi, Some(r.fi), twin_of(r.fi, r.a, r.z))];
        let mut ends = [false, false];
        for prepend in [false, true] {
            let mut nd = if prepend { r.a } else { r.z };
            loop {
                let all = &at[&hk(nd)];
                let cand: Vec<usize> = all.iter().copied().filter(|&j| !used[j]).collect();
                if all.len() != 2 || cand.len() != 1 {
                    break;
                }
                let j = cand[0];
                let (ja, jz, jc, jfi) = (reps[j].a, reps[j].z, reps[j].c, reps[j].fi);
                let jt = twin_of(jfi, ja, jz);
                used[j] = true;
                if prepend {
                    let (fwd, rev) = if jz == nd { (Some(jfi), jt) } else { (jt, Some(jfi)) };
                    let seg: Vec<P> = if jz == nd { jc.to_vec() } else { jc.iter().rev().copied().collect() };
                    let grown = seg.len() - 1;
                    chain = seg[..seg.len() - 1].iter().copied().chain(chain).collect();
                    for s in spans.iter_mut() {
                        s.0 += grown;
                    }
                    spans.insert(0, (grown, jfi, fwd, rev));
                    nd = if jz == nd { ja } else { jz };
                } else {
                    let (fwd, rev) = if ja == nd { (Some(jfi), jt) } else { (jt, Some(jfi)) };
                    let seg: Vec<P> = if ja == nd { jc.to_vec() } else { jc.iter().rev().copied().collect() };
                    chain.extend_from_slice(&seg[1..]);
                    spans.push((chain.len() - 1, jfi, fwd, rev));
                    nd = if ja == nd { jz } else { ja };
                }
            }
            ends[prepend as usize] = at[&hk(nd)].len() == 1;
        }
        (chain, spans, ends[1], ends[0])
    };

    let mut feats = Vec::new();
    let mut chain_i = 0;
    let (base_m, thick) = (dk.base_m, dk.thickness_m);
    let (ramp, step) = (dk.ramp_m.max(1.0), dk.step_m.max(0.25));
    for i in 0..n {
        if used[i] {
            continue;
        }
        let (chain, spans, ramp_head, ramp_tail) = walk(i, &mut used);
        chain_i += 1;
        let [lon0, lat0] = chain[0];
        let kx = 111320.0 * lat0.to_radians().cos();
        let mpp = 156543.03392 * lat0.to_radians().cos() / 2f64.powf(dk.match_zoom);
        let pts: Vec<P> = chain.iter().map(|&[x, y]| [(x - lon0) * kx, (y - lat0) * 111320.0]).collect();
        let mut cum = vec![0.0];
        for k in 1..pts.len() {
            let (dx, dy) = (pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]);
            cum.push(cum[k - 1] + (dx * dx + dy * dy).sqrt());
        }
        let l = pts.windows(2).map(|w| len(&w[0], &w[1])).sum::<f64>();
        let bounds: Vec<(f64, usize, Option<usize>, Option<usize>)> = spans.iter().map(|&(e, pp, ff, rr)| (cum[e], pp, ff, rr)).collect();
        let props_at = |d: f64| {
            let b = bounds.iter().find(|b| d <= b.0 + 1e-6).unwrap_or(&bounds[bounds.len() - 1]);
            (b.1, b.2, b.3)
        };
        let rh = if ramp_head { ramp.min(l) } else { 0.0 };
        let rt = if ramp_tail { ramp.min(l - rh) } else { 0.0 };
        let mut cuts = vec![0.0, l];
        let mut d = step;
        while d < rh {
            cuts.push(d);
            d += step;
        }
        d = step;
        while d < rt {
            cuts.push(l - d);
            d += step;
        }
        cuts.extend([rh, l - rt]);
        cuts.extend(bounds.iter().map(|b| b.0).filter(|&b| rh < b && b < l - rt));
        cuts.sort_by(f64::total_cmp);
        cuts.dedup();
        for w in cuts.windows(2) {
            let (d0, d1) = (w[0], w[1]);
            if d1 <= d0 {
                continue;
            }
            let part = substring(&pts, d0, d1);
            let mid = (d0 + d1) / 2.0;
            let (pp, ffi, rfi) = props_at(mid);
            let pprops = roads.road(pp);
            let cls = pprops.get("highway").and_then(Cell::as_str).unwrap_or("");
            let px = m.gwidth(m.group_of(cls), dk.match_zoom);
            let half = (px * mpp / 2.0).max(2.0) * dk.width_scale;
            let up = if ramp_head { mid / ramp } else { 1.0 };
            let dn = if ramp_tail { (l - mid) / ramp } else { 1.0 };
            let t = up.min(dn).min(1.0);
            let t = t * t * (3.0 - 2.0 * t);
            // one ribbon per directed edge: a two-way bridge is two half-width ribbons side by side (the edge with the chain on the right)
            let mut ribbons: Vec<(Vec<P>, Option<usize>)> = Vec::new();
            if pprops.get("__rs_twoway").is_some_and(py_truth) && ffi.is_some() && rfi.is_some() {
                for (dlt, fdir) in [(-1.0, ffi), (1.0, rfi)] {
                    ribbons.push((strip(&part, 0.0, dlt * half), fdir));
                }
            } else {
                ribbons.push((strip(&part, half, -half), ffi.or(rfi)));
            }
            let to_lonlat = |r: &[P]| -> Value {
                json!(r.iter().map(|&[x, y]| [py_round(x / kx + lon0, 6), py_round(y / 111320.0 + lat0, 6)]).collect::<Vec<_>>())
            };
            for (ring, fdir) in &ribbons {
                if ring.len() < 4 {
                    continue;
                }
                let mut props: Map<String, Value> = match fdir { Some(f) => roads.road(*f).to_map(), None => pprops.to_map() };
                props.shift_remove("__rs_cls");          // Python marks the class (_mark_cls) after it makes the decks
                props.insert("__rs_base".into(), json!(py_round(base_m * t, 2)));
                props.insert("__rs_height".into(), json!(py_round(base_m * t + thick, 2)));
                props.insert("__rs_chain".into(), json!(chain_i));
                props.insert("__rs_edges".into(), json!(fdir.iter().collect::<Vec<_>>()));
                feats.push(json!({"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [to_lonlat(ring)]}}));
            }
            // the casing: a strip along each long side of the deck, up to just under the deck's top (an extrusion has no outline)
            if dk.casing_px != 0.0 {
                let cw = dk.casing_px * mpp;
                let mut edges: Vec<usize> = ribbons.iter().filter_map(|r| r.1).collect();
                edges.sort();
                edges.dedup();
                for sgn in [1.0, -1.0] {
                    let ring = strip(&part, sgn * half, sgn * (half + cw));
                    if ring.len() < 4 {
                        continue;
                    }
                    feats.push(json!({"type": "Feature", "properties": {
                        "highway": pprops.get(hw).map_or(Value::Null, Cell::to_value), "__rs_chain": chain_i, "__rs_casing_slab": 1,
                        "__rs_edges": edges, "__rs_base": py_round((base_m * t - 0.5).max(0.0), 2),
                        "__rs_height": py_round(base_m * t + thick * 0.35, 2)},
                        "geometry": {"type": "Polygon", "coordinates": [to_lonlat(&ring)]}}));
                }
            }
        }
    }
    feats
}
