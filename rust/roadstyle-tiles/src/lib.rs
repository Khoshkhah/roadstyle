//! The style's sources as vector tiles (Mapbox Vector Tile 2.1), made when the map asks for them, with the rules of roadstyle's
//! tiles.py: the page gives MapLibre one source, `{"type": "vector", "tiles": ["<prefix>roads/{z}/{x}/{y}"]}`, and each of the
//! style's sources is a layer in its tiles (the layers' `source-layer`). One GeoJSON text of all the roads (Tartu: 150 MB) is then
//! not made, parsed and cut into tiles by MapLibre again.
//!
//! Each feature has its index in its source as its id (tiles.py), and its properties (a null
//! value is left out: MapLibre reads a missing one as null). Below the last zoom a line is simplified to half a tile unit, and a
//! line shorter than that is left out. A feature is clipped to the tile and a buffer around it, except a feature of a whole layer
//! (the name and arrow slots): it goes whole into every tile it touches, because MapLibre places a label only in the tile that has
//! its anchor.

// Ported numeric code: index loops over parallel arrays and tuple types of the Python stages read as they are in Python.
#![allow(clippy::needless_range_loop, clippy::type_complexity)]

pub mod pmtiles;

use rstar::{primitives::GeomWithData, primitives::Rectangle, RTree, AABB};
use serde_json::{Map, Value};
use indexmap::IndexMap;
use std::collections::{HashMap, HashSet};

/// The tile's size in its own units.
pub const EXTENT: f64 = 4096.0;
/// The name of the one vector source.
pub const SOURCE: &str = "roads";

type P = [f64; 2];

enum Geom {
    Points(Vec<P>),
    Lines(Vec<Vec<P>>),
    Polygons(Vec<Vec<Vec<P>>>),
}

#[derive(Clone, PartialEq)]
enum Val {
    Str(Box<str>),
    Bool(bool),
    Int(i64),
    UInt(u64),
    Dbl(f64),
}

struct Feat {
    id: Option<u64>,
    geom: Geom,
    /// (key, value): the numbers of the layer's key and value
    props: Vec<(u32, u32)>,
}

/// A source made ready: its keys, its distinct values (each also as the bytes of its Value message in a tile, made once and not for
/// each tile: half of a tile's time was this), its features and their boxes.
struct Layer {
    keys: Vec<String>,
    vals: Vec<Val>,
    encoded: Vec<Vec<u8>>,
    feats: Vec<Feat>,
    tree: RTree<GeomWithData<Rectangle<P>, u32>>,
    /// The features go whole into the tiles: not clipped and not simplified.
    whole: bool,
    min_zoom: u32,
}

/// The sources of a style, ready to be cut into tiles: the layers in their order, the first and last zoom of the tiles (MapLibre
/// zooms the last one in), and the buffer around a tile in its units (wide lines, their offsets and the labels along them reach over
/// the tile's edge).
pub struct Tiles {
    layers: IndexMap<String, Layer>,
    min_zoom: u32,
    max_zoom: u32,
    buffer: f64,
}

/// Web Mercator in [0, 1] (x to the east, y to the south), as the tiles count.
fn merc(c: &Value) -> Option<P> {
    merc_ll(c.get(0)?.as_f64()?, c.get(1)?.as_f64()?)
}

fn merc_ll(lon: f64, lat: f64) -> Option<P> {
    if !lon.is_finite() || !lat.is_finite() {
        return None; // as JSON: a number that is not finite is null
    }
    let lat = lat.clamp(-85.051_128_78, 85.051_128_78);
    let y = (std::f64::consts::FRAC_PI_4 + lat.to_radians() / 2.0).tan().ln();
    Some([(lon + 180.0) / 360.0, 0.5 - y / (2.0 * std::f64::consts::PI)])
}

fn line(c: &Value) -> Vec<P> {
    c.as_array().map_or(Vec::new(), |a| a.iter().filter_map(merc).collect())
}

fn rings(c: &Value) -> Vec<Vec<P>> {
    c.as_array().map_or(Vec::new(), |a| a.iter().map(line).collect())
}

