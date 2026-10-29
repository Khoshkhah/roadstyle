//! Zoom bands for the road layer (docs/design/tile_speed.md, "Zoom bands"). MapLibre evaluates each data-driven paint property for each
//! feature of a tile, so a property that is a constant at the zoom of the tile is cheaper. A zoom curve whose first stops give one value
//! is that value below its last such stop: the road layer is then one layer for each band of zooms, and a band puts the constant in the
//! place of the curve. A tile builds only the layers of its zoom (the worker skips a layer whose `minzoom` and `maxzoom` exclude it).

use super::*;

/// The paint properties that a band can make constant.
const PROPERTIES: [&str; 3] = ["line-blur", "line-opacity", "line-offset"];

/// A value that is 0 for every feature (a literal 0, a table of 0, a `case` or `match` that gives only 0, a product with a 0).
fn is_zero(v: &Value) -> bool {
    let Some(a) = v.as_array() else { return v.as_f64() == Some(0.0) };
    match a.first().and_then(Value::as_str) {
        Some("literal") => a[1].as_array().map_or(a[1].as_f64() == Some(0.0), |l| l.iter().all(|x| x.as_f64() == Some(0.0))),
        Some("*") => a[1..].iter().any(is_zero),
        Some("at") => is_zero(&a[2]),
        // the outputs: after each condition, and the last (the fallback)
        Some("case") => a[2..].iter().step_by(2).chain([a.last().unwrap()]).all(is_zero),
        Some("match") => a[3..].iter().step_by(2).chain([a.last().unwrap()]).all(is_zero),
        _ => false,
    }
}

/// The zoom up to which a paint value is one value for every zoom, and that value: the first stop's value up to the first stop, a 0 up to
/// the last of the stops that start with 0.
fn constant_until(v: &Value) -> Option<(f64, Value)> {
    let [op, how, input, stops @ ..] = v.as_array()?.as_slice() else { return None };
    if op != "interpolate" || how[0] != "linear" || input != &json!(["zoom"]) {
        return None;
    }
    let stop = |i: usize| (stops[2 * i].as_f64().unwrap(), &stops[2 * i + 1]);
    let n = stops.len() / 2;
    if !is_zero(stop(0).1) {
        return Some((stop(0).0, stop(0).1.clone()));
    }
    let last = (0..n).take_while(|&i| is_zero(stop(i).1)).last().unwrap();
    Some((stop(last).0, json!(0)))
}

/// A zoom curve (or a `let` over one) with only the stops that the zooms from `lo` up to `hi` read: from the last stop at or before `lo` to
/// the first stop at or after `hi`. A curve between the same stops gives the same value.
fn trim_stops(v: &Value, lo: f64, hi: f64) -> Value {
    match v.as_array().map(Vec::as_slice) {
        Some([l, name, row, curve]) if l == "let" => json!(["let", name, row, trim_stops(curve, lo, hi)]),
        Some([op, how, input, stops @ ..]) if op == "interpolate" && input == &json!(["zoom"]) => {
            let zs: Vec<f64> = stops.iter().step_by(2).map(|z| z.as_f64().unwrap()).collect();
            let from = zs.iter().rposition(|z| *z <= lo).unwrap_or(0);
            let to = zs.iter().position(|z| *z >= hi).unwrap_or(zs.len() - 1).max((from + 1).min(zs.len() - 1));
            let mut out = vec![op.clone(), how.clone(), input.clone()];
            out.extend(stops[2 * from..2 * (to + 1)].iter().cloned());
            Value::Array(out)
        }
        _ => v.clone(),
    }
}

