//! Text values that are numbers in a tile (docs/design/tiling.md, "The keys of a tile"). A road feature carries no text that a number can replace:
//! the class `__rs_cls` is `__rs_cc` (an index of the filter panel's classes), the class column (`highway`) is `__rs_ci` (the index of the class in the
//! model's classes: a piece has it from the engine, a slot gets it here), the dash pattern `__rs_dash` is the index (from 1) of the pattern in the
//! road layer's `match`, and the end shape `__rs_cap` is 1 for a flat end and 2 for a square one. The tile cut (`Builder`) writes the numbers, and
//! `encode_style` makes the style's expressions read them: one rule for every path (the page's archive, the map worker, a server, the program).

use roadstyle_model::mark::Mark;
use serde_json::Value;

/// The numbers of the text keys of a road feature: the classes of the filter panel and the dash patterns of the road layer.
#[derive(Clone, Debug, Default)]
pub struct Codes {
    /// the classes of the filter panel (`__rs_cc`)
    pub class: Vec<String>,
    /// the model's classes (`__rs_ci`: a class that is not in the list has the number of the list)
    pub classes: Vec<String>,
    /// the class column of the roads (the pieces' text class, `highway` by default); the slots' own class is `highway`
    pub class_col: String,
    pub dashes: Vec<String>,
}

fn is_dash_match(a: &[Value]) -> bool {
    a.first().is_some_and(|f| f == "match") && a.get(1) == Some(&serde_json::json!(["to-string", ["coalesce", ["get", Mark::Dash.name()], ""]]))
}

/// The dash patterns that the layers' expressions name: the labels of the `match` on `__rs_dash`, in their order.
pub fn dash_patterns(layers: &[Value]) -> Vec<String> {
    fn walk(v: &Value, out: &mut Vec<String>) {
        if let Some(a) = v.as_array() {
            if is_dash_match(a) {
                out.extend(a[2..a.len() - 1].iter().step_by(2).filter_map(|l| l.as_str().map(String::from)));
            }
            a.iter().for_each(|x| walk(x, out));
        } else if let Some(o) = v.as_object() {
            o.values().for_each(|x| walk(x, out));
        }
    }
    let mut out = Vec::new();
    layers.iter().for_each(|l| walk(l, &mut out));
    let mut seen = std::collections::HashSet::new();
    out.retain(|d| seen.insert(d.clone()));        // the same patterns come in each road layer
    out
}

/// A `match` on the class text (the class column or the slots' `highway`, with or without a default of text) reads `__rs_ci` and the numbers of the classes.
fn is_class_match(a: &[Value], cols: &[&str]) -> bool {
    a.first().is_some_and(|f| f == "match")
        && cols.iter().any(|c| a.get(1) == Some(&serde_json::json!(["get", c])) || a.get(1) == Some(&serde_json::json!(["coalesce", ["get", c], ""])))
}

fn recode_class_match(a: &mut Vec<Value>, classes: &[String]) {
    let at = |s: &str| classes.iter().position(|c| c == s);
    let n = a.len();
    let mut out = vec![a[0].clone(), serde_json::json!(["coalesce", ["get", Mark::ClassIndex.name()], -1])];
    for i in (2..n - 1).step_by(2) {
        let codes: Vec<Value> = match &a[i] {
            Value::String(s) => at(s).map(|p| vec![p.into()]).unwrap_or_default(),
            Value::Array(l) => l.iter().filter_map(|x| x.as_str().and_then(at)).map(Value::from).collect(),
            _ => Vec::new(),
        };
        if !codes.is_empty() {        // a label that is no class of the model never matched a road of the model
            out.push(if codes.len() == 1 { codes[0].clone() } else { Value::Array(codes) });
            out.push(a[i + 1].clone());
        }
    }
    out.push(a[n - 1].clone());
    *a = out;
}

/// The expressions of the layers in `layers` that read the numbers (the layers of a tile source only: a GeoJSON source keeps its text).
pub fn encode_style(layers: &mut [Value], codes: &Codes) {
    let (dashes, cols) = (&codes.dashes, [codes.class_col.as_str(), "highway"]);
    fn walk(v: &mut Value, dashes: &[String], classes: &[String], cols: &[&str]) {
        match v {
            Value::Array(a) => {
                if !classes.is_empty() && is_class_match(a, cols) {
                    recode_class_match(a, classes);
                }
                if is_dash_match(a) {
                    a[1] = serde_json::json!(["coalesce", ["get", Mark::Dash.name()], 0]);
                    let n = a.len();
                    for i in (2..n - 1).step_by(2) {
                        if let Some(at) = a[i].as_str().and_then(|s| dashes.iter().position(|d| d == s)) {
                            a[i] = (at as u64 + 1).into();
                        }
                    }
                }
                if a.len() == 3 && a[0] == "==" && a[1] == serde_json::json!(["get", Mark::Cap.name()]) && a[2] == "square" {
                    a[2] = 2.into();
                }
                a.iter_mut().for_each(|x| walk(x, dashes, classes, cols));
            }
            Value::Object(o) => o.values_mut().for_each(|x| walk(x, dashes, classes, cols)),
            _ => {}
        }
    }
    layers.iter_mut().filter(|l| l.get("source-layer").is_some()).for_each(|l| walk(l, dashes, &codes.classes, &cols));
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn the_expressions_read_the_numbers() {
        let m = json!(["match", ["to-string", ["coalesce", ["get", Mark::Dash.name()], ""]], "4,4", ["literal", [4, 4]], "2,5", ["literal", [2, 5]], ["literal", [1, 0]]]);
        let cap = json!(["case", ["==", ["get", Mark::Cap.name()], "square"], "square", "round"]);
        let mut layers = vec![json!({"id": "a", "source-layer": "simple", "paint": {"line-dasharray": m, "line-cap": cap}}), json!({"id": "g", "source": "geo", "paint": {"line-dasharray": m}})];
        let dashes = dash_patterns(&layers);
        assert_eq!(dashes, ["4,4", "2,5"]);
        encode_style(&mut layers, &Codes { dashes: dashes.clone(), classes: vec!["motorway".into(), "primary".into()], class_col: "highway".into(), ..Default::default() });
        assert_eq!(layers[0]["paint"]["line-dasharray"], json!(["match", ["coalesce", ["get", Mark::Dash.name()], 0], 1, ["literal", [4, 4]], 2, ["literal", [2, 5]], ["literal", [1, 0]]]));
        assert_eq!(layers[0]["paint"]["line-cap"], json!(["case", ["==", ["get", Mark::Cap.name()], 2], "square", "round"]));
        assert_eq!(layers[1]["paint"]["line-dasharray"], m, "a GeoJSON layer keeps the text");
    }
}
