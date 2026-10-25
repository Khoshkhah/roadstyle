//! The solver's input from the edges (roadstyle's `level_input`, docs/levels.md): the roads, their bands and
//! priorities, and their relations. The geometry follows shapely and GEOS (a circle is a polygon of 32 sides) so the
//! relations are the same.

use crate::Error;
use super::solve::Rules;
use super::{LevelEdge, Options, Order, Pt};
use crate::flags;
use rstar::{RTree, RTreeObject, AABB};
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
fn truthy(v: Option<&str>) -> bool {
    v.is_some_and(flags::yes_text)
}

/// The OSM level of an edge (`_level`): a non-zero `layer`, else bridge 1, tunnel -1, else 0.
pub fn level(e: &LevelEdge) -> i64 {
    flags::level(
        flags::layer(e.layer.as_deref()),
        truthy(e.bridge.as_deref()),
        truthy(e.tunnel.as_deref()),
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

/// The priority of a road (`order`): with "class", the class order of the map (`class_order`, roadstyle's theme); with
/// "priority", plus 300 for a roundabout, 200 for a tunnel, 100 for a bridge; with a column, its number (None: no wish).
fn priority(e: &LevelEdge, order: Order) -> Option<f64> {
    match order {
        Order::None => return None,
        Order::Column => return e.order,
        _ => {}
    }
    let z = |c: &str| -> Option<f64> {
        Some(match c {
            "motorway" => 9.0,
            "trunk" => 8.0,
            "primary" => 7.0,
            "secondary" => 6.0,
            "tertiary" | "raceway" => 5.0,
            "unclassified" | "residential" | "road" | "busway" => 4.0,
            "living_street" => 3.0,
            "pedestrian" => 2.0,
            "motorway_link" => 1.9,
            "trunk_link" => 1.85,
            "primary_link" => 1.8,
            "secondary_link" => 1.75,
            "tertiary_link" => 1.7,
            "service" => 1.5,
            "track" => 1.1,
            "footway" | "path" | "cycleway" | "bridleway" | "corridor" => 1.0,
            "steps" => 0.9,
            "platform" => 0.5,
            "construction" => 0.0,
            _ => return None,
        })
    };
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
    } else if truthy(a.tunnel.as_deref()) {
        2.0
    } else if truthy(a.bridge.as_deref()) {
        1.0
    } else {
        0.0
    };
    Some(class + 100.0 * tier)
}

/// The UTM zone of a point and the projection to it: the transverse Mercator series of Krüger (6th order, as PROJ).
struct Utm {
    lon0: f64,
    north: f64,
    a: f64,
    alpha: [f64; 6],
    c: f64,
}

impl Utm {
    fn new(lon: f64, lat: f64) -> Utm {
        let zone = (((lon + 180.0) / 6.0).floor() as i32).clamp(0, 59) + 1;
        let f = 1.0 / 298.257_223_563;
        let n = f / (2.0 - f);
        let (n2, n3) = (n * n, n * n * n);
        let (n4, n5, n6) = (n2 * n2, n2 * n3, n3 * n3);
        Utm {
            lon0: (zone as f64 * 6.0 - 183.0).to_radians(),
            north: if lat >= 0.0 { 0.0 } else { 10_000_000.0 },
            a: 6_378_137.0 / (1.0 + n) * (1.0 + n2 / 4.0 + n4 / 64.0 + n6 / 256.0),
            alpha: [
                n / 2.0 - 2.0 * n2 / 3.0 + 5.0 * n3 / 16.0 + 41.0 * n4 / 180.0 - 127.0 * n5 / 288.0
                    + 7891.0 * n6 / 37800.0,
                13.0 * n2 / 48.0 - 3.0 * n3 / 5.0 + 557.0 * n4 / 1440.0 + 281.0 * n5 / 630.0
                    - 1983433.0 * n6 / 1935360.0,
                61.0 * n3 / 240.0 - 103.0 * n4 / 140.0
                    + 15061.0 * n5 / 26880.0
                    + 167603.0 * n6 / 181440.0,
                49561.0 * n4 / 161280.0 - 179.0 * n5 / 168.0 + 6601661.0 * n6 / 7257600.0,
                34729.0 * n5 / 80640.0 - 3418889.0 * n6 / 1995840.0,
                212378941.0 * n6 / 319334400.0,
            ],
            c: 2.0 * n.sqrt() / (1.0 + n),
        }
    }

    fn project(&self, p: Pt) -> Pt {
        let (phi, lam) = (p.1.to_radians(), p.0.to_radians() - self.lon0);
        let s = phi.sin();
        let t = (s.atanh() - self.c * (self.c * s).atanh()).sinh();
        let xi = t.atan2(lam.cos());
        let eta = (lam.sin() / (1.0 + t * t).sqrt()).atanh();
        let (mut x, mut y) = (eta, xi);
        for (j, al) in self.alpha.iter().enumerate() {
            let k = 2.0 * (j + 1) as f64;
            x += al * (k * xi).cos() * (k * eta).sinh();
            y += al * (k * xi).sin() * (k * eta).cosh();
        }
        let k0 = 0.9996;
        (500_000.0 + k0 * self.a * x, self.north + k0 * self.a * y)
    }
}

/// The lines in metres, in the UTM zone of the center of their box (geopandas' `estimate_utm_crs`).
fn metres(lines: &[&[Pt]]) -> Vec<Vec<Pt>> {
    let (mut x0, mut y0, mut x1, mut y1) = (f64::MAX, f64::MAX, f64::MIN, f64::MIN);
    for p in lines.iter().flat_map(|l| l.iter()) {
        (x0, y0, x1, y1) = (x0.min(p.0), y0.min(p.1), x1.max(p.0), y1.max(p.1));
    }
    let utm = Utm::new((x0 + x1) / 2.0, (y0 + y1) / 2.0);
    lines
        .iter()
        .map(|l| l.iter().map(|&p| utm.project(p)).collect())
        .collect()
}

// ---- plane geometry (metres) ----

fn sub(a: Pt, b: Pt) -> Pt {
    (a.0 - b.0, a.1 - b.1)
}
fn cross(a: Pt, b: Pt) -> f64 {
    a.0 * b.1 - a.1 * b.0
}
fn dot(a: Pt, b: Pt) -> f64 {
    a.0 * b.0 + a.1 * b.1
}

fn point_seg(p: Pt, a: Pt, b: Pt) -> f64 {
    let ab = sub(b, a);
    let l = dot(ab, ab);
    let t = if l == 0.0 {
        0.0
    } else {
        (dot(sub(p, a), ab) / l).clamp(0.0, 1.0)
    };
    let q = (a.0 + t * ab.0, a.1 + t * ab.1);
    dot(sub(p, q), sub(p, q)).sqrt()
}

fn orient(a: Pt, b: Pt, c: Pt) -> f64 {
    cross(sub(b, a), sub(c, a))
}

fn on_seg(p: Pt, a: Pt, b: Pt) -> bool {
    p.0 >= a.0.min(b.0) && p.0 <= a.0.max(b.0) && p.1 >= a.1.min(b.1) && p.1 <= a.1.max(b.1)
}

fn segs_meet(a: Pt, b: Pt, c: Pt, d: Pt) -> bool {
    let (d1, d2, d3, d4) = (
        orient(c, d, a),
        orient(c, d, b),
        orient(a, b, c),
        orient(a, b, d),
    );
    if ((d1 > 0.0 && d2 < 0.0) || (d1 < 0.0 && d2 > 0.0))
        && ((d3 > 0.0 && d4 < 0.0) || (d3 < 0.0 && d4 > 0.0))
    {
        return true;
    }
    (d1 == 0.0 && on_seg(a, c, d))
        || (d2 == 0.0 && on_seg(b, c, d))
        || (d3 == 0.0 && on_seg(c, a, b))
        || (d4 == 0.0 && on_seg(d, a, b))
}

fn seg_seg(a: Pt, b: Pt, c: Pt, d: Pt) -> f64 {
    if segs_meet(a, b, c, d) {
        return 0.0;
    }
    point_seg(a, c, d)
        .min(point_seg(b, c, d))
        .min(point_seg(c, a, b))
        .min(point_seg(d, a, b))
}

/// The distance between two sets of lines.
fn distance(a: &[Vec<Pt>], b: &[Vec<Pt>]) -> f64 {
    let mut best = f64::INFINITY;
    for la in a {
        for lb in b {
            for sa in la.windows(2) {
                for sb in lb.windows(2) {
                    best = best.min(seg_seg(sa[0], sa[1], sb[0], sb[1]));
                }
            }
        }
    }
    best
}

/// GEOS's buffer of a point (8 segments for a quarter circle): a polygon of 32 sides, counterclockwise.
fn circle(p: Pt, r: f64) -> Vec<Pt> {
    let inc = 2.0 * std::f64::consts::PI / 32.0;
    (0..32)
        .map(|i| {
            let a = i as f64 * inc;
            (p.0 + r * a.cos(), p.1 + r * a.sin())
        })
        .collect()
}

/// The part `[t0, t1]` of the segment a-b inside a convex polygon (counterclockwise), or None (Cyrus-Beck).
fn clip(a: Pt, b: Pt, poly: &[Pt]) -> Option<(f64, f64)> {
    let (mut t0, mut t1) = (0.0f64, 1.0f64);
    let d = sub(b, a);
    for k in 0..poly.len() {
        let (p, q) = (poly[k], poly[(k + 1) % poly.len()]);
        let e = sub(q, p);
        // inside: cross(e, x - p) >= 0
        let num = cross(e, sub(a, p));
        let den = cross(e, d);
        if den == 0.0 {
            if num < 0.0 {
                return None;
            }
        } else {
            let t = -num / den;
            if den > 0.0 {
                t0 = t0.max(t);
            } else {
                t1 = t1.min(t);
            }
            if t0 > t1 {
                return None;
            }
        }
    }
    Some((t0, t1))
}

/// The parts of a line out of a set of convex polygons (a line's `difference` with their union), one segment each,
/// without parts of length 0. Only their distance and whether there is one are used.
fn outside(line: &[Pt], polys: &[Vec<Pt>]) -> Vec<Vec<Pt>> {
    let mut out = Vec::new();
    for s in line.windows(2) {
        let (a, b) = (s[0], s[1]);
        let mut inside: Vec<(f64, f64)> = polys.iter().filter_map(|p| clip(a, b, p)).collect();
        inside.sort_by(|x, y| x.0.total_cmp(&y.0));
        let at = |t: f64| (a.0 + t * (b.0 - a.0), a.1 + t * (b.1 - a.1));
        let mut t = 0.0;
        for (u, v) in inside.into_iter().chain([(1.0, 1.0)]) {
            if u > t && at(u) != at(t) {
                out.push(vec![at(t), at(u)]);
            }
            t = t.max(v);
        }
    }
    out
}

/// Whether a part of the upper road crosses the lower road (`_crosses`): they meet at a point (or along a piece) out
/// of the circles of 0.5 m around the ends of both roads.
fn crosses(part: &[Pt], upper: &[Pt], lower: &[Pt]) -> bool {
    let ends: Vec<Vec<Pt>> = [
        upper[0],
        *upper.last().unwrap(),
        lower[0],
        *lower.last().unwrap(),
    ]
    .iter()
    .map(|&p| circle(p, 0.5))
    .collect();
    let free = |p: Pt| ends.iter().all(|c| clip(p, p, c).is_none());
    for s in part.windows(2) {
        for l in lower.windows(2) {
            let (a, b, c, d) = (s[0], s[1], l[0], l[1]);
            let (d1, d2) = (orient(c, d, a), orient(c, d, b));
            if d1 == 0.0 && d2 == 0.0 {
                // on one line: the common piece
                let ab = sub(b, a);
                let len2 = dot(ab, ab);
                if len2 == 0.0 {
                    if on_seg(a, c, d) && free(a) {
                        return true;
                    }
                    continue;
                }
                let (tc, td) = (dot(sub(c, a), ab) / len2, dot(sub(d, a), ab) / len2);
                let (u, v) = (tc.min(td).max(0.0), tc.max(td).min(1.0));
                if u > v {
                    continue;
                }
                let at = |t: f64| (a.0 + t * ab.0, a.1 + t * ab.1);
                if u == v {
                    if free(at(u)) {
                        return true;
                    }
                } else if !outside(&[at(u), at(v)], &ends).is_empty() {
                    return true;
                }
            } else if segs_meet(a, b, c, d) {
                // one point: where the lines cross, or an end on the other segment
                let p = if d1 == 0.0 {
                    a
                } else if d2 == 0.0 {
                    b
                } else if orient(a, b, c) == 0.0 {
                    c
                } else if orient(a, b, d) == 0.0 {
                    d
                } else {
                    let t = d1 / (d1 - d2);
                    (a.0 + t * (b.0 - a.0), a.1 + t * (b.1 - a.1))
                };
                if free(p) {
                    return true;
                }
            }
        }
    }
    false
}

fn length(l: &[Pt]) -> f64 {
    l.windows(2)
        .map(|s| dot(sub(s[1], s[0]), sub(s[1], s[0])).sqrt())
        .sum()
}

/// The point at `d` metres along the line.
fn interpolate(l: &[Pt], d: f64) -> Pt {
    let mut cum = 0.0;
    for s in l.windows(2) {
        let len = dot(sub(s[1], s[0]), sub(s[1], s[0])).sqrt();
        if d <= cum + len {
            let t = if len == 0.0 { 0.0 } else { (d - cum) / len };
            return (
                s[0].0 + t * (s[1].0 - s[0].0),
                s[0].1 + t * (s[1].1 - s[0].1),
            );
        }
        cum += len;
    }
    *l.last().unwrap()
}

/// The piece of the line from `a` to `b` metres (shapely's `substring`, `a` < `b`).
fn substring(l: &[Pt], a: f64, b: f64) -> Vec<Pt> {
    let mut out = vec![interpolate(l, a)];
    let mut cum = 0.0;
    for s in l.windows(2) {
        if a < cum && cum < b {
            out.push(s[0]);
        } else if cum >= b {
            break;
        }
        cum += dot(sub(s[1], s[0]), sub(s[1], s[0])).sqrt();
    }
    out.push(interpolate(l, b));
    out
}

/// The three casing parts of a road (`casing_parts`): the heads `[start, end]` metres long (cut in their ratio on a
/// short road), and the main part, None when it is shorter than 5 cm.
fn casing_parts(l: &[Pt], heads: [f64; 2]) -> [Option<Vec<Pt>>; 3] {
    let n = length(l);
    let [mut h0, mut h1] = heads;
    if h0 + h1 >= n {
        (h0, h1) = (n * h0 / (h0 + h1), n * h1 / (h0 + h1));
    }
    [
        Some(substring(l, 0.0, h0)),
        (n - h1 - h0 > 0.05).then(|| substring(l, h0, n - h1)),
        Some(substring(l, n - h1, n)),
    ]
}

struct Indexed(usize, AABB<[f64; 2]>);

impl RTreeObject for Indexed {
    type Envelope = AABB<[f64; 2]>;
    fn envelope(&self) -> Self::Envelope {
        self.1
    }
}

/// The rules of the roads (`_relations` and `_stack_parts`), the band of each road and its priority (None: no order wish).
/// With `band_col`, roads of different bands are a stack pair also where they only meet (no tunnel mouths). `heads`: a
/// road's own head lengths (heads.csv), else `head_m`; they decide which parts of a stack's upper road cross.
pub fn relations(
    edges: &[&LevelEdge],
    roads: &Roads,
    o: &Options,
    heads: &HashMap<usize, [f64; 2]>,
) -> (Rules, Vec<i64>, Vec<Option<f64>>) {
    let n = roads.first.len();
    let band_dist = o.band_dist;
    let head: Vec<&LevelEdge> = roads.first.iter().map(|&i| edges[i]).collect();
    let band: Vec<i64> = head
        .iter()
        .map(|e| if o.band_col { band(e) } else { level(e) })
        .collect();
    let omega: Vec<Option<f64>> = head.iter().map(|e| priority(e, o.order)).collect();
    let re: Vec<(u32, u32)> = roads.first.iter().map(|&i| roads.ends[i]).collect();
    let lines: Vec<&[Pt]> = head.iter().map(|e| e.geometry.as_slice()).collect();
    let m = metres(&lines);

    // meet: the road ends at each node. A path (PATH_CLASSES) at a node where a car road goes on (two car road ends or more there) is a
    // crossing, not a meet: the map draws the path under the road, which keeps its outline (OSM-Carto's look; a meet put the road's head
    // under the path's fill, a notch in the outline and a step in the casing, 2026-10-25). So the road's head at that node is lifted over
    // the path (a crossing: a wish after the stack rules, so a bridge outranks it), and the road's own ends there meet as at any node. Only where the other rules agree: the path and
    // the road are of one band (a footbridge or a tunnel mouth at the node stays a meet), and the road's priority is above the path's (the
    // order wish puts it over the path too; a pedestrian street over a service road stays a meet). A platform is not a car road.
    let is_path = |r: usize| crate::PATH_CLASSES.contains(&head[r].highway.as_str());
    let is_car = |r: usize| !is_path(r) && head[r].highway != "platform" && omega[r].is_some();
    let crossing = |car: usize, path: usize| is_car(car) && is_path(path) && band[car] == band[path] && omega[car] > omega[path];
    let mut at: BTreeMap<u32, Vec<(usize, usize)>> = BTreeMap::new();
    for (r, &(s, t)) in re.iter().enumerate() {
        at.entry(s).or_default().push((r, 0));
        at.entry(t).or_default().push((r, 2));
    }
    let mut meets = Vec::new();
    let mut crossings = Vec::new();
    let mut shared: BTreeMap<(usize, usize), BTreeSet<u32>> = BTreeMap::new();
    for (&v, here) in &at {
        let cars = here.iter().filter(|&&(r, _)| is_car(r)).count();
        for (i, &(x, ex)) in here.iter().enumerate() {
            for &(y, ey) in &here[i + 1..] {
                if x != y {
                    shared.entry((x.min(y), x.max(y))).or_default().insert(v);
                    if cars >= 2 && (crossing(x, y) || crossing(y, x)) {
                        let (car, end, path) = if crossing(x, y) { (x, ex, y) } else { (y, ey, x) };
                        crossings.push((car, path, end));
                        continue;
                    }
                    meets.push(if x < y {
                        (x, ex, y, ey)
                    } else {
                        (y, ey, x, ex)
                    });
                }
            }
        }
    }
    let mut node_at: HashMap<u32, Pt> = HashMap::new();
    for (r, &(s, t)) in re.iter().enumerate() {
        node_at.entry(s).or_insert(m[r][0]);
        node_at.entry(t).or_insert(*m[r].last().unwrap());
    }

    // stack: roads of different bands within band_dist, away from the nodes they share
    let mut near = BTreeSet::new();
    if band.iter().any(|&b| b != band[0]) {
        let boxes: Vec<AABB<[f64; 2]>> = m
            .iter()
            .map(|l| {
                let (mut x0, mut y0, mut x1, mut y1) = (f64::MAX, f64::MAX, f64::MIN, f64::MIN);
                for p in l {
                    (x0, y0, x1, y1) = (x0.min(p.0), y0.min(p.1), x1.max(p.0), y1.max(p.1));
                }
                AABB::from_corners([x0, y0], [x1, y1])
            })
            .collect();
        let tree = RTree::bulk_load(
            boxes
                .iter()
                .enumerate()
                .map(|(i, b)| Indexed(i, *b))
                .collect(),
        );
        for i in 0..n {
            let (lo, hi) = (boxes[i].lower(), boxes[i].upper());
            let q = AABB::from_corners(
                [lo[0] - band_dist, lo[1] - band_dist],
                [hi[0] + band_dist, hi[1] + band_dist],
            );
            for o in tree.locate_in_envelope_intersecting(&q) {
                let j = o.0;
                if i < j
                    && band[i] != band[j]
                    && distance(std::slice::from_ref(&m[i]), std::slice::from_ref(&m[j]))
                        <= band_dist
                {
                    near.insert((i, j));
                }
            }
        }
    }
    let mut stacks = Vec::new();
    let mut only_meet = BTreeSet::new();
    for &(i, j) in &near {
        if let Some(nodes) = shared.get(&(i, j)).filter(|_| !o.band_col) {
            let hole: Vec<Vec<Pt>> = nodes
                .iter()
                .map(|v| circle(node_at[v], band_dist))
                .collect();
            let (a, b) = (outside(&m[i], &hole), outside(&m[j], &hole));
            if a.is_empty() || b.is_empty() || distance(&a, &b) > band_dist {
                only_meet.insert((i, j));
                continue;
            }
        }
        stacks.push(if band[i] > band[j] { (i, j) } else { (j, i) });
    }

    // order: where roads meet, of one band or of different bands that only meet
    let mut orders = Vec::new();
    for &(x, y) in shared.keys() {
        let (Some(wx), Some(wy)) = (omega[x], omega[y]) else {
            continue;
        };
        if wx == wy {
            continue;
        }
        if band[x] == band[y] || only_meet.contains(&(x, y)) {
            orders.push(if wx > wy { (x, y) } else { (y, x) });
        }
    }

    // the parts of each stack's upper road that are lifted (`_stack_parts`)
    let mut touching: HashMap<usize, BTreeSet<usize>> = HashMap::new();
    let mut at_head: HashMap<(usize, usize), BTreeSet<usize>> = HashMap::new();
    for &(x, ex, y, ey) in &meets {
        touching.entry(x).or_default().insert(y);
        touching.entry(y).or_default().insert(x);
        at_head.entry((x, ex)).or_default().insert(y);
        at_head.entry((y, ey)).or_default().insert(x);
    }
    let empty = BTreeSet::new();
    let (mut lifts, mut near) = (Vec::new(), Vec::new());
    for &(u, l) in &stacks {
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
    (
        Rules {
            roads: n,
            meets,
            lifts,
            crossings,
            orders,
            near,
            fixed: Vec::new(),
        },
        band,
        omega,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn utm_as_pyproj() {
        // pyproj (always_xy): EPSG:32632 (7.42, 43.73) and EPSG:32735 (26.7, -20.1)
        for (lon, lat, x, y) in [
            (7.42, 43.73, 372751.1228, 4843098.2362),
            (26.7, -20.1, 468638.1863, 7777424.4129),
        ] {
            let (px, py) = Utm::new(lon, lat).project((lon, lat));
            assert!((px - x).abs() < 1e-3 && (py - y).abs() < 1e-3, "{px} {py}");
        }
    }

    #[test]
    fn a_line_out_of_a_circle() {
        let c = vec![circle((0.0, 0.0), 1.0)];
        let parts = outside(&[(-3.0, 0.0), (3.0, 0.0)], &c);
        assert_eq!(parts.len(), 2);
        assert!(
            (parts[0][1].0 + 1.0).abs() < 1e-12 && parts[0][0] == (-3.0, 0.0),
            "{parts:?}"
        );
        assert!(outside(&[(-0.5, 0.0), (0.5, 0.0)], &c).is_empty());
    }

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

    #[test]
    fn a_crossing_and_a_join() {
        let upper = [(-10.0, 0.0), (10.0, 0.0)];
        assert!(crosses(&upper, &upper, &[(0.0, -10.0), (0.0, 10.0)]));
        // the lower road starts at the end of the upper road: a join, not a crossing
        assert!(!crosses(&upper, &upper, &[(10.0, 0.0), (10.0, 10.0)]));
    }
}
