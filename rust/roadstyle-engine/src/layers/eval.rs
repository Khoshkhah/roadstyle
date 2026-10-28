use super::*;

/// MapLibre's `to-boolean` of a value: false for null, false, 0, NaN and the empty text; true for everything else.
pub(super) fn to_boolean(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().is_some_and(|x| x != 0.0 && !x.is_nan()),
        Value::String(s) => !s.is_empty(),
        _ => true,
    }
}

/// _ev's three values: a value, or one only the page can tell (the zoom, an operator it does not read).
enum Ev {
    V(Value),
    Maybe,
}

/// _same: MapLibre's ==, a boolean never equals a number.
pub(super) fn same(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Bool(_), Value::Bool(_)) => a == b,
        (Value::Bool(_), _) | (_, Value::Bool(_)) => false,
        (Value::Number(x), Value::Number(y)) => x.as_f64() == y.as_f64(),
        _ => a == b,
    }
}

pub(super) fn as_num(v: &Value) -> Option<f64> {
    match v {
        Value::Number(n) => n.as_f64(),
        Value::Bool(b) => Some(*b as u8 as f64),
        _ => None,
    }
}

/// _ev: a MapLibre expression on a feature's properties, or Maybe where only the page can tell.
fn ev(e: &Value, p: &dyn Get) -> Ev {
    let Some(arr) = e.as_array().filter(|a| !a.is_empty()) else { return Ev::V(e.clone()) };
    let (op, a) = (arr[0].as_str().unwrap_or(""), &arr[1..]);
    match op {
        "literal" => Ev::V(a[0].clone()),
        // R8's class index: an item of a literal list
        "at" if a.len() == 2 => match (ev(&a[0], p), ev(&a[1], p)) {
            (Ev::V(Value::Number(i)), Ev::V(Value::Array(arr))) => i.as_u64().and_then(|i| arr.get(i as usize)).map_or(Ev::Maybe, |v| Ev::V(v.clone())),
            _ => Ev::Maybe,
        },
        "get" if a.len() == 1 => Ev::V(a[0].as_str().and_then(|k| p.value(k)).unwrap_or(Value::Null)),
        "has" if a.len() == 1 => Ev::V(Value::Bool(a[0].as_str().is_some_and(|k| p.value(k).is_some()))),
        "all" | "any" => {
            let all = op == "all";
            let mut out = Ev::V(Value::Bool(all));
            for x in a {
                match ev(x, p) {
                    Ev::Maybe => out = Ev::Maybe,
                    Ev::V(v) if to_boolean(&v) != all => return Ev::V(Value::Bool(!all)),
                    _ => {}
                }
            }
            out
        }
        "!" | "to-boolean" | "==" | "!=" | "<" | ">" | "<=" | ">=" | "%" | "*" | "+" | "-" => {
            let mut vals = Vec::new();
            for x in a {
                match ev(x, p) {
                    Ev::Maybe => return Ev::Maybe,
                    Ev::V(v) => vals.push(v),
                }
            }
            match op {
                "!" => Ev::V(Value::Bool(!to_boolean(&vals[0]))),
                "to-boolean" => Ev::V(Value::Bool(crate::roads::yes(&vals[0]))),      // on a road's flag column: the one road-flag rule
                "==" => Ev::V(Value::Bool(same(&vals[0], &vals[1]))),
                "!=" => Ev::V(Value::Bool(!same(&vals[0], &vals[1]))),
                _ => {
                    if let (Value::String(x), Value::String(y)) = (&vals[0], &vals[1]) {
                        return match op {
                            "<" => Ev::V((x < y).into()), ">" => Ev::V((x > y).into()), "<=" => Ev::V((x <= y).into()), ">=" => Ev::V((x >= y).into()),
                            "+" => Ev::V(format!("{x}{y}").into()),
                            _ => Ev::Maybe,
                        };
                    }
                    let (Some(x), Some(y)) = (as_num(&vals[0]), as_num(&vals[1])) else { return Ev::Maybe };
                    match op {
                        "<" => Ev::V((x < y).into()), ">" => Ev::V((x > y).into()), "<=" => Ev::V((x <= y).into()), ">=" => Ev::V((x >= y).into()),
                        "%" if y == 0.0 => Ev::Maybe,
                        "%" => Ev::V(json!(x - y * (x / y).floor())),
                        "*" => Ev::V(json!(x * y)), "+" => Ev::V(json!(x + y)), "-" => Ev::V(json!(x - y)),
                        _ => Ev::Maybe,
                    }
                }
            }
        }
        "coalesce" => {
            for x in a {
                match ev(x, p) {
                    Ev::Maybe => return Ev::Maybe,
                    Ev::V(Value::Null) => {}
                    v => return v,
                }
            }
            Ev::V(Value::Null)
        }
        "case" => {
            let mut i = 0;
            while i + 1 < a.len() {
                match ev(&a[i], p) {
                    Ev::Maybe => return Ev::Maybe,
                    Ev::V(v) if to_boolean(&v) => return ev(&a[i + 1], p),
                    _ => {}
                }
                i += 2;
            }
            ev(&a[a.len() - 1], p)
        }
        "match" => {
            let v = match ev(&a[0], p) { Ev::Maybe => return Ev::Maybe, Ev::V(v) => v };
            let mut i = 1;
            while i + 1 < a.len() {
                let hit = match &a[i] { Value::Array(labels) => labels.iter().any(|l| same(&v, l)), l => same(&v, l) };
                if hit {
                    return ev(&a[i + 1], p);
                }
                i += 2;
            }
            ev(&a[a.len() - 1], p)
        }
        _ => Ev::Maybe,
    }
}

