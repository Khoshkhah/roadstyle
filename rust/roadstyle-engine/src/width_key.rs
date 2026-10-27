//! The road layer's width and offset as one table lookup for each zoom stop (docs/design/tile_contract.md, phase 1).
//!
//! The layer's `line-width` and `line-offset` are an `interpolate` on the zoom whose stops are a `case` tree on the piece's kind
//! (`__rs_k`), `__rs_pair`, `__rs_bridge` and `__rs_twoway`, and a class table (`["at", ["get", "__rs_ci"], ["literal", [...]]]`).
//! MapLibre calculates the tree for each feature at two zooms: 0.38 s of 1.4 s on the Burnaby tilted view. Here the engine calculates
//! it one time for each combination of the four values and the class, and the style has one table for each stop that a piece reads with
//! one small integer, `__rs_wk` (a mode of the four values, times the number of classes, plus the class index). The pixels do not change:
//! the tables hold the numbers of the old expression.

use roadstyle_model::eval::{ev, known, num};
use roadstyle_model::mark::Mark;
use serde_json::{json, Map, Value};

const KINDS: usize = 6;
const MODES: usize = 20;

/// The mode of a piece's kind and flags: the width reads its kind group (a shadow, a bridge's casing, a tunnel's gap or dashes, another
/// casing, a fill or an item), the pair flag and the twoway flag (the width of a two-way road at the higher zooms); the offset reads the pair
/// flag and the twoway flag.
/// `compact` checks that the old expressions give the same numbers inside each mode.
fn mode(kind: usize, pair: bool, bridge: bool, twoway: bool) -> usize {
    let group = match kind {
        2 => 0,
        0 if bridge => 1,
        3 | 4 => 2,
        0 => 3,
        _ => 4,
    };
    group * 4 + usize::from(pair) * 2 + usize::from(twoway)
}

/// The key of a piece (None: a kind that the layer does not know, or a class index out of `stride`, the classes and one more).
pub fn key(kind: i64, pair: bool, bridge: bool, twoway: bool, class: usize, stride: usize) -> Option<i64> {
    let kind = usize::try_from(kind).ok().filter(|k| *k < KINDS)?;
    (class < stride).then(|| (mode(kind, pair, bridge, twoway) * stride + class) as i64)
}

/// The stops of an `interpolate` on the zoom whose outputs are `["*", E, factor]`: (zoom, E), and the factor.
fn stops(e: &Value) -> Option<(Vec<(Value, Value)>, Value)> {
    let a = e.as_array()?;
    if a.len() < 5 || a[0] != "interpolate" || a[2] != json!(["zoom"]) {
        return None;
    }
    let mut out = Vec::new();
    let mut factor = None;
    for p in a[3..].chunks(2) {
        let o = p.get(1)?.as_array()?;
        if o.len() != 3 || o[0] != "*" || factor.as_ref().is_some_and(|f| *f != o[2]) {
            return None;
        }
        factor = Some(o[2].clone());
        out.push((p[0].clone(), o[1].clone()));
    }
    Some((out, factor?))
}

/// The keys that an expression reads.
fn gets(e: &Value, out: &mut Vec<String>) {
    if let Value::Array(a) = e {
        if let [op, Value::String(k)] = a.as_slice() {
            if op == "get" || op == "has" {
                out.push(k.clone());
            }
        }
        a.iter().for_each(|x| gets(x, out));
    }
}

/// Replace the road layer's `line-width` and `line-offset` (in `paint`, after `layers::class_index`) by one table for each stop, read by
/// `__rs_wk`. None, and `paint` as it was, when an expression has another shape, reads another key, or has a value that is not a
/// number: the layer then keeps its expressions and its pieces have no key.
pub fn compact(paint: &mut Value, stride: usize) -> bool {
    compact_to(paint, stride).is_some()
}