fn geom(g: &Value) -> Option<Geom> {
    let c = &g["coordinates"];
    let list = |f: &dyn Fn(&Value) -> Vec<Vec<P>>| c.as_array().map_or(Vec::new(), |a| a.iter().map(f).collect());
    Some(match g["type"].as_str()? {
        "Point" => Geom::Points(vec![merc(c)?]),
        "MultiPoint" => Geom::Points(c.as_array()?.iter().filter_map(merc).collect()),
        "LineString" => Geom::Lines(vec![line(c)]),
        "MultiLineString" => Geom::Lines(rings(c)),
        "Polygon" => Geom::Polygons(vec![rings(c)]),
        "MultiPolygon" => Geom::Polygons(list(&rings)),
        _ => return None,
    })
}

fn val(v: &Value) -> Option<Val> {
    Some(match v {
        Value::String(s) => Val::Str(s.as_str().into()),
        Value::Bool(b) => Val::Bool(*b),
        Value::Number(n) => match (n.as_i64(), n.as_u64()) {
            (Some(i), _) => Val::Int(i),
            (_, Some(u)) => Val::UInt(u),
            _ => Val::Dbl(n.as_f64()?),
        },
        Value::Null | Value::Array(_) | Value::Object(_) => return None, // tiles.py (mapbox_vector_tile) leaves out a list or an object
    })
}

fn bounds(g: &Geom) -> Option<(P, P)> {
    let mut lo = [f64::INFINITY; 2];
    let mut hi = [f64::NEG_INFINITY; 2];
    let mut add = |p: &P| {
        for k in 0..2 {
            lo[k] = lo[k].min(p[k]);
            hi[k] = hi[k].max(p[k]);
        }
    };
    match g {
        Geom::Points(ps) => ps.iter().for_each(&mut add),
        Geom::Lines(ls) => ls.iter().flatten().for_each(&mut add),
        Geom::Polygons(ps) => ps.iter().flatten().flatten().for_each(&mut add),
    }
    (lo[0] <= hi[0]).then_some((lo, hi))
}

impl Tiles {
    pub fn new(min_zoom: u32, max_zoom: u32, buffer: f64) -> Tiles {
        Tiles { layers: IndexMap::new(), min_zoom, max_zoom, buffer }
    }

    /// Add a GeoJSON source of the style (`{"type": "geojson", "data": FeatureCollection, ...}`) as the layer `name`, and free its
    /// tree. The properties in `keep` and every `__rs_*` property go into the tiles, all of a whole layer's (tiles.py's tile_props). `whole`: see the module; `min_zoom`: the layer's first zoom.
    pub fn add(&mut self, name: &str, source: Value, keep: &HashSet<String>, whole: bool, min_zoom: u32) {
        let Value::Object(mut s) = source else { return };
        let features = match s.remove("data").map(|mut d| d["features"].take()) {
            Some(Value::Array(f)) => f,
            _ => Vec::new(),
        };
        drop(s);
        let mut b = Builder::default();
        for (i, f) in features.into_iter().enumerate() {
            let Value::Object(mut f) = f else { continue };
            let Some(g) = f.get("geometry").and_then(geom) else { continue };
            let id = Some(i as u64); // tiles.py: a feature's id is its index in its source
            let props = match f.remove("properties") {
                Some(Value::Object(p)) => p,
                _ => Map::new(),
            };
            // tiles.py's tile_props: a whole layer (keep=None there) all its properties, else `keep` and every __rs_*
            b.push(id, g, props.into_iter().filter(|(k, _)| whole || k.starts_with("__rs_") || keep.contains(k)));
        }
        self.layers.insert(name.to_string(), b.layer(whole, min_zoom));
    }

    /// Add a source of typed features (roads, simple), as `add` adds its JSON.
    pub fn add_typed(&mut self, name: &str, source: roadstyle_model::props::Source, keep: &HashSet<String>, whole: bool, min_zoom: u32) {
        let mut b = Builder::default();
        for (i, f) in source.feats.into_iter().enumerate() {
            let Some(c) = f.coords else { continue };
            let g = Geom::Lines(vec![c.iter().filter_map(|p| merc_ll(p[0], p[1])).collect()]);
            b.push(Some(i as u64), g, f.props.into_iter().filter(|(k, _)| whole || k.starts_with("__rs_") || keep.contains(*k)));
        }
        self.layers.insert(name.to_string(), b.layer(whole, min_zoom));
    }

