//! The slots of one group: where its chains are free of crossing roads, how they divide into slots, and each slot's feature.

use super::chain::chains;
use super::geom::{bbox, floor_divmod, point_line_dist, project, seg_meet};
use super::{Group, Rep};
use crate::road::Roads;
use crate::simple::{Line, Pt, KY};
use roadstyle_model::mark::Mark;
use roadstyle_model::{Cell, Role};
use rstar::{primitives::GeomWithData, primitives::Rectangle, RTree, AABB};
use serde_json::{json, Map, Value};
use std::collections::HashSet;

const NAME_MARGIN_M: f64 = 2.0; // a name or an arrow stays this far beyond a crossing road's drawn half-width
const ZEBRA_HALF_M: f64 = 2.0; // ... and at least this far from a footway, path, cycleway or steps
const ARROW_MIN_M: f64 = 8.0; // a one-way stretch too short for a name slot still gets an arrow slot from this length

type Boxes = RTree<GeomWithData<Rectangle<[f64; 2]>, usize>>;

/// A box tree of lines, in the order of `lines`.
fn box_tree<'a>(lines: impl Iterator<Item = &'a [Pt]>) -> Boxes {
    RTree::bulk_load(lines.enumerate().map(|(g, c)| { let (lo, hi) = bbox(c); GeomWithData::new(Rectangle::from_corners(lo, hi), g) }).collect())
}

/// The slot features of a group (the group's `edges` are its representatives).
pub(super) fn group_slots(roads: &Roads, look: &super::SlotLook, g: &Group, reps: &[Rep]) -> Vec<Value> {
    let edges: Vec<&Rep> = g.reps.iter().map(|&r| &reps[r]).collect();
    let hw = main_class(roads, &edges);
    let rank = hw.as_str().and_then(|h| look.z_order.get(h)).cloned().unwrap_or(json!(0));
    let near = Near { edges: &edges, tree: (edges.len() > 32).then(|| box_tree(edges.iter().map(|e| e.c.as_slice()))) };
    let mut feats = Vec::new();
    for (chain, members) in chains(&edges, g.oneway) {
        let cid = 1 + members.iter().map(|&e| edges[e].owner.0).min().unwrap();
        let line = Line::new(&chain);
        let free = free_stretches(roads, look, &edges, (&chain, &members), &line);
        for (i, a, b) in slot_ranges(&free, look.slot_m, g.oneway) {
            let (road, twin) = near.owner(&members, &line, a, b);
            let p = slot_props(g, &hw, &rank, (cid, i), (road, twin));
            let geometry = crate::obj([("type", "LineString".into()), ("coordinates", json!(line.lonlat(&line.part(a, b), 1e6)))]);
            feats.push(crate::obj([("type", "Feature".into()), ("properties", Value::Object(p)), ("geometry", geometry)]));
        }
    }
    feats
}

/// The properties of one slot `i` of chain `cid`, on the road `road` (and its twin).
fn slot_props(g: &Group, hw: &Value, rank: &Value, (cid, i): (usize, i64), (road, twin): (usize, Option<usize>)) -> Map<String, Value> {
    let mut p = Map::new();
    p.insert("slot".into(), i.into());
    p.insert("chain".into(), cid.into());
    p.insert("rank".into(), rank.clone());
    p.insert("name".into(), g.name.clone().map_or(Value::Null, Value::from));
    p.insert("highway".into(), hw.clone());
    p.insert("oneway".into(), (g.oneway as u8).into());
    p.insert("lvl".into(), g.lvl.clone());
    p.insert(Mark::Edge.name().into(), crate::road::key(road).get().into());
    if let Some(t) = twin {
        p.insert(Mark::Edge2.name().into(), crate::road::key(t).get().into());
    }
    if !g.fl.is_null() {
        p.insert("fl".into(), g.fl.clone());
    }
    if g.tun {
        p.insert(Mark::Tunnel.name().into(), true.into());
    }
    p
}

/// The group's class: the most common (the first of equal counts).
fn main_class(roads: &Roads, edges: &[&Rep]) -> Value {
    let mut count: indexmap::IndexMap<String, (usize, Value)> = indexmap::IndexMap::new();
    for e in edges {
        let v = roads.role(e.p, Role::Class).map_or(Value::Null, Cell::to_value);
        count.entry(v.to_string()).or_insert((0, v)).0 += 1;
    }
    let mut best = (0, Value::Null);
    for (k, v) in count.into_values() {
        if k > best.0 {
            best = (k, v);
        }
    }
    best.1
}

/// The roads of a group, with a box tree when the group is big.
struct Near<'a> {
    edges: &'a [&'a Rep],
    tree: Option<Boxes>,
}

impl Near<'_> {
    /// The owner of the slot from `a` to `b` of `line`: the nearest road of the group (the first of equal distances). A big group looks
    /// only at the roads whose box is as near as the nearest road of this chain.
    fn owner(&self, members: &[usize], line: &Line, a: f64, b: f64) -> (usize, Option<usize>) {
        if self.edges.len() == 1 {
            return self.edges[0].owner;
        }
        let m = line.at((a + b) / 2.0);
        let pt = [m[0] / line.kx + line.lon0, m[1] / KY + line.lat0];
        let mut best = (f64::INFINITY, 0);
        let try_road = |g: usize, best: &mut (f64, usize)| {
            let d = point_line_dist(pt, &self.edges[g].c);
            if d < best.0 || (d == best.0 && g < best.1) {
                *best = (d, g);
            }
        };
        match &self.tree {
            Some(t) => {
                members.iter().for_each(|&g| try_road(g, &mut best));
                let r = best.0;
                for h in t.locate_in_envelope_intersecting(&AABB::from_corners([pt[0] - r, pt[1] - r], [pt[0] + r, pt[1] + r])) {
                    try_road(h.data, &mut best);
                }
            }
            None => (0..self.edges.len()).for_each(|g| try_road(g, &mut best)),
        }
        self.edges[best.1].owner
    }
}

