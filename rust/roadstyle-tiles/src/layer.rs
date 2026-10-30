//! A source made ready for tiles: the features, their boxes and the builder that interns the properties.

use super::*;

pub(crate) struct Feat {
    pub(crate) id: Option<u64>,
    /// the zooms [from, until) at which a layer of the style draws it (rules.rs; every zoom with no rules)
    pub(crate) from: f32,
    pub(crate) until: f32,
    pub(crate) geom: Geom,
    /// (key, value): the numbers of the layer's key and value
    pub(crate) props: Vec<(u32, u32)>,
    /// a feature that waits for its line and properties (`Tiles::add_waiting`): its road (`__rs_edge`) and the caller's tag
    pub(crate) wait: Option<(u64, u64)>,
}

/// The boxes of the features of one first tile zoom, and their tree, made when a tile first reads it.
pub(crate) struct Tree {
    pub(crate) first: u32,
    pub(crate) boxes: Vec<GeomWithData<Rectangle<P>, u32>>,
    // ponytail: the boxes stay after the tree is made (Tartu 4.5 MB); take them into the tree if the memory counts
    pub(crate) tree: std::sync::OnceLock<RTree<GeomWithData<Rectangle<P>, u32>>>,
}

impl Tree {
    pub(crate) fn get(&self) -> &RTree<GeomWithData<Rectangle<P>, u32>> {
        self.tree.get_or_init(|| RTree::bulk_load(self.boxes.clone()))
    }
}

/// A source made ready: its keys, its distinct values (each also as the bytes of its Value message in a tile, made once and not for
/// each tile: half of a tile's time was this), its features and their boxes.
pub(crate) struct Layer {
    pub(crate) keys: Vec<String>,
    pub(crate) vals: Vec<Val<'static>>,
    pub(crate) encoded: Vec<Vec<u8>>,
    pub(crate) feats: Vec<Feat>,
    /// one tree for each first tile zoom of its features (the first zoom that draws them, the last zoom for the rest), in the order of
    /// the zooms: a tile of zoom z reads only the trees of zoom z or less (Tartu z10: 4,422 features, not 114,182)
    pub(crate) trees: Vec<Tree>,
    /// the numbers of the keys and the values, kept while a feature waits (`Tiles::make` adds its properties)
    pub(crate) at: Option<(Numbers<String>, Numbers<Vec<u8>>)>,
    /// The features go whole into the tiles: not clipped and not simplified.
    pub(crate) whole: bool,
    pub(crate) min_zoom: u32,
    /// each feature id's place (audit R14: a click asks by id)
    pub(crate) by_id: HashMap<u64, u32>,
}

/// The numbers of a layer's keys or values (a fast hash: a tile looks up each property of each feature it makes).
pub(crate) type Numbers<K> = HashMap<K, u32, foldhash::fast::FixedState>;

