//! the bridges as ramped deck ribbons for the 3D view (the fill-extrusion source `decks`). The ribbons are made
//! with shapely (GEOS buffers and offset curves); this module makes the same strips with its own mitre offsets, so a polygon can have
//! other vertices than GEOS gives, but it covers the same ground (tests/test_engine_parity.py compares them by shape).

use roadstyle_model::mark::Mark;
use crate::bridge_curve::{self, Pvi};
use crate::bridge_profile::{self, BridgeProfile, Curve, Kind};
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
#[derive(PartialEq)]
struct Dist(f64);
impl Eq for Dist {}
impl Ord for Dist {
    fn cmp(&self, o: &Self) -> std::cmp::Ordering {
        o.0.total_cmp(&self.0)
    }
}
impl PartialOrd for Dist {
    fn partial_cmp(&self, o: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(o))
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

/// The smaller of a and b, rounded where they are within k of each other (at most k / 4 lower). k = 0: the exact minimum. The ramp's apex (where the two ramps of a short bridge
/// meet) is rounded so it has no ridge.
fn smin(a: f64, b: f64, k: f64) -> f64 {
    if k <= 0.0 {
        return a.min(b);
    }
    let h = (k - (a - b).abs()).max(0.0) / k;
    a.min(b) - h * h * k * 0.25
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

    /// The chains of the bridge roads, in the order of their first road: `__rs_chain` of a chain is its place + 1.
    fn chains(&self) -> Vec<Chain> {
        let mut used = vec![false; self.reps.len()];
        let mut out = Vec::new();
        for i in 0..used.len() {
            if !used[i] {
                out.push(self.walk(i, &mut used));
            }
        }
        out
    }

    /// The position of each node, by its key.
    fn positions(&self) -> HashMap<(u64, u64), Node> {
        let mut at = HashMap::new();
        for r in &self.reps {
            at.insert(hk(r.a), r.a);
            at.insert(hk(r.z), r.z);
        }
        at
    }
}

/// The heights that a caller gives: for each group of bridges (index: group - 1) the height of the whole group. Two sources, which are checked as one:
/// `bridge_heights` (road id as text -> metres, by the edge id column `id_col`; the id of any road of the group names it, as a two-way pair's either edge) and
/// `bridge_height_col` (a column of the roads: a road with a value gives its group that height; a road with no value gives nothing). Two heights for one group
/// (from one source or from both), a height that is not a number of 0 or more, an id that no road has, and a missing column are errors. An id of a road that is not a
/// 3D bridge gets a warning (its height does nothing); so do the roads with a value in the height column that are not 3D bridges (one warning, with their number).
pub struct Own<'a> {
    pub heights: Option<&'a std::collections::BTreeMap<String, f64>>,
    pub id_col: &'a str,
    pub height_col: Option<&'a str>,
}

