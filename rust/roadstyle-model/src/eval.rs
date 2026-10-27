//! A MapLibre expression's value on a feature, for the operators that the tile rules (roadstyle-tiles) and the width keys
//! (roadstyle-engine) read: `get`, `literal`, `coalesce`, `to-boolean`, `!`, `all`, `any`, `==`, `!=`, `at`, `case`, `match`, `+` and `*`.

use serde_json::{Map, Value};

/// A number as JSON: an integer when it has no fraction (the Python engine's `+` and `*` of integers give integers).
pub fn num(x: f64) -> Value {
    if x.fract() == 0.0 && x.abs() < 1e15 { Value::from(x as i64) } else { Value::from(x) }
}

/// An expression of only the operators that `ev` knows.
pub fn known(e: &Value) -> bool {
    match e.as_array() {
        Some(a) => match a.first().and_then(Value::as_str) {
            Some("get" | "literal") => true,
            Some("coalesce" | "to-boolean" | "!" | "all" | "any" | "==" | "!=" | "at" | "case" | "match" | "+" | "*") => a[1..].iter().all(known),
            _ => false,
        },
        None => true,
    }
}

pub fn truthy(v: &Value) -> bool {
    match v {
        Value::Bool(b) => *b,
        Value::Null => false,
        Value::Number(n) => n.as_f64().is_some_and(|x| x != 0.0),
        Value::String(s) => !s.is_empty(),
        _ => true,
    }
}

pub fn same(a: &Value, b: &Value) -> bool {
    match (a.as_f64(), b.as_f64()) {
        (Some(x), Some(y)) => x == y,
        _ => a == b,
    }
}

/// The value of a MapLibre expression on a feature, for the operators of the clauses; Null for another operator (the clause then
/// gives 0: the feature stays in the tiles).
pub fn ev(e: &Value, p: &Map<String, Value>) -> Value {
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
        "+" => (1..a.len()).map(arg).try_fold(0.0, |s, v| v.as_f64().map(|x| s + x)).map_or(Value::Null, num),
        "*" => (1..a.len()).map(arg).try_fold(1.0, |s, v| v.as_f64().map(|x| s * x)).map_or(Value::Null, num),
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

