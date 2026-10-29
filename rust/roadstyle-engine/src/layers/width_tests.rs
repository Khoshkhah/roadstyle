//! width_table.rs against the case form (`width_curve`): the same width for every piece, in each mode of the style.

use super::*;
use crate::layers::width_table::{piece, table_form, ROW_VAR};
use crate::layers::eval::{ev, Ev};

const LOOK: &[u8] = include_bytes!("../../../roadstyle-rs/tests/data/look.json");
const ROWS: usize = 48;

/// The width of a piece at zoom `z` (`live`: the feature state of the width): the zoom curve, with the variable of a `let` put in. Only the
/// two stops round `z` are evaluated.
fn width_at(e: &Value, z: f64, p: &Map<String, Value>, live: Option<f64>) -> f64 {
    let (row, curve) = if e[0] == "let" { (ev(&e[2], p), e[3].as_array().unwrap()) } else { (Ev::Maybe, e.as_array().unwrap()) };
    let state = json!(["coalesce", ["feature-state", LIVE_WIDTH], 1]);
    let at_stop = |i: usize| {
        let mut stop = swap(&curve[4 + 2 * i], &state, &json!(live.unwrap_or(1.0)));
        if let Ev::V(r) = &row {
            stop = swap(&stop, &json!(["var", ROW_VAR]), r);
        }
        let Ev::V(v) = ev(&stop, p) else { panic!("a stop is not known") };
        v.as_f64().unwrap()
    };
    let zs: Vec<f64> = curve[3..].iter().step_by(2).map(|z| z.as_f64().unwrap()).collect();
    let hi = zs.iter().position(|s| *s >= z).unwrap_or(zs.len() - 1);
    let lo = zs.iter().rposition(|s| *s <= z).unwrap_or(0);
    if lo == hi {
        return at_stop(lo);
    }
    let t = (z - zs[lo]) / (zs[hi] - zs[lo]);
    at_stop(lo) * (1.0 - t) + at_stop(hi) * t
}

/// The old and the new width agree for every piece kind, flag, class, zoom (11 to 21, in halves) and live width.
#[test]
fn the_table_gives_the_widths_of_the_case_form() {
    let mut look: Value = serde_json::from_slice(LOOK).unwrap();
    look["args"]["arrows"] = true.into();
    let look = crate::Look::from_value(look).unwrap();
    let table = roadstyle_model::RoadTable::new(Vec::new(), Vec::new(), roadstyle_model::table::Lines::default()).unwrap();
    let roles = roadstyle_model::Roles::resolve(&table, &[]).unwrap();
    let roads = crate::road::Roads::new(table, roles, None);
    let (classes, live, mut checked) = (look.model.classes.clone(), json!(["coalesce", ["feature-state", LIVE_WIDTH], 1]), 0);
    for (pairs, tunnel) in [(false, false), (true, false), (true, true)] {
        let mut cx = Ctx::new(&look, &roads, false).unwrap();
        (cx.pairs, cx.any_tunnel) = (pairs, tunnel);
        let curve = width_curve(&cx, &widths(&cx, false), false);
        let (old, new) = (times_each_stop(&curve, &live), table_form(&curve, cx.hw, &classes, &live).expect("the page's width is a table"));
        for row in 0..ROWS {
            for class in 0..=classes.len() {
                let p = piece(row, class, cx.hw, &classes);
                for z in (22..=42).map(|i| i as f64 / 2.0) {
                    for live in [None, Some(2.5)] {
                        let (a, b) = (width_at(&old, z, &p, live), width_at(&new, z, &p, live));
                        assert!((a - b).abs() < 1e-5, "pairs {pairs} tunnel {tunnel} row {row} class {class} zoom {z} live {live:?}: {a} against {b}");
                        checked += 1;
                    }
                }
            }
        }
    }
    assert!(checked > 100_000);
}

#[test]
fn a_width_that_a_feature_sets_is_not_a_table() {
    let (classes, live) = (["primary".to_string()], json!(1));
    let wm = Mark::WidthM.name();
    let metres = json!(["interpolate", ["linear"], ["zoom"], 12, ["case", ["has", wm], ["get", wm], 2]]);
    assert!(table_form(&metres, "highway", &classes, &live).is_none());
    let max = json!(["interpolate", ["linear"], ["zoom"], 12, ["max", 1, 2]]);
    assert!(table_form(&max, "highway", &classes, &live).is_none(), "an operator that the evaluator does not know");
}
