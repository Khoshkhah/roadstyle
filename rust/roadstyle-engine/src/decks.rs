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

/// The group of each of `n` reps (numbered from 1 in the order of the first rep): the reps that share a node are one group (union-find).
fn groups_of(n: usize, at: &HashMap<(u64, u64), Vec<usize>>) -> Vec<usize> {
    fn find(p: &mut [usize], mut i: usize) -> usize {
        while p[i] != i {
            p[i] = p[p[i]];
            i = p[i];
        }
        i
    }
    let mut parent: Vec<usize> = (0..n).collect();
    for reps in at.values() {
        for w in reps.windows(2) {
            let (a, b) = (find(&mut parent, w[0]), find(&mut parent, w[1]));
            parent[a.max(b)] = a.min(b);
        }
    }
    let mut number: HashMap<usize, usize> = HashMap::new();
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        let root = find(&mut parent, i);
        let next = number.len() + 1;
        out.push(*number.entry(root).or_insert(next));
    }
    out
}

/// A chain of bridge roads through nodes of degree 2: its line, its spans, its group and its two end nodes (the node's height is the group's, `Bridges::dfree`).
struct Chain {
    group: usize,
    pts: Vec<P>,
    spans: Vec<Span>,
    head: (u64, u64),
    tail: (u64, u64),
}

/// A distance in a priority queue (the smallest first).
#[derive(PartialEq, PartialOrd)]
struct Dist(f64);
impl Eq for Dist {}
impl Ord for Dist {
    fn cmp(&self, o: &Self) -> std::cmp::Ordering {
        o.0.total_cmp(&self.0)
    }
}

/// The distance in metres from each node of the bridge roads to the nearest free end (a node that only one road uses), along the roads. A node with no free
/// end in its group has none. The height of a node comes from it: 0 at a free end, rising at one grade to the group's height, so two chains that meet at a
/// node have one height there.
fn free_end_distances(reps: &[Rep], lens: &[f64], at: &HashMap<(u64, u64), Vec<usize>>) -> HashMap<(u64, u64), f64> {
    let mut best: HashMap<(u64, u64), f64> = HashMap::new();
    let mut heap = std::collections::BinaryHeap::new();
    for (nd, v) in at {
        if v.len() == 1 {
            best.insert(*nd, 0.0);
            heap.push((Dist(0.0), *nd));
        }
    }
    while let Some((Dist(d), nd)) = heap.pop() {
        if best.get(&nd).is_some_and(|&b| d > b) {
            continue;
        }
        for &i in &at[&nd] {
            let other = if hk(reps[i].a) == nd { hk(reps[i].z) } else { hk(reps[i].a) };
            let nd2 = d + lens[i];
            if best.get(&other).is_none_or(|&b| nd2 < b) {
                best.insert(other, nd2);
                heap.push((Dist(nd2), other));
            }
        }
    }
    best
}

/// The smaller of a and b, rounded where they are within k of each other (at most k / 4 lower), by `weight` (0: the exact minimum). The ramp's apex
/// (where the two ramps of a short bridge meet) is rounded so it has no ridge; at the ends of a chain the weight is 0, so the height at a node is exactly the node's.
fn smin(a: f64, b: f64, k: f64, weight: f64) -> f64 {
    let h = (k - (a - b).abs()).max(0.0) / k;
    a.min(b) - weight * h * h * k * 0.25
}

/// The bridge roads: one representative for each two-way pair, and where each node is used.
struct Bridges<'a> {
    reps: Vec<Rep<'a>>,
    /// the group of each rep (from 1): reps that touch through a shared node are one group, whatever their level
    group: Vec<usize>,
    /// the length in metres of each group (index: group - 1): the sum of its roads, one for each two-way pair
    group_len: Vec<f64>,
    /// the distance in metres from each node to the nearest free end of its group (`free_end_distances`)
    dfree: HashMap<(u64, u64), f64>,
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
        let group = groups_of(reps.len(), &at);
        let lens: Vec<f64> = reps.iter().map(|r| {
            let kx = 111320.0 * r.c[0][1].to_radians().cos();
            r.c.windows(2).map(|w| ((w[1][0] - w[0][0]) * kx).hypot((w[1][1] - w[0][1]) * 111320.0)).sum::<f64>()
        }).collect();
        let mut group_len = vec![0.0; group.iter().copied().max().unwrap_or(0)];
        for (l, g) in lens.iter().zip(&group) {
            group_len[g - 1] += l;
        }
        let dfree = free_end_distances(&reps, &lens, &at);
        Bridges { reps, group, group_len, dfree, pair_edges, at }
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
        let mut nodes = [hk(r.z), hk(r.a)];          // the chain's end nodes: [tail, head]
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
            nodes[prepend as usize] = hk(nd);
        }
        Chain { group: self.group[start], pts, spans, head: nodes[1], tail: nodes[0] }
    }
}

