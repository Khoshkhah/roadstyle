//! A feature's zooms, from the style (2026-10-25): a layer's filter hides a feature out of a span of zooms with its top clauses that
//! read the zoom: `[">=", ["zoom"], E]` (the class minzoom, `casing.drop_below_px`), `["<", ["zoom"], E]`, and an "all" or "any" of
//! them and of clauses on the feature (a casing's seam: from zoom 17 without lap, below 17 with lap). A tile leaves out a feature that
//! every layer of its source hides at every zoom of that tile, so the rule is in the style only and each way to the tiles reads it.

use roadstyle_model::eval::{ev, known, truthy};
use serde_json::{Map, Value};

/// The zoom clauses of one source: for each layer that draws it, the clauses at the top of its filter that read the zoom.
#[derive(Clone, Default)]
pub struct ZoomRules {
    layers: Vec<Vec<Value>>,
    /// the properties that the clauses read
    keys: Vec<String>,
}

impl ZoomRules {
    /// The clauses of the layers that draw `source` (its GeoJSON name, or its tile layer's name). None when a layer draws every feature
    /// at every zoom (it has no such clause), or when no layer draws the source (a page can read it).
    pub fn of(layers: &[Value], source: &str) -> ZoomRules {
        let mut out = ZoomRules::default();
        // a tiled style's layer names its tile layer (`source-layer`), a GeoJSON style's layer its source
        for l in layers.iter().filter(|l| l["source-layer"].as_str().or(l["source"].as_str()) == Some(source)) {
            let mut top = Vec::new();
            tops(&l["filter"], &mut top);
            let clauses: Vec<Value> = top.into_iter().filter(|c| reads_zoom(c)).cloned().collect();
            if clauses.is_empty() {
                return ZoomRules::default();
            }
            out.layers.push(clauses);
        }
        let mut keys = Vec::new();
        out.layers.iter().flatten().for_each(|e| gets(e, &mut keys));
        keys.sort();
        keys.dedup();
        out.keys = keys;
        out
    }

    pub fn is_empty(&self) -> bool {
        self.layers.is_empty()
    }

    /// The properties that the clauses read, in their order.
    pub fn keys(&self) -> &[String] {
        &self.keys
    }

    /// The properties that the clauses read.
    pub fn reads(&self, k: &str) -> bool {
        self.keys.iter().any(|x| x == k)
    }

    /// The zooms [from, until) at which a layer draws the feature with the properties `p`: over the layers, the lowest `from` and the
    /// highest `until` of the span where all of its clauses hold.
    pub fn span(&self, p: &Map<String, Value>) -> (f64, f64) {
        self.layers.iter().map(|cs| cs.iter().fold(ALL, |a, c| meet(a, span(c, p)))).fold((f64::INFINITY, 0.0), |a, s| (a.0.min(s.0), a.1.max(s.1)))
    }
}

const ALL: (f64, f64) = (0.0, f64::INFINITY);
const NONE: (f64, f64) = (f64::INFINITY, 0.0);

fn meet(a: (f64, f64), b: (f64, f64)) -> (f64, f64) {
    (a.0.max(b.0), a.1.min(b.1))
}

/// The zooms [from, until) where the clause `c` holds for the feature `p`; every zoom for a clause that this does not know (the
/// feature then stays in the tiles). An "any" of spans with a gap gives the span over them.
fn span(c: &Value, p: &Map<String, Value>) -> (f64, f64) {
    let num = |e: &Value, or: f64| if reads_zoom(e) { or } else { ev(e, p).as_f64().unwrap_or(or) };
    match c.as_array().map(Vec::as_slice) {
        Some([op, z, e]) if op == ">=" && *z == serde_json::json!(["zoom"]) => (num(e, 0.0), f64::INFINITY),
        Some([op, z, e]) if op == "<" && *z == serde_json::json!(["zoom"]) => (0.0, num(e, f64::INFINITY)),
        Some([op, cs @ ..]) if op == "all" => cs.iter().fold(ALL, |a, c| meet(a, span(c, p))),
        Some([op, cs @ ..]) if op == "any" => {
            cs.iter().map(|c| span(c, p)).filter(|s| s.0 < s.1).fold(NONE, |a, s| (a.0.min(s.0), a.1.max(s.1)))
        }
        _ if !reads_zoom(c) && known(c) => if truthy(&ev(c, p)) { ALL } else { NONE },
        _ => ALL,
    }
}

