//! A level area as the level editor has it (roadstyle_levels::area), made by roadstyle-levels make from tests/data/level_area/edges.parquet
//! (a part of Monaco). The goldens are the engine's (`ROADSTYLE_BLESS=1` writes them): make's output (level_area/rust_make.json: the
//! counts and the hashes of roads.parquet's rows and pairs.csv's rows) and the check before a rule is added (level_area/rust_conflicts.json).
//! The solve is feasible (the solver checks its hard rules), with edits and with the local re-solve.

mod common;

use roadstyle_rs::level_editor::read_pairs;
use roadstyle_rs::levels::area::{Area, AreaRoad, PairRow, Previous, Relation, Why};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::OnceLock;

/// make's files of the fixture's edges, in memory: (roads.parquet, pairs.csv).
fn made() -> &'static (Vec<u8>, String) {
    static MADE: OnceLock<(Vec<u8>, String)> = OnceLock::new();
    MADE.get_or_init(|| {
        let p = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/level_area/edges.parquet");
        let table = roadstyle_rs::read::read_roads(std::fs::read(p).unwrap(), "geometry").unwrap();
        let f = roadstyle_rs::level_area::make_files(&table, &Default::default(), "").unwrap();
        (f.roads, f.pairs)
    })
}

fn area() -> Area {
    let rows = roadstyle_rs::read::read_table(made().0.clone(), "geometry").unwrap();
    let id = |v: &Value| v.as_i64().unwrap();      // roads.parquet has the ids as Int64
    let ids = |v: &Value| v.as_array().unwrap().iter().map(id).collect();
    let roads = rows.iter().map(|r| AreaRoad { id: id(&r.cols["road"]), edges: ids(&r.cols["edges"]), reversed: ids(&r.cols["reversed"]) })
        .collect();
    Area::new(roads, read_pairs(&made().1).unwrap()).unwrap()
}

#[test]
fn make_is_its_golden() {
    let rows = roadstyle_rs::read::read_table(made().0.clone(), "geometry").unwrap();
    let mut pairs: Vec<&str> = made().1.lines().collect();
    pairs.sort();
    let rows_json: Vec<Value> = rows.iter().map(|r| json!([r.cols, r.blob])).collect();
    common::golden("level_area/rust_make.json", &json!({"roads": rows.len(), "pairs": pairs.len() - 1, "columns": rows[0].cols.keys().collect::<Vec<_>>(),
        "roads_hash": common::hash16(&Value::Array(rows_json)), "pairs_hash": common::hash16(&json!(pairs))}));
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

/// The check before rules are added: an order wish that is there (a duplicate), one the other way of a stack (a loop) and one between the
/// first and the last road; the answers (the row, why, and how many rules it meets) are the golden.
#[test]
fn the_check_before_a_rule_is_added_is_its_golden() {
    let a = area();
    let order = a.pairs.iter().find(|r| r.relation == Relation::Order).unwrap();
    let stack = a.pairs.iter().find(|r| r.relation == Relation::Stack).unwrap();
    let (first, last) = (a.roads[0].id, a.roads[a.roads.len() - 1].id);
    let csv = format!("relation,a,b,a_end,b_end,enabled\norder,{},{},,,true\norder,{},{},,,true\norder,{first},{last},,,true\n",
                      order.a, order.b, stack.b, stack.a);
    let got: Vec<Value> = a.conflicts(&[], &read_pairs(&csv).unwrap()).unwrap().into_iter().map(|c| {
        json!([c.row, match c.why { Why::Duplicate => "duplicate", Why::NotKept => "not kept", Why::Loop => "loop" }, c.with.len()])
    }).collect();
    common::golden("level_area/rust_conflicts.json", &Value::Array(got));
}
