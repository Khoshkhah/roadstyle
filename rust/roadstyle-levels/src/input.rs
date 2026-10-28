//! The solver's input from the edges (roadstyle's `level_input`, docs/levels.md): the roads, their bands and
//! priorities, and their relations. The geometry follows shapely and GEOS (a circle is a polygon of 32 sides) so the
//! relations are the same.

use crate::Error;
use super::solve::Rules;
use super::{LevelEdge, Options, Order, Pt};
use crate::flags;
use crate::plane::{casing_parts, circle, crosses, distance, metres, outside, Indexed};
use rstar::{RTree, AABB};
use std::collections::{BTreeMap, BTreeSet, HashMap};

/// The roads: edges with the same line (in one direction or the other) and the same `highway`, `tunnel`, `bridge`,
/// `layer` and band (roadstyle's `_road_split`).
pub struct Roads {
    /// The end nodes of each edge (equal end points are one node).
    pub ends: Vec<(u32, u32)>,
    /// The first edge of each road.
    pub first: Vec<usize>,
    /// The road of each edge, and whether the edge runs the same way as its road's first edge.
    pub road: Vec<usize>,
    pub same: Vec<bool>,
}

fn bits(p: &Pt) -> (u64, u64) {
    (p.0.to_bits(), p.1.to_bits())
}

pub fn road_split(edges: &[&LevelEdge]) -> Result<Roads, Error> {
    let mut node: HashMap<(u64, u64), u32> = HashMap::new();
    let mut id = |p: &Pt| {
        let k = node.len() as u32;
        *node.entry(bits(p)).or_insert(k)
    };
    let mut ends = Vec::with_capacity(edges.len());
    for e in edges {
        if e.geometry.len() < 2 {
            return Err(Error::Input(format!(
                "levels: edge {} has a line of less than two points",
                e.edge_id
            )));
        }
        ends.push((id(&e.geometry[0]), id(e.geometry.last().unwrap())));
    }
    type Key<'a> = ((u32, u32), Vec<(u64, u64)>, [Option<&'a str>; 5]);
    let mut roads: HashMap<Key, usize> = HashMap::new();
    let (mut first, mut road, mut same) = (Vec::new(), Vec::new(), Vec::new());
    for (i, e) in edges.iter().enumerate() {
        let fwd: Vec<(u64, u64)> = e.geometry.iter().map(bits).collect();
        let rev: Vec<(u64, u64)> = fwd.iter().rev().copied().collect();
        let (s, t) = ends[i];
        let a = e;
        let kind = [
            Some(a.highway.as_str()),
            a.tunnel.as_deref(),
            a.bridge.as_deref(),
            a.layer.as_deref(),
            a.band.as_deref(),
        ];
        let key = ((s.min(t), s.max(t)), fwd.clone().min(rev), kind);
        let r = *roads.entry(key).or_insert_with(|| {
            first.push(i);
            first.len() - 1
        });
        road.push(r);
        same.push(
            edges[first[r]]
                .geometry
                .iter()
                .map(bits)
                .eq(fwd.iter().copied()),
        );
    }
    Ok(Roads {
        ends,
        first,
        road,
        same,
    })
}

/// A yes/no tag (crate::flags, the one rule).
fn is_yes_tag(v: Option<&str>) -> bool {
    v.is_some_and(flags::yes_text)
}

/// The OSM level of an edge (`_level`): a non-zero `layer`, else bridge 1, tunnel -1, else 0.
pub fn level(e: &LevelEdge) -> i64 {
    flags::level(
        flags::layer(e.layer.as_deref()),
        is_yes_tag(e.bridge.as_deref()),
        is_yes_tag(e.tunnel.as_deref()),
    )
}

/// The band of a road from `band_col` (`pd.to_numeric(...).fillna(0).round()`: a value that is not a number is 0).
fn band(e: &LevelEdge) -> i64 {
    e.band
        .as_deref()
        .and_then(|s| s.trim().parse::<f64>().ok())
        .filter(|v| v.is_finite())
        .map_or(0, |v| v.round_ties_even() as i64)
}