/// _drop_empty_layers: a road layer stays when its filter holds, or may hold, for some feature of its source; roads-fill always stays.
pub(super) fn drop_empty_layers(layers: Vec<Value>, feats: &HashMap<&str, Vec<&dyn Get>>) -> Vec<Value> {
    layers.into_iter().filter(|l| {
        let id = l["id"].as_str().unwrap_or("");
        if !id.starts_with("roads-") || id == "roads-fill" {
            return true;
        }
        let (Some(f), Some(fs)) = (l.get("filter"), l["source"].as_str().and_then(|s| feats.get(s))) else { return true };
        fs.iter().any(|p| match ev(f, *p) { Ev::Maybe => true, Ev::V(v) => to_boolean(&v) })
    }).collect()
}

/// _swap: `v` with every part equal to `old` replaced by `new`.
pub(crate) fn swap(v: &Value, old: &Value, new: &Value) -> Value {
    if v == old {
        return new.clone();
    }
    match v { Value::Array(a) => Value::Array(a.iter().map(|x| swap(x, old, new)).collect()), _ => v.clone() }
}

/// _bake_state: every ["global-state", k] its start value, and the tunnel mix without `let`.
pub(super) fn bake(e: &Value, state: &Map<String, Value>) -> Value {
    match e {
        Value::Array(a) => {
            if a.len() == 2 && a[0] == "global-state" {
                let v = &state[a[1].as_str().unwrap()];
                return if v.is_array() || v.is_object() { json!(["literal", v]) } else { v.clone() };
            }
            if a.len() == 4 && a[0] == "let" && a[1] == "m" && a[2].as_array().is_some_and(|x| x.first() == Some(&json!("to-rgba"))) {
                return bake(&a[2][1], state);
            }
            Value::Array(a.iter().map(|x| bake(x, state)).collect())
        }
        Value::Object(o) => Value::Object(o.iter().map(|(k, v)| (k.clone(), bake(v, state))).collect()),
        _ => e.clone(),
    }
}




