//! The properties of a road or a piece, and the typed features of the sources `roads` and `simple` (docs/design/rust_engine.md, step 3).
//! `Props` has the methods of serde_json's `Map` with `preserve_order` (an insert of a key that is there keeps its place); a mark's key is
//! its static name, with no copy (R17: no global table of names). A `Feat` keeps its line as numbers, not as JSON
//! arrays. The JSON text they write is byte for byte the text of the same tree of `serde_json::Value`.

use serde_json::{Map, Value};
use std::borrow::Cow;

/// A key: a mark's name (static), a name that the props borrow (a road's column), or an owned one (an overlay's field).
pub type Key<'a> = Cow<'a, str>;

fn key<'a>(k: &str) -> Key<'a> {
    crate::mark::Mark::of(k).map_or_else(|| Cow::Owned(k.to_string()), |m| Cow::Borrowed(m.name()))
}

/// The properties in their order. `V`: JSON values, or the road's cells (`Cell`: a piece's properties borrow its road's, with no copy;
/// `to_values` makes the JSON form).
#[derive(Clone, Debug, PartialEq)]
pub struct Props<'a, V = Value>(Vec<(Key<'a>, V)>);

impl<V> Default for Props<'_, V> {
    fn default() -> Self {
        Props(Vec::new())
    }
}

impl<'a, V> Props<'a, V> {
    /// Insert with a name that the props borrow (no copy): a road's column, a mark.
    pub fn insert_name(&mut self, k: &'a str, v: V) -> Option<V> {
        match self.at(k) {
            Some(i) => Some(std::mem::replace(&mut self.0[i].1, v)),
            None => {
                self.0.push((Cow::Borrowed(k), v));
                None
            }
        }
    }

    /// A key's place: by its text, with no lock (audit R11).
    fn at(&self, k: &str) -> Option<usize> {
        self.0.iter().position(|e| e.0 == k)
    }

    pub fn get(&self, k: &str) -> Option<&V> {
        self.at(k).map(|i| &self.0[i].1)
    }

    pub fn get_mut(&mut self, k: &str) -> Option<&mut V> {
        self.at(k).map(|i| &mut self.0[i].1)
    }

    pub fn contains_key(&self, k: &str) -> bool {
        self.at(k).is_some()
    }

    pub fn insert(&mut self, k: &str, v: V) -> Option<V> {
        match self.at(k) {
            Some(i) => Some(std::mem::replace(&mut self.0[i].1, v)),
            None => {
                self.0.push((key(k), v));
                None
            }
        }
    }

    /// Give the property `from` the name `to`, in its place (a property `to` that is there goes away). False: no property `from`.
    pub fn rename(&mut self, from: &str, to: &str) -> bool {
        let Some(i) = self.at(from) else { return false };
        if let Some(j) = self.at(to).filter(|&j| j != i) {
            self.0.remove(j);
            return self.rename(from, to);
        }
        self.0[i].0 = key(to);
        true
    }

    pub fn shift_remove(&mut self, k: &str) -> Option<V> {
        self.at(k).map(|i| self.0.remove(i).1)
    }

    pub fn retain(&mut self, mut keep: impl FnMut(&str, &V) -> bool) {
        self.0.retain(|(k, v)| keep(k, v));
    }

    pub fn iter(&self) -> impl Iterator<Item = (&str, &V)> {
        self.0.iter().map(|(k, v)| (k.as_ref(), v))
    }
}

impl<'a> Props<'a, crate::Cell<'a>> {
    /// The same properties as JSON values.
    pub fn to_values(self) -> Props<'a> {
        Props(self.0.into_iter().map(|(k, v)| (k, v.to_value())).collect())
    }
}

