//! A feature's first zoom, from the style (2026-10-25): a layer's filter hides a feature below a zoom with a top clause
//! `[">=", ["zoom"], E]` whose E reads only the feature (the class minzoom, `casing.drop_below_px`). A tile leaves out a feature that
//! every layer of its source hides at every zoom of that tile, so the rule is in the style only and each way to the tiles reads it.

use serde_json::{Map, Value};

/// The first-zoom clauses of one source: for each layer that draws it, the E of each `[">=", ["zoom"], E]` at the top of its filter.
#[derive(Clone, Default)]
pub struct ZoomRules {
    layers: Vec<Vec<Value>>,
    /// the properties that the clauses read
    keys: Vec<String>,
}

impl ZoomRules {
    /// The clauses of the layers that draw `source` (its GeoJSON name, or its tile layer's name). None when a layer draws every feature
    /// from zoom 0 (it has no such clause), or when no layer draws the source (a page can read it).
    pub fn of(layers: &[Value], source: &str) -> ZoomRules {
        let mut out = ZoomRules::default();
        // a tiled style's layer names its tile layer (`source-layer`), a GeoJSON style's layer its source
        for l in layers.iter().filter(|l| l["source-layer"].as_str().or(l["source"].as_str()) == Some(source)) {
            let mut top = Vec::new();
            tops(&l["filter"], &mut top);
            let clauses: Vec<Value> = top.into_iter().filter_map(|c| match c.as_array().map(Vec::as_slice) {
                Some([op, z, e]) if op == ">=" && *z == serde_json::json!(["zoom"]) && !reads_zoom(e) => Some(e.clone()),
                _ => None,
            }).collect();
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

    /// The properties that the clauses read.
    pub fn reads(&self, k: &str) -> bool {
        self.keys.iter().any(|x| x == k)
    }

    /// The first zoom at which a layer draws the feature with the properties `p`: the lowest over the layers of the highest E of its
    /// clauses (an E that is not a number: 0).
    pub fn first_zoom(&self, p: &Map<String, Value>) -> f64 {
        self.layers.iter().map(|cs| cs.iter().map(|e| ev(e, p).as_f64().unwrap_or(0.0)).fold(0.0, f64::max)).fold(f64::INFINITY, f64::min)
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

fn truthy(v: &Value) -> bool {
    match v {
        Value::Bool(b) => *b,
        Value::Null => false,
        Value::Number(n) => n.as_f64().is_some_and(|x| x != 0.0),
        Value::String(s) => !s.is_empty(),
        _ => true,
    }
}

fn same(a: &Value, b: &Value) -> bool {
    match (a.as_f64(), b.as_f64()) {
        (Some(x), Some(y)) => x == y,
        _ => a == b,
    }
}

/// The value of a MapLibre expression on a feature, for the operators of the clauses; Null for another operator (the clause then
/// gives 0: the feature stays in the tiles).
fn ev(e: &Value, p: &Map<String, Value>) -> Value {
    let Some(a) = e.as_array() else { return e.clone() };
    let Some(op) = a.first().and_then(Value::as_str) else { return Value::Null };
    let arg = |i: usize| a.get(i).map_or(Value::Null, |x| ev(x, p));
    match op {
        "get" => a.get(1).and_then(Value::as_str).and_then(|k| p.get(k)).cloned().unwrap_or(Value::Null),
        "literal" => a.get(1).cloned().unwrap_or(Value::Null),
        "coalesce" => (1..a.len()).map(arg).find(|v| !v.is_null()).unwrap_or(Value::Null),
        "to-boolean" => truthy(&arg(1)).into(),
        "!" => (!truthy(&arg(1))).into(),
        "all" => (1..a.len()).all(|i| truthy(&arg(i))).into(),
        "any" => (1..a.len()).any(|i| truthy(&arg(i))).into(),
        "==" => same(&arg(1), &arg(2)).into(),
        "!=" => (!same(&arg(1), &arg(2))).into(),
        "at" => arg(1).as_f64().and_then(|i| arg(2).as_array().and_then(|l| l.get(i as usize)).cloned()).unwrap_or(Value::Null),
        "case" => {
            let mut i = 1;
            while i + 1 < a.len() {
                if truthy(&arg(i)) {
                    return arg(i + 1);
                }
                i += 2;
            }
            arg(a.len() - 1)
        }
        "match" => {
            let x = arg(1);
            let mut i = 2;
            while i + 1 < a.len() {
                let hit = match &a[i] {
                    Value::Array(ls) => ls.iter().any(|l| same(l, &x)),
                    l => same(l, &x),
                };
                if hit {
                    return arg(i + 1);
                }
                i += 2;
            }
            arg(a.len() - 1)
        }
        _ => Value::Null,
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
        let z = |p: Value| r.first_zoom(p.as_object().unwrap());
        assert_eq!(z(json!({"highway": "residential", "__rs_k": 1, "__rs_ci": 1})), 13.0);
        assert_eq!(z(json!({"highway": "primary", "__rs_k": 0, "__rs_ci": 1})), 12.0);       // the casing: from 12
        assert_eq!(z(json!({"highway": "primary", "__rs_k": 0, "__rs_ci": 1, "__rs_bridge": true})), 0.0);
        assert_eq!(z(json!({"highway": "service", "__rs_k": 0, "__rs_ci": 2})), 15.0);
        // a second layer on the source with no clause draws every feature from zoom 0
        let more = [layers[0].clone(), json!({"source": "simple", "filter": ["has", "x"]})];
        assert!(ZoomRules::of(&more, "simple").is_empty());
        assert!(ZoomRules::of(&layers, "slots").is_empty());
    }
}