fn compact_to(paint: &mut Value, stride: usize) -> Option<()> {
    let (wide, ws) = stops(&paint["line-width"])?;
    let (off, os) = stops(&paint["line-offset"])?;
    let own = [Mark::PieceKind, Mark::Pair, Mark::Bridge, Mark::Twoway, Mark::ClassIndex].map(|m| m.name().to_string());
    let mut read = Vec::new();
    wide.iter().chain(&off).for_each(|(_, e)| gets(e, &mut read));
    if !wide.iter().chain(&off).all(|(_, e)| known(e)) || read.iter().any(|k| !own.contains(k)) {
        return None;
    }
    let exprs: Vec<&Value> = wide.iter().chain(&off).map(|(_, e)| e).collect();
    // the value of every stop's expression for each (mode, class), from the first combination of the mode; every other one must agree
    let mut rows: Vec<Option<Vec<Vec<f64>>>> = vec![None; MODES];      // [mode][class] -> values
    for code in 0..KINDS * 8 {
        let (kind, pair, bridge, twoway) = (code / 8, code / 4 % 2 == 1, code / 2 % 2 == 1, code % 2 == 1);
        let mut by_class = Vec::new();
        for class in 0..stride {
            let mut p = Map::new();
            p.insert(Mark::PieceKind.name().into(), json!(kind));
            for (m, on) in [(Mark::Pair, pair), (Mark::Bridge, bridge), (Mark::Twoway, twoway)] {
                if on {
                    p.insert(m.name().into(), json!(true));      // a false flag is not in a tile
                }
            }
            p.insert(Mark::ClassIndex.name().into(), json!(class));
            by_class.push(exprs.iter().map(|e| ev(e, &p).as_f64()).collect::<Option<Vec<f64>>>()?);
        }
        let slot = &mut rows[mode(kind, pair, bridge, twoway)];
        match slot {
            None => *slot = Some(by_class),
            Some(first) if *first != by_class => return None,      // the modes do not tell these expressions apart: no keys
            _ => {}
        }
    }
    let seen: Vec<&Vec<Vec<f64>>> = rows.iter().map(|r| r.as_ref()).collect::<Option<_>>()?;
    let table = |i: usize| Value::Array(seen.iter().flat_map(|m| m.iter().map(move |v| num(v[i]))).collect());
    let make = |ss: &[(Value, Value)], factor: &Value, first: usize| {
        let mut out = vec![json!("interpolate"), json!(["linear"]), json!(["zoom"])];
        for (j, (z, _)) in ss.iter().enumerate() {
            out.push(z.clone());
            out.push(json!(["*", ["at", ["get", Mark::WidthKey.name()], ["literal", table(first + j)]], factor]));
        }
        Value::Array(out)
    };
    let (w, o) = (make(&wide, &ws, 0), make(&off, &os, wide.len()));
    paint["line-width"] = w;
    paint["line-offset"] = o;
    Some(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The width and the offset of the Burnaby road layer before the width keys (28 classes and the fallback, 9 stops each): every combination of the
    /// kind, the three flags and the class gives the same number from the table as from the old expression, at every stop.
    #[test]
    fn the_tables_give_the_numbers_of_the_old_expressions() {
        let old: Value = serde_json::from_str(include_str!("../tests/data/road_width_old.json")).unwrap();
        let mut new = old.clone();
        assert!(compact(&mut new, 29), "the road layer's expressions have the known shape");
        let mut keys = std::collections::HashSet::new();
        for prop in ["line-width", "line-offset"] {
            let (o, w) = (old[prop].as_array().unwrap(), new[prop].as_array().unwrap());
            assert_eq!(o.len(), w.len());
            assert_eq!(o.len(), 3 + 2 * 9, "{prop}: the stops");
            for i in 0..9 {
                assert_eq!(o[3 + 2 * i], w[3 + 2 * i], "{prop}: the zoom of stop {i}");
                assert_eq!(o[4 + 2 * i][2], w[4 + 2 * i][2], "{prop}: the live factor of stop {i}");
                for code in 0..KINDS * 8 {
                    let (kind, pair, bridge, twoway) = (code / 8, code / 4 % 2 == 1, code / 2 % 2 == 1, code % 2 == 1);
                    for class in 0..29usize {
                        let mut p = Map::new();
                        p.insert("__rs_k".into(), json!(kind));
                        for (k, on) in [("__rs_pair", pair), ("__rs_bridge", bridge), ("__rs_twoway", twoway)] {
                            if on {
                                p.insert(k.into(), json!(true));
                            }
                        }
                        p.insert("__rs_ci".into(), json!(class));
                        let k = key(kind as i64, pair, bridge, twoway, class, 29).unwrap();
                        keys.insert(k);
                        p.insert("__rs_wk".into(), json!(k));
                        let (a, b) = (ev(&o[4 + 2 * i][1], &p).as_f64().unwrap(), ev(&w[4 + 2 * i][1], &p).as_f64().unwrap());
                        assert_eq!(a, b, "{prop}, stop {i}, kind {kind} pair {pair} bridge {bridge} twoway {twoway} class {class}");
                    }
                }
            }
        }
        assert_eq!(keys.len(), MODES * 29, "every mode is used");
        assert!(key(6, false, false, false, 0, 29).is_none() && key(0, false, false, false, 29, 29).is_none());
    }

    #[test]
    fn modes_that_do_not_tell_the_expressions_apart_give_no_keys() {
        // a width that reads the twoway flag of a casing: one mode holds both values of it
        let old: Value = serde_json::from_str(include_str!("../tests/data/road_width_old.json")).unwrap();
        let mut paint = old.clone();
        let e = paint["line-width"][4][1].clone();
        paint["line-width"][4][1] = json!(["+", e, ["case", ["to-boolean", ["get", "__rs_twoway"]], 1, 0]]);
        paint["line-width"][4][1] = json!(["+", paint["line-width"][4][1].clone(), ["case", ["to-boolean", ["get", "__rs_bridge"]], 1, 0]]);
        let ok = compact(&mut paint.clone(), 29);
        // twoway and bridge are both in the modes' keys for a casing, a fill, ... except where a mode merges them: a fill with bridge
        assert!(!ok, "a fill's width that reads the bridge flag is not what the modes tell apart");
    }

    #[test]
    fn an_expression_that_reads_another_key_stays() {
        let old: Value = serde_json::from_str(include_str!("../tests/data/road_width_old.json")).unwrap();
        let mut paint = old.clone();
        paint["line-width"][4] = json!(["*", ["+", paint["line-width"][4][1].clone(), ["get", "__rs_w"]], ["coalesce", ["feature-state", "rs_w"], 1]]);
        let before = paint.clone();
        assert!(!compact(&mut paint, 29));
        assert_eq!(paint, before, "the paint is as it was");
    }
}