fn own_heights(roads: &Roads, b: &Bridges, o: &Own, warnings: &mut Vec<String>) -> Result<Vec<Option<f64>>, crate::Error> {
    use crate::colors::category_text;
    let key = o.id_col;
    let bad_height = |what: &str, id: &str, h: f64| crate::error::Error::Options(format!("{what}: the height of {id:?} is {h}; a height is a number of metres, 0 or more"));
    if o.heights.is_some() && roads.at(0).is_some_and(|f| f.get(key).is_none()) {
        return Err(crate::error::column(key, "bridge_heights names its ids by it, and the roads do not have it"));
    }
    if let Some(c) = o.height_col {
        if roads.at(0).is_some_and(|f| f.get(c).is_none()) {
            return Err(crate::error::column(c, "bridge_height_col names it, and the roads do not have it"));
        }
    }
    if let Some((id, h)) = o.heights.into_iter().flatten().find(|(_, h)| !h.is_finite() || **h < 0.0) {
        return Err(bad_height("bridge_heights", id, *h));
    }
    let mut group_of_edge: HashMap<usize, usize> = HashMap::new();
    for (i, r) in b.reps.iter().enumerate() {
        for &fi in b.pair_edges.get(&self::key(r.a, r.z)).into_iter().flatten() {
            group_of_edge.insert(fi, b.group[i]);
        }
    }
    let road_id = |fi: usize| roads.get(fi, key).map(category_text).unwrap_or_else(|| format!("row {fi}"));
    let mut own: Vec<Option<(f64, String)>> = vec![None; b.group_len.len()];
    let mut seen: std::collections::HashSet<&String> = std::collections::HashSet::new();
    let mut off_bridge = 0usize;
    for fi in 0..roads.len() {
        // the heights this road gives its group: (the keyword, the height)
        let mut gives: Vec<(&str, f64)> = Vec::new();
        if let Some(heights) = o.heights {
            let id = roads.get(fi, key).map(category_text).unwrap_or_else(|| "None".into());
            if let Some((k, &h)) = heights.get_key_value(&id) {
                seen.insert(k);
                if group_of_edge.contains_key(&fi) {
                    gives.push(("bridge_heights", h));
                } else {
                    warnings.push(format!("bridge_heights: the road {id} is not a 3D bridge (a bridge with a level of 1 or more), so its height does nothing"));
                }
            }
        }
        if let Some(c) = o.height_col {
            let cell = roads.get(fi, c).filter(|v| !v.is_null());
            if let Some(cell) = cell {
                let h = cell.as_f64().ok_or_else(|| crate::Error::Data(format!("bridge_height_col: the road {} has {c} {}, and that is not a number", road_id(fi), cell.to_value())))?;
                if !h.is_finite() || h < 0.0 {
                    return Err(bad_height("bridge_height_col", &road_id(fi), h));
                }
                if group_of_edge.contains_key(&fi) {
                    gives.push(("bridge_height_col", h));
                } else {
                    off_bridge += 1;
                }
            }
        }
        for (what, h) in gives {
            let g = group_of_edge[&fi];
            let id = road_id(fi);
            match &own[g - 1] {
                Some((h0, id0)) if (h0 - h).abs() > 1e-9 => {
                    return Err(crate::Error::Data(format!("{what}: the roads {id0} and {id} touch each other (one group of bridges), and they have two heights, {h0} m and {h} m; a group has one height")));
                }
                Some(_) => {}
                None => own[g - 1] = Some((h, id)),
            }
        }
    }
    if let Some(id) = o.heights.into_iter().flat_map(|h| h.keys()).find(|k| !seen.contains(k)) {
        return Err(crate::Error::Data(format!("bridge_heights: no road has the {key} {id}")));
    }
    if off_bridge > 0 {
        let c = o.height_col.unwrap_or_default();
        warnings.push(format!("bridge_height_col: {off_bridge} roads that are not 3D bridges (a bridge with a level of 1 or more) have a value in {c}, so those values do nothing"));
    }
    Ok(own.into_iter().map(|o| o.map(|(h, _)| h)).collect())
}

/// The deck features of the roads, and the complete profile that they were made from, in two parts. The first part, the filler (`bridge_fill::fill`), reads the input profile `input` (a JSON value
/// in which every key is optional; None is the same as `{}`, the least), keeps what it gives and fills the rest with the rules (`today_profile`). The second part, the maker (`make_pieces`),
/// makes the pieces from the complete profile. It has no rules and no defaults: a profile that does not fit the roads (other chains, other lengths, other nodes) is an error.
/// `hw`: the property that has the user's `highway` column (a casing slab's `highway`). `own`: the heights of whole groups that the caller gave (`bridge_heights`, `bridge_height_col`);
/// they are the rule's group heights, and an input profile has its own heights, so the caller gives one of the two.
pub fn bridge_decks_and_profile(roads: &Roads, dk: &DeckLook, m: &Model, hw: &str, input: Option<&Value>, own: Option<&Own>, warnings: &mut Vec<String>) -> Result<(Vec<Value>, BridgeProfile), crate::Error> {
    let bridges = Bridges::new(roads);
    let given = match own {
        Some(o) => own_heights(roads, &bridges, o, warnings)?,
        None => Vec::new(),
    };
    let chains = bridges.chains();
    let empty = json!({});
    let profile = crate::bridge_fill::fill(today_profile(&bridges, &chains, dk, &given), input.unwrap_or(&empty), warnings)?;
    let feats = make_pieces(roads, dk, m, hw, &chains, &profile, warnings)?;
    Ok((feats, profile))
}