impl<'a> Props<'a> {
    /// The property as a cell (the type that the stages read the roads' columns with).
    pub fn cell(&self, k: &str) -> Option<crate::Cell<'_>> {
        self.get(k).map(crate::Cell::Json)
    }

    /// The same properties as a JSON object.
    pub fn to_map(&self) -> Map<String, Value> {
        self.iter().map(|(k, v)| (k.to_string(), v.clone())).collect()
    }

    /// The JSON text of the object, as serde_json writes the `Map`.
    pub fn write_json(&self, out: &mut Vec<u8>) {
        out.push(b'{');
        for (i, (k, v)) in self.0.iter().enumerate() {
            if i > 0 {
                out.push(b',');
            }
            serde_json::to_writer(&mut *out, k.as_ref()).unwrap();
            out.push(b':');
            serde_json::to_writer(&mut *out, &crate::table::JsSafe(v)).unwrap();
        }
        out.push(b'}');
    }
}

impl std::ops::Index<&str> for Props<'_> {
    type Output = Value;

    /// As the `Map`'s: a missing key is an error.
    fn index(&self, k: &str) -> &Value {
        self.get(k).unwrap_or_else(|| panic!("no property {k}"))
    }
}

/// The props of (name, value) pairs; a name that they can borrow is not copied.
impl<'a, V> FromIterator<(&'a str, V)> for Props<'a, V> {
    fn from_iter<I: IntoIterator<Item = (&'a str, V)>>(it: I) -> Props<'a, V> {
        let mut p = Props::default();
        for (k, v) in it {
            p.insert_name(k, v);
        }
        p
    }
}

impl<'a, V> FromIterator<(Key<'a>, V)> for Props<'a, V> {
    fn from_iter<I: IntoIterator<Item = (Key<'a>, V)>>(it: I) -> Props<'a, V> {
        let mut p = Props::default();
        for (k, v) in it {
            match k {
                Cow::Borrowed(k) => p.insert_name(k, v),
                Cow::Owned(k) => p.insert(&k, v),
            };
        }
        p
    }
}