/// _crossing_half_m: half the class's drawn width at zoom 20 in metres at `lat` (a path class: at least a zebra's half-width), plus the margin.
fn crossing_half_m(look: &super::SlotLook, cls: Option<&str>, lat: f64) -> f64 {
    let px = cls.and_then(|c| look.width_z20.get(c)).copied().unwrap_or(look.width_fallback);
    let half = 0.5 * px * 40075016.686 * lat.to_radians().cos() / (512.0 * 2f64.powi(20));
    let path = matches!(cls, Some("footway" | "path" | "cycleway" | "steps"));
    (if path { half.max(ZEBRA_HALF_M) } else { half }) + NAME_MARGIN_M
}

/// The stretches (from, to; in metres along the chain) that no other road crosses.
fn free_stretches(roads: &Roads, look: &super::SlotLook, edges: &[&Rep], (chain, members): (&[Pt], &[usize]), line: &Line) -> Vec<(f64, f64)> {
    let mut cuts = crossing_cuts(roads, look, edges, (chain, members), line);
    cuts.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let mut free = Vec::new();
    let mut at = 0.0f64;
    for (lo, hi) in cuts {
        if lo > at {
            free.push((at, lo));
        }
        at = at.max(hi);
    }
    if at < line.len() {
        free.push((at, line.len()));
    }
    free
}

/// The crossings: every other road that meets or crosses the chain takes half its width plus a margin out of it.
fn crossing_cuts(roads: &Roads, look: &super::SlotLook, edges: &[&Rep], (chain, members): (&[Pt], &[usize]), line: &Line) -> Vec<(f64, f64)> {
    let bits = |c: &[Pt]| c.iter().map(|p| (p[0].to_bits(), p[1].to_bits())).collect::<Vec<_>>();
    let mine: HashSet<usize> = members.iter().flat_map(|&e| [Some(edges[e].owner.0), edges[e].owner.1]).flatten().collect();
    let back: HashSet<Vec<(u64, u64)>> = members.iter().map(|&e| bits(&edges[e].c.iter().rev().copied().collect::<Vec<_>>())).collect();
    let (lo, hi) = bbox(chain);
    let mut cuts = Vec::new();
    // a long chain: an R-tree of its segments, else every road in its box is checked against all of them (Tartu: 2 s)
    let segs = (chain.len() > 16).then(|| box_tree(chain.windows(2)));
    for k in roads.topo().near(lo, hi) {
        let kc = roads.line(k).unwrap();
        if mine.contains(&k) || back.contains(&bits(kc)) {
            continue;
        }
        let half = crossing_half_m(look, roads.role(k, Role::Class).and_then(Cell::as_str), line.lat0);
        let mut meet = |w: &[Pt], v: &[Pt]| {
            let pts = seg_meet(w[0], w[1], v[0], v[1]);
            if !pts.is_empty() {
                let d: Vec<f64> = pts.iter().map(|p| project(&line.xy, [(p[0] - line.lon0) * line.kx, (p[1] - line.lat0) * KY])).collect();
                cuts.push((d.iter().copied().fold(f64::INFINITY, f64::min) - half, d.iter().copied().fold(f64::NEG_INFINITY, f64::max) + half));
            }
        };
        for v in kc.windows(2) {
            match &segs {
                // only the chain's segments whose box meets this segment's box can meet it (the cuts are sorted by the caller)
                Some(t) => {
                    let (lo, hi) = bbox(v);
                    for h in t.locate_in_envelope_intersecting(&AABB::from_corners(lo, hi)) {
                        meet(&chain[h.data..h.data + 2], v);
                    }
                }
                None => chain.windows(2).for_each(|w| meet(w, v)),
            }
        }
    }
    cuts
}

/// Each free stretch divided into slots on its own, starting with a name slot (an even number): the slots' numbers and their
/// ends (metres along the chain).
fn slot_ranges(free: &[(f64, f64)], slot_m: f64, oneway: bool) -> Vec<(i64, f64, f64)> {
    let mut out = Vec::new();
    let mut nxt: i64 = 0;
    for &(lo, hi) in free {
        nxt += nxt % 2;
        let length = hi - lo;
        let (q, r) = floor_divmod(length, slot_m);
        let pieces = (q as i64 + if r > slot_m * 0.3 { 1 } else { 0 }).max(1);
        for j in 0..pieces {
            let (a, b) = (lo + j as f64 * slot_m, lo + ((j + 1) as f64 * slot_m).min(length));
            if b - a < slot_m * 0.2 {
                if !(oneway && b - a >= ARROW_MIN_M) {
                    continue;
                }
                nxt += 1 - nxt % 2; // too short for a name, long enough for an arrow: an odd slot
            }
            out.push((nxt, a, b));
            nxt += 1;
        }
    }
    out
}