/// The class order of the map (`class_order`, roadstyle's theme): the classes of each rank.
const CLASS_ORDER: &[(&[&str], f64)] = &[
    (&["motorway"], 9.0),
    (&["trunk"], 8.0),
    (&["primary"], 7.0),
    (&["secondary"], 6.0),
    (&["tertiary", "raceway"], 5.0),
    (&["unclassified", "residential", "road", "busway"], 4.0),
    (&["living_street"], 3.0),
    (&["pedestrian"], 2.0),
    (&["motorway_link"], 1.9),
    (&["trunk_link"], 1.85),
    (&["primary_link"], 1.8),
    (&["secondary_link"], 1.75),
    (&["tertiary_link"], 1.7),
    (&["service"], 1.5),
    (&["track"], 1.1),
    (&["footway", "path", "cycleway", "bridleway", "corridor"], 1.0),
    (&["steps"], 0.9),
    (&["platform"], 0.5),
    (&["construction"], 0.0),
];

/// The priority of a road (`order`): with "class", the class order of the map (`class_order`, roadstyle's theme); with
/// "priority", plus 300 for a roundabout, 200 for a tunnel, 100 for a bridge; with a column, its number (None: no wish).
fn priority(e: &LevelEdge, order: Order) -> Option<f64> {
    match order {
        Order::None => return None,
        Order::Column => return e.order,
        _ => {}
    }
    let z = |c: &str| CLASS_ORDER.iter().find(|(names, _)| names.contains(&c)).map(|&(_, v)| v);
    let h = e.highway.as_str();
    if h.is_empty() {
        return None; // a road with no class takes no part in the order (the caller's empty highway is no class)
    }
    let class = z(h).unwrap_or_else(|| match h.strip_suffix("_link") {
        Some(b) => z(b).unwrap_or(4.0) - 0.5,
        None => 4.0,
    });
    if order == Order::Class {
        return Some(class);
    }
    let a = e;
    let tier = if matches!(
        a.junction.as_deref().map(str::to_lowercase).as_deref(),
        Some("roundabout" | "circular")
    ) {
        3.0
    } else if is_yes_tag(a.tunnel.as_deref()) {
        2.0
    } else if is_yes_tag(a.bridge.as_deref()) {
        1.0
    } else {
        0.0
    };
    Some(class + 100.0 * tier)
}


/// The roads as the rules read them: for each road its first edge, band, priority, end nodes and line in metres.
struct Net<'a> {
    head: Vec<&'a LevelEdge>,
    band: Vec<i64>,
    omega: Vec<Option<f64>>,
    ends: Vec<(u32, u32)>,
    m: Vec<Vec<Pt>>,
}

