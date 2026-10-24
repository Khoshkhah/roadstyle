//! A level area as the level editor has it (roadstyle_levels::area), on tests/data/level_area/ (tests/make_goldens.py level_area): the
//! solve is feasible (the solver checks its hard rules), with edits and with the local re-solve, and the check before a rule is added
//! says what roadstyle's rule_conflicts says.

use roadstyle_rs::level_editor::read_pairs;
use roadstyle_rs::levels::area::{Area, AreaRoad, PairRow, Previous, Relation, Why};
use serde_json::Value;
use std::collections::HashMap;
use std::path::PathBuf;

fn data(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/level_area").join(name)
}

fn area() -> Area {
    let rows = roadstyle_rs::read::read_table(std::fs::read(data("roads.parquet")).unwrap(), "geometry").unwrap();
    let id = |v: &Value| v.as_str().unwrap().parse::<i64>().unwrap();
    let ids = |v: &Value| v.as_array().unwrap().iter().map(id).collect();
    let roads = rows.iter().map(|r| AreaRoad { id: id(&r.cols["road"]), edges: ids(&r.cols["edges"]), reversed: ids(&r.cols["reversed"]) })
        .collect();
    Area::new(roads, read_pairs(&std::fs::read_to_string(data("pairs.csv")).unwrap()).unwrap()).unwrap()
}

#[test]
fn the_solve_with_edits_and_the_local_re_solve() {
    let a = area();
    let base = a.solve(&[], &HashMap::new(), 20, 1.0).unwrap();
    assert_eq!(base.levels.len(), a.roads.len());
    assert!(base.levels.iter().all(|v| v[0].max(v[1]).max(v[2]) <= v[3]), "a casing over its fill");
    let stack = a.pairs.iter().find(|r| r.relation == Relation::Stack).unwrap().clone();
    let order = a.pairs.iter().find(|r| r.relation == Relation::Order).unwrap().clone();
    let edits = [PairRow { enabled: false, ..stack.clone() }, PairRow { enabled: false, ..order.clone() },
                 PairRow { a: order.b, b: order.a, ..order.clone() }];
    assert_eq!(a.merged(&edits).unwrap().len(), a.pairs.len() - 1, "two rules off, one on");
    let (local, how) = a.solve_local(&edits, &Previous::from(&base), &[stack.a, order.a], 3, 20, 1.0).unwrap();
    assert!(local.levels.iter().all(|v| v[0].max(v[1]).max(v[2]) <= v[3]), "{how:?}");
    // a rule that switches off a rule that is not there
    let off = PairRow { a: order.b, b: order.a, enabled: false, ..order };
    assert!(matches!(a.merged(&[off]).unwrap_err(), roadstyle_rs::levels::Error::Edits(m) if m.contains("to switch off")));
}

#[test]
fn the_check_before_a_rule_is_added_as_roadstyle() {
    let a = area();
    let checks: Value = serde_json::from_str(&std::fs::read_to_string(data("checks.json")).unwrap()).unwrap();
    let text = |v: &Value, k: &str| v[k].as_str().unwrap_or("").to_string();
    let csv = std::iter::once("relation,a,b,a_end,b_end,enabled".to_string())
        .chain(checks["rows"].as_array().unwrap().iter().map(|r| ["relation", "a", "b", "a_end", "b_end", "enabled"].map(|k| text(r, k)).join(",")))
        .collect::<Vec<_>>().join("\n");
    let got: Vec<Value> = a.conflicts(&[], &read_pairs(&csv).unwrap()).unwrap().into_iter().map(|c| {
        assert!(!c.with.is_empty());
        serde_json::json!([c.row, match c.why { Why::Duplicate => "duplicate", Why::NotKept => "not kept", Why::Loop => "loop" }])
    }).collect();
    assert_eq!(Value::Array(got), checks["conflicts"]);
}

/// make (roadstyle-levels make) on make's input of the fixture: the same roads.parquet (every column but the line, which is the first
/// edge's) and the same pairs.csv rows as roadstyle's make_area.
#[test]
fn make_gives_roadstyle_s_input() {
    let dir = std::env::temp_dir().join(format!("roadstyle-make-{}", std::process::id()));
    let table = roadstyle_rs::read::read_roads(std::fs::read(data("edges.parquet")).unwrap(), "geometry").unwrap();
    let made = roadstyle_rs::level_area::make_area(&table, &dir, &Default::default()).unwrap();
    let lines = |p: PathBuf| {
        let mut l: Vec<String> = std::fs::read_to_string(p).unwrap().lines().map(String::from).collect();
        l.sort();
        l
    };
    assert_eq!(lines(dir.join("pairs.csv")), lines(data("pairs.csv")));
    let rows = |p: PathBuf| roadstyle_rs::read::read_table(std::fs::read(p).unwrap(), "geometry").unwrap();
    let (got, want) = (rows(dir.join("roads.parquet")), rows(data("roads.parquet")));
    assert_eq!((made.roads, got.len()), (want.len(), want.len()));
    for (g, w) in got.iter().zip(&want) {
        assert_eq!(g.cols, w.cols, "road {}", w.cols["road"]);
        assert_eq!(g.blob.is_some(), w.blob.is_some());
    }
    std::fs::remove_dir_all(&dir).ok();
}