    /// The properties of the feature `id` of the source `name` (those in the tiles), as JSON; `null` when there is no such feature.
    /// The map draws the roads from other sources, so a click on a road asks for its properties here (`__rs_edge` is its id).
    pub fn props(&self, name: &str, id: u64) -> String {
        let Some(layer) = self.layers.get(name) else { return "null".into() };
        let Some(f) = layer.feats.iter().find(|f| f.id == Some(id)) else { return "null".into() };
        let m: Map<String, Value> = f.props.iter().map(|(k, v)| {
            let v = match &layer.vals[*v as usize] {
                Val::Str(s) => Value::from(&**s),
                Val::Bool(b) => Value::from(*b),
                Val::Int(i) => Value::from(*i),
                Val::UInt(u) => Value::from(*u),
                Val::Dbl(d) => Value::from(*d),
            };
            (layer.keys[*k as usize].clone(), v)
        }).collect();
        Value::Object(m).to_string()
    }

    /// The archive of every tile of the bounds `[min lon, min lat, max lon, max lat]` (an empty tile is left out), in zoom and then x, y
    /// order, as render's tiled page and export_style write it; `layers`: the tile layers of the metadata's vector_layers.
    pub fn archive(&self, bounds: [f64; 4], layers: &[String]) -> Option<Vec<u8>> {
        let mut w = pmtiles::Writer::default();
        let (lo, hi) = (merc_ll(bounds[0], bounds[1])?, merc_ll(bounds[2], bounds[3])?);
        for z in self.min_zoom..=self.max_zoom {
            let n = (1u64 << z) as f64;
            let last = (1u32 << z) - 1;
            let cell = |v: f64| ((v * n).floor().max(0.0) as u32).min(last);      // tiles.py's _tile_range
            let (x0, x1, y0, y1) = (cell(lo[0]), cell(hi[0]), cell(hi[1]), cell(lo[1]));
            for x in x0..=x1 {
                for y in y0..=y1 {
                    let t = self.tile(z, x, y);
                    if !t.is_empty() {
                        w.write_tile(pmtiles::tile_id(z, x, y), &pmtiles::gzip(&t));
                    }
                }
            }
        }
        let e7: Vec<i32> = bounds.iter().map(|v| (v * 1e7) as i32).collect();
        let place = pmtiles::Place { min_lon_e7: e7[0], min_lat_e7: e7[1], max_lon_e7: e7[2], max_lat_e7: e7[3],
                                     center_zoom: ((self.min_zoom + self.max_zoom) / 2) as u8,
                                     center_lon_e7: (e7[0] + e7[2]) / 2, center_lat_e7: (e7[1] + e7[3]) / 2 };
        let meta = serde_json::json!({"vector_layers": layers.iter().map(|n| serde_json::json!({"id": n, "fields": {}})).collect::<Vec<_>>()});
        w.finish(&place, &meta.to_string())
    }

    /// The tile z/x/y as a vector tile with a layer for each source that has features in it; empty when nothing is in it.
    pub fn tile(&self, z: u32, x: u32, y: u32) -> Vec<u8> {
        if z < self.min_zoom || z > self.max_zoom {
            return Vec::new();
        }
        let mut out = Vec::new();
        for (name, layer) in &self.layers {
            if z >= layer.min_zoom {
                out.extend(self.layer_tile(name, layer, z, x, y)); // a tile's layers are repeated fields: their bytes join
            }
        }
        out
    }

