//! the bridges as ramped deck ribbons for the 3D view (the fill-extrusion source `decks`). The ribbons are made
//! with shapely (GEOS buffers and offset curves); this module makes the same strips with its own mitre offsets, so a polygon can have
//! other vertices than GEOS gives, but it covers the same ground (tests/test_engine_parity.py compares them by shape).

use roadstyle_model::mark::Mark;
use crate::layers::{round_to, Model};
use crate::road::Roads;
use roadstyle_model::Cell;
use serde_json::{json, Map, Value};
use std::collections::HashMap;

type P = [f64; 2];
type Node = (f64, f64);

/// The look values of the 3D bridge decks (roadstyle-look: config bridge_decks).
pub use roadstyle_look::DeckLook;

/// A node as a hash key (the rounded floats' bits: round_to gives no -0.0).
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

/// A part of a chain: the chain's last point index of the road, its feature, the road with the chain's direction, its reverse twin.
#[derive(Clone, Copy)]
struct Span {
    end: usize,
    fi: usize,
    fwd: Option<usize>,
    rev: Option<usize>,
}

/// A chain of bridge roads through nodes of degree 2: its line, its spans, and whether each end is a free end (a ramp there).
struct Chain {
    pts: Vec<P>,
    spans: Vec<Span>,
    ramp_head: bool,
    ramp_tail: bool,
}

/// The bridge roads: one representative for each two-way pair, and where each node is used.
struct Bridges<'a> {
    reps: Vec<Rep<'a>>,
    pair_edges: HashMap<((u64, u64), (u64, u64)), Vec<usize>>,
    at: HashMap<(u64, u64), Vec<usize>>,
}

impl<'a> Bridges<'a> {
    fn new(roads: &'a Roads) -> Self {
        let mut reps: Vec<Rep> = Vec::new();
        let mut pair_edges: HashMap<((u64, u64), (u64, u64)), Vec<usize>> = HashMap::new();
        for (fi, p) in roads.iter().enumerate() {
            let Some(c) = p.line() else { continue };
            let lvl = p.get("lvl").and_then(Cell::as_f64).unwrap_or(0.0);
            if !p.get(Mark::Bridge.name()).is_some_and(crate::roads::yes) || lvl < 1.0 || c.len() < 2 {
                continue;
            }
            let [a, z] = roads.topo().ends[fi].expect("a line of two points or more").map(|n| { let q = roads.topo().points[n as usize]; (q[0], q[1]) });
            pair_edges.entry(key(a, z)).or_default().push(fi);
            if (p.get(Mark::Twoway.name()).is_some_and(crate::roads::yes) && lt((z, a), (a, z))) || p.get(Mark::Dup.name()).is_some_and(crate::roads::yes) {
                continue;
            }
            reps.push(Rep { a, z, c, fi });
        }
        let mut at: HashMap<(u64, u64), Vec<usize>> = HashMap::new();
        for (i, r) in reps.iter().enumerate() {
            at.entry(hk(r.a)).or_default().push(i);
            at.entry(hk(r.z)).or_default().push(i);
        }
        Bridges { reps, pair_edges, at }
    }

    fn twin_of(&self, fi: usize, a: Node, z: Node) -> Option<usize> {
        self.pair_edges.get(&key(a, z)).and_then(|v| v.iter().copied().find(|&f| f != fi))
    }