/// The heights that a caller gives (`bridge_heights`: road id as text -> metres, by the edge id column `key`): for each group of bridges (index: group - 1) the height of
/// the whole group. The id of any road of the group names it, as a two-way pair's either edge; two heights for one group, a height that is not a number of 0 or more, an id
/// that no road has, and a missing column are errors; an id of a road that is not a 3D bridge gets a warning (its height does nothing).
fn own_heights(roads: &Roads, b: &Bridges, heights: &std::collections::BTreeMap<String, f64>, key: &str, warnings: &mut Vec<String>) -> Result<Vec<Option<f64>>, crate::Error> {
    use crate::colors::category_text;
    if roads.at(0).is_some_and(|f| f.get(key).is_none()) {
        return Err(crate::error::column(key, "bridge_heights names its ids by it, and the roads do not have it"));
    }
    if let Some((id, h)) = heights.iter().find(|(_, h)| !h.is_finite() || **h < 0.0) {
        return Err(crate::error::Error::Options(format!("bridge_heights: the height of {id:?} is {h}; a height is a number of metres, 0 or more")));
    }
    let mut group_of_edge: HashMap<usize, usize> = HashMap::new();
    for (i, r) in b.reps.iter().enumerate() {
        for &fi in b.pair_edges.get(&self::key(r.a, r.z)).into_iter().flatten() {
            group_of_edge.insert(fi, b.group[i]);
        }
    }
    let mut own: Vec<Option<(f64, String)>> = vec![None; b.group_len.len()];
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    for fi in 0..roads.len() {
        let id = roads.get(fi, key).map(category_text).unwrap_or_else(|| "None".into());
        let Some(&h) = heights.get(&id) else { continue };
        seen.insert(id.clone());
        let Some(&g) = group_of_edge.get(&fi) else {
            warnings.push(format!("bridge_heights: the road {id} is not a 3D bridge (a bridge with a level of 1 or more), so its height does nothing"));
            continue;
        };
        match &own[g - 1] {
            Some((h0, id0)) if (h0 - h).abs() > 1e-9 => {
                return Err(crate::Error::Data(format!("bridge_heights: the roads {id0} and {id} touch each other (one group of bridges), and they have two heights, {h0} m and {h} m; a group has one height")));
            }
            Some(_) => {}
            None => own[g - 1] = Some((h, id)),
        }
    }
    if let Some(id) = heights.keys().find(|k| !seen.contains(*k)) {
        return Err(crate::Error::Data(format!("bridge_heights: no road has the {key} {id}")));
    }
    Ok(own.into_iter().map(|o| o.map(|(h, _)| h)).collect())
}

/// _bridge_decks: the deck features of the roads (the roads source's features, in its order: a feature's index is its id).
/// `hw`: the property that has the user's `highway` column (a casing slab's `highway`). `own`: the heights that the caller gave (`bridge_heights` and the edge id column).
pub fn bridge_decks(roads: &Roads, dk: &DeckLook, m: &Model, hw: &str, own: Option<(&std::collections::BTreeMap<String, f64>, &str)>, warnings: &mut Vec<String>) -> Result<Vec<Value>, crate::Error> {
    let bridges = Bridges::new(roads);
    let given = match own {
        Some((heights, key)) => own_heights(roads, &bridges, heights, key, warnings)?,
        None => Vec::new(),
    };
    let mut used = vec![false; bridges.reps.len()];
    let mut feats = Vec::new();
    let mut chain_i = 0;
    for i in 0..used.len() {
        if !used[i] {
            chain_i += 1;
            let ch = bridges.walk(i, &mut used);
            let h = given.get(ch.group - 1).copied().flatten().unwrap_or_else(|| deck_height(dk, bridges.group_len[ch.group - 1]));
            let far = |nd: &(u64, u64)| bridges.dfree.get(nd).copied().unwrap_or(f64::INFINITY);
            feats.extend(chain_features(roads, dk, m, hw, &ch, chain_i, (h, far(&ch.head), far(&ch.tail))));
        }
    }
    Ok(feats)
}