    fn layer_tile(&self, name: &str, layer: &Layer, z: u32, x: u32, y: u32) -> Vec<u8> {
        let n = (1u64 << z) as f64;
        let buffer = if layer.whole { 0.0 } else { self.buffer };
        let (x0, y0) = (x as f64 / n, y as f64 / n);
        // tiles.py: a feature is in the tiles its box touches; the buffer is for the clipping only
        let found = layer.tree.locate_in_envelope_intersecting(&AABB::from_corners([x0, y0], [x0 + 1.0 / n, y0 + 1.0 / n]));
        let mut hits: Vec<u32> = found.map(|h| h.data).collect();
        hits.sort_unstable(); // the order of the source: the drawing order of features in one layer
        // the tile's own units: (merc * 2^z - x) * EXTENT
        let to = |p: &P| [(p[0] * n - x as f64) * EXTENT, (p[1] * n - y as f64) * EXTENT];
        let (lo, hi) = (-buffer, EXTENT + buffer);
        let simplify = !layer.whole && z < self.max_zoom;
        let mut enc = Encoder::default();
        for i in hits {
            let f = &layer.feats[i as usize];
            let (kind, geometry) = match &f.geom {
                Geom::Points(ps) => {
                    let ps: Vec<[i32; 2]> =
                        ps.iter().map(to).filter(|p| p[0] >= 0.0 && p[0] < EXTENT && p[1] >= 0.0 && p[1] < EXTENT).map(round).collect();
                    (1, points_cmd(&ps))
                }
                Geom::Lines(ls) => {
                    let ls: Vec<Vec<P>> = ls.iter().map(|l| l.iter().map(to).collect()).collect();
                    (2, lines_cmd(&line_parts(ls, simplify, (!layer.whole).then_some((lo, hi)))))
                }
                Geom::Polygons(ps) => {
                    let mut rings = Vec::new();
                    for poly in ps {
                        for (k, r) in poly.iter().enumerate() {
                            let mut r = dedup(clip_ring(&r.iter().map(to).collect::<Vec<_>>(), lo, hi).into_iter().map(round));
                            if r.len() > 1 && r[0] == r[r.len() - 1] {
                                r.pop();
                            }
                            let a = area(&r);
                            if r.len() < 3 || a == 0 {
                                if k == 0 {
                                    break; // no outer ring: no polygon
                                }
                                continue;
                            }
                            // the outer ring has a positive area in the tile's units (y down), a hole a negative one
                            if (k == 0) != (a > 0) {
                                r.reverse();
                            }
                            rings.push(r);
                        }
                    }
                    (3, rings_cmd(&rings))
                }
            };
            if !geometry.is_empty() {
                enc.feature(f, kind, &geometry, &layer.keys);
            }
        }
        enc.finish(name, &layer.encoded)
    }
}

/// A layer made feature by feature: the keys in the order they come, and the box of each feature.
#[derive(Default)]
struct Builder {
    keys: Vec<String>,
    key_at: HashMap<String, u32>,
    vals: Vec<Val>,
    encoded: Vec<Vec<u8>>,
    val_at: HashMap<Vec<u8>, u32>,
    feats: Vec<Feat>,
    boxes: Vec<GeomWithData<Rectangle<P>, u32>>,
}

impl Builder {
    /// A feature without a point (bounds) is left out; a null value is not in the tiles.
    fn push<K: AsRef<str>>(&mut self, id: Option<u64>, g: Geom, props: impl Iterator<Item = (K, Value)>) {
        let Some((lo, hi)) = bounds(&g) else { return };
        let (keys, key_at, vals, encoded, val_at) = (&mut self.keys, &mut self.key_at, &mut self.vals, &mut self.encoded, &mut self.val_at);
        let props = props
            .filter_map(|(k, v)| {
                let v = val(&v)?;
                let m = encode(&v);
                let v = match val_at.get(&m) {
                    Some(&at) => at,
                    None => {
                        vals.push(v);
                        encoded.push(m.clone());
                        val_at.insert(m, vals.len() as u32 - 1);
                        vals.len() as u32 - 1
                    }
                };
                let at = match key_at.get(k.as_ref()) {
                    Some(&at) => at,
                    None => {
                        keys.push(k.as_ref().to_string());
                        key_at.insert(k.as_ref().to_string(), keys.len() as u32 - 1);
                        keys.len() as u32 - 1
                    }
                };
                Some((at, v))
            })
            .collect();
        self.boxes.push(GeomWithData::new(Rectangle::from_corners(lo, hi), self.feats.len() as u32));
        self.feats.push(Feat { id, geom: g, props });
    }

    fn layer(self, whole: bool, min_zoom: u32) -> Layer {
        Layer { keys: self.keys, vals: self.vals, encoded: self.encoded, feats: self.feats, tree: RTree::bulk_load(self.boxes), whole, min_zoom }
    }
}