    /// The chain that has the road `start`; its roads are `used` after it.
    fn walk(&self, start: usize, used: &mut [bool]) -> Chain {
        let r = &self.reps[start];
        used[start] = true;
        let mut pts: Vec<P> = r.c.to_vec();
        let mut spans = vec![Span { end: pts.len() - 1, fi: r.fi, fwd: Some(r.fi), rev: self.twin_of(r.fi, r.a, r.z) }];
        let mut ends = [false, false];
        for prepend in [false, true] {
            let mut nd = if prepend { r.a } else { r.z };
            loop {
                let all = &self.at[&hk(nd)];
                let cand: Vec<usize> = all.iter().copied().filter(|&j| !used[j]).collect();
                if all.len() != 2 || cand.len() != 1 {
                    break;
                }
                let j = &self.reps[cand[0]];
                used[cand[0]] = true;
                let jt = self.twin_of(j.fi, j.a, j.z);
                // the road runs along the chain when it starts (appending) or ends (prepending) at the node
                let (near, far) = if prepend { (j.z, j.a) } else { (j.a, j.z) };
                let along = near == nd;
                let (fwd, rev) = if along { (Some(j.fi), jt) } else { (jt, Some(j.fi)) };
                let seg: Vec<P> = if along { j.c.to_vec() } else { j.c.iter().rev().copied().collect() };
                if prepend {
                    let grown = seg.len() - 1;
                    pts.splice(0..0, seg[..grown].iter().copied());
                    spans.iter_mut().for_each(|s| s.end += grown);
                    spans.insert(0, Span { end: grown, fi: j.fi, fwd, rev });
                } else {
                    pts.extend_from_slice(&seg[1..]);
                    spans.push(Span { end: pts.len() - 1, fi: j.fi, fwd, rev });
                }
                nd = if along { far } else { near };
            }
            ends[prepend as usize] = self.at[&hk(nd)].len() == 1;
        }
        Chain { pts, spans, ramp_head: ends[1], ramp_tail: ends[0] }
    }
}

/// _bridge_decks: the deck features of the roads (the roads source's features, in its order: a feature's index is its id).
/// `hw`: the property that has the user's `highway` column (a casing slab's `highway`).
pub fn bridge_decks(roads: &Roads, dk: &DeckLook, m: &Model, hw: &str) -> Vec<Value> {
    let bridges = Bridges::new(roads);
    let mut used = vec![false; bridges.reps.len()];
    let mut feats = Vec::new();
    let mut chain_i = 0;
    for i in 0..used.len() {
        if !used[i] {
            chain_i += 1;
            feats.extend(chain_features(roads, dk, m, hw, &bridges.walk(i, &mut used), chain_i));
        }
    }
    feats
}

/// A chain in metres around its first point (lon0, lat0), and the metres of a pixel at the deck look's zoom.
struct Frame {
    lon0: f64,
    lat0: f64,
    kx: f64,
    mpp: f64,
}

impl Frame {
    fn to_lonlat(&self, r: &[P]) -> Value {
        json!(r.iter().map(|&[x, y]| [round_to(x / self.kx + self.lon0, 6), round_to(y / 111320.0 + self.lat0, 6)]).collect::<Vec<_>>())
    }
}

/// The cut points along a chain of length `l` (metres): its ends, a step along each ramp, the ramps' ends and the spans' ends between them.
fn cuts_of(l: f64, (rh, rt): (f64, f64), step: f64, span_ends: impl Iterator<Item = f64>) -> Vec<f64> {
    let mut cuts = vec![0.0, l, rh, l - rt];
    cuts.extend(std::iter::successors(Some(step), |d| Some(d + step)).take_while(|&d| d < rh));
    cuts.extend(std::iter::successors(Some(step), |d| Some(d + step)).take_while(|&d| d < rt).map(|d| l - d));
    cuts.extend(span_ends.filter(|&b| rh < b && b < l - rt));
    cuts.sort_by(f64::total_cmp);
    cuts.dedup();
    cuts
}