/// Today's rule as a complete profile: the height of a group (from its length, or the caller's), a node's height from its distance to the nearest free end (0 at a free end, rising at
/// the grade to the group's height), a chain with the top that is its group's height. The nodes are named n1, n2... from the north to the south, the chains c1, c2... in the order of the engine.
fn today_profile(b: &Bridges, chains: &[Chain], dk: &DeckLook, given: &[Option<f64>]) -> BridgeProfile {
    let grade = if dk.base_m > 0.0 { dk.ramp_m / dk.base_m } else { 8.0 };       // metres of ramp for a metre of height
    let top = |g: usize| given.get(g - 1).copied().flatten().unwrap_or_else(|| deck_height(dk, b.group_len[g - 1]));
    let at = b.positions();
    // the nodes of the chains, from the north to the south (then from the west to the east)
    let mut keys: Vec<(u64, u64)> = chains.iter().flat_map(|c| [c.head, c.tail]).collect();
    keys.sort_by(|x, y| at[y].1.total_cmp(&at[x].1).then(at[x].0.total_cmp(&at[y].0)));
    keys.dedup();
    let id_of: HashMap<(u64, u64), String> = keys.iter().enumerate().map(|(i, k)| (*k, format!("n{}", i + 1))).collect();
    let group_of_node: HashMap<(u64, u64), usize> = chains.iter().flat_map(|c| [(c.head, c.group), (c.tail, c.group)]).collect();
    let mut groups: Vec<bridge_profile::Group> = (1..=b.group_len.len()).map(|g| bridge_profile::Group { name: format!("group {g}"), nodes: Vec::new(), chains: Vec::new() }).collect();
    for k in &keys {
        let g = group_of_node[k];
        let (h, far) = (top(g), b.dfree.get(k).copied().unwrap_or(f64::INFINITY));
        let t = (far / (h * grade).max(1.0)).min(1.0);
        let ground = b.at.get(k).is_some_and(|v| v.len() == 1);
        let ids: Vec<String> = chains.iter().enumerate().filter(|(_, c)| c.head == *k || c.tail == *k).map(|(i, _)| format!("c{}", i + 1)).collect();
        groups[g - 1].nodes.push(bridge_profile::Node {
            id: id_of[k].clone(), lonlat: [at[k].0, at[k].1], kind: if ground { Kind::Ground } else { Kind::Junction }, chains: ids,
            z_m: h * t * t * (3.0 - 2.0 * t), source: if ground { "data" } else { "rule" }.into(), method: if ground { "mapped" } else { "derived" }.into() });
    }
    for (i, c) in chains.iter().enumerate() {
        groups[c.group - 1].chains.push(bridge_profile::Chain {
            id: format!("c{}", i + 1), osm_ways: Vec::new(), length_m: chain_length(c), from: id_of[&c.head].clone(), to: id_of[&c.tail].clone(), points: Vec::new(),
            top_m: Some(top(c.group)), width_m: None, width_source: None });
    }
    BridgeProfile { format: bridge_profile::FORMAT.into(), ground: None, parameters: bridge_profile::Parameters { design_speed_kmh: 50.0, design_grade: 1.0 / grade, curve: Some(Curve::Smooth), height_rule: None }, groups }
}

/// The length of a chain in metres: its line in the metres around its first point (the same frame as `chain_features`).
fn chain_length(ch: &Chain) -> f64 {
    let [lon0, lat0] = ch.pts[0];
    let kx = 111320.0 * lat0.to_radians().cos();
    let pts: Vec<P> = ch.pts.iter().map(|&[x, y]| [(x - lon0) * kx, (y - lat0) * 111320.0]).collect();
    pts.windows(2).map(|w| len(&w[0], &w[1])).sum::<f64>()
}

