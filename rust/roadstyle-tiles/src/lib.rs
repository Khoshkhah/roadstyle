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

pub mod buffer;
pub mod error;
pub mod pmtiles;
pub mod rules;
pub mod stage;

pub use error::Error;
use roadstyle_model::feature_table::FeatureTable;
use rstar::{primitives::GeomWithData, primitives::Rectangle, RTree, AABB};
use serde_json::{Map, Value};
use indexmap::IndexMap;
use std::collections::{HashMap, HashSet};

/// The tile's size in its own units.
pub const EXTENT: f64 = 4096.0;
/// The last zoom of a tile: MapLibre's last zoom (a map asks for no tile after it).
pub const MAX_ZOOM: u32 = 24;

/// The zooms `min_zoom` to `max_zoom` are tile zooms: from 0 to `MAX_ZOOM`, the first not after the last.
fn check_zooms(min_zoom: f64, max_zoom: f64) -> Result<(), Error> {
    if !(0.0 <= min_zoom && min_zoom <= max_zoom && max_zoom <= MAX_ZOOM as f64) {
        return Err(Error::Options(format!("the tile zooms are {min_zoom} to {max_zoom}: give zooms from 0 to {MAX_ZOOM}, the first not after the last")));
    }
    Ok(())
}
/// The name of the one vector source.
pub const SOURCE: &str = "roads";
/// The pieces' tile layer: the vector source's `promoteId` (`__rs_edge`, the road's row) is their feature id, so their tiles have no MVT
/// id (MapLibre does not read it there).
const PROMOTED: &str = "simple";

type P = [f64; 2];

enum Geom {
    Points(Vec<P>),
    Lines(Vec<Vec<P>>),
    Polygons(Vec<Vec<Vec<P>>>),
}

/// A value of a tile feature (the vector tile spec's value kinds that the tiles use).
/// A layer keeps `Val<'static>`; a property that is read borrows its text (no copy of a value that the layer has).
#[derive(Clone, PartialEq)]
pub enum Val<'a> {
    Str(std::borrow::Cow<'a, str>),
    Bool(bool),
    Int(i64),
    UInt(u64),
    Dbl(f64),
}

struct Feat {
    id: Option<u64>,
    /// the zooms [from, until) at which a layer of the style draws it (rules.rs; every zoom with no rules)
    from: f32,
    until: f32,
    geom: Geom,
    /// (key, value): the numbers of the layer's key and value
    props: Vec<(u32, u32)>,
    /// a feature that waits for its line and properties (`Tiles::add_waiting`): its road (`__rs_edge`) and the caller's tag
    wait: Option<(u64, u64)>,
}

/// The boxes of the features of one first tile zoom, and their tree, made when a tile first reads it.
struct Tree {
    first: u32,
    boxes: Vec<GeomWithData<Rectangle<P>, u32>>,
    // ponytail: the boxes stay after the tree is made (Tartu 4.5 MB); take them into the tree if the memory counts
    tree: std::sync::OnceLock<RTree<GeomWithData<Rectangle<P>, u32>>>,
}

impl Tree {
    fn get(&self) -> &RTree<GeomWithData<Rectangle<P>, u32>> {
        self.tree.get_or_init(|| RTree::bulk_load(self.boxes.clone()))
    }
}

/// A source made ready: its keys, its distinct values (each also as the bytes of its Value message in a tile, made once and not for
/// each tile: half of a tile's time was this), its features and their boxes.
struct Layer {
    keys: Vec<String>,
    vals: Vec<Val<'static>>,
    encoded: Vec<Vec<u8>>,
    feats: Vec<Feat>,
    /// one tree for each first tile zoom of its features (the first zoom that draws them, the last zoom for the rest), in the order of
    /// the zooms: a tile of zoom z reads only the trees of zoom z or less (Tartu z10: 4,422 features, not 114,182)
    trees: Vec<Tree>,
    /// the numbers of the keys and the values, kept while a feature waits (`Tiles::make` adds its properties)
    at: Option<(Numbers<String>, Numbers<Vec<u8>>)>,
    /// The features go whole into the tiles: not clipped and not simplified.
    whole: bool,
    min_zoom: u32,
    /// each feature id's place (audit R14: a click asks by id)
    by_id: HashMap<u64, u32>,
}

/// The numbers of a layer's keys or values (a fast hash: a tile looks up each property of each feature it makes).
type Numbers<K> = HashMap<K, u32, foldhash::fast::FixedState>;

/// The last tiles asked for, up to `TILE_CACHE_BYTES` (audit R14: a map asks for the same tiles again).
#[derive(Default)]
struct TileCache {
    tiles: HashMap<(u32, u32, u32), std::sync::Arc<Vec<u8>>>,
    order: std::collections::VecDeque<(u32, u32, u32)>,
    bytes: usize,
}

/// The bytes of the tile cache.
const TILE_CACHE_BYTES: usize = 64 << 20;

/// The sources of a style, ready to be cut into tiles: the layers in their order, the first and last zoom of the tiles (MapLibre
/// zooms the last one in), and the buffer around a tile in its units (wide lines, their offsets and the labels along them reach over
/// the tile's edge).
pub struct Tiles {
    layers: IndexMap<String, Layer>,
    /// the style's layers, for each source's first-zoom rules (`drawn_by`)
    style: Vec<Value>,
    min_zoom: u32,
    max_zoom: u32,
    /// the buffer of each zoom (index: the zoom), in tile units
    buffers: Vec<f64>,
    cache: std::sync::Mutex<TileCache>,
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

/// A line of longitude and latitude in Web Mercator (a point that is not finite is left out).
fn line_geom(c: &[[f64; 2]]) -> Geom {
    Geom::Lines(vec![c.iter().filter_map(|p| merc_ll(p[0], p[1])).collect()])
}

/// The properties that a line layer's tiles keep: every `__rs_*` one and those in `keep`, all of them when `whole` (tiles.py's tile_props).
fn kept(k: &str, keep: &HashSet<String>, whole: bool) -> bool {
    whole || k.starts_with(roadstyle_model::mark::PREFIX) || keep.contains(k)
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

/// A property's value as the tiles keep it: a JSON value, or a cell of the roads' Arrow columns (audit N5: no JSON copy of each cell).
pub trait TileValue {
    fn tile_val(&self) -> Option<Val<'_>>;
}

impl TileValue for Value {
    fn tile_val(&self) -> Option<Val<'_>> {
        val(self)
    }
}

impl TileValue for roadstyle_model::Cell<'_> {
    fn tile_val(&self) -> Option<Val<'_>> {
        use roadstyle_model::Cell;
        Some(match *self {
            Cell::Null => return None,
            Cell::Bool(b) => Val::Bool(b),
            // an integer past 2**53 - 1 as text, as every JSON form writes it
            Cell::Int(i) if i.unsigned_abs() > roadstyle_model::table::JS_MAX_SAFE_INT => Val::Str(i.to_string().into()),
            Cell::Int(i) => Val::Int(i),
            Cell::Float(f) if f.is_finite() => Val::Dbl(f),
            Cell::Float(_) => return None,
            Cell::Str(s) => Val::Str(s.into()),
            Cell::Json(v) => return val(v),
        })
    }
}