/// The parts of a line (in the tile's units) in a tile: simplified to half a unit and none when shorter than that (tiles.py), then
/// clipped to the square [lo, hi]^2 when `clip` is given.
fn line_parts(mut ls: Vec<Vec<P>>, simplify: bool, clip: Option<(f64, f64)>) -> Vec<Vec<[i32; 2]>> {
    if simplify {
        ls = ls.iter().map(|l| douglas_peucker(l, 0.5)).collect();
    }
    // tiles.py: a line shorter than half a tile unit is left out at every zoom (a whole layer's lines are not checked)
    if clip.is_some() && ls.iter().map(|l| length(l)).sum::<f64>() < 0.5 {
        return Vec::new();
    }
    ls.into_iter()
        .flat_map(|l| match clip {
            Some((lo, hi)) => clip_line(&l, lo, hi),
            None => vec![l],
        })
        .map(|l| dedup(l.into_iter().map(round)))
        .filter(|l| l.len() >= 2)
        .collect()
}

fn length(l: &[P]) -> f64 {
    l.windows(2).map(|w| (w[1][0] - w[0][0]).hypot(w[1][1] - w[0][1])).sum()
}

/// The distance from p to the segment ab.
fn seg_dist(p: P, a: P, b: P) -> f64 {
    let d = [b[0] - a[0], b[1] - a[1]];
    let l2 = d[0] * d[0] + d[1] * d[1];
    let t = if l2 == 0.0 { 0.0 } else { (((p[0] - a[0]) * d[0] + (p[1] - a[1]) * d[1]) / l2).clamp(0.0, 1.0) };
    (p[0] - a[0] - t * d[0]).hypot(p[1] - a[1] - t * d[1])
}

/// Douglas-Peucker: the points of the line that keep it within `tol` of the original (shapely's simplify).
/// ponytail: no topology check (GEOS's preserve_topology also keeps a line from crossing itself); add it if a simplified road
/// crosses itself at a low zoom.
fn douglas_peucker(ps: &[P], tol: f64) -> Vec<P> {
    if ps.len() < 3 {
        return ps.to_vec();
    }
    let mut keep = vec![false; ps.len()];
    (keep[0], keep[ps.len() - 1]) = (true, true);
    let mut todo = vec![(0, ps.len() - 1)];
    while let Some((a, b)) = todo.pop() {
        let (mut far, mut at) = (0.0, a);
        for i in a + 1..b {
            let d = seg_dist(ps[i], ps[a], ps[b]);
            if d > far {
                (far, at) = (d, i);
            }
        }
        if far > tol {
            keep[at] = true;
            todo.push((a, at));
            todo.push((at, b));
        }
    }
    ps.iter().zip(keep).filter(|(_, k)| *k).map(|(p, _)| *p).collect()
}

fn round(p: P) -> [i32; 2] {
    [p[0].round() as i32, p[1].round() as i32]
}

fn dedup(ps: impl Iterator<Item = [i32; 2]>) -> Vec<[i32; 2]> {
    let mut out: Vec<[i32; 2]> = Vec::new();
    for p in ps {
        if out.last() != Some(&p) {
            out.push(p);
        }
    }
    out
}

/// Twice the signed area by the surveyor's formula.
fn area(r: &[[i32; 2]]) -> i64 {
    (0..r.len()).map(|i| {
        let (a, b) = (r[i], r[(i + 1) % r.len()]);
        a[0] as i64 * b[1] as i64 - b[0] as i64 * a[1] as i64
    }).sum()
}

/// The parts of a line inside the square [lo, hi]^2 (Liang-Barsky on each segment).
fn clip_line(ps: &[P], lo: f64, hi: f64) -> Vec<Vec<P>> {
    let mut out = Vec::new();
    let mut cur: Vec<P> = Vec::new();
    for w in ps.windows(2) {
        match clip_seg(w[0], w[1], lo, hi) {
            Some((a, b)) => {
                if cur.last() != Some(&a) {
                    if cur.len() >= 2 {
                        out.push(std::mem::take(&mut cur));
                    }
                    cur.clear();
                    cur.push(a);
                }
                cur.push(b);
                if b != w[1] {
                    out.push(std::mem::take(&mut cur)); // the line leaves the square here
                }
            }
            None => {
                if cur.len() >= 2 {
                    out.push(std::mem::take(&mut cur));
                }
                cur.clear();
            }
        }
    }
    if cur.len() >= 2 {
        out.push(cur);
    }
    out
}

