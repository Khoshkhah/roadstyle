//! The style's sources as vector tiles (Mapbox Vector Tile 2.1), made when the map asks for them, with the rules of roadstyle's
//! the page gives MapLibre one source, `{"type": "vector", "tiles": ["<prefix>roads/{z}/{x}/{y}"]}`, and each of the
//! style's sources is a layer in its tiles (the layers' `source-layer`). One GeoJSON text of all the roads (Tartu: 150 MB) is then
//! not made, parsed and cut into tiles by MapLibre again.
//!
//! Each feature has its index in its source as its id, and its properties (a null
//! value is left out: MapLibre reads a missing one as null). Below the last zoom a line is simplified to half a tile unit, and a
//! line shorter than that is left out. A feature is clipped to the tile and a buffer around it, except a feature of a whole layer
//! (the name and arrow slots): it goes whole into every tile it touches, because MapLibre places a label only in the tile that has
//! its anchor.

// Numeric code: index loops over parallel arrays and tuple types read as they are.
#![allow(clippy::needless_range_loop, clippy::type_complexity)]

pub mod buffer;
pub mod error;
pub mod pmtiles;
pub mod rules;
pub mod stage;
mod geom;
mod layer;
mod mvt;
mod small;
mod val;

pub use error::Error;
pub use val::{TileValue, Val};
use geom::*;
use val::*;
use layer::*;
use mvt::*;
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
/// The pieces' tile layer: the MVT id of a piece is its road's key (the engine's `__rs_edge`, which is not a tile key), so all pieces of a
/// road share it and one feature state lights them all (docs/design/tile_v2_plan.md, step 4).
const PIECES: &str = "simple";
/// The slots' tile layer: the MVT id of a slot is its road's key too (the feature's own `id`).
const SLOTS: &str = "slots";

/// A layer whose features have a road's key as their MVT id (the pieces and the slots).
fn road_layer(name: &str) -> bool {
    name == PIECES || name == SLOTS
}

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
    /// the generation of the road set (the archive's metadata carries it; `stage::TileOptions::tiles` sets it)
    generation: Option<String>,
    /// the props files of the layers with popup fields: (layer, JSON array of the fields by row, the row being the feature id)
    pub props_files: Vec<(String, String)>,
}