fn val(v: &Value) -> Option<Val<'_>> {
    Some(match v {
        Value::String(s) => Val::Str(s.as_str().into()),
        Value::Bool(b) => Val::Bool(*b),
        Value::Number(n) => match (n.as_i64(), n.as_u64()) {
            // an integer past 2**53 - 1 as text, as every JSON form writes it (JavaScript would round it; tiles.py's roads have text)
            (Some(i), _) if i.unsigned_abs() > roadstyle_model::table::JS_MAX_SAFE_INT => Val::Str(i.to_string().into()),
            (_, Some(u)) if u > roadstyle_model::table::JS_MAX_SAFE_INT => Val::Str(u.to_string().into()),
            (Some(i), _) => Val::Int(i),
            (_, Some(u)) => Val::UInt(u),
            _ => Val::Dbl(n.as_f64()?),
        },
        Value::Null | Value::Array(_) | Value::Object(_) => return None, // tiles.py (mapbox_vector_tile) leaves out a list or an object
    })
}

impl Val<'_> {
    /// The value with its own text (a layer keeps it).
    fn owned(&self) -> Val<'static> {
        match self {
            Val::Str(s) => Val::Str(std::borrow::Cow::Owned(s.to_string())),
            Val::Bool(b) => Val::Bool(*b),
            Val::Int(i) => Val::Int(*i),
            Val::UInt(u) => Val::UInt(*u),
            Val::Dbl(d) => Val::Dbl(*d),
        }
    }
}