impl<'a> Net<'a> {
    fn new(edges: &[&'a LevelEdge], roads: &Roads, o: &Options) -> Self {
        let head: Vec<&LevelEdge> = roads.first.iter().map(|&i| edges[i]).collect();
        let band = head.iter().map(|e| if o.band_col { band(e) } else { level(e) }).collect();
        let omega = head.iter().map(|e| priority(e, o.order)).collect();
        let ends = roads.first.iter().map(|&i| roads.ends[i]).collect();
        let lines: Vec<&[Pt]> = head.iter().map(|e| e.geometry.as_slice()).collect();
        let m = metres(&lines);
        Net { head, band, omega, ends, m }
    }
}

/// What the road ends at the nodes give.
struct AtNodes {
    /// (road, end, road, end) of two roads that end at one node
    meets: Vec<(usize, usize, usize, usize)>,
    /// (car road, path, end) of a path that a car road crosses at its end
    crossings: Vec<(usize, usize, usize)>,
    /// the nodes that each pair of roads shares
    shared: BTreeMap<(usize, usize), BTreeSet<u32>>,
}

/// meet: the road ends at each node. A path (PATH_CLASSES) at a node where a car road goes on (two car road ends or more there) is a
/// crossing, not a meet: the map draws the path under the road, which keeps its outline (OSM-Carto's look; a meet put the road's head
/// under the path's fill, a notch in the outline and a step in the casing, 2026-10-25). So the road's head at that node is lifted over
/// the path (a crossing: a wish after the stack rules, so a bridge outranks it), and the road's own ends there meet as at any node. Only where the other rules agree: the path and
/// the road are of one band (a footbridge or a tunnel mouth at the node stays a meet), and the road's priority is above the path's (the
/// order wish puts it over the path too; a pedestrian street over a service road stays a meet). A platform is not a car road.
fn at_nodes(net: &Net) -> AtNodes {
    let is_path = |r: usize| crate::PATH_CLASSES.contains(&net.head[r].highway.as_str());
    let is_car = |r: usize| !is_path(r) && net.head[r].highway != "platform" && net.omega[r].is_some();
    let crossing = |car: usize, path: usize| is_car(car) && is_path(path) && net.band[car] == net.band[path] && net.omega[car] > net.omega[path];
    let mut at: BTreeMap<u32, Vec<(usize, usize)>> = BTreeMap::new();
    for (r, &(s, t)) in net.ends.iter().enumerate() {
        at.entry(s).or_default().push((r, 0));
        at.entry(t).or_default().push((r, 2));
    }
    let mut out = AtNodes { meets: Vec::new(), crossings: Vec::new(), shared: BTreeMap::new() };
    for (&v, here) in &at {
        let cars = here.iter().filter(|&&(r, _)| is_car(r)).count();
        for (i, &(x, ex)) in here.iter().enumerate() {
            for &(y, ey) in &here[i + 1..] {
                if x == y {
                    continue;
                }
                out.shared.entry((x.min(y), x.max(y))).or_default().insert(v);
                if cars >= 2 && (crossing(x, y) || crossing(y, x)) {
                    let (car, end, path) = if crossing(x, y) { (x, ex, y) } else { (y, ey, x) };
                    out.crossings.push((car, path, end));
                } else {
                    out.meets.push(if x < y { (x, ex, y, ey) } else { (y, ey, x, ex) });
                }
            }
        }
    }
    out
}

/// The pairs of roads of different bands that are within `band_dist` of each other.
fn near_pairs(net: &Net, band_dist: f64) -> BTreeSet<(usize, usize)> {
    let mut near = BTreeSet::new();
    if net.band.iter().all(|&b| b == net.band[0]) {
        return near;
    }
    let boxes: Vec<AABB<[f64; 2]>> = net.m.iter().map(|l| {
        let (mut x0, mut y0, mut x1, mut y1) = (f64::MAX, f64::MAX, f64::MIN, f64::MIN);
        for p in l {
            (x0, y0, x1, y1) = (x0.min(p.0), y0.min(p.1), x1.max(p.0), y1.max(p.1));
        }
        AABB::from_corners([x0, y0], [x1, y1])
    }).collect();
    let tree = RTree::bulk_load(boxes.iter().enumerate().map(|(i, b)| Indexed(i, *b)).collect());
    for (i, b) in boxes.iter().enumerate() {
        let (lo, hi) = (b.lower(), b.upper());
        let q = AABB::from_corners([lo[0] - band_dist, lo[1] - band_dist], [hi[0] + band_dist, hi[1] + band_dist]);
        for Indexed(j, _) in tree.locate_in_envelope_intersecting(&q) {
            let j = *j;
            if i < j && net.band[i] != net.band[j] && distance(std::slice::from_ref(&net.m[i]), std::slice::from_ref(&net.m[j])) <= band_dist {
                near.insert((i, j));
            }
        }
    }
    near
}

/// stack: roads of different bands within band_dist, away from the nodes they share. The stacks as (upper, lower), and the pairs of
/// roads that only meet (no stack).
fn stacks(net: &Net, shared: &BTreeMap<(usize, usize), BTreeSet<u32>>, o: &Options) -> (Vec<(usize, usize)>, BTreeSet<(usize, usize)>) {
    let mut node_at: HashMap<u32, Pt> = HashMap::new();
    for (r, &(s, t)) in net.ends.iter().enumerate() {
        node_at.entry(s).or_insert(net.m[r][0]);
        node_at.entry(t).or_insert(*net.m[r].last().unwrap());
    }
    let (m, band, band_dist) = (&net.m, &net.band, o.band_dist);
    let mut stacks = Vec::new();
    let mut only_meet = BTreeSet::new();
    for (i, j) in near_pairs(net, band_dist) {
        if let Some(nodes) = shared.get(&(i, j)).filter(|_| !o.band_col) {
            let hole: Vec<Vec<Pt>> = nodes.iter().map(|v| circle(node_at[v], band_dist)).collect();
            let (a, b) = (outside(&m[i], &hole), outside(&m[j], &hole));
            if a.is_empty() || b.is_empty() || distance(&a, &b) > band_dist {
                only_meet.insert((i, j));
                continue;
            }
        }
        stacks.push(if band[i] > band[j] { (i, j) } else { (j, i) });
    }
    (stacks, only_meet)
}

/// order: where roads meet, of one band or of different bands that only meet; (higher, lower).
fn orders(net: &Net, shared: &BTreeMap<(usize, usize), BTreeSet<u32>>, only_meet: &BTreeSet<(usize, usize)>) -> Vec<(usize, usize)> {
    let mut orders = Vec::new();
    for &(x, y) in shared.keys() {
        let (Some(wx), Some(wy)) = (net.omega[x], net.omega[y]) else { continue };
        if wx != wy && (net.band[x] == net.band[y] || only_meet.contains(&(x, y))) {
            orders.push(if wx > wy { (x, y) } else { (y, x) });
        }
    }
    orders
}

/// The parts of each stack's upper road that are lifted (`_stack_parts`) and, with `near_rules`, those that only pass near.
#[allow(clippy::type_complexity)]
fn lifts(net: &Net, stacks: &[(usize, usize)], meets: &[(usize, usize, usize, usize)], heads: &HashMap<usize, [f64; 2]>, o: &Options)
         -> (Vec<(usize, usize, usize)>, Vec<(usize, usize, usize)>) {
    let mut touching: HashMap<usize, BTreeSet<usize>> = HashMap::new();
    let mut at_head: HashMap<(usize, usize), BTreeSet<usize>> = HashMap::new();
    for &(x, ex, y, ey) in meets {
        touching.entry(x).or_default().insert(y);
        touching.entry(y).or_default().insert(x);
        at_head.entry((x, ex)).or_default().insert(y);
        at_head.entry((y, ey)).or_default().insert(x);
    }
    let empty = BTreeSet::new();
    let m = &net.m;
    let (mut lifts, mut near) = (Vec::new(), Vec::new());
    for &(u, l) in stacks {
        let parts = casing_parts(&m[u], heads.get(&u).copied().unwrap_or([o.head_m; 2]));
        let tl = touching.get(&l).unwrap_or(&empty);
        for (h, p) in parts.iter().enumerate() {
            let Some(p) = p else { continue };
            if h != 1 {
                let ah = at_head.get(&(u, h)).unwrap_or(&empty);
                if ah.contains(&l) || ah.intersection(tl).next().is_some() {
                    continue;
                }
            }
            if crosses(p, &m[u], &m[l]) {
                lifts.push((u, l, h));
            } else if o.near_rules {
                near.push((u, l, h));
            }
        }
    }
    (lifts, near)
}

/// The rules of the roads (`_relations` and `_stack_parts`), the band of each road and its priority (None: no order wish).
/// With `band_col`, roads of different bands are a stack pair also where they only meet (no tunnel mouths). `heads`: a
/// road's own head lengths (heads.csv), else `head_m`; they decide which parts of a stack's upper road cross.
pub fn relations(edges: &[&LevelEdge], roads: &Roads, o: &Options, heads: &HashMap<usize, [f64; 2]>) -> (Rules, Vec<i64>, Vec<Option<f64>>) {
    let net = Net::new(edges, roads, o);
    let AtNodes { meets, crossings, shared } = at_nodes(&net);
    let (stacks, only_meet) = stacks(&net, &shared, o);
    let orders = orders(&net, &shared, &only_meet);
    let (lifts, near) = lifts(&net, &stacks, &meets, heads, o);
    let rules = Rules { roads: roads.first.len(), meets, lifts, crossings, orders, near, fixed: Vec::new() };
    (rules, net.band, net.omega)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A road of two edges through a node and a path that ends there (a bridge with `bridge`): the rules of the roads.
    fn node_rules(path: &str, bridge: bool, road: &str) -> Rules {
        let e = |id: i64, hw: &str, br: bool, geometry: Vec<Pt>| LevelEdge {
            edge_id: id,
            highway: hw.into(),
            bridge: br.then(|| "yes".into()),
            layer: br.then(|| "1".into()),
            geometry,
            ..Default::default()
        };
        let edges = [
            e(1, road, false, vec![(18.0, 59.0), (18.001, 59.0)]),
            e(2, road, false, vec![(18.001, 59.0), (18.002, 59.0)]),
            e(3, path, bridge, vec![(18.001, 59.0), (18.001, 59.001)]),
        ];
        let refs: Vec<&LevelEdge> = edges.iter().collect();
        let roads = road_split(&refs).unwrap();
        relations(&refs, &roads, &Options { method: crate::Method::Solve, ..Default::default() }, &HashMap::new()).0
    }

    #[test]
    fn a_path_at_a_node_where_a_road_goes_on_is_a_crossing() {
        // a footway: under both of the road's heads there (crossings), no meet with it; the road's own edges meet
        let r = node_rules("footway", false, "residential");
        assert_eq!(r.crossings, vec![(0, 2, 2), (1, 2, 0)], "{r:?}");
        assert_eq!(r.meets, vec![(0, 2, 1, 0)]);
        // a footbridge (another band) and a pedestrian street over a service road (the order puts the path over the road) stay meets
        for r in [node_rules("footway", true, "residential"), node_rules("pedestrian", false, "service")] {
            assert!(r.crossings.is_empty() && r.meets.len() == 3, "{r:?}");
        }
    }

}