/// The features of one chain: its deck pieces (cut where the ramps and the roads change) and their casing slabs.
fn chain_features(roads: &Roads, dk: &DeckLook, m: &Model, hw: &str, ch: &Chain, chain_i: usize) -> Vec<Value> {
    let [lon0, lat0] = ch.pts[0];
    let cos = lat0.to_radians().cos();
    let frame = Frame { lon0, lat0, kx: 111320.0 * cos, mpp: 156543.03392 * cos / 2f64.powf(dk.match_zoom) };
    let pts: Vec<P> = ch.pts.iter().map(|&[x, y]| [(x - lon0) * frame.kx, (y - lat0) * 111320.0]).collect();
    let mut cum = vec![0.0];
    for k in 1..pts.len() {
        let (dx, dy) = (pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]);
        cum.push(cum[k - 1] + (dx * dx + dy * dy).sqrt());
    }
    let l = pts.windows(2).map(|w| len(&w[0], &w[1])).sum::<f64>();
    let bounds: Vec<(f64, Span)> = ch.spans.iter().map(|s| (cum[s.end], *s)).collect();
    let (ramp, step) = (dk.ramp_m.max(1.0), dk.step_m.max(0.25));
    let rh = if ch.ramp_head { ramp.min(l) } else { 0.0 };
    let rt = if ch.ramp_tail { ramp.min(l - rh) } else { 0.0 };
    let mut feats = Vec::new();
    for w in cuts_of(l, (rh, rt), step, bounds.iter().map(|b| b.0)).windows(2) {
        let (d0, d1) = (w[0], w[1]);
        if d1 <= d0 {
            continue;
        }
        let mid = (d0 + d1) / 2.0;
        let span = bounds.iter().find(|b| mid <= b.0 + 1e-6).unwrap_or(&bounds[bounds.len() - 1]).1;
        let pprops = roads.road(span.fi);
        let cls = pprops.role(roadstyle_model::Role::Class).and_then(Cell::as_str).unwrap_or("");
        let half = (m.gwidth(m.group_of(cls), dk.match_zoom) * frame.mpp / 2.0).max(2.0) * dk.width_scale;
        let up = if ch.ramp_head { mid / ramp } else { 1.0 };
        let dn = if ch.ramp_tail { (l - mid) / ramp } else { 1.0 };
        let t = up.min(dn).min(1.0);
        let lift = t * t * (3.0 - 2.0 * t);
        let part = substring(&pts, d0, d1);
        // one ribbon per directed edge: a two-way bridge is two half-width ribbons side by side (the edge with the chain on the right)
        let ribbons: Vec<(Vec<P>, Option<usize>)> = if pprops.get(Mark::Twoway.name()).is_some_and(crate::roads::yes) && span.fwd.is_some() && span.rev.is_some() {
            [(-1.0, span.fwd), (1.0, span.rev)].into_iter().map(|(dlt, fdir)| (strip(&part, 0.0, dlt * half), fdir)).collect()
        } else {
            vec![(strip(&part, half, -half), span.fwd.or(span.rev))]
        };
        for (ring, fdir) in ribbons.iter().filter(|r| r.0.len() >= 4) {
            let mut props: Map<String, Value> = match fdir { Some(f) => roads.road(*f).to_map(), None => pprops.to_map() };
            props.shift_remove(Mark::Class.name());          // the class mark is put after the decks are made
            props.insert(Mark::DeckBase.name().into(), json!(round_to(dk.base_m * lift, 2)));
            props.insert(Mark::DeckHeight.name().into(), json!(round_to(dk.base_m * lift + dk.thickness_m, 2)));
            props.insert(Mark::DeckChain.name().into(), json!(chain_i));
            props.insert(Mark::Edges.name().into(), json!(fdir.iter().map(|&r| crate::road::key(r).get()).collect::<Vec<_>>()));
            feats.push(json!({"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [frame.to_lonlat(ring)]}}));
        }
        if dk.casing_px != 0.0 {
            let mut edges: Vec<usize> = ribbons.iter().filter_map(|r| r.1).collect();
            edges.sort();
            edges.dedup();
            let highway = pprops.get(hw).map_or(Value::Null, Cell::to_value);
            feats.extend(casing_slabs(dk, &frame, &part, half, lift, (chain_i, &edges, highway)));
        }
    }
    feats
}

/// The casing: a strip along each long side of the deck, up to just under the deck's top (an extrusion has no outline).
fn casing_slabs(dk: &DeckLook, frame: &Frame, part: &[P], half: f64, lift: f64, (chain_i, edges, highway): (usize, &[usize], Value)) -> Vec<Value> {
    let cw = dk.casing_px * frame.mpp;
    [1.0, -1.0].into_iter().filter_map(|sgn| {
        let ring = strip(part, sgn * half, sgn * (half + cw));
        (ring.len() >= 4).then(|| json!({"type": "Feature", "properties": {
            "highway": highway, Mark::DeckChain.name(): chain_i, Mark::CasingSlab.name(): 1,
            Mark::Edges.name(): edges.iter().map(|&r| crate::road::key(r).get()).collect::<Vec<_>>(), Mark::DeckBase.name(): round_to((dk.base_m * lift - 0.5).max(0.0), 2),
            Mark::DeckHeight.name(): round_to(dk.base_m * lift + dk.thickness_m * 0.35, 2)},
            "geometry": {"type": "Polygon", "coordinates": [frame.to_lonlat(&ring)]}}))
    }).collect()
}