fn clip_seg(a: P, b: P, lo: f64, hi: f64) -> Option<(P, P)> {
    let d = [b[0] - a[0], b[1] - a[1]];
    let (mut t0, mut t1) = (0.0f64, 1.0f64);
    for k in 0..2 {
        for (p, q) in [(-d[k], a[k] - lo), (d[k], hi - a[k])] {
            if p == 0.0 {
                if q < 0.0 {
                    return None;
                }
            } else {
                let t = q / p;
                if p < 0.0 {
                    t0 = t0.max(t);
                } else {
                    t1 = t1.min(t);
                }
            }
        }
    }
    if t0 > t1 {
        return None;
    }
    let at = |t: f64| if t == 0.0 { a } else if t == 1.0 { b } else { [a[0] + t * d[0], a[1] + t * d[1]] };
    Some((at(t0), at(t1)))
}

/// A ring cut to the square [lo, hi]^2 (Sutherland-Hodgman); the parts outside become the square's edge, which the map does not draw.
fn clip_ring(r: &[P], lo: f64, hi: f64) -> Vec<P> {
    let mut pts = r.to_vec();
    for (k, edge, keep_above) in [(0, lo, true), (0, hi, false), (1, lo, true), (1, hi, false)] {
        if pts.is_empty() {
            break;
        }
        let inside = |p: &P| if keep_above { p[k] >= edge } else { p[k] <= edge };
        let mut out = Vec::with_capacity(pts.len());
        for i in 0..pts.len() {
            let (a, b) = (pts[(i + pts.len() - 1) % pts.len()], pts[i]);
            if inside(&b) {
                if !inside(&a) {
                    out.push(cut(a, b, k, edge));
                }
                out.push(b);
            } else if inside(&a) {
                out.push(cut(a, b, k, edge));
            }
        }
        pts = out;
    }
    pts
}