/// The pieces of every chain, from the profile. The heights of the two nodes of a chain, with its top, give the ramps of the curve `smooth`; with the curve `design` the heights of its nodes and
/// its interior points, with the length of the vertical curve at each point, give the height along the chain (`bridge_curve`). The maker has no rule: a value that is missing is an error. It
/// warns of what it can see in the shapes: a level top of a long bridge, a low point on a bridge, two decks that cross without room between them (the curve `design` only).
fn make_pieces(roads: &Roads, dk: &DeckLook, m: &Model, hw: &str, chains: &[Chain], profile: &BridgeProfile, warnings: &mut Vec<String>) -> Result<Vec<Value>, crate::Error> {
    let bad = |s: String| Err(crate::Error::Data(format!("bridge_profile: {s}")));
    let design = profile.parameters.curve.unwrap_or(Curve::Smooth) == Curve::Design;
    let mut nodes: HashMap<&str, &bridge_profile::Node> = HashMap::new();
    let mut by_id: HashMap<&str, (usize, &bridge_profile::Chain)> = HashMap::new();
    for (gi, g) in profile.groups.iter().enumerate() {
        nodes.extend(g.nodes.iter().map(|n| (n.id.as_str(), n)));
        by_id.extend(g.chains.iter().map(|c| (c.id.as_str(), (gi, c))));
    }
    if by_id.len() != chains.len() {
        return bad(format!("the profile has {} chains and these roads have {}: the profile is not for these roads", by_id.len(), chains.len()));
    }
    let mut feats = Vec::new();
    let cos0 = chains.first().map_or(1.0, |c| c.pts[0][1].to_radians().cos());
    let mut decks: Vec<(Vec<P>, Box<dyn Fn(f64) -> f64 + '_>)> = Vec::new();             // for the crossings: the line of each chain in metres, its height along it
    for (i, ch) in chains.iter().enumerate() {
        let (chain_i, id) = (i + 1, format!("c{}", i + 1));
        let Some(&(gi, cp)) = by_id.get(id.as_str()) else { return bad(format!("the profile has no chain {id}: the profile is not for these roads")) };
        if gi + 1 != ch.group {
            return bad(format!("the chain {id} is in group {} in the profile and in group {} in these roads", gi + 1, ch.group));
        }
        let l = chain_length(ch);
        if (cp.length_m - l).abs() > 0.5 {
            return bad(format!("the chain {id} is {:.1} m long in the profile and {l:.1} m in these roads: the profile is not for these roads", cp.length_m));
        }
        if !design && !cp.points.is_empty() {
            return bad(format!("the chain {id} has interior control points; they need the curve `design`: set parameters.curve to \"design\""));
        }
        let Some(top) = cp.top_m else { return bad(format!("the chain {id} has no top_m: the profile needs it (the full height of the chain, which the lift is a fraction of)")) };
        let mut z = [0.0; 2];
        for (k, (nid, end)) in [(&cp.from, ch.pts[0]), (&cp.to, ch.pts[ch.pts.len() - 1])].into_iter().enumerate() {
            let Some(n) = nodes.get(nid.as_str()) else { return bad(format!("the chain {id} starts or ends at the node {nid}, which the profile does not have")) };
            if bridge_profile::metres_between(n.lonlat, end) > bridge_profile::MATCH_M {
                return bad(format!("the node {nid} is not where the chain {id} {} in these roads: the profile is not for these roads", if k == 0 { "starts" } else { "ends" }));
            }
            if n.z_m > top + 1e-9 {
                return bad(format!("the node {nid} is {} m high, above the top of the chain {id} ({top} m)", n.z_m));
            }
            z[k] = n.z_m;
        }
        let shape = if design {
            let mut p = vec![Pvi { s: 0.0, z: z[0], curve_m: 0.0 }];
            for q in &cp.points {
                let Some(c) = q.curve_m else { return bad(format!("the point at {} m of the chain {id} has no curve_m: fill the profile first (the filler writes the length of the curve)", q.s)) };
                p.push(Pvi { s: q.s, z: q.z_m, curve_m: c });
            }
            p.push(Pvi { s: l, z: z[1], curve_m: 0.0 });
            // the profile's length is within 0.5 m of the roads' (checked above): the points keep their place on the chain, scaled to the roads' length
            let edge = cp.length_m;
            if let Err(e) = bridge_curve::check(&p.iter().enumerate().map(|(k, q)| if k + 1 == p.len() { Pvi { s: edge, ..*q } } else { *q }).collect::<Vec<_>>(), edge) {
                return bad(format!("the chain {id}: {e}"));
            }
            if let Some(q) = p.iter().find(|q| q.z > top + 1e-9) {
                return bad(format!("the point at {} m of the chain {id} is {} m high, above the top of the chain ({top} m)", q.s, q.z));
            }
            p.iter_mut().for_each(|q| { q.s *= l / edge; q.curve_m *= l / edge; });
            design_warnings(&p, &id, warnings);
            Shape::Design(p)
        } else {
            Shape::Smooth(bridge_profile::smoothstep_inverse(z[0] / top), bridge_profile::smoothstep_inverse(z[1] / top))
        };
        let lift = lift_fn(dk, top, l, &shape);
        if design {
            decks.push((ch.pts.iter().map(|&[x, y]| [x * 111320.0 * cos0, y * 111320.0]).collect(), Box::new(move |d| top * lift(d))));
        }
        feats.extend(chain_features(roads, dk, m, hw, ch, chain_i, (top, &shape, cp.width_m)));
    }
    if design {
        crossing_warnings(&decks, warnings);
    }
    Ok(feats)
}

/// The shape of a chain's height.
enum Shape {
    /// the smoothstep ramps of today: the ramp parameter at the head and the tail node
    Smooth(f64, f64),
    /// straight grades and vertical curves: the points from the head end to the tail end
    Design(Vec<Pvi>),
}

/// The checks of the shape of one chain (the curve `design`): a level top on a long bridge has no drainage, and a low point (a sag) is on the bridge.
fn design_warnings(p: &[Pvi], id: &str, warnings: &mut Vec<String>) {
    const LEVEL_M: f64 = 76.0;                      // the longest level top: the design note, rule 6 (a grade of 0.5 % drains a bridge; below 76 m the deck is short enough)
    for w in p.windows(2) {
        let flat = (w[1].z - w[0].z).abs() < 1e-6;
        let run = (w[1].s - w[1].curve_m / 2.0) - (w[0].s + w[0].curve_m / 2.0);
        if flat && run > LEVEL_M {
            warnings.push(format!("bridge_profile: the chain {id} has a level top of {run:.0} m (from {:.0} m to {:.0} m): the deck has no drainage; a grade of at least 0.5 % drains it", w[0].s, w[1].s));
        }
    }
    for i in 1..p.len() - 1 {
        let (g1, g2) = ((p[i].z - p[i - 1].z) / (p[i].s - p[i - 1].s), (p[i + 1].z - p[i].z) / (p[i + 1].s - p[i].s));
        if g1 < -1e-9 && g2 > 1e-9 {
            warnings.push(format!("bridge_profile: the chain {id} has its low point on the bridge at {:.0} m: water stays there", p[i].s));
        }
    }
}

/// Two decks that cross in the plan (their lines cross at a point that is not near an end of either) and are less than the clearance apart at the crossing. `decks`: the line of each chain in
/// metres (the x scale of its first point) and its height at a distance along it. The crossings come from the lines of the chains, not from the level solver.
fn crossing_warnings(decks: &[(Vec<P>, Box<dyn Fn(f64) -> f64 + '_>)], warnings: &mut Vec<String>) {
    const CLEARANCE_M: f64 = 5.0;                   // rule 1 of the design note
    const NEAR_END_M: f64 = 2.0;
    let boxes: Vec<[f64; 4]> = decks.iter().map(|(p, _)| p.iter().fold([f64::MAX, f64::MAX, f64::MIN, f64::MIN], |b, q| [b[0].min(q[0]), b[1].min(q[1]), b[2].max(q[0]), b[3].max(q[1])])).collect();
    let cum = |p: &[P]| { let mut c = vec![0.0]; for w in p.windows(2) { c.push(c[c.len() - 1] + len(&w[0], &w[1])); } c };
    for i in 0..decks.len() {
        for j in i + 1..decks.len() {
            if boxes[i][0] > boxes[j][2] || boxes[j][0] > boxes[i][2] || boxes[i][1] > boxes[j][3] || boxes[j][1] > boxes[i][3] {
                continue;
            }
            let (ci, cj) = (cum(&decks[i].0), cum(&decks[j].0));
            let mut done = false;
            for a in 0..decks[i].0.len() - 1 {
                for b in 0..decks[j].0.len() - 1 {
                    let (p, r, q, t) = (decks[i].0[a], [decks[i].0[a + 1][0] - decks[i].0[a][0], decks[i].0[a + 1][1] - decks[i].0[a][1]], decks[j].0[b], [decks[j].0[b + 1][0] - decks[j].0[b][0], decks[j].0[b + 1][1] - decks[j].0[b][1]]);
                    let den = r[0] * t[1] - r[1] * t[0];
                    if den.abs() < 1e-12 {
                        continue;
                    }
                    let (u, v) = (((q[0] - p[0]) * t[1] - (q[1] - p[1]) * t[0]) / den, ((q[0] - p[0]) * r[1] - (q[1] - p[1]) * r[0]) / den);
                    if !(0.0..=1.0).contains(&u) || !(0.0..=1.0).contains(&v) {
                        continue;
                    }
                    let (di, dj) = (ci[a] + u * len(&decks[i].0[a], &decks[i].0[a + 1]), cj[b] + v * len(&decks[j].0[b], &decks[j].0[b + 1]));
                    let (li, lj) = (ci[ci.len() - 1], cj[cj.len() - 1]);
                    if di < NEAR_END_M || di > li - NEAR_END_M || dj < NEAR_END_M || dj > lj - NEAR_END_M {
                        continue;
                    }
                    let (zi, zj) = ((decks[i].1)(di), (decks[j].1)(dj));
                    if (zi - zj).abs() < CLEARANCE_M && !done {
                        warnings.push(format!("bridge_profile: the chains c{} and c{} cross at {di:.0} m and {dj:.0} m along them, and the decks are {:.1} m high and {:.1} m high: the upper deck needs {CLEARANCE_M} m above the lower one", i + 1, j + 1, zi, zj));
                        done = true;
                    }
                }
            }
        }
    }
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

/// The ramps of the curve `smooth`: the length that a rise of the full height `h` takes, the lengths of the ramp at the head and at the tail node (`la`, `lb`: the ramp parameter there, 0 on the
/// ground, 1 at the full height), and the width over which the apex is rounded.
// THE HEIGHT OF A NODE: 0 at a free end, rising at one grade (`ramp_m` over `base_m`) with the distance to the nearest free end, up to the group's height `h`. A chain draws between the heights of
// its two end nodes, so the chains that meet at a node have one height there, and a short bridge rises only as far as the grade lets it (no wall on a bridge of a few metres).
// THE ROUNDING of the apex: where the ramp from the head end and the ramp from the tail end give the same lift (`cross`, metres from the head end), the deck has a crest, and the crest is
// rounded (`smin`) over a width that must lie inside the chain. So the width is the smaller of 0.4 and what fits between the crossing and the nearer end. Where the two ramps cross at
// an end of the chain (a node whose lift is what the ramp gives) or outside it, the deck has no crest and the width is 0: the exact minimum, and the lift at a node is exact.
fn smooth_ramps(dk: &DeckLook, h: f64, l: f64, la: f64, lb: f64) -> (f64, f64, f64, f64) {
    let grade = if dk.base_m > 0.0 { dk.ramp_m / dk.base_m } else { 8.0 };       // metres of ramp for a metre of height
    let full_ramp = (h * grade).max(1.0);                                          // metres that a rise of the full height takes
    let (rh, rt) = ((full_ramp * (1.0 - la)).min(l), (full_ramp * (1.0 - lb)).min(l));
    let cross = (l + full_ramp * (lb - la)) / 2.0;
    (full_ramp, rh, rt, (2.0 * cross.min(l - cross) / full_ramp).clamp(0.0, 0.4))
}

/// The lift (0 on the ground, 1 at the full height `h`) at a distance `d` along a chain of length `l`.
fn lift_fn(dk: &DeckLook, h: f64, l: f64, shape: &Shape) -> Box<dyn Fn(f64) -> f64> {
    match shape {
        Shape::Smooth(la, lb) => {
            let (la, lb) = (*la, *lb);
            let (full_ramp, _, _, round_k) = smooth_ramps(dk, h, l, la, lb);
            Box::new(move |d| {
                let t = smin(la + d / full_ramp, lb + (l - d) / full_ramp, round_k).clamp(0.0, 1.0);
                t * t * (3.0 - 2.0 * t)
            })
        }
        Shape::Design(p) => {
            let p = p.clone();
            Box::new(move |d| (bridge_curve::z_at(&p, d.clamp(0.0, l)) / h).clamp(0.0, 1.0))
        }
    }
}

/// The cut points along a chain with the curve `design`: its ends, each place where the shape changes (a point, the ends of a curve), a step inside each curve, and the roads' ends. A piece between two is
/// a straight grade, or a short part of a curve.
fn design_cuts(p: &[Pvi], l: f64, step: f64, span_ends: impl Iterator<Item = f64>) -> Vec<f64> {
    let mut cuts = vec![0.0, l];
    cuts.extend(bridge_curve::breaks(p).into_iter().filter(|&d| 0.0 < d && d < l));
    for (a, b) in bridge_curve::curves(p) {
        cuts.extend(std::iter::successors(Some(a + step), |d| Some(d + step)).take_while(|&d| d < b));
    }
    cuts.extend(span_ends.filter(|&b| 0.0 < b && b < l));
    cuts.sort_by(f64::total_cmp);
    cuts.dedup_by(|a, b| (*a - *b).abs() < 0.05);          // a piece shorter than 5 cm is a sliver
    cuts
}

/// The features of one chain: its deck pieces (cut where the ramps and the roads change) and their casing slabs. `h`: the full height of the chain; `la`, `lb`: the ramp
/// parameter at its head and its tail node (0: on the ground, 1: at the full height), from the heights of the two nodes of the profile; `width`: the width of the deck, or None for
/// the width of each road's class.
fn chain_features(roads: &Roads, dk: &DeckLook, m: &Model, hw: &str, ch: &Chain, chain_i: usize, (h, shape, width): (f64, &Shape, Option<f64>)) -> Vec<Value> {
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
    let lift_at = lift_fn(dk, h, l, shape);
    let step = dk.step_m.max(0.25);
    let cuts = match shape {
        Shape::Smooth(la, lb) => {
            let (_, rh, rt, _) = smooth_ramps(dk, h, l, *la, *lb);
            cuts_of(l, (rh, rt), step, bounds.iter().map(|b| b.0))
        }
        Shape::Design(p) => design_cuts(p, l, step, bounds.iter().map(|b| b.0)),
    };
    let mut feats = Vec::new();
    for w in cuts.windows(2) {
        let (d0, d1) = (w[0], w[1]);
        if d1 <= d0 {
            continue;
        }
        let mid = (d0 + d1) / 2.0;
        let span = bounds.iter().find(|b| mid <= b.0 + 1e-6).unwrap_or(&bounds[bounds.len() - 1]).1;
        let pprops = roads.road(span.fi);
        let cls = pprops.role(roadstyle_model::Role::Class).and_then(Cell::as_str).unwrap_or("");
        // half the width of the deck: the profile's width for the chain, else the width of the road's class
        let half = width.map_or_else(|| (m.gwidth(m.group_of(cls), dk.match_zoom) * frame.mpp / 2.0).max(2.0) * dk.width_scale, |w| w / 2.0);
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