impl<'a, V> IntoIterator for Props<'a, V> {
    type Item = (Key<'a>, V);
    type IntoIter = std::vec::IntoIter<(Key<'a>, V)>;

    fn into_iter(self) -> Self::IntoIter {
        self.0.into_iter()
    }
}

/// The properties of a drawn feature that the page's modules read (mark.rs: the marks and columns of `Kind::Pieces`).
pub fn page_reads() -> Vec<String> {
    crate::mark::page_reads(crate::mark::Kind::Pieces)
}

/// A property of a road that the road table keeps (R1): every public field (the popup, the tooltip, an app's click), the stage
/// values that the page's modules read on a row (`Kind::Table`), and the fills (`__rs_fill*`: the filter's swatches of a view's
/// palette).
pub fn table_keeps(k: &str) -> bool {
    use crate::mark::{Kind, Mark};
    if !k.starts_with(crate::mark::PREFIX) {
        return true;            // a user's column (also one named like a slot's mark: rank, chain), and lvl
    }
    if crate::mark::is_fill(k) {
        return true;
    }
    Mark::of(k).is_some_and(|m| m.page_reads().contains(&Kind::Table))
}

/// The feature properties that the expressions of `v` read: `["get", name]` and `["has", name]` (the forms with an object, `["get",
/// key, object]`, read the object). A read whose name is not a literal is in `unknown`.
pub fn expression_reads(v: &Value, out: &mut std::collections::HashSet<String>, unknown: &mut Vec<Value>) {
    match v {
        Value::Array(a) => {
            if a.len() == 2 && (a[0] == "get" || a[0] == "has") {
                match &a[1] {
                    Value::String(k) => drop(out.insert(k.clone())),
                    other => unknown.push(other.clone()),
                }
            }
            a.iter().for_each(|x| expression_reads(x, out, unknown));
        }
        Value::Object(o) => o.values().for_each(|x| expression_reads(x, out, unknown)),
        _ => {}
    }
}

/// What a road piece keeps (R1): the reads of the layers on the source `simple` (the road layer) and the page's declaration for a piece
/// (PAGE_READS's `pieces`). A road's popup reads the road table, not its pieces.
pub fn piece_reads(layers: &[Value]) -> std::collections::HashSet<String> {
    // `__rs_edge` is the carrier of the pieces' feature id (the tiles and the page write it as the id)
    let mut read: std::collections::HashSet<String> = page_reads().into_iter().chain([crate::mark::Mark::Edge.name().to_string()]).collect();
    let mut unknown = Vec::new();
    layers.iter().filter(|l| l["source"] == "simple").for_each(|l| expression_reads(l, &mut read, &mut unknown));
    read
}

/// The properties that the layers on the source `source` read (`expression_reads`).
pub fn source_reads(layers: &[Value], source: &str) -> std::collections::HashSet<String> {
    let mut read = std::collections::HashSet::new();
    let mut unknown = Vec::new();
    layers.iter().filter(|l| l["source"] == source).for_each(|l| expression_reads(l, &mut read, &mut unknown));
    read
}

/// The metadata key of the names of the base-map layers (stage 1 writes it): the tiles of such a layer keep what its layers and the
/// popup read, not all its properties.
pub const BASE_LAYERS: &str = "roadstyle:base";

/// The version of the contract between the tiles (and the inline sources) and the page (metadata `roadstyle:contract`; docs/design/
/// tile_v2_plan.md, section 8): the row as the feature id of the pieces and the slots, the layer's one key set, the sort key
/// `r * 2^32 + id`, no colour text in a piece. A change is a new version.
pub const CONTRACT: i64 = 2;
/// The metadata key of `CONTRACT`.
pub const CONTRACT_KEY: &str = "roadstyle:contract";

/// The metadata key of the generation of the road set: the first 16 hex characters of `roadstyle_levels::edge_hash` of its edge ids. A
/// road's row (the tiles' feature id) is valid in one generation only; the tile URL and the archive carry it.
pub const GENERATION: &str = "roadstyle:generation";

/// The metadata key of the popup fields of each overlay that has some, by its source: `{source: [field]}`. They are not in the
/// overlay's tiles: its props file holds them by row (the tiles' feature id).
pub const POPUPS: &str = "roadstyle:popups";

/// `POPUPS` of a style.
pub fn overlay_popups(metadata: &Value) -> std::collections::HashMap<String, Vec<String>> {
    metadata[POPUPS].as_object().into_iter().flatten()
        .map(|(k, v)| (k.clone(), v.as_array().into_iter().flatten().filter_map(Value::as_str).map(String::from).collect())).collect()
}

/// The fields of `roadstyle:interaction`'s popup and tooltip.
pub fn interaction_fields(metadata: &Value) -> std::collections::HashSet<String> {
    let i = &metadata["roadstyle:interaction"];
    ["popup", "tooltip"].into_iter().flat_map(|k| i[k].as_array().into_iter().flatten().filter_map(Value::as_str).map(String::from)).collect()
}

/// The properties that a style's drawing reads: the layers' expressions (`expression_reads`), the popup and
/// tooltip fields of `roadstyle:interaction`, the page's modules (`page_reads`), `name`, `kind` and the caller's `keep`.
pub fn drawn(layers: &[Value], metadata: &Value, keep: &[String]) -> std::collections::HashSet<String> {
    let mut read: std::collections::HashSet<String> = keep.iter().cloned().chain(["name".to_string(), "kind".to_string()]).chain(page_reads()).collect();
    let mut unknown = Vec::new();
    layers.iter().for_each(|l| expression_reads(l, &mut read, &mut unknown));
    read.extend(interaction_fields(metadata));
    read
}

/// Read a property of a road, of a typed feature or of a JSON one (the layers read all three).
pub trait Get {
    fn value(&self, k: &str) -> Option<Value>;
}

impl Get for Props<'_> {
    fn value(&self, k: &str) -> Option<Value> {
        self.get(k).cloned()
    }
}

impl Get for Map<String, Value> {
    fn value(&self, k: &str) -> Option<Value> {
        self.get(k).cloned()
    }
}

/// A feature of the source `roads` or `simple`: its id, its properties and its line (None: not a LineString, `"geometry": null`).
pub struct Feat {
    pub id: usize,
    pub props: Props<'static>,
    pub coords: Option<Vec<[f64; 2]>>,
}

/// A GeoJSON source of typed features, `{"type": "geojson", "data": {"type": "FeatureCollection", "features": [...]}, "tolerance": t}`.
/// `id_first`: each feature is `{"id", "type", "properties", "geometry"}` (roads), else `{"type", "geometry", "properties", "id"}` (simple).
pub struct Source {
    pub feats: Vec<Feat>,
    pub id_first: bool,
    pub tolerance: f64,
    /// render's data_maxzoom: the last zoom at which MapLibre cuts the source into tiles (None: MapLibre's default)
    pub maxzoom: Option<i64>,
}

impl Source {
    pub fn write_json(&self, out: &mut Vec<u8>) {
        out.extend_from_slice(br#"{"type":"geojson","data":{"type":"FeatureCollection","features":["#);
        for (i, f) in self.feats.iter().enumerate() {
            if i > 0 {
                out.push(b',');
            }
            let id = |out: &mut Vec<u8>| out.extend_from_slice(f.id.to_string().as_bytes());
            let geometry = |out: &mut Vec<u8>| match &f.coords {
                None => out.extend_from_slice(b"null"),
                Some(c) => {
                    out.extend_from_slice(br#"{"type":"LineString","coordinates":"#);
                    serde_json::to_writer(&mut *out, c).unwrap();
                    out.push(b'}');
                }
            };
            if self.id_first {
                out.extend_from_slice(br#"{"id":"#);
                id(out);
                out.extend_from_slice(br#","type":"Feature","properties":"#);
                f.props.write_json(out);
                out.extend_from_slice(br#","geometry":"#);
                geometry(out);
            } else {
                out.extend_from_slice(br#"{"type":"Feature","geometry":"#);
                geometry(out);
                out.extend_from_slice(br#","properties":"#);
                f.props.write_json(out);
                out.extend_from_slice(br#","id":"#);
                id(out);
            }
            out.push(b'}');
        }
        out.extend_from_slice(br#"]},"tolerance":"#);
        serde_json::to_writer(&mut *out, &self.tolerance).unwrap();
        if let Some(z) = self.maxzoom {
            out.extend_from_slice(br#","maxzoom":"#);
            out.extend_from_slice(z.to_string().as_bytes());
        }
        out.push(b'}');
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::mark::Mark;
    use serde_json::json;

    #[test]
    fn the_text_of_a_source_is_the_text_of_its_json_tree() {
        let props: Props = [("highway", json!("primary")), ("lvl", json!(0)), (Mark::Rank.name(), json!(1.5)), ("name", json!("A \"B\""))]
            .into_iter().collect();
        let mut p2 = props.clone();
        assert_eq!(p2.insert("lvl", json!(2)), Some(json!(0)), "an insert of a key that is there keeps its place");
        assert_eq!(p2.iter().map(|(k, _)| k).collect::<Vec<_>>(), ["highway", "lvl", Mark::Rank.name(), "name"]);
        assert_eq!(p2.shift_remove("lvl"), Some(json!(2)));
        assert!(!p2.contains_key("lvl") && p2.get("never seen").is_none());
        for id_first in [true, false] {
            let s = Source { feats: vec![Feat { id: 3, props: props.clone(), coords: Some(vec![[7.0, 43.5], [7.25, 43.75]]) },
                                         Feat { id: 4, props: Props::default(), coords: None }], id_first, tolerance: 0.05, maxzoom: None };
            let mut text = Vec::new();
            s.write_json(&mut text);
            let feature = |id: usize, p: &Props, g: Value| if id_first {
                crate::obj([("id", id.into()), ("type", "Feature".into()), ("properties", Value::Object(p.to_map())), ("geometry", g)])
            } else {
                crate::obj([("type", "Feature".into()), ("geometry", g), ("properties", Value::Object(p.to_map())), ("id", id.into())])
            };
            let tree = crate::obj([("type", "geojson".into()), ("data", crate::obj([("type", "FeatureCollection".into()), ("features", json!([
                feature(3, &props, json!({"type": "LineString", "coordinates": [[7.0, 43.5], [7.25, 43.75]]})),
                feature(4, &Props::default(), Value::Null)]))])), ("tolerance", 0.05.into())]);
            assert_eq!(String::from_utf8(text).unwrap(), tree.to_string());
        }
    }
}