/// The road layer as one layer for each band of zooms. The first keeps the id (the dashboard finds the road layer by it); the others are
/// `<id>-z<first zoom>`. A layer with no band to make stays as it is.
pub(super) fn split(layer: Value) -> Vec<Value> {
    let constants: Vec<(&str, f64, Value)> =
        PROPERTIES.iter().filter_map(|k| constant_until(layer["paint"].get(k)?).map(|(z, v)| (*k, z, v))).collect();
    let mut cuts: Vec<f64> = constants.iter().map(|c| c.1).filter(|z| *z > 0.0).collect();
    cuts.sort_by(f64::total_cmp);
    cuts.dedup();
    if cuts.is_empty() {
        return vec![layer];
    }
    let edges: Vec<f64> = std::iter::once(0.0).chain(cuts.iter().copied()).collect();
    edges.iter().enumerate().map(|(i, &lo)| {
        let hi = edges.get(i + 1).copied();
        let mut l = layer.clone();
        for v in l["paint"].as_object_mut().into_iter().flat_map(|p| p.values_mut()) {
            *v = trim_stops(v, lo, hi.unwrap_or(f64::INFINITY));
        }
        if i > 0 {
            l["id"] = format!("{}-z{lo}", layer["id"].as_str().unwrap()).into();
            l["minzoom"] = json!(lo);
        }
        if let Some(hi) = hi {
            l["maxzoom"] = json!(hi);
        }
        for (k, _, v) in constants.iter().filter(|c| hi.is_some_and(|hi| hi <= c.1)) {
            l["paint"][*k] = v.clone();
        }
        l
    }).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::layers::build::{line_paint, widths, Ctx};
    use crate::layers::eval::{ev, Ev};

    const LOOK: &[u8] = include_bytes!("../../../roadstyle-rs/tests/data/look.json");

    /// The value of a paint property at the zoom `z` for the feature `p`: the zoom curve between the two stops round `z`.
    fn value_at(e: &Value, z: f64, p: &Map<String, Value>, fill_on: bool) -> f64 {
        // a `let` over the curve (the width's row): the row's value in place of its variable
        let (row, e) = match e.as_array().map(Vec::as_slice) {
            Some([l, name, row, curve]) if l == "let" => (Some((name.clone(), row)), curve),
            _ => (None, e),
        };
        let state = |v: &Value| swap(&swap(v, &json!(["coalesce", ["feature-state", LIVE_WIDTH], 1]), &json!(1.0)), &gs("rs_fill_on"), &json!(fill_on));
        let num = |v: &Value| match ev(&row.as_ref().map_or_else(|| state(v), |(name, r)| {
            let Ev::V(r) = ev(&state(r), p) else { panic!("the row is not known") };
            swap(&state(v), &json!(["var", name]), &r)
        }), p) { Ev::V(v) => as_num(&v).expect("a number"), Ev::Maybe => panic!("not known: {v}") };
        let Some([op, _, _, stops @ ..]) = e.as_array().map(Vec::as_slice).filter(|a| a[0] == "interpolate") else { return num(e) };
        assert_eq!(op, "interpolate");
        let zs: Vec<f64> = stops.iter().step_by(2).map(|z| z.as_f64().unwrap()).collect();
        let hi = zs.iter().position(|s| *s >= z).unwrap_or(zs.len() - 1);
        let lo = zs.iter().rposition(|s| *s <= z).unwrap_or(0);
        if lo == hi || z <= zs[0] || z >= zs[zs.len() - 1] {
            return num(&stops[2 * if z <= zs[0] { 0 } else if z >= zs[zs.len() - 1] { zs.len() - 1 } else { lo } + 1]);
        }
        let t = (z - zs[lo]) / (zs[hi] - zs[lo]);
        num(&stops[2 * lo + 1]) * (1.0 - t) + num(&stops[2 * hi + 1]) * t
    }

    /// Each band layer gives the values of the one layer at the zooms of the band, for every kind of piece, class, flag and state.
    #[test]
    fn the_bands_give_the_values_of_the_one_layer() {
        let mut look: Value = serde_json::from_slice(LOOK).unwrap();
        look["args"]["arrows"] = true.into();
        let look = crate::Look::from_value(look).unwrap();
        let table = roadstyle_model::RoadTable::new(Vec::new(), Vec::new(), roadstyle_model::table::Lines::default()).unwrap();
        let roles = roadstyle_model::Roles::resolve(&table, &[]).unwrap();
        let roads = crate::road::Roads::new(table, roles, None);
        let (classes, mut checked) = (look.model.classes.clone(), 0);
        for (pairs, tunnel) in [(false, false), (true, false), (true, true)] {
            let mut cx = Ctx::new(&look, &roads, false).unwrap();
            (cx.pairs, cx.any_tunnel) = (pairs, tunnel);
            let (paint, _) = line_paint(&cx, &widths(&cx, false), &[], &["__rs_fill".to_string()]);
            let one = json!({"id": "roads-simple", "type": "line", "source": "simple", "paint": paint});
            let bands = split(one.clone());
            assert!(bands.len() >= 3, "{} layers", bands.len());
            assert_eq!(bands[0]["id"], "roads-simple");
            for band in &bands {
                let (lo, hi) = (band["minzoom"].as_f64().unwrap_or(0.0), band["maxzoom"].as_f64().unwrap_or(24.0));
                for kind in 0..=4 {
                    for flags in 0..8 {
                        for class in 0..=classes.len() {
                            let p = json!({"highway": classes.get(class).cloned().unwrap_or_else(|| "other".into()), "__rs_ci": class, "__rs_k": kind,
                                           "__rs_bridge": flags & 1 == 1, "__rs_twoway": flags & 2 == 2, "__rs_pair": flags & 4 == 4});
                            let p = p.as_object().unwrap();
                            for z in (0..48).map(|i| i as f64 / 2.0).filter(|z| (lo..hi).contains(z)) {
                                for fill_on in [true, false] {
                                    for k in ["line-width", "line-blur", "line-opacity", "line-offset"] {
                                        let (a, b) = (value_at(&one["paint"][k], z, p, fill_on), value_at(&band["paint"][k], z, p, fill_on));
                                        assert!((a - b).abs() < 1e-9, "{k} kind {kind} flags {flags} class {class} zoom {z} fill_on {fill_on}: {a} against {b}");
                                        checked += 1;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        assert!(checked > 100_000, "{checked}");
    }

    #[test]
    fn a_band_has_constants_where_the_curve_is_constant() {
        let one = json!({"id": "roads-simple", "paint": {
            "line-blur": ["interpolate", ["linear"], ["zoom"], 14, 0, 17, ["get", "b"]],
            "line-opacity": ["interpolate", ["linear"], ["zoom"], 14, ["case", ["get", "a"], 0, 1], 17, 1],
            "line-offset": ["interpolate", ["linear"], ["zoom"], 12, ["*", ["case", ["get", "t"], ["at", ["get", "c"], ["literal", [0, 0]]], 0], 2], 15, ["*", 0, 2], 16, ["get", "o"]]}});
        let bands = split(one);
        let ids: Vec<&str> = bands.iter().map(|b| b["id"].as_str().unwrap()).collect();
        assert_eq!(ids, ["roads-simple", "roads-simple-z14", "roads-simple-z15"]);
        assert_eq!((bands[0]["maxzoom"].clone(), bands[1]["minzoom"].clone(), bands[1]["maxzoom"].clone(), bands[2].get("maxzoom")), (json!(14.0), json!(14.0), json!(15.0), None));
        assert_eq!(bands[0]["paint"]["line-blur"], json!(0));
        assert_eq!(bands[0]["paint"]["line-opacity"], json!(["case", ["get", "a"], 0, 1]));
        assert_eq!(bands[0]["paint"]["line-offset"], json!(0));
        assert_eq!(bands[1]["paint"]["line-blur"].as_array().unwrap()[0], "interpolate", "z14 to z15 is not constant");
        assert_eq!(bands[1]["paint"]["line-offset"], json!(0));
        assert_eq!(bands[2]["paint"]["line-offset"].as_array().unwrap()[0], "interpolate");
    }

    #[test]
    fn a_layer_with_nothing_constant_stays_one_layer() {
        let one = json!({"id": "roads-simple", "paint": {"line-blur": ["get", "b"], "line-offset": ["get", "o"]}});
        assert_eq!(split(one.clone()), vec![one]);
    }
}