impl Layer {
    /// The features in the tile z/x/y and its buffer (`buffer`, tile units) (of the trees of zoom z or less), in the order of the
    /// source: the drawing order of features in one layer. A feature out of the tile whose box is in the buffer is in the tile: its
    /// stroke can reach into it.
    pub(crate) fn hits(&self, z: u32, x: u32, y: u32, buffer: f64) -> Vec<u32> {
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
pub(crate) struct Builder {
    pub(crate) keys: Vec<String>,
    pub(crate) key_at: Numbers<String>,
    pub(crate) vals: Vec<Val<'static>>,
    pub(crate) encoded: Vec<Vec<u8>>,
    pub(crate) val_at: Numbers<Vec<u8>>,
    pub(crate) feats: Vec<Feat>,
    pub(crate) boxes: Vec<(f32, GeomWithData<Rectangle<P>, u32>)>,
    pub(crate) rules: rules::ZoomRules,
    /// the layer is the pieces': a property `__rs_edge` is a feature's id, not a key
    pub(crate) road_id: bool,
    /// the classes of the filter panel: the text `__rs_cls` of a road feature goes into the tile as its index in this list, `__rs_cc` (None: not a road layer; an empty list: the page has no filter panel, so the class is not in the tile)
    pub(crate) codes: Option<crate::codes::Codes>,
    /// the numbers of the last feature's properties, by place: the pieces of one road come one after another and have most of their
    /// properties the same, which then take their numbers with no lookup
    pub(crate) last: Vec<(u32, u32)>,
    /// a value's bytes, to look it up with no new buffer
    pub(crate) scratch: Vec<u8>,
}

impl Builder {
    /// A feature without a point (bounds) is left out; a null value is not in the tiles.
    pub(crate) fn push<K: AsRef<str>, V: TileValue>(&mut self, id: Option<u64>, g: Geom, props: impl Iterator<Item = (K, V)>) {
        let Some((lo, hi)) = bounds(&g) else { return };
        let (props, from, until, road) = self.intern(props);
        self.boxes.push((from, GeomWithData::new(Rectangle::from_corners(lo, hi), self.feats.len() as u32)));
        self.feats.push(Feat { id: road.or(id), from, until, geom: g, props, wait: None });
    }

    /// A feature that waits for its line and properties (`Tiles::add_waiting`): its box and its first zoom, from `rule_props`.
    pub(crate) fn wait<K: AsRef<str>, V: TileValue>(&mut self, id: u64, g: Geom, rule_props: impl Iterator<Item = (K, V)>, wait: (u64, u64)) {
        let Some((lo, hi)) = bounds(&g) else { return };
        let (from, until) = if self.rules.is_empty() { (0.0, f32::INFINITY) } else {
            // the values that `intern` reads
            let read = rule_props.filter(|(k, _)| self.rules.reads(k.as_ref())).filter_map(|(k, v)| Some((k.as_ref().to_string(), json_of(&v.tile_val()?)))).collect();
            let (a, b) = self.rules.span(&read);
            (a as f32, b as f32)
        };
        self.boxes.push((from, GeomWithData::new(Rectangle::from_corners(lo, hi), self.feats.len() as u32)));
        self.feats.push(Feat { id: Some(if self.road_id { wait.0 } else { id }), from, until, geom: Geom::Lines(Vec::new()), props: Vec::new(), wait: Some(wait) });
    }

    /// The numbers of the properties' keys and values (a key or a value seen first gets the next number), and the first zoom that
    /// the rules give them.
    pub(crate) fn intern<K: AsRef<str>, V: TileValue>(&mut self, props: impl Iterator<Item = (K, V)>) -> (Vec<(u32, u32)>, f32, f32, Option<u64>) {
        let (keys, key_at, vals, encoded, val_at, scratch) = (&mut self.keys, &mut self.key_at, &mut self.vals, &mut self.encoded, &mut self.val_at, &mut self.scratch);
        let (rules, last, road_id, codes) = (&self.rules, &self.last, self.road_id, &self.codes);
        let mut read = Map::new();        // the values that the first-zoom rules read
        let mut j = 0;
        let (mut road, edge) = (None, roadstyle_model::mark::Mark::Edge.name());
        let props: Vec<(u32, u32)> = props
            .filter_map(|(k, v)| {
                let v = v.tile_val()?;
                // a text class is a small number in a tile: the index in the filter panel's list (a class that the list lacks has no key: no filter hides it)
                let (key, v): (&str, Val) = match codes.as_ref() {
                    // a text class, a dash pattern and a square end are numbers in a tile (codes.rs); a class that the filter panel lacks has no key: no filter hides it
                    Some(c) if k.as_ref() == roadstyle_model::mark::Mark::Class.name() => match &v {
                        Val::Str(s) => match c.class.iter().position(|x| x == s.as_ref()) {
                            Some(i) => (roadstyle_model::mark::Mark::ClassCode.name(), Val::Int(i as i64)),
                            None => return None,
                        },
                        _ => return None,
                    },
                    Some(c) if k.as_ref() == roadstyle_model::mark::Mark::Dash.name() => match &v {
                        Val::Str(s) => (k.as_ref(), Val::Int(c.dashes.iter().position(|x| x == s.as_ref())? as i64 + 1)),
                        _ => return None,
                    },
                    Some(_) if k.as_ref() == roadstyle_model::mark::Mark::Cap.name() => match &v {
                        Val::Str(s) if s == "square" => (k.as_ref(), Val::Int(2)),
                        Val::Bool(true) => (k.as_ref(), Val::Int(1)),
                        _ => return None,
                    },
                    _ => (k.as_ref(), v),
                };
                if road_id && key == edge {
                    road = match v { Val::Int(i) => u64::try_from(i).ok(), Val::UInt(u) => Some(u), _ => None };
                    return None;
                }
                if rules.reads(key) {
                    read.insert(key.to_string(), json_of(&v));
                }
                if v == Val::Bool(false) && key.starts_with(roadstyle_model::mark::PREFIX) {
                    return None; // a false flag: every reader of a __rs_* flag takes a missing key as false (to-boolean, a truthy check)
                }
                j += 1;
                if let Some(&(at, n)) = last.get(j - 1).filter(|(at, n)| keys[*at as usize] == key && vals[*n as usize] == v) {
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
                let at = match key_at.get(key) {
                    Some(&at) => at,
                    None => {
                        keys.push(key.to_string());
                        key_at.insert(key.to_string(), keys.len() as u32 - 1);
                        keys.len() as u32 - 1
                    }
                };
                Some((at, v))
            })
            .collect();
        self.last.clone_from(&props);
        let (from, until) = if rules.is_empty() { (0.0, f32::INFINITY) } else { let (a, b) = rules.span(&read); (a as f32, b as f32) };
        (props, from, until, road)
    }

    pub(crate) fn layer(self, whole: bool, min_zoom: u32, max_zoom: u32) -> Layer {
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
pub(crate) const PX: f64 = EXTENT / 512.0;

/// Rule B (docs/design/tile_v2_plan.md, step 3b), for the pieces of a tile below the last zoom: a road whose pieces together are under
/// 1 px is left out (its casing and its fill each count: the longer one decides), unless it goes out of the tile (its length here is
/// a cut); and a casing end piece (a seam, with or without lap) under 1 px is left out. Every fill and every casing body stays.
pub(crate) fn drop_tiny(layer: &Layer, made: &mut Vec<(&Feat, u32, Vec<u32>, Vec<Vec<[i32; 2]>>)>) {
    let key = |k: &str| layer.keys.iter().position(|x| x == k).map(|k| k as u32);
    use roadstyle_model::mark::Mark;
    let kind = key(Mark::PieceKind.name());
    let seam = key(Mark::Seam.name());
    let len = |parts: &Vec<Vec<[i32; 2]>>| parts.iter().map(|l| length(&l.iter().map(|p| [p[0] as f64, p[1] as f64]).collect::<Vec<P>>())).sum::<f64>();
    let get = |f: &Feat, k: u32| f.props.iter().find(|p| p.0 == k).map(|p| p.1);
    // by road (a feature's id): the length of each kind of piece, and whether a point is out of the tile
    let mut roads: HashMap<u64, (HashMap<Option<u32>, f64>, bool)> = HashMap::new();
    let lens: Vec<f64> = made.iter().map(|m| len(&m.3)).collect();
    for (m, l) in made.iter().zip(&lens) {
        let Some(e) = m.0.id else { continue };
        let r = roads.entry(e).or_default();
        *r.0.entry(kind.and_then(|k| get(m.0, k))).or_default() += l;
        r.1 |= m.3.iter().flatten().any(|p| p[0] < 0 || p[0] > EXTENT as i32 || p[1] < 0 || p[1] > EXTENT as i32);
    }
    let mut lens = lens.into_iter();
    made.retain(|m| {
        let l = lens.next().unwrap();
        let tiny_road = m.0.id.is_some_and(|e| { let r = &roads[&e]; !r.1 && r.0.values().all(|&v| v < PX) });
        !tiny_road && !(seam.is_some_and(|s| get(m.0, s).is_some()) && l < PX)
    });
}