fn json_of(v: &Val<'_>) -> Value {
    match v {
        Val::Str(s) => Value::from(&**s),
        Val::Bool(b) => Value::from(*b),
        Val::Int(i) => Value::from(*i),
        Val::UInt(u) => Value::from(*u),
        Val::Dbl(d) => Value::from(*d),
    }
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
    /// The tiles of the zooms `min_zoom` to `max_zoom` (see `check_zooms`), with `buffer` (tile units, 0 or more) round each tile.
    pub fn new(min_zoom: u32, max_zoom: u32, buffer: f64) -> Result<Tiles, Error> {
        check_zooms(min_zoom as f64, max_zoom as f64)?;
        Tiles::with_buffers(min_zoom, max_zoom, vec![buffer; max_zoom as usize + 1])
    }

    /// `new` with a buffer for each zoom (`buffers[z]`, tile units, 0 or more; one for each zoom 0 to `max_zoom`).
    pub fn with_buffers(min_zoom: u32, max_zoom: u32, buffers: Vec<f64>) -> Result<Tiles, Error> {
        check_zooms(min_zoom as f64, max_zoom as f64)?;
        if let Some(b) = buffers.iter().find(|b| !(**b >= 0.0 && b.is_finite())) {
            return Err(Error::Options(format!("the tile buffer is {b}: give 0 or more")));
        }
        if buffers.len() != max_zoom as usize + 1 {
            return Err(Error::Options(format!("{} tile buffers for the zooms 0 to {max_zoom}", buffers.len())));
        }
        Ok(Tiles { layers: IndexMap::new(), style: Vec::new(), min_zoom, max_zoom, buffers, cache: Default::default() })
    }

    /// The style's layers: a source added after this leaves out of a tile each feature that every layer drawing it hides at every zoom
    /// of that tile (rules.rs: the class minzoom, `casing.drop_below_px`).
    pub fn drawn_by(&mut self, layers: &[Value]) {
        self.style = layers.iter().map(|l| serde_json::json!({"source": l["source"], "source-layer": l["source-layer"], "filter": l["filter"]})).collect();
    }

    fn builder(&self, name: &str) -> Builder {
        Builder { rules: rules::ZoomRules::of(&self.style, name), ..Default::default() }
    }

    /// A new layer: the caches of the old tiles go.
    fn put(&mut self, name: &str, layer: Layer) {
        self.layers.insert(name.to_string(), layer);
        *self.cache.get_mut().unwrap() = TileCache::default();
    }

    /// Add a GeoJSON source of the style (`{"type": "geojson", "data": FeatureCollection, ...}`) as the layer `name`, and free its
    /// tree. The properties in `keep` and every `__rs_*` property go into the tiles, all of a whole layer's (tiles.py's tile_props). `whole`: see the module; `min_zoom`: the layer's first zoom.
    pub fn add(&mut self, name: &str, source: &Value, keep: &HashSet<String>, whole: bool, min_zoom: u32) {
        let empty = Map::new();
        let mut b = self.builder(name);
        for (i, f) in source["data"]["features"].as_array().into_iter().flatten().enumerate() {
            let Some(g) = f.get("geometry").and_then(geom) else { continue };
            let id = Some(i as u64); // tiles.py: a feature's id is its index in its source
            let props = f["properties"].as_object().unwrap_or(&empty);
            // tiles.py's tile_props: a whole layer (keep=None there) all its properties, else `keep` and every __rs_*
            b.push(id, g, props.iter().filter(|(k, _)| whole || k.starts_with(roadstyle_model::mark::PREFIX) || keep.contains(k.as_str())).map(|(k, v)| (k.as_str(), v.clone())));
        }
        self.put(name, b.layer(whole, min_zoom, self.max_zoom));
    }

    /// Add a typed table of features (a base-map layer, audit R10) as the layer `name`, as `add` adds the same features as GeoJSON: each
    /// feature's id is its row, and its properties are the keys of its GeoJSON feature (`FeatureTable::has_key`).
    pub fn add_features(&mut self, name: &str, t: &FeatureTable, keep: &HashSet<String>, whole: bool, min_zoom: u32) {
        use roadstyle_model::feature_table::GeomType;
        let g = t.geometries_of();
        let names: Vec<&str> = t.names().iter().map(String::as_str).filter(|k| whole || k.starts_with(roadstyle_model::mark::PREFIX) || keep.contains(*k)).collect();
        let mut b = self.builder(name);
        for row in 0..t.len() {
            let Some(kind) = g.kind(row) else { continue };
            let pts = |r: &[[f64; 2]]| r.iter().filter_map(|p| merc_ll(p[0], p[1])).collect::<Vec<P>>();
            let geom = match kind {
                // a point that is not finite is null in GeoJSON, and `add` leaves that feature out
                GeomType::Point => match g.parts(row).next().and_then(|mut r| r.next()).and_then(|r| r.first()).and_then(|p| merc_ll(p[0], p[1])) {
                    Some(p) => Geom::Points(vec![p]),
                    None => continue,
                },
                GeomType::MultiPoint => Geom::Points(g.parts(row).flat_map(|mut r| r.next().map(pts)).flatten().collect()),
                GeomType::LineString | GeomType::MultiLineString => Geom::Lines(g.parts(row).flat_map(|r| r.map(pts)).collect()),
                GeomType::Polygon | GeomType::MultiPolygon => Geom::Polygons(g.parts(row).map(|r| r.map(pts).collect()).collect()),
            };
            let props = names.iter().filter(|k| t.has_key(row, k)).filter_map(|k| t.get(row, k).map(|c| (*k, c)));
            b.push(Some(row as u64), geom, props);
        }
        self.put(name, b.layer(whole, min_zoom, self.max_zoom));
    }

    /// Add a source of typed features (roads, simple), as `add` adds its JSON.
    pub fn add_typed(&mut self, name: &str, source: roadstyle_model::props::Source, keep: &HashSet<String>, whole: bool, min_zoom: u32) {
        self.add_lines(name, source.feats.into_iter().map(|f| (f.coords, f.props.into_iter())), keep, whole, min_zoom);
    }

    /// A layer of lines, each with its properties (a feature's id is its index; a feature with no line is left out, and keeps its
    /// index). The properties are the `__rs_*` ones and those in `keep` (all of them when `whole`).
    pub fn add_lines<L, K, V, P>(&mut self, name: &str, feats: impl Iterator<Item = (Option<L>, P)>, keep: &HashSet<String>, whole: bool, min_zoom: u32)
    where L: AsRef<[[f64; 2]]>, K: AsRef<str>, V: TileValue, P: Iterator<Item = (K, V)> {
        let mut b = self.builder(name);
        for (i, (c, props)) in feats.enumerate() {
            let Some(c) = c else { continue };
            b.push(Some(i as u64), line_geom(c.as_ref()), props.filter(|(k, _)| kept(k.as_ref(), keep, whole)));
        }
        self.put(name, b.layer(whole, min_zoom, self.max_zoom));
    }

    /// The properties that the first-zoom rules of the layer `name` read (rules.rs), for `add_waiting`.
    pub fn rule_keys(&self, name: &str) -> Vec<String> {
        rules::ZoomRules::of(&self.style, name).keys().to_vec()
    }

    /// A layer of lines as add_lines makes it, but each feature waits for its properties: now only its box and its first zoom are
    /// made, from its line and `rule_props` (the properties of `rule_keys`; a tile has the same features as add_lines' tiles). Each
    /// feature has its road (`__rs_edge`, for replace_lines) and a tag of the caller's. A tile asks `waiting`, and `make` gives those
    /// features their properties, before `tile`; `props` and `archive` read only the features that were made.
    pub fn add_waiting<L, K, V, P>(&mut self, name: &str, feats: impl Iterator<Item = (Option<L>, P, u64, u64)>, keep: &HashSet<String>, whole: bool,
                                   min_zoom: u32)
    where L: AsRef<[[f64; 2]]>, K: AsRef<str>, V: TileValue, P: Iterator<Item = (K, V)> {
        let mut b = self.builder(name);
        for (i, (c, rule_props, road, tag)) in feats.enumerate() {
            let Some(c) = c else { continue };
            b.wait(i as u64, line_geom(c.as_ref()), rule_props.filter(|(k, _)| kept(k.as_ref(), keep, whole)), (road, tag));
        }
        self.put(name, b.layer(whole, min_zoom, self.max_zoom));
    }

    /// The features of the layer `name` that the tile z/x/y has and that wait (`add_waiting`): each feature's place and tag.
    pub fn waiting(&self, name: &str, z: u32, x: u32, y: u32) -> Vec<(u32, u64)> {
        let Some(layer) = self.layers.get(name).filter(|l| l.at.is_some() && z >= self.min_zoom && z <= self.max_zoom && z >= l.min_zoom) else { return Vec::new() };
        layer.hits(z, x, y, self.pad(layer, z)).into_iter().filter_map(|i| layer.feats[i as usize].wait.map(|(_, tag)| (i, tag))).collect()
    }

    /// Give waiting features of the layer `name` their line and properties (`keep`, `whole`: add_waiting's): each as (place, line,
    /// properties). The line must be the one that add_waiting had (its box and first zoom stay).
    pub fn make<L, K, V, P>(&mut self, name: &str, feats: impl Iterator<Item = (u32, L, P)>, keep: &HashSet<String>, whole: bool)
    where L: AsRef<[[f64; 2]]>, K: AsRef<str>, V: TileValue, P: Iterator<Item = (K, V)> {
        let Some(layer) = self.layers.get_mut(name) else { return };
        let Some((key_at, val_at)) = layer.at.take() else { return };
        let mut b = Builder { keys: std::mem::take(&mut layer.keys), key_at, vals: std::mem::take(&mut layer.vals),
                              encoded: std::mem::take(&mut layer.encoded), val_at, ..Default::default() };
        for (i, c, props) in feats {
            let (props, ..) = b.intern(props.filter(|(k, _)| kept(k.as_ref(), keep, whole)));
            let f = &mut layer.feats[i as usize];
            (f.geom, f.props, f.wait) = (line_geom(c.as_ref()), props, None);
        }
        (layer.keys, layer.vals, layer.encoded) = (b.keys, b.vals, b.encoded);
        layer.at = layer.feats.iter().any(|f| f.wait.is_some()).then_some((b.key_at, b.val_at));
    }

    /// Replace the features of some roads in the line layer `name` (one that add_lines made): the features whose `__rs_edge` is in
    /// `edges` go, and `feats` come with the layer's rules (`keep`, `whole`, as add_lines). The new features' ids go on after the layer's
    /// last. Only this layer's box trees are made again (one for each first zoom), and the cached tiles go. Returns how many features went.
    pub fn replace_lines<L, K, V, P>(&mut self, name: &str, edges: &HashSet<u64>, feats: impl Iterator<Item = (Option<L>, P)>, keep: &HashSet<String>,
                                     whole: bool) -> Result<usize, Error>
    where L: AsRef<[[f64; 2]]>, K: AsRef<str>, V: TileValue, P: Iterator<Item = (K, V)> {
        let rules = rules::ZoomRules::of(&self.style, name);
        let layer = self.layers.get_mut(name).ok_or_else(|| Error::Options(format!("replace: the tiles have no layer {name}")))?;
        let edge = layer.keys.iter().position(|k| k == roadstyle_model::mark::Mark::Edge.name()).map(|k| k as u32);
        // ponytail: one pass over the features' keys (no index of each road's features); an index if a large area is slow
        let mut gone = vec![false; layer.feats.len()];
        let mut n = 0;
        for (i, f) in layer.feats.iter_mut().enumerate() {
            let e = f.props.iter().find(|(k, _)| Some(*k) == edge).and_then(|(_, v)| match layer.vals[*v as usize] { Val::Int(x) => u64::try_from(x).ok(), Val::UInt(x) => Some(x), _ => None });
            if e.or(f.wait.map(|w| w.0)).is_some_and(|e| edges.contains(&e)) {
                (gone[i], f.id, f.geom, f.props, f.wait) = (true, None, Geom::Lines(Vec::new()), Vec::new(), None);
                n += 1;
            }
        }
        let first = layer.feats.len() as u64;
        let boxes = layer.trees.iter().flat_map(|t| &t.boxes).filter(|h| !gone[h.data as usize])
            .map(|h| (layer.feats[h.data as usize].from, *h)).collect();
        let keys = std::mem::take(&mut layer.keys);
        let encoded = std::mem::take(&mut layer.encoded);
        let (key_at, val_at) = layer.at.take().unwrap_or_else(|| (keys.iter().enumerate().map(|(i, k)| (k.clone(), i as u32)).collect(),
                                                                  encoded.iter().enumerate().map(|(i, m)| (m.clone(), i as u32)).collect()));
        let mut b = Builder { key_at, val_at, keys, encoded, vals: std::mem::take(&mut layer.vals), feats: std::mem::take(&mut layer.feats), boxes, rules, last: Vec::new(), scratch: Vec::new() };
        for (j, (c, props)) in feats.enumerate() {
            let Some(c) = c else { continue };
            b.push(Some(first + j as u64), line_geom(c.as_ref()), props.filter(|(k, _)| kept(k.as_ref(), keep, whole)));
        }
        let min_zoom = layer.min_zoom;
        *layer = b.layer(whole, min_zoom, self.max_zoom);      // the trees by first zoom again
        *self.cache.get_mut().unwrap() = TileCache::default();
        Ok(n)
    }

    /// The properties of the feature `id` of the source `name` (those in the tiles), as JSON; `null` when there is no such feature.
    /// The map draws the roads from other sources, so a click on a road asks for its properties here (`__rs_edge` is its id).
    pub fn props(&self, name: &str, id: u64) -> String {
        let Some(layer) = self.layers.get(name) else { return "null".into() };
        let Some(f) = layer.by_id.get(&id).map(|&i| &layer.feats[i as usize]) else { return "null".into() };
        let m: Map<String, Value> = f.props.iter().map(|(k, v)| (layer.keys[*k as usize].clone(), json_of(&layer.vals[*v as usize]))).collect();
        Value::Object(m).to_string()
    }

    /// The archive of every tile of the bounds `[min lon, min lat, max lon, max lat]` (an empty tile is left out), in zoom and then x, y
    /// order, as render's tiled page and export_style write it; `layers`: the tile layers of the metadata's vector_layers.
    pub fn archive(&self, bounds: [f64; 4], layers: &[String]) -> Result<Vec<u8>, Error> {
        let mut w = pmtiles::Writer::default();
        let ll = |lon, lat| merc_ll(lon, lat).ok_or_else(|| Error::Options(format!("the archive's bounds {bounds:?} are not longitude and latitude")));
        let (lo, hi) = (ll(bounds[0], bounds[1])?, ll(bounds[2], bounds[3])?);
        for z in self.min_zoom..=self.max_zoom {
            let n = (1u64 << z) as f64;
            let last = (1u32 << z) - 1;
            let cell = |v: f64| ((v * n).floor().max(0.0) as u32).min(last);      // tiles.py's _tile_range
            // the bounds and the zoom's buffer: a tile whose buffer has a road's stroke has the road (tiles.py: the padded boxes)
            let b = self.buffers[z as usize] / EXTENT / n;
            let (x0, x1, y0, y1) = (cell(lo[0] - b), cell(hi[0] + b), cell(hi[1] - b), cell(lo[1] + b));
            for x in x0..=x1 {
                for y in y0..=y1 {
                    let t = self.build(z, x, y);       // each tile once: the cache is for a map that asks again (review 4, D9)
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
        w.finish(&place, &meta.to_string()).ok_or(Error::Empty)
    }

    /// The box of every feature `[min lon, min lat, max lon, max lat]` (None: no feature), as an archive's bounds.
    pub fn bounds(&self) -> Option<[f64; 4]> {
        use rstar::Envelope;
        use rstar::RTreeObject;
        let boxes: Vec<AABB<P>> = self.layers.values().flat_map(|l| &l.trees).flat_map(|t| &t.boxes).map(|b| b.envelope()).collect();
        let b = boxes.into_iter().reduce(|a, b| a.merged(&b))?;
        let (lo, hi) = (b.lower(), b.upper());
        let lon = |x: f64| x * 360.0 - 180.0;
        let lat = |y: f64| (std::f64::consts::PI * (1.0 - 2.0 * y)).sinh().atan().to_degrees();
        Some([lon(lo[0]), lat(hi[1]), lon(hi[0]), lat(lo[1])])
    }

    /// The tile layers, in their order.
    pub fn layer_names(&self) -> Vec<String> {
        self.layers.iter().filter(|(_, l)| !l.trees.is_empty()).map(|(k, _)| k.clone()).collect()      // a layer with no feature is none
    }

    /// The tile z/x/y, made again (`tile` with no cache): for a walk that asks for each tile once (the archive, a folder of tiles).
    pub fn build(&self, z: u32, x: u32, y: u32) -> Vec<u8> {
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

    /// The first and the last zoom of the tiles.
    pub fn zooms(&self) -> (u32, u32) {
        (self.min_zoom, self.max_zoom)
    }

    /// The tile z/x/y as a vector tile with a layer for each source that has features in it; empty when nothing is in it. The last
    /// tiles that a map asked for are kept (64 MB), as a map asks for the same tiles again.
    pub fn tile(&self, z: u32, x: u32, y: u32) -> Vec<u8> {
        if z < self.min_zoom || z > self.max_zoom {
            return Vec::new();
        }
        if let Some(t) = self.cache.lock().unwrap().tiles.get(&(z, x, y)) {
            return t.to_vec();
        }
        let out = self.build(z, x, y);
        let mut c = self.cache.lock().unwrap();
        c.bytes += out.len();
        c.tiles.insert((z, x, y), std::sync::Arc::new(out.clone()));
        c.order.push_back((z, x, y));
        while c.bytes > TILE_CACHE_BYTES {
            let Some(old) = c.order.pop_front() else { break };
            if let Some(t) = c.tiles.remove(&old) {
                c.bytes -= t.len();
            }
        }
        out
    }

    /// The buffer round a tile of zoom `z` of `layer`, in tile units: none for a whole layer (its features go whole into the tiles
    /// they touch).
    fn pad(&self, layer: &Layer, z: u32) -> f64 {
        if layer.whole { 0.0 } else { self.buffers[z as usize] }
    }

    fn layer_tile(&self, name: &str, layer: &Layer, z: u32, x: u32, y: u32) -> Vec<u8> {
        let n = (1u64 << z) as f64;
        let buffer = self.pad(layer, z);
        let hits = layer.hits(z, x, y, buffer);
        // the tile's own units: (merc * 2^z - x) * EXTENT
        let to = |p: &P| [(p[0] * n - x as f64) * EXTENT, (p[1] * n - y as f64) * EXTENT];
        let (lo, hi) = (-buffer, EXTENT + buffer);
        let simplify = !layer.whole && z < self.max_zoom;
        let tiny = name == PROMOTED && simplify;
        let mut made: Vec<(&Feat, u32, Vec<u32>, Vec<Vec<[i32; 2]>>)> = Vec::new();
        for i in hits {
            let f = &layer.feats[i as usize];
            debug_assert!(f.wait.is_none(), "a tile of features that wait: make them first (Tiles::waiting)");
            debug_assert!(z == self.max_zoom || ((z + 1) as f32) > f.from, "the trees give only the features drawn at zoom {z}");
            let (kind, geometry) = match &f.geom {
                Geom::Points(ps) => {
                    let ps: Vec<[i32; 2]> =
                        ps.iter().map(to).filter(|p| p[0] >= 0.0 && p[0] < EXTENT && p[1] >= 0.0 && p[1] < EXTENT).map(round).collect();
                    (1, points_cmd(&ps))
                }
                Geom::Lines(ls) => {
                    // ponytail: simplified for each tile (in the tile's units, tiles.py's rule); a cache for each (feature, zoom) was slower
                    // on Tartu (most lines lie in one tile of a zoom), so the tile bytes are cached instead
                    let ls: Vec<Vec<P>> = ls.iter().map(|l| {
                        let l: Vec<P> = l.iter().map(to).collect();
                        if simplify { douglas_peucker_kept(&l, 0.5).iter().map(|&j| l[j as usize]).collect() } else { l }
                    }).collect();
                    let parts = line_parts(ls, (!layer.whole).then_some((lo, hi)));
                    if tiny {
                        made.push((f, 2, lines_cmd(&parts), parts));
                        continue;
                    }
                    (2, lines_cmd(&parts))
                }
                Geom::Polygons(ps) => {
                    let mut rings = Vec::new();
                    for poly in ps {
                        for (k, r) in poly.iter().enumerate() {
                            // tiles.py: a whole layer's polygon goes into every tile its box touches as it is, not clipped
                            let r: Vec<P> = r.iter().map(to).collect();
                            let mut r = dedup(if layer.whole { r } else { clip_ring(&r, lo, hi) }.into_iter().map(round));
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
                made.push((f, kind, geometry, Vec::new()));
            }
        }
        if tiny {
            drop_tiny(layer, &mut made);
        }
        let mut enc = Encoder::default();
        for (f, kind, geometry, _) in &made {
            if !geometry.is_empty() {
                enc.feature(f, *kind, geometry, &layer.keys, name != PROMOTED);
            }
        }
        enc.finish(name, &layer.encoded)
    }
}

impl Layer {
    /// The features in the tile z/x/y and its buffer (`buffer`, tile units) (of the trees of zoom z or less), in the order of the
    /// source: the drawing order of features in one layer. A feature out of the tile whose box is in the buffer is in the tile: its
    /// stroke can reach into it (tiles.py took only the features whose box touches the tile).
    fn hits(&self, z: u32, x: u32, y: u32, buffer: f64) -> Vec<u32> {
        let n = (1u64 << z) as f64;
        let b = buffer / EXTENT;
        let (x0, y0) = ((x as f64 - b) / n, (y as f64 - b) / n);
        let tile = AABB::from_corners([x0, y0], [x0 + (1.0 + 2.0 * b) / n, y0 + (1.0 + 2.0 * b) / n]);
        let trees = self.trees.iter().take_while(|t| t.first <= z);
        // a feature that no layer draws at a zoom of this tile (zoom z up to z + 1) is left out: its last zoom is not after z
        let mut hits: Vec<u32> = trees.flat_map(|t| t.get().locate_in_envelope_intersecting(&tile)).map(|h| h.data)
            .filter(|&i| self.feats[i as usize].until > z as f32).collect();
        hits.sort_unstable();
        hits
    }
}

/// A layer made feature by feature: the keys in the order they come, and the box of each feature.
#[derive(Default)]
struct Builder {
    keys: Vec<String>,
    key_at: Numbers<String>,
    vals: Vec<Val<'static>>,
    encoded: Vec<Vec<u8>>,
    val_at: Numbers<Vec<u8>>,
    feats: Vec<Feat>,
    boxes: Vec<(f32, GeomWithData<Rectangle<P>, u32>)>,
    rules: rules::ZoomRules,
    /// the numbers of the last feature's properties, by place: the pieces of one road come one after another and have most of their
    /// properties the same, which then take their numbers with no lookup
    last: Vec<(u32, u32)>,
    /// a value's bytes, to look it up with no new buffer
    scratch: Vec<u8>,
}

impl Builder {
    /// A feature without a point (bounds) is left out; a null value is not in the tiles.
    fn push<K: AsRef<str>, V: TileValue>(&mut self, id: Option<u64>, g: Geom, props: impl Iterator<Item = (K, V)>) {
        let Some((lo, hi)) = bounds(&g) else { return };
        let (props, from, until) = self.intern(props);
        self.boxes.push((from, GeomWithData::new(Rectangle::from_corners(lo, hi), self.feats.len() as u32)));
        self.feats.push(Feat { id, from, until, geom: g, props, wait: None });
    }

    /// A feature that waits for its line and properties (`Tiles::add_waiting`): its box and its first zoom, from `rule_props`.
    fn wait<K: AsRef<str>, V: TileValue>(&mut self, id: u64, g: Geom, rule_props: impl Iterator<Item = (K, V)>, wait: (u64, u64)) {
        let Some((lo, hi)) = bounds(&g) else { return };
        let (from, until) = if self.rules.is_empty() { (0.0, f32::INFINITY) } else {
            // the values that `intern` reads
            let read = rule_props.filter(|(k, _)| self.rules.reads(k.as_ref())).filter_map(|(k, v)| Some((k.as_ref().to_string(), json_of(&v.tile_val()?)))).collect();
            let (a, b) = self.rules.span(&read);
            (a as f32, b as f32)
        };
        self.boxes.push((from, GeomWithData::new(Rectangle::from_corners(lo, hi), self.feats.len() as u32)));
        self.feats.push(Feat { id: Some(id), from, until, geom: Geom::Lines(Vec::new()), props: Vec::new(), wait: Some(wait) });
    }

    /// The numbers of the properties' keys and values (a key or a value seen first gets the next number), and the first zoom that
    /// the rules give them.
    fn intern<K: AsRef<str>, V: TileValue>(&mut self, props: impl Iterator<Item = (K, V)>) -> (Vec<(u32, u32)>, f32, f32) {
        let (keys, key_at, vals, encoded, val_at, scratch) = (&mut self.keys, &mut self.key_at, &mut self.vals, &mut self.encoded, &mut self.val_at, &mut self.scratch);
        let (rules, last) = (&self.rules, &self.last);
        let mut read = Map::new();        // the values that the first-zoom rules read
        let mut j = 0;
        let props: Vec<(u32, u32)> = props
            .filter_map(|(k, v)| {
                let v = v.tile_val()?;
                if rules.reads(k.as_ref()) {
                    read.insert(k.as_ref().to_string(), json_of(&v));
                }
                if v == Val::Bool(false) && k.as_ref().starts_with(roadstyle_model::mark::PREFIX) {
                    return None; // a false flag: every reader of a __rs_* flag takes a missing key as false (to-boolean, a truthy check)
                }
                j += 1;
                if let Some(&(at, n)) = last.get(j - 1).filter(|(at, n)| keys[*at as usize] == k.as_ref() && vals[*n as usize] == v) {
                    return Some((at, n));        // the key and the value of the last feature's property in this place
                }
                scratch.clear();
                encode_into(&v, scratch);
                let v = match val_at.get(scratch.as_slice()) {
                    Some(&at) => at,
                    None => {
                        vals.push(v.owned());
                        encoded.push(scratch.clone());
                        val_at.insert(scratch.clone(), vals.len() as u32 - 1);
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
        self.last.clone_from(&props);
        let (from, until) = if rules.is_empty() { (0.0, f32::INFINITY) } else { let (a, b) = rules.span(&read); (a as f32, b as f32) };
        (props, from, until)
    }

    fn layer(self, whole: bool, min_zoom: u32, max_zoom: u32) -> Layer {
        let by_id = self.feats.iter().enumerate().filter_map(|(i, f)| f.id.map(|id| (id, i as u32))).rev().collect();      // the first of an id
        // the first tile zoom z of a feature: a tile of zoom z < max_zoom has it when z + 1 > from (a layer draws it in the zooms of
        // that tile); the tiles of max_zoom have every feature (MapLibre scales them up for every zoom after it)
        let mut by_first: std::collections::BTreeMap<u32, Vec<_>> = Default::default();
        for (from, b) in self.boxes {
            by_first.entry((from.floor().max(0.0) as u32).min(max_zoom)).or_default().push(b);
        }
        let trees = by_first.into_iter().map(|(first, boxes)| Tree { first, boxes, tree: Default::default() }).collect();
        let at = self.feats.iter().any(|f| f.wait.is_some()).then_some((self.key_at, self.val_at));
        Layer { keys: self.keys, vals: self.vals, encoded: self.encoded, feats: self.feats, trees, at, whole, min_zoom, by_id }
    }
}


/// 1 px of a 512 px tile, in tile units.
const PX: f64 = EXTENT / 512.0;

/// Rule B (docs/design/tile_v2_plan.md, step 3b), for the pieces of a tile below the last zoom: a road whose pieces together are under
/// 1 px is left out (its casing and its fill each count: the longer one decides), unless it goes out of the tile (its length here is
/// a cut); and a casing end piece (`__rs_seam`, with or without lap) under 1 px is left out. Every fill and every casing body stays.
fn drop_tiny(layer: &Layer, made: &mut Vec<(&Feat, u32, Vec<u32>, Vec<Vec<[i32; 2]>>)>) {
    let key = |k: &str| layer.keys.iter().position(|x| x == k).map(|k| k as u32);
    let (Some(edge), kind) = (key("__rs_edge"), key("__rs_k")) else { return };
    let seam = key("__rs_seam");
    let len = |parts: &Vec<Vec<[i32; 2]>>| parts.iter().map(|l| length(&l.iter().map(|p| [p[0] as f64, p[1] as f64]).collect::<Vec<P>>())).sum::<f64>();
    let get = |f: &Feat, k: u32| f.props.iter().find(|p| p.0 == k).map(|p| p.1);
    // by road (the value's number, one for each distinct value): the length of each kind of piece, and whether a point is out of the tile
    let mut roads: HashMap<u32, (HashMap<Option<u32>, f64>, bool)> = HashMap::new();
    let lens: Vec<f64> = made.iter().map(|m| len(&m.3)).collect();
    for (m, l) in made.iter().zip(&lens) {
        let Some(e) = get(m.0, edge) else { continue };
        let r = roads.entry(e).or_default();
        *r.0.entry(kind.and_then(|k| get(m.0, k))).or_default() += l;
        r.1 |= m.3.iter().flatten().any(|p| p[0] < 0 || p[0] > EXTENT as i32 || p[1] < 0 || p[1] > EXTENT as i32);
    }
    let mut lens = lens.into_iter();
    made.retain(|m| {
        let l = lens.next().unwrap();
        let tiny_road = get(m.0, edge).is_some_and(|e| { let r = &roads[&e]; !r.1 && r.0.values().all(|&v| v < PX) });
        !tiny_road && !(seam.is_some_and(|s| get(m.0, s).is_some()) && l < PX)
    });
}

/// The parts of a line (in the tile's units, simplified: `Tiles::kept`) in a tile: none when shorter than half a unit (tiles.py), then
/// clipped to the square [lo, hi]^2 when `clip` is given.
fn line_parts(ls: Vec<Vec<P>>, clip: Option<(f64, f64)>) -> Vec<Vec<[i32; 2]>> {
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
/// The places of the points that Douglas-Peucker keeps (to `tol`), in their order.
fn douglas_peucker_kept(ps: &[P], tol: f64) -> Vec<u32> {
    if ps.len() < 3 {
        return (0..ps.len() as u32).collect();
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
    keep.iter().enumerate().filter(|(_, k)| **k).map(|(i, _)| i as u32).collect()
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

/// The bytes of a value's Value message in a tile, written to `m`.
fn encode_into(v: &Val<'_>, m: &mut Vec<u8>) {
    match v {
        Val::Str(s) => bytes_field(m, 1, s.as_bytes()),
        Val::Dbl(d) => {
            m.push((3 << 3) | 1);
            m.extend_from_slice(&d.to_le_bytes());
        }
        Val::Int(i) if *i < 0 => {
            m.push(6 << 3);
            varint(m, ((*i << 1) ^ (*i >> 63)) as u64);
        }
        Val::Int(i) => {
            m.push(5 << 3);
            varint(m, *i as u64);
        }
        Val::UInt(u) => {
            m.push(5 << 3);
            varint(m, *u);
        }
        Val::Bool(b) => {
            m.push(7 << 3);
            m.push(*b as u8);
        }
    }
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
    fn feature(&mut self, f: &Feat, kind: u32, geometry: &[u32], names: &[String], with_id: bool) {
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
        if let Some(id) = f.id.filter(|_| with_id) {
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
        let mut t = Tiles::new(0, 15, 80.0).unwrap();
        t.add("roads", &json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": [
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

    /// The text of the tile z/x/y of a "simple" layer with these pieces: (edge, kind, seam, coordinates); the tile is empty when no piece stays.
    fn pieces(z: u32, x: u32, y: u32, fs: &[(i64, i64, bool, [[f64; 2]; 2])]) -> String {
        let mut t = Tiles::new(0, 3, 80.0).unwrap();
        let features: Vec<Value> = fs.iter().map(|(e, k, seam, c)| json!({"type": "Feature", "properties": {"__rs_edge": e, "__rs_k": k, "__rs_seam": seam},
            "geometry": {"type": "LineString", "coordinates": c}})).collect();
        t.add("simple", &json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": features}}), &keys(&[]), false, 0);
        String::from_utf8_lossy(&t.tile(z, x, y)).into_owned()
    }

    // zoom 0: 1 px is 0.7 degrees of longitude; 0.1 degrees is 0.14 px
    const SHORT: [[f64; 2]; 2] = [[10.0, 10.0], [10.1, 10.0]];
    const LONG: [[f64; 2]; 2] = [[10.0, 10.0], [15.0, 10.0]];

    #[test]
    fn a_road_under_1_px_is_left_out_of_a_low_zoom_tile() {
        assert!(pieces(0, 0, 0, &[(1, 0, false, SHORT), (1, 1, false, SHORT)]).is_empty());
        assert!(!pieces(0, 0, 0, &[(1, 1, false, LONG)]).is_empty());
        assert!(!pieces(3, 4, 3, &[(1, 1, false, [[10.0, 10.0], [10.1, 10.0]])]).is_empty(), "the last zoom keeps every piece");
    }

    #[test]
    fn a_road_that_goes_out_of_the_tile_stays() {
        // 0.1 degrees across the line between the tiles 1/0/0 and 1/1/0: a cut of 0.07 px at each side
        let across = [[-0.05, 10.0], [0.05, 10.0]];
        assert!(!pieces(1, 0, 0, &[(1, 1, false, across)]).is_empty());
        assert!(!pieces(1, 1, 0, &[(1, 1, false, across)]).is_empty());
    }

    #[test]
    fn a_casing_end_piece_under_1_px_is_left_out_and_a_short_fill_stays() {
        let t = pieces(0, 0, 0, &[(1, 0, false, LONG), (1, 0, true, SHORT)]);
        assert!(!t.is_empty() && !t.contains("__rs_seam"), "the short seam goes, the casing body stays");
        let t = pieces(0, 0, 0, &[(1, 0, false, LONG), (1, 1, false, SHORT)]);
        assert!(t.contains("__rs_k"), "a short fill of a long road stays");
        assert!(pieces(0, 0, 0, &[(1, 0, true, LONG)]).contains("__rs_seam"), "a long seam stays");
    }

    #[test]
    fn the_outer_ring_has_a_positive_area() {
        let mut t = Tiles::new(0, 15, 80.0).unwrap();
        // a square around (1, 1) degrees, counterclockwise in lon / lat (clockwise on the screen after y goes down)
        t.add("land", &json!({"type": "geojson", "generateId": true, "data": {"type": "FeatureCollection", "features": [
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
        let bend = |h: f64| vec![[0.0, 0.0], [50.0, h], [100.0, 0.0]];
        assert_eq!(douglas_peucker_kept(&bend(0.4), 0.5), vec![0, 2]);
        assert_eq!(douglas_peucker_kept(&bend(0.6), 0.5), vec![0, 1, 2]);
        assert_eq!(line_parts(vec![bend(0.4)], None)[0].len(), 3, "the last zoom keeps every point (no simplification)");
        let short = || vec![vec![[0.0, 0.0], [0.4, 0.0]]];
        assert!(line_parts(short(), Some((-80.0, 4176.0))).is_empty(), "at every zoom");
        // a whole line keeps its points out of the tile, a clipped one ends at the buffer
        let long = || vec![vec![[0.0, 10.0], [4000.0, 10.0], [9000.0, 10.0]]];
        assert_eq!(line_parts(long(), None), vec![vec![[0, 10], [4000, 10], [9000, 10]]]);
        assert_eq!(line_parts(long(), Some((-80.0, 4176.0))), vec![vec![[0, 10], [4000, 10], [4176, 10]]]);
        // the zooms: no tile out of 6 to 15, no tile of a layer before its first zoom
        let fc = json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": 1, "properties": {}, "geometry": {"type": "LineString", "coordinates": [[1.0, 1.0], [1.01, 1.0]]}}]}});
        let mut t = Tiles::new(6, 15, 80.0).unwrap();
        t.add("slots", &fc, &keys(&[]), true, 14);
        let at = |z: u32| {
            let n = (1u64 << z) as f64;
            let [x, y] = merc(&json!([1.005, 1.0])).unwrap();
            t.tile(z, (x * n) as u32, (y * n) as u32)
        };
        assert!(at(13).is_empty() && at(16).is_empty() && !at(14).is_empty() && !at(15).is_empty());
    }

    #[test]
    fn the_buffer_is_in_pixels() {
        // roads 100 px wide (a reach of 50 px) 40 px and 60 px above tiles of zoom 18 (Burnaby): the stroke of the first reaches into
        // its tile, so the tile has it; with the buffer as 80 units (10 px) the tile had none, and the road's casing was missing in the
        // tile (each tile is drawn inside its own edges only). The second does not reach into its tile.
        let layers = [json!({"type": "line", "source": "roads", "paint": {"line-width": 100}})];
        let o = stage::TileOptions::new(&layers, &json!({}), &json!({"minzoom": 0, "maxzoom": 18, "buffer_px": 80, "extent": 4096}), &json!({}), &[]).unwrap();
        let mut t = o.tiles().unwrap();
        let n = (1u64 << 18) as f64;
        let at = |x: f64, y: f64| [x / n * 360.0 - 180.0, (std::f64::consts::PI * (1.0 - 2.0 * y / n)).sinh().atan().to_degrees()];
        let road = |x: f64, px: f64| json!({"type": "Feature", "properties": {}, "geometry": {"type": "LineString",
            "coordinates": [at(x + 0.1, 89738.0 - px / 512.0), at(x + 0.9, 89738.0 - px / 512.0)]}});
        t.add("roads", &json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": [road(41536.0, 40.0), road(41540.0, 60.0)]}}),
              &keys(&[]), false, 0);
        assert!(!t.tile(18, 41536, 89737).is_empty());
        assert!(!t.tile(18, 41536, 89738).is_empty(), "the road 40 px out of the tile is in it");
        assert!(t.tile(18, 41536, 89739).is_empty(), "and not in the tile after it");
        assert!(t.tile(18, 41540, 89738).is_empty(), "the road 60 px out of the tile is not in it");
    }

    #[test]
    fn bad_settings_are_errors_not_panics() {
        // zooms past MAX_ZOOM overflowed the shifts of the archive (1 << z); a first zoom after the last; a buffer below 0
        for (lo, hi, buffer) in [(0, 40, 80.0), (5, 4, 80.0), (0, 15, -1.0), (0, 15, f64::NAN)] {
            assert!(matches!(Tiles::new(lo, hi, buffer), Err(Error::Options(_))), "{lo} {hi} {buffer}");
        }
        let settings = |max: f64| json!({"minzoom": 0, "maxzoom": max, "buffer_px": 80, "extent": 4096});
        assert!(matches!(stage::TileOptions::new(&[], &json!({}), &settings(40.0), &json!({}), &[]), Err(Error::Options(_))));
        assert!(stage::TileOptions::new(&[], &json!({}), &settings(MAX_ZOOM as f64), &json!({}), &[]).is_ok());
        assert!(matches!(stage::TileOptions::from_style(&json!({}), &[]), Err(Error::Options(_))));
        // a tile far out of the world is empty; bounds that are not longitude and latitude, and an archive of no tile, are errors
        let t = Tiles::new(0, MAX_ZOOM, 80.0).unwrap();
        assert!(t.tile(MAX_ZOOM, u32::MAX, u32::MAX).is_empty());
        assert!(matches!(t.archive([f64::NAN, 0.0, 1.0, 1.0], &[]), Err(Error::Options(_))));
        assert_eq!(Tiles::new(0, 2, 80.0).unwrap().archive([0.0, 0.0, 1.0, 1.0], &[]), Err(Error::Empty));
    }
}