fn cut(a: P, b: P, k: usize, edge: f64) -> P {
    let t = (edge - a[k]) / (b[k] - a[k]);
    let mut p = [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
    p[k] = edge;
    p
}

// --- the geometry commands (MoveTo 1, LineTo 2, ClosePath 7) with zigzag deltas ---

fn command(id: u32, count: usize) -> u32 {
    (id & 7) | ((count as u32) << 3)
}

fn zigzag(v: i32) -> u32 {
    ((v << 1) ^ (v >> 31)) as u32
}

struct Cursor(Vec<u32>, [i32; 2]);

impl Cursor {
    fn to(&mut self, p: [i32; 2]) {
        self.0.push(zigzag(p[0] - self.1[0]));
        self.0.push(zigzag(p[1] - self.1[1]));
        self.1 = p;
    }
}

fn points_cmd(ps: &[[i32; 2]]) -> Vec<u32> {
    let mut c = Cursor(Vec::new(), [0, 0]);
    if !ps.is_empty() {
        c.0.push(command(1, ps.len()));
        ps.iter().for_each(|&p| c.to(p));
    }
    c.0
}

fn lines_cmd(ls: &[Vec<[i32; 2]>]) -> Vec<u32> {
    let mut c = Cursor(Vec::new(), [0, 0]);
    for l in ls {
        c.0.push(command(1, 1));
        c.to(l[0]);
        c.0.push(command(2, l.len() - 1));
        l[1..].iter().for_each(|&p| c.to(p));
    }
    c.0
}

fn rings_cmd(rs: &[Vec<[i32; 2]>]) -> Vec<u32> {
    let mut c = Cursor(Vec::new(), [0, 0]);
    for r in rs {
        c.0.push(command(1, 1));
        c.to(r[0]);
        c.0.push(command(2, r.len() - 1));
        r[1..].iter().for_each(|&p| c.to(p));
        c.0.push(command(7, 1));
    }
    c.0
}

// --- protocol buffers: the tile with one layer ---

fn varint(out: &mut Vec<u8>, mut v: u64) {
    while v >= 0x80 {
        out.push((v as u8) | 0x80);
        v >>= 7;
    }
    out.push(v as u8);
}

fn bytes_field(out: &mut Vec<u8>, field: u32, data: &[u8]) {
    varint(out, ((field << 3) | 2) as u64);
    varint(out, data.len() as u64);
    out.extend_from_slice(data);
}

fn packed(out: &mut Vec<u8>, field: u32, vs: &[u32]) {
    let mut d = Vec::with_capacity(vs.len() * 2);
    vs.iter().for_each(|&v| varint(&mut d, v as u64));
    bytes_field(out, field, &d);
}

/// The bytes of a value's Value message in a tile.
fn encode(v: &Val) -> Vec<u8> {
    let mut m = Vec::new();
    match v {
        Val::Str(s) => bytes_field(&mut m, 1, s.as_bytes()),
        Val::Dbl(d) => {
            m.push((3 << 3) | 1);
            m.extend_from_slice(&d.to_le_bytes());
        }
        Val::Int(i) if *i < 0 => {
            m.push(6 << 3);
            varint(&mut m, ((*i << 1) ^ (*i >> 63)) as u64);
        }
        Val::Int(i) => {
            m.push(5 << 3);
            varint(&mut m, *i as u64);
        }
        Val::UInt(u) => {
            m.push(5 << 3);
            varint(&mut m, *u);
        }
        Val::Bool(b) => {
            m.push(7 << 3);
            m.push(*b as u8);
        }
    }
    m
}

/// One layer of a tile: its keys and values in the order they first come (the layer's numbers of them), and the features.
#[derive(Default)]
struct Encoder {
    features: Vec<u8>,
    keys: Vec<String>,
    key_at: HashMap<u32, u32>,
    values: Vec<u32>,
    value_at: HashMap<u32, u32>,
}

impl Encoder {
    fn feature(&mut self, f: &Feat, kind: u32, geometry: &[u32], names: &[String]) {
        let mut tags = Vec::with_capacity(f.props.len() * 2);
        for (k, v) in &f.props {
            let key = *self.key_at.entry(*k).or_insert_with(|| {
                self.keys.push(names[*k as usize].clone());
                self.keys.len() as u32 - 1
            });
            let at = *self.value_at.entry(*v).or_insert_with(|| {
                self.values.push(*v);
                self.values.len() as u32 - 1
            });
            tags.push(key);
            tags.push(at);
        }
        let mut msg = Vec::new();
        if let Some(id) = f.id {
            msg.push(1 << 3);
            varint(&mut msg, id);
        }
        packed(&mut msg, 2, &tags);
        msg.push(3 << 3);
        varint(&mut msg, kind as u64);
        packed(&mut msg, 4, geometry);
        bytes_field(&mut self.features, 2, &msg);
    }

    fn finish(self, name: &str, encoded: &[Vec<u8>]) -> Vec<u8> {
        if self.features.is_empty() {
            return Vec::new();
        }
        let mut layer = Vec::new();
        layer.push(15 << 3);
        varint(&mut layer, 2); // version
        bytes_field(&mut layer, 1, name.as_bytes());
        layer.extend_from_slice(&self.features);
        self.keys.iter().for_each(|k| bytes_field(&mut layer, 3, k.as_bytes()));
        self.values.iter().for_each(|&v| bytes_field(&mut layer, 4, &encoded[v as usize]));
        layer.push(5 << 3);
        varint(&mut layer, EXTENT as u64);
        let mut tile = Vec::with_capacity(layer.len() + 8);
        bytes_field(&mut tile, 3, &layer);
        tile
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn keys(k: &[&str]) -> HashSet<String> {
        k.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn a_line_across_the_tile_is_cut_at_the_buffer() {
        let parts = clip_line(&[[-1000.0, 100.0], [5000.0, 100.0], [5000.0, 6000.0]], -512.0, 4608.0);
        assert_eq!(parts, vec![vec![[-512.0, 100.0], [4608.0, 100.0]]]);
        let inside = clip_line(&[[10.0, 10.0], [20.0, 20.0], [30.0, 10.0]], -512.0, 4608.0);
        assert_eq!(inside, vec![vec![[10.0, 10.0], [20.0, 20.0], [30.0, 10.0]]]);
    }

    #[test]
    fn a_tile_has_the_feature_its_id_and_properties() {
        let mut t = Tiles::new(0, 15, 80.0);
        t.add("roads", json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": 7, "properties": {"name": "A", "lanes": 2, "w": 1.5, "bridge": true, "gone": null, "n": -3},
             "geometry": {"type": "LineString", "coordinates": [[1.0, 1.0], [10.0, 10.0]]}}]}}), &keys(&["name", "lanes", "w", "bridge", "gone", "n"]), false, 0);
        let tile = t.tile(0, 0, 0);
        assert!(!tile.is_empty());
        assert!(!t.tile(3, 4, 3).is_empty(), "the road is in tile 3/4/3");
        assert!(t.tile(3, 2, 5).is_empty(), "and not in a tile far from it");
        // the bytes have the layer's name, the keys and a string value, and no key for the null value
        let text = String::from_utf8_lossy(&tile);
        assert!(text.contains("roads") && text.contains("name") && text.contains("lanes") && !text.contains("gone"));
        // tiles.py: a feature's id is its index in its source (not its own "id")
        assert_eq!(t.props("roads", 0), r#"{"name":"A","lanes":2,"w":1.5,"bridge":true,"n":-3}"#);
        assert_eq!(t.props("roads", 7), "null");
    }

    #[test]
    fn the_outer_ring_has_a_positive_area() {
        let mut t = Tiles::new(0, 15, 80.0);
        // a square around (1, 1) degrees, counterclockwise in lon / lat (clockwise on the screen after y goes down)
        t.add("land", json!({"type": "geojson", "generateId": true, "data": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon",
             "coordinates": [[[0.5, 0.5], [1.5, 0.5], [1.5, 1.5], [0.5, 1.5], [0.5, 0.5]]]}}]}}), &keys(&[]), false, 0);
        let f = &t.layers["land"].feats[0];
        assert_eq!(f.id, Some(0));
        let Geom::Polygons(ps) = &f.geom else { panic!() };
        let r: Vec<[i32; 2]> = ps[0][0].iter().map(|p| round([p[0] * 4096.0 * 64.0, p[1] * 4096.0 * 64.0])).collect();
        assert!(area(&r) < 0, "lon / lat counterclockwise is negative in the tile's units");
        assert!(!t.tile(0, 0, 0).is_empty());
    }

    #[test]
    fn the_rules_of_tiles_py() {
        // below the last zoom: a bend of 0.4 units goes, a bend of 0.6 units stays, a line shorter than 0.5 units goes
        let bend = |h: f64| vec![vec![[0.0, 0.0], [50.0, h], [100.0, 0.0]]];
        assert_eq!(line_parts(bend(0.4), true, None), vec![vec![[0, 0], [100, 0]]]);
        assert_eq!(line_parts(bend(0.6), true, None).len(), 1);
        assert_eq!(line_parts(bend(0.6), true, None)[0].len(), 3);
        assert_eq!(line_parts(bend(0.4), false, None)[0].len(), 3, "the last zoom keeps every point");
        let short = || vec![vec![[0.0, 0.0], [0.4, 0.0]]];
        assert!(line_parts(short(), true, Some((-80.0, 4176.0))).is_empty());
        assert!(line_parts(short(), false, Some((-80.0, 4176.0))).is_empty(), "also at the last zoom");
        // a whole line keeps its points out of the tile, a clipped one ends at the buffer
        let long = || vec![vec![[0.0, 10.0], [4000.0, 10.0], [9000.0, 10.0]]];
        assert_eq!(line_parts(long(), false, None), vec![vec![[0, 10], [4000, 10], [9000, 10]]]);
        assert_eq!(line_parts(long(), false, Some((-80.0, 4176.0))), vec![vec![[0, 10], [4000, 10], [4176, 10]]]);
        // the zooms: no tile out of 6 to 15, no tile of a layer before its first zoom
        let fc = json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": 1, "properties": {}, "geometry": {"type": "LineString", "coordinates": [[1.0, 1.0], [1.01, 1.0]]}}]}});
        let mut t = Tiles::new(6, 15, 80.0);
        t.add("slots", fc, &keys(&[]), true, 14);
        let at = |z: u32| {
            let n = (1u64 << z) as f64;
            let [x, y] = merc(&json!([1.005, 1.0])).unwrap();
            t.tile(z, (x * n) as u32, (y * n) as u32)
        };
        assert!(at(13).is_empty() && at(16).is_empty() && !at(14).is_empty() && !at(15).is_empty());
    }
}