/// The full height of a bridge group of `len` metres: `base_m` for a short one, `max_m` for a long one, a line between (a long bridge crosses
/// something wide, so it stands higher; the ramps then grow with the height, which keeps the grade of `ramp_m` over `base_m`).
fn deck_height(dk: &DeckLook, len: f64) -> f64 {
    if dk.grow_to_m <= dk.grow_from_m {
        return dk.base_m;
    }
    dk.base_m + (dk.max_m - dk.base_m).max(0.0) * ((len - dk.grow_from_m) / (dk.grow_to_m - dk.grow_from_m)).clamp(0.0, 1.0)
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
fn chain_features(roads: &Roads, dk: &DeckLook, m: &Model, hw: &str, ch: &Chain, chain_i: usize, (h, far_head, far_tail): (f64, f64, f64)) -> Vec<Value> {
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
    // THE HEIGHT OF A NODE: 0 at a free end, rising at one grade (`ramp_m` over `base_m`) with the distance to the nearest free end, up to the group's height `h`.
    // A chain draws between the heights of its two end nodes, so the chains that meet at a node have one height there, and a short bridge rises only as far
    // as the grade lets it (no wall on a bridge of a few metres).
    let grade = if dk.base_m > 0.0 { dk.ramp_m / dk.base_m } else { 8.0 };       // metres of ramp for a metre of height
    let (full_ramp, step) = ((h * grade).max(1.0), dk.step_m.max(0.25));         // metres that a rise of the full height takes
    let (la, lb) = ((far_head / full_ramp).min(1.0), (far_tail / full_ramp).min(1.0));
    let (rh, rt) = ((full_ramp * (1.0 - la)).min(l), (full_ramp * (1.0 - lb)).min(l));
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
        // the smooth lift (0 on the ground, 1 at the full height) at a distance along the chain: from each end node
        let edge = (0.15 * l).max(1.0);                    // the rounding fades out over the last 15 % of a chain at each end
        let lift_at = |d: f64| {
            let w = (d / edge).clamp(0.0, 1.0).min(((l - d) / edge).clamp(0.0, 1.0));
            let t = smin(la + d / full_ramp, lb + (l - d) / full_ramp, 0.4, w * w * (3.0 - 2.0 * w)).clamp(0.0, 1.0);
            t * t * (3.0 - 2.0 * t)
        };
        let (lift, ends) = (lift_at(mid), [lift_at(d0), lift_at(d1)]);
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
            props.insert(Mark::DeckBase.name().into(), json!(round_to(h * lift, 2)));
            props.insert(Mark::DeckHeight.name().into(), json!(round_to(h * lift + dk.thickness_m, 2)));
            props.insert(Mark::DeckChain.name().into(), json!(chain_i));
            props.insert(Mark::DeckGroup.name().into(), json!(ch.group));
            props.insert(Mark::DeckFull.name().into(), json!(h));
            props.insert(Mark::DeckThick.name().into(), json!(dk.thickness_m));
            props.insert(Mark::DeckLift0.name().into(), json!(round_to(ends[0], 4)));
            props.insert(Mark::DeckLift1.name().into(), json!(round_to(ends[1], 4)));
            props.insert(Mark::DeckS0.name().into(), json!(round_to(d0 / l, 5)));
            props.insert(Mark::DeckS1.name().into(), json!(round_to(d1 / l, 5)));
            // the chain's end nodes (on its first and last piece): the page reads the ground height at them, so chains that meet at a node agree
            if d0 <= 1e-9 {
                props.insert(Mark::DeckEndA.name().into(), json!([round_to(ch.pts[0][0], 7), round_to(ch.pts[0][1], 7)]));
            }
            if d1 >= l - 1e-9 {
                let z = ch.pts[ch.pts.len() - 1];
                props.insert(Mark::DeckEndB.name().into(), json!([round_to(z[0], 7), round_to(z[1], 7)]));
            }
            props.insert(Mark::Edges.name().into(), json!(fdir.iter().map(|&r| crate::road::key(r).get()).collect::<Vec<_>>()));
            feats.push(json!({"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [frame.to_lonlat(ring)]}}));
        }
        if dk.casing_px != 0.0 {
            let mut edges: Vec<usize> = ribbons.iter().filter_map(|r| r.1).collect();
            edges.sort();
            edges.dedup();
            let highway = pprops.get(hw).map_or(Value::Null, Cell::to_value);
            let mut slabs = casing_slabs(dk, &frame, &part, (half, h, lift), (chain_i, &edges, highway));
            for f in &mut slabs {
                f["properties"][Mark::DeckGroup.name()] = json!(ch.group);
                f["properties"][Mark::DeckFull.name()] = json!(h);
                f["properties"][Mark::DeckThick.name()] = json!(dk.thickness_m);
                f["properties"][Mark::DeckLift0.name()] = json!(round_to(ends[0], 4));
                f["properties"][Mark::DeckLift1.name()] = json!(round_to(ends[1], 4));
                f["properties"][Mark::DeckS0.name()] = json!(round_to(d0 / l, 5));
                f["properties"][Mark::DeckS1.name()] = json!(round_to(d1 / l, 5));
            }
            feats.extend(slabs);
        }
    }
    feats
}

/// The casing: a strip along each long side of the deck, up to just under the deck's top (an extrusion has no outline).
fn casing_slabs(dk: &DeckLook, frame: &Frame, part: &[P], (half, h, lift): (f64, f64, f64), (chain_i, edges, highway): (usize, &[usize], Value)) -> Vec<Value> {
    let cw = dk.casing_px * frame.mpp;
    [1.0, -1.0].into_iter().filter_map(|sgn| {
        let ring = strip(part, sgn * half, sgn * (half + cw));
        (ring.len() >= 4).then(|| json!({"type": "Feature", "properties": {
            "highway": highway, Mark::DeckChain.name(): chain_i, Mark::CasingSlab.name(): 1,
            Mark::Edges.name(): edges.iter().map(|&r| crate::road::key(r).get()).collect::<Vec<_>>(), Mark::DeckBase.name(): round_to((h * lift - 0.5).max(0.0), 2),
            Mark::DeckHeight.name(): round_to(h * lift + dk.thickness_m * 0.35, 2)},
            "geometry": {"type": "Polygon", "coordinates": [frame.to_lonlat(&ring)]}}))
    }).collect()
}