/// The properties that a layer's tiles keep: those in `keep`, the one key set of the layer (stage::TileOptions::rule).
fn kept(k: &str, keep: &HashSet<String>) -> bool {
    keep.contains(k)
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
        Ok(Tiles { layers: IndexMap::new(), style: Vec::new(), min_zoom, max_zoom, buffers, cache: Default::default(), generation: None, props_files: Vec::new() })
    }

    /// The style's layers: a source added after this leaves out of a tile each feature that every layer drawing it hides at every zoom
    /// of that tile (rules.rs: the class minzoom, `casing.drop_below_px`).
    pub fn drawn_by(&mut self, layers: &[Value]) {
        self.style = layers.iter().map(|l| serde_json::json!({"source": l["source"], "source-layer": l["source-layer"], "type": l["type"], "filter": l["filter"]})).collect();
    }

    /// Only `fill` and `line` style layers draw the layer `name` (small.rs): a point, a symbol or an extrusion needs its shape as it is.
    fn flat(&self, name: &str) -> bool {
        let mut types = self.style.iter().filter(|l| l["source-layer"].as_str().or(l["source"].as_str()) == Some(name)).peekable();
        types.peek().is_some() && types.all(|l| matches!(l["type"].as_str(), Some("fill" | "line")))
    }

    fn builder(&self, name: &str) -> Builder {
        Builder { rules: rules::ZoomRules::of(&self.style, name), road_id: road_layer(name), ..Default::default() }
    }

    /// A new layer: the caches of the old tiles go.
    fn put(&mut self, name: &str, layer: Layer) {
        self.layers.insert(name.to_string(), layer);
        *self.cache.get_mut().unwrap() = TileCache::default();
    }

    /// Add a GeoJSON source of the style (`{"type": "geojson", "data": FeatureCollection, ...}`) as the layer `name`, and free its
    /// tree. The properties in `keep` go into the tiles. `whole`: see the module; `min_zoom`: the layer's first zoom.
    pub fn add(&mut self, name: &str, source: &Value, keep: &HashSet<String>, whole: bool, min_zoom: u32) {
        let empty = Map::new();
        let mut b = self.builder(name);
        for (i, f) in source["data"]["features"].as_array().into_iter().flatten().enumerate() {
            let Some(g) = f.get("geometry").and_then(geom) else { continue };
            // a feature's id is its index in its source; a piece's or a slot's is its road's key (the feature's own id)
            let id = f.get("id").and_then(Value::as_u64).filter(|_| road_layer(name)).or(Some(i as u64));
            let props = f["properties"].as_object().unwrap_or(&empty);
            b.push(id, g, props.iter().filter(|(k, _)| kept(k, keep)).map(|(k, v)| (k.as_str(), v.clone())));
        }
        self.put(name, b.layer(whole, min_zoom, self.max_zoom));
    }

    /// Add a typed table of features (a base-map layer, audit R10) as the layer `name`, as `add` adds the same features as GeoJSON: each
    /// feature's id is its row, and its properties are the keys of its GeoJSON feature (`FeatureTable::has_key`).
    pub fn add_features(&mut self, name: &str, t: &FeatureTable, keep: &HashSet<String>, whole: bool, min_zoom: u32) {
        use roadstyle_model::feature_table::GeomType;
        let g = t.geometries_of();
        let names: Vec<&str> = t.names().iter().map(String::as_str).filter(|k| kept(k, keep)).collect();
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
    /// index). The properties are those in `keep`.
    pub fn add_lines<L, K, V, P>(&mut self, name: &str, feats: impl Iterator<Item = (Option<L>, P)>, keep: &HashSet<String>, whole: bool, min_zoom: u32)
    where L: AsRef<[[f64; 2]]>, K: AsRef<str>, V: TileValue, P: Iterator<Item = (K, V)> {
        let mut b = self.builder(name);
        for (i, (c, props)) in feats.enumerate() {
            let Some(c) = c else { continue };
            b.push(Some(i as u64), line_geom(c.as_ref()), props.filter(|(k, _)| kept(k.as_ref(), keep)));
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
            b.wait(i as u64, line_geom(c.as_ref()), rule_props.filter(|(k, _)| kept(k.as_ref(), keep)), (road, tag));
        }
        self.put(name, b.layer(whole, min_zoom, self.max_zoom));
    }

    /// The features of the layer `name` that the tile z/x/y has and that wait (`add_waiting`): each feature's place and tag.
    pub fn waiting(&self, name: &str, z: u32, x: u32, y: u32) -> Vec<(u32, u64)> {
        let Some(layer) = self.layers.get(name).filter(|l| l.at.is_some() && z >= self.min_zoom && z <= self.max_zoom && z >= l.min_zoom) else { return Vec::new() };
        layer.hits(z, x, y, self.pad(layer, z)).into_iter().filter_map(|i| layer.feats[i as usize].wait.map(|(_, tag)| (i, tag))).collect()
    }

    /// Give waiting features of the layer `name` their line and properties (`keep`: add_waiting's): each as (place, line,
    /// properties). The line must be the one that add_waiting had (its box and first zoom stay).
    pub fn make<L, K, V, P>(&mut self, name: &str, feats: impl Iterator<Item = (u32, L, P)>, keep: &HashSet<String>)
    where L: AsRef<[[f64; 2]]>, K: AsRef<str>, V: TileValue, P: Iterator<Item = (K, V)> {
        let Some(layer) = self.layers.get_mut(name) else { return };
        let Some((key_at, val_at)) = layer.at.take() else { return };
        let mut b = Builder { keys: std::mem::take(&mut layer.keys), key_at, vals: std::mem::take(&mut layer.vals),
                              encoded: std::mem::take(&mut layer.encoded), val_at, road_id: road_layer(name), ..Default::default() };
        for (i, c, props) in feats {
            let (props, ..) = b.intern(props.filter(|(k, _)| kept(k.as_ref(), keep)));
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
        // ponytail: one pass over the features' keys (no index of each road's features); an index if a large area is slow
        let mut gone = vec![false; layer.feats.len()];
        let mut n = 0;
        for (i, f) in layer.feats.iter_mut().enumerate() {
            if f.id.is_some_and(|e| edges.contains(&e)) {
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
        let mut b = Builder { key_at, val_at, keys, encoded, vals: std::mem::take(&mut layer.vals), feats: std::mem::take(&mut layer.feats), boxes, rules,
                              road_id: road_layer(name), last: Vec::new(), scratch: Vec::new() };
        for (j, (c, props)) in feats.enumerate() {
            let Some(c) = c else { continue };
            b.push(Some(first + j as u64), line_geom(c.as_ref()), props.filter(|(k, _)| kept(k.as_ref(), keep)));
        }
        let min_zoom = layer.min_zoom;
        *layer = b.layer(whole, min_zoom, self.max_zoom);      // the trees by first zoom again
        *self.cache.get_mut().unwrap() = TileCache::default();
        Ok(n)
    }

    /// The properties of the feature `id` of the source `name` (those in the tiles), as JSON; `null` when there is no such feature.
    /// The map draws the roads from other sources, so a click on a road asks for its properties here.
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
            let cell = |v: f64| ((v * n).floor().max(0.0) as u32).min(last);      // the tile index of this coordinate
            // the bounds and the zoom's buffer: a tile whose buffer has a road's stroke has the road
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
        let meta = serde_json::json!({"vector_layers": layers.iter().map(|n| serde_json::json!({"id": n, "fields": {}})).collect::<Vec<_>>(),
                                      "contract": roadstyle_model::props::CONTRACT, "generation": self.generation});
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
        let tiny = name == PIECES && simplify;
        // the base map's shapes below the last zoom (small.rs); the pieces have rule B
        let flat = z < self.max_zoom && !road_layer(name) && self.flat(name);
        let reach = self.buffers[z as usize];
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
                    // ponytail: simplified for each tile; a cache for each (feature, zoom) was slower
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
                            // a whole layer's polygon goes into every tile its box touches as it is, not clipped
                            let r: Vec<P> = r.iter().map(to).collect();
                            let mut r = dedup(if flat { small::ring(&r, -reach, EXTENT + reach) } else if layer.whole { r } else { clip_ring(&r, lo, hi) }.into_iter().map(round));
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
                enc.feature(f, *kind, geometry, &layer.keys);
            }
        }
        enc.finish(name, &layer.encoded)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use roadstyle_model::mark::Mark;
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
        let features: Vec<Value> = fs.iter().map(|(e, k, seam, c)| json!({"type": "Feature", "properties": {(Mark::Edge.name()): e, (Mark::PieceKind.name()): k, (Mark::Seam.name()): seam},
            "geometry": {"type": "LineString", "coordinates": c}})).collect();
        t.add("simple", &json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": features}}), &keys(&[Mark::Edge.name(), Mark::PieceKind.name(), Mark::Seam.name()]), false, 0);
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
        assert!(!t.is_empty() && !t.contains(Mark::Seam.name()), "the short seam goes, the casing body stays");
        let t = pieces(0, 0, 0, &[(1, 0, false, LONG), (1, 1, false, SHORT)]);
        assert!(t.contains(Mark::PieceKind.name()), "a short fill of a long road stays");
        assert!(pieces(0, 0, 0, &[(1, 0, true, LONG)]).contains(Mark::Seam.name()), "a long seam stays");
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

    /// The fields of a protobuf message: (field number, varint value, bytes).
    fn fields(b: &[u8]) -> Vec<(u64, u64, &[u8])> {
        let (mut i, mut out) = (0, Vec::new());
        let varint = |i: &mut usize| {
            let (mut v, mut s) = (0u64, 0);
            loop {
                let x = b[*i];
                *i += 1;
                v |= ((x & 0x7f) as u64) << s;
                s += 7;
                if x < 0x80 {
                    return v;
                }
            }
        };
        while i < b.len() {
            let k = varint(&mut i);
            if k & 7 == 2 {
                let n = varint(&mut i) as usize;
                out.push((k >> 3, 0, &b[i..i + n]));
                i += n;
            } else {
                out.push((k >> 3, varint(&mut i), &b[0..0]));
            }
        }
        out
    }

    /// The points of every feature of the tile's layer `name`, in the tile's units: (feature's points, as the commands give them).
    fn points_of(tile: &[u8], name: &str) -> Vec<Vec<[i32; 2]>> {
        let unzig = |v: u64| ((v >> 1) as i64 ^ -((v & 1) as i64)) as i32;
        let layers = fields(tile).into_iter().filter(|f| f.0 == 3).map(|f| fields(f.2));
        let layer = layers.into_iter().find(|l| l.iter().any(|f| f.0 == 1 && f.2 == name.as_bytes())).unwrap_or_default();
        layer.iter().filter(|f| f.0 == 2).map(|f| {
            let geometry = fields(f.2).into_iter().find(|g| g.0 == 4).map_or(&b""[..], |g| g.2);
            let (mut i, mut nums) = (0, Vec::new());
            while i < geometry.len() {
                let (mut v, mut s) = (0u64, 0);
                loop {
                    let x = geometry[i];
                    i += 1;
                    v |= ((x & 0x7f) as u64) << s;
                    s += 7;
                    if x < 0x80 {
                        break;
                    }
                }
                nums.push(v);
            }
            let (mut at, mut pts, mut k) = ([0i32, 0i32], Vec::new(), 0);
            while k < nums.len() {
                let (id, count) = (nums[k] & 7, (nums[k] >> 3) as usize);
                k += 1;
                if id == 7 {
                    continue;
                }
                for _ in 0..count {
                    at = [at[0] + unzig(nums[k]), at[1] + unzig(nums[k + 1])];
                    pts.push(at);
                    k += 2;
                }
            }
            pts
        }).collect()
    }

    /// The tile z/x/y of a polygon `land` (a flat layer when `flat`: only a fill layer draws it), with these points in longitude and latitude.
    fn land(flat: bool, z: u32, x: u32, y: u32, ring: &[[f64; 2]]) -> Vec<u8> {
        let mut t = Tiles::new(0, 5, 80.0).unwrap();
        let layers = [json!({"type": if flat { "fill" } else { "circle" }, "source": "land"})];
        t.drawn_by(&layers);
        let source = json!({"type": "geojson", "data": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}]}});
        t.add("land", &source, &keys(&[]), true, 0);
        t.tile(z, x, y)
    }

    #[test]
    fn a_flat_layers_polygon_is_cut_to_the_tile_and_simplified() {
        // a square of 40 degrees with a point every 0.1 degree on each side. The tile 4/6/5 holds the square's west side and not its corners:
        // the straight side needs its two ends only, and the points out of the tile and its buffer go.
        let side = |a: [f64; 2], b: [f64; 2]| (0..400).map(move |i| [a[0] + (b[0] - a[0]) * i as f64 / 400.0, a[1] + (b[1] - a[1]) * i as f64 / 400.0]);
        let (a, b, c, d) = ([-60.0, 20.0], [-20.0, 20.0], [-20.0, 60.0], [-60.0, 60.0]);
        let ring: Vec<[f64; 2]> = side(a, b).chain(side(b, c)).chain(side(c, d)).chain(side(d, a)).chain([a]).collect();
        let flat = points_of(&land(true, 4, 6, 5, &ring), "land");
        let whole = points_of(&land(false, 4, 6, 5, &ring), "land");
        assert_eq!(whole[0].len(), 1600, "the layer that a circle layer draws keeps every point");
        assert!(flat[0].len() <= 8, "the straight sides need their corners only: {}", flat[0].len());
        let buffer = 80.0 / 512.0 * 4096.0;
        assert!(flat[0].iter().flatten().all(|c| (-buffer..=4096.0 + buffer).contains(&(*c as f64))), "{:?}", flat[0]);
        assert!(whole[0].iter().flatten().any(|c| (*c as f64) < -buffer || (*c as f64) > 4096.0 + buffer));
        // the last zoom is as it was
        assert_eq!(land(true, 5, 12, 10, &ring), land(false, 5, 12, 10, &ring));
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