/// The clauses of a filter that must all hold: the items of its "all", and of an "all" in it.
fn tops<'a>(f: &'a Value, out: &mut Vec<&'a Value>) {
    match f.as_array() {
        Some(a) if a.first() == Some(&Value::from("all")) => a[1..].iter().for_each(|x| tops(x, out)),
        _ => out.push(f),
    }
}

fn reads_zoom(e: &Value) -> bool {
    match e {
        Value::Array(a) => a.first() == Some(&Value::from("zoom")) || a.iter().any(reads_zoom),
        _ => false,
    }
}

fn gets(e: &Value, out: &mut Vec<String>) {
    if let Value::Array(a) = e {
        if let [op, Value::String(k)] = a.as_slice() {
            if op == "get" {
                out.push(k.clone());
            }
        }
        a.iter().for_each(|x| gets(x, out));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn the_first_zoom_of_a_class_and_of_a_casing() {
        let layers = [json!({"source": "simple", "filter": ["all", ["all",
            [">=", ["zoom"], ["match", ["coalesce", ["get", "highway"], ""], "residential", 13.0, "service", 15.0, 0.0]],
            ["any", ["!", ["to-boolean", ["get", "__rs_seam"]]], [">=", ["zoom"], 17]],
            [">=", ["zoom"], ["case", ["all", ["==", ["get", "__rs_k"], 0], ["!", ["to-boolean", ["get", "__rs_bridge"]]]],
                              ["at", ["get", "__rs_ci"], ["literal", [3, 12, 9]]], 0]]]]})];
        let r = ZoomRules::of(&layers, "simple");
        let z = |p: Value| r.span(p.as_object().unwrap()).0;
        assert_eq!(z(json!({"highway": "residential", "__rs_k": 1, "__rs_ci": 1})), 13.0);
        assert_eq!(z(json!({"highway": "primary", "__rs_k": 0, "__rs_ci": 1})), 12.0);       // the casing: from 12
        assert_eq!(z(json!({"highway": "primary", "__rs_k": 0, "__rs_ci": 1, "__rs_bridge": true})), 0.0);
        assert_eq!(z(json!({"highway": "service", "__rs_k": 0, "__rs_ci": 2})), 15.0);
        assert_eq!(r.span(json!({"highway": "primary", "__rs_k": 1}).as_object().unwrap()), (0.0, f64::INFINITY));
        // a second layer on the source with no clause draws every feature from zoom 0
        let more = [layers[0].clone(), json!({"source": "simple", "filter": ["has", "x"]})];
        assert!(ZoomRules::of(&more, "simple").is_empty());
        assert!(ZoomRules::of(&layers, "slots").is_empty());
    }

    #[test]
    fn the_zooms_of_a_seam() {
        // the casing's seam (_simple_pieces): an end without lap from zoom 17, an end with lap below 17
        let layers = [json!({"source-layer": "simple", "filter": ["all", [">=", ["zoom"], ["match", ["get", "highway"], "residential", 13, 0]],
            ["any", ["!", ["to-boolean", ["get", "__rs_seam"]]],
                    ["all", ["!", ["to-boolean", ["get", "__rs_lap"]]], [">=", ["zoom"], 17]],
                    ["all", ["to-boolean", ["get", "__rs_lap"]], ["<", ["zoom"], 17]]]]})];
        let r = ZoomRules::of(&layers, "simple");
        let s = |p: Value| r.span(p.as_object().unwrap());
        assert_eq!(s(json!({"highway": "residential"})), (13.0, f64::INFINITY));
        assert_eq!(s(json!({"highway": "residential", "__rs_seam": true})), (17.0, f64::INFINITY));
        assert_eq!(s(json!({"highway": "primary", "__rs_seam": true, "__rs_lap": true})), (0.0, 17.0));
        assert_eq!(s(json!({"highway": "residential", "__rs_seam": true, "__rs_lap": true})), (13.0, 17.0));
        // a clause of an operator that the rules do not know keeps the feature at every zoom
        let other = [json!({"source": "s", "filter": ["any", ["in", ["get", "a"], ["literal", [1]]], [">=", ["zoom"], 17]]})];
        assert_eq!(ZoomRules::of(&other, "s").span(json!({"a": 2}).as_object().unwrap()), (0.0, f64::INFINITY));
    }
}