pub(super) fn props_of<'a>(fs: &'a [Value], empty: &'a Map<String, Value>) -> Vec<&'a Map<String, Value>> {
    fs.iter().map(|f| f["properties"].as_object().unwrap_or(empty)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// `ev` of `e` on the properties `p`: Some(value), or None where only the page can tell (Ev::Maybe).
    fn ev_of(e: Value, p: Value) -> Option<Value> {
        match ev(&e, p.as_object().unwrap()) {
            Ev::V(v) => Some(v),
            Ev::Maybe => None,
        }
    }

    #[test]
    fn ev_reads_the_properties() {
        let p = json!({"highway": "primary", "lanes": 2, "bridge": "no", "oneway": true});
        assert_eq!(ev_of(json!(["get", "highway"]), p.clone()), Some(json!("primary")));
        assert_eq!(ev_of(json!(["get", "name"]), p.clone()), Some(Value::Null));
        assert_eq!(ev_of(json!(["has", "lanes"]), p.clone()), Some(json!(true)));
        assert_eq!(ev_of(json!(["literal", [1, 2]]), p.clone()), Some(json!([1, 2])));
        assert_eq!(ev_of(json!(["at", 1, ["literal", ["a", "b"]]]), p.clone()), Some(json!("b")));
        assert_eq!(ev_of(json!(["at", 5, ["literal", ["a", "b"]]]), p.clone()), None, "an index past the list: the page tells");
        // the one road-flag rule (roadstyle_model::flags): "no" is no, a text that is set is yes
        assert_eq!(ev_of(json!(["to-boolean", ["get", "bridge"]]), p.clone()), Some(json!(false)));
        assert_eq!(ev_of(json!(["to-boolean", ["get", "highway"]]), p.clone()), Some(json!(true)));
        assert_eq!(ev_of(json!(["!", ["get", "name"]]), p), Some(json!(true)));
    }

    #[test]
    fn ev_compares_as_maplibre() {
        let p = json!({"lanes": 2, "oneway": true, "highway": "primary"});
        // a boolean never equals a number; 2 and 2.0 are the same number
        assert_eq!(ev_of(json!(["==", ["get", "oneway"], 1]), p.clone()), Some(json!(false)));
        assert_eq!(ev_of(json!(["==", ["get", "lanes"], 2.0]), p.clone()), Some(json!(true)));
        assert_eq!(ev_of(json!(["!=", ["get", "highway"], "primary"]), p.clone()), Some(json!(false)));
        assert_eq!(ev_of(json!(["<", "primary", "residential"]), p.clone()), Some(json!(true)));
        assert_eq!(ev_of(json!(["+", "a", "b"]), p.clone()), Some(json!("ab")));
        assert_eq!(ev_of(json!(["%", -1, 3]), p.clone()), Some(json!(2.0)), "the remainder has the sign of the divisor");
        assert_eq!(ev_of(json!(["%", 1, 0]), p.clone()), None);
        assert_eq!(ev_of(json!(["*", ["get", "lanes"], 1.5]), p), Some(json!(3.0)));
    }

    #[test]
    fn ev_gives_maybe_where_only_the_page_can_tell() {
        let p = json!({"highway": "primary"});
        assert_eq!(ev_of(json!(["zoom"]), p.clone()), None);
        // all / any stop at an answer that the rest cannot change, else Maybe stays
        assert_eq!(ev_of(json!(["all", false, ["zoom"]]), p.clone()), Some(json!(false)));
        assert_eq!(ev_of(json!(["all", true, ["zoom"]]), p.clone()), None);
        assert_eq!(ev_of(json!(["any", ["zoom"], true]), p.clone()), Some(json!(true)));
        assert_eq!(ev_of(json!(["==", ["zoom"], 3]), p.clone()), None);
        assert_eq!(ev_of(json!(["coalesce", ["get", "name"], ["get", "highway"]]), p.clone()), Some(json!("primary")));
        assert_eq!(ev_of(json!(["coalesce", ["zoom"], "x"]), p.clone()), None);
        assert_eq!(ev_of(json!(["case", ["==", ["get", "highway"], "trunk"], 1, ["has", "highway"], 2, 3]), p.clone()), Some(json!(2)));
        assert_eq!(ev_of(json!(["match", ["get", "highway"], ["trunk", "primary"], "big", "small"]), p.clone()), Some(json!("big")));
        assert_eq!(ev_of(json!(["match", ["get", "highway"], "trunk", "big", "small"]), p), Some(json!("small")));
    }
}

