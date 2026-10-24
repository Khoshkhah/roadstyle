//! The properties of a road or a piece, and the typed features of the sources `roads` and `simple` (docs/design/rust_engine.md, step 3).
//! `Props` has the methods of serde_json's `Map` with `preserve_order` (an insert of a key that is there keeps its place), but each key
//! name is kept once for the whole program: an entry is about 48 bytes, not about 100. A `Feat` keeps its line as numbers, not as JSON
//! arrays. The JSON text they write is byte for byte the text of the same tree of `serde_json::Value`.

use serde_json::{Map, Value};
use std::collections::HashSet;
use std::sync::{Mutex, OnceLock};

fn names() -> &'static Mutex<HashSet<&'static str>> {
    static NAMES: OnceLock<Mutex<HashSet<&'static str>>> = OnceLock::new();
    NAMES.get_or_init(Default::default)
}

/// The one copy of a key name (made the first time; a program has some hundred names).
fn intern(k: &str) -> &'static str {
    let mut t = names().lock().unwrap();
    if let Some(&s) = t.get(k) {
        return s;
    }
    let s: &'static str = Box::leak(k.into());
    t.insert(s);
    s
}

/// The copy of a name, if a property has it.
fn find(k: &str) -> Option<&'static str> {
    names().lock().unwrap().get(k).copied()
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Props(Vec<(&'static str, Value)>);

impl Props {
    fn at(&self, k: &str) -> Option<usize> {
        let k = find(k)?;
        self.0.iter().position(|e| std::ptr::eq(e.0, k))
    }

    pub fn get(&self, k: &str) -> Option<&Value> {
        self.at(k).map(|i| &self.0[i].1)
    }

    /// The property as a cell (the type that the stages read the roads' columns with).
    pub fn cell(&self, k: &str) -> Option<crate::Cell<'_>> {
        self.get(k).map(crate::Cell::Json)
    }

    pub fn get_mut(&mut self, k: &str) -> Option<&mut Value> {
        self.at(k).map(|i| &mut self.0[i].1)
    }

    pub fn contains_key(&self, k: &str) -> bool {
        self.at(k).is_some()
    }

    pub fn insert(&mut self, k: &str, v: Value) -> Option<Value> {
        match self.at(k) {
            Some(i) => Some(std::mem::replace(&mut self.0[i].1, v)),
            None => {
                self.0.push((intern(k), v));
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
        self.0[i].0 = intern(to);
        true
    }

    pub fn shift_remove(&mut self, k: &str) -> Option<Value> {
        self.at(k).map(|i| self.0.remove(i).1)
    }

    pub fn values_mut(&mut self) -> impl Iterator<Item = &mut Value> {
        self.0.iter_mut().map(|(_, v)| v)
    }

    pub fn iter(&self) -> impl Iterator<Item = (&'static str, &Value)> {
        self.0.iter().map(|(k, v)| (*k, v))
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
            serde_json::to_writer(&mut *out, k).unwrap();
            out.push(b':');
            serde_json::to_writer(&mut *out, v).unwrap();
        }
        out.push(b'}');
    }
}

impl std::ops::Index<&str> for Props {
    type Output = Value;

    /// As the `Map`'s: a missing key is an error.
    fn index(&self, k: &str) -> &Value {
        self.get(k).unwrap_or_else(|| panic!("no property {k}"))
    }
}

impl<K: AsRef<str>> FromIterator<(K, Value)> for Props {
    fn from_iter<I: IntoIterator<Item = (K, Value)>>(it: I) -> Props {
        let mut p = Props::default();
        for (k, v) in it {
            p.insert(k.as_ref(), v);
        }
        p
    }
}

impl IntoIterator for Props {
    type Item = (&'static str, Value);
    type IntoIter = std::vec::IntoIter<(&'static str, Value)>;

    fn into_iter(self) -> Self::IntoIter {
        self.0.into_iter()
    }
}

/// The page's declaration (src/roadstyle/static/dashboard/reads.json): the properties that its dashboard modules read on a drawn
/// feature (`pieces`) and on a row of the road table (`table`).
pub const PAGE_READS: &str = include_str!("../../../src/roadstyle/static/dashboard/reads.json");

fn declared(part: &str) -> Vec<String> {
    let v: Value = serde_json::from_str(PAGE_READS).expect("reads.json is JSON");
    v[part].as_array().into_iter().flatten().filter_map(Value::as_str).map(String::from).collect()
}

/// The properties of a drawn feature that the page's modules read (PAGE_READS's `pieces`).
pub fn page_reads() -> Vec<String> {
    declared("pieces")
}

/// A property of a road that the road table keeps (R1): every public field (the popup, the tooltip, an app's click), the stage
/// values that the page's modules read on a row (PAGE_READS's `table`), and the fills (`__rs_fill*`: the filter's swatches of a view's
/// palette).
pub fn table_keeps(k: &str) -> bool {
    static TABLE: std::sync::OnceLock<std::collections::HashSet<String>> = std::sync::OnceLock::new();
    !k.starts_with("__rs_") || k.starts_with("__rs_fill") || TABLE.get_or_init(|| declared("table").into_iter().collect()).contains(k)
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

/// The properties that a style's drawing reads (tiles.py's tile_props): the layers' expressions (`expression_reads`), the popup and
/// tooltip fields of `roadstyle:interaction`, the page's modules (`page_reads`), `name`, `kind` and the caller's `keep`. Every `__rs_*`
/// property goes too, apart from this set.
pub fn drawn(layers: &[Value], metadata: &Value, keep: &[String]) -> std::collections::HashSet<String> {
    let mut read: std::collections::HashSet<String> = keep.iter().cloned().chain(["name".to_string(), "kind".to_string()]).chain(page_reads()).collect();
    let mut unknown = Vec::new();
    layers.iter().for_each(|l| expression_reads(l, &mut read, &mut unknown));
    let i = &metadata["roadstyle:interaction"];
    for k in ["popup", "tooltip"] {
        read.extend(i[k].as_array().into_iter().flatten().filter_map(Value::as_str).map(String::from));
    }
    read
}

/// Read a property of a road, of a typed feature or of a JSON one (the layers read all three).
pub trait Get {
    fn value(&self, k: &str) -> Option<Value>;
}

impl Get for Props {
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
    pub props: Props,
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
    use serde_json::json;

    #[test]
    fn the_text_of_a_source_is_the_text_of_its_json_tree() {
        let props: Props = [("highway", json!("primary")), ("lvl", json!(0)), ("__rs_s", json!(1.5)), ("name", json!("A \"B\""))]
            .into_iter().collect();
        let mut p2 = props.clone();
        assert_eq!(p2.insert("lvl", json!(2)), Some(json!(0)), "an insert of a key that is there keeps its place");
        assert_eq!(p2.iter().map(|(k, _)| k).collect::<Vec<_>>(), ["highway", "lvl", "__rs_s", "name"]);
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
