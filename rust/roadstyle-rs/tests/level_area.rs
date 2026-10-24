//! A level area as the level editor has it (roadstyle_levels::area), on tests/data/level_area/ (tests/make_goldens.py level_area): the
//! solve is feasible (the solver checks its hard rules), with edits and with the local re-solve, and the check before a rule is added
//! says what roadstyle's rule_conflicts says.

use roadstyle_rs::levels::area::{read_rows, Area, AreaRoad, PairRow};
use serde_json::Value;
use std::collections::HashMap;
use std::path::PathBuf;

fn data(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/level_area").join(name)
}

fn area() -> Area {
    let rows = roadstyle_rs::read::read_table(std::fs::read(data("roads.parquet")).unwrap(), "geometry").unwrap();
    let ids = |v: &Value| v.as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect();
    let roads = rows.iter().map(|r| AreaRoad { id: r.cols["road"].as_str().unwrap().into(), edges: ids(&r.cols["edges"]), reversed: ids(&r.cols["reversed"]) })
        .collect();
    Area::new(roads, read_rows(&std::fs::read_to_string(data("pairs.csv")).unwrap()).unwrap())
}

fn row(relation: &str, a: &str, b: &str, a_end: &str, enabled: &str) -> PairRow {
    PairRow { relation: relation.into(), a: a.into(), b: b.into(), a_end: a_end.into(), enabled: enabled.into(), ..Default::default() }
}

#[test]
fn the_solve_with_edits_and_the_local_re_solve() {
    let a = area();
    let base = a.solve(&[], &HashMap::new(), 20, 1.0).unwrap();
    assert_eq!(base.levels.len(), a.roads.len());
    assert!(base.levels.iter().all(|v| v[0].max(v[1]).max(v[2]) <= v[3]), "a casing over its fill");
    let stack = a.pairs.iter().find(|r| r.relation == "stack").unwrap().clone();
    let order = a.pairs.iter().find(|r| r.relation == "order").unwrap().clone();
    let edits = [row("stack", &stack.a, &stack.b, &stack.a_end, "false"), row("order", &order.a, &order.b, "", "false"),
                 row("order", &order.b, &order.a, "", "true")];
    let merged = a.merged(&edits).unwrap();
    assert_eq!(merged.len(), a.pairs.len() - 1, "two rules off, one on");
    let (local, how) = a.solve_local(&edits, &base, &[stack.a.clone(), order.a.clone()], 3, 20, 1.0).unwrap();
    assert!(local.levels.iter().all(|v| v[0].max(v[1]).max(v[2]) <= v[3]), "{how:?}");
    // a rule that switches off a rule that is not there
    assert!(a.merged(&[row("order", &order.b, &order.a, "", "false")]).unwrap_err().contains("to switch off"));
}

#[test]
fn the_check_before_a_rule_is_added_as_roadstyle() {
    let a = area();
    let checks: Value = serde_json::from_str(&std::fs::read_to_string(data("checks.json")).unwrap()).unwrap();
    let text = |v: &Value, k: &str| v[k].as_str().unwrap_or("").to_string();
    let rows: Vec<PairRow> = checks["rows"].as_array().unwrap().iter().map(|r| PairRow {
        relation: text(r, "relation"), a: text(r, "a"), b: text(r, "b"), a_end: text(r, "a_end"), b_end: text(r, "b_end"), enabled: text(r, "enabled"),
    }).collect();
    let got: Vec<Value> = a.conflicts(&[], &rows).unwrap().into_iter().map(|(i, why, with)| {
        assert!(!with.is_empty());
        serde_json::json!([i, why])
    }).collect();
    assert_eq!(Value::Array(got), checks["conflicts"]);
}
