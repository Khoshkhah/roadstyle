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

/// The editor's answers for some roads (what the page asks when the panel needs it) are those of its answers for all roads: facts_of is
/// facts with each road's ends, levels_of reads levels_csv back, road_of and find name the roads of their ids and edge_refs.
#[test]
fn the_answers_for_some_roads_are_those_for_all() {
    let (roads, pairs) = made();
    let ed = roadstyle_rs::level_editor::Editor::new(roads.clone(), pairs).unwrap();
    let all: Vec<Value> = serde_json::from_str(&ed.facts()).unwrap();
    let ids = ed.road_ids();
    let (heads, caps) = (format!("road,start_m,end_m\n{},2.5,\n", ids[1]), format!("road,start,end\n{},,flat\n", ids[2]));
    let ends = ed.ends(&heads, &caps).unwrap();
    let auto = ed.ends("", "").unwrap();
    // a road by an edge id, an unknown id (left out) and a road twice (once)
    let edge = all[3]["directions"][0]["edge"].as_str().unwrap().to_string();
    let asked = vec![ids[1].clone(), ids[2].clone(), "1".into(), edge, ids[1].clone()];
    let some: Vec<Value> = serde_json::from_str(&ed.facts_of(&asked, &heads, &caps).unwrap()).unwrap();
    assert_eq!(some.len(), 3);
    for f in &some {
        let i = f["i"].as_u64().unwrap() as usize;
        let mut want = all[i].clone();
        for (k, v) in [("i", json!(i)), ("heads", json!(ends[i].0)), ("heads_own", json!(ends[i].2.clone().map(|x| !x.is_empty()))),
                       ("caps", json!(ends[i].3)), ("heads_auto", json!(auto[i].0)), ("caps_auto", json!(auto[i].1))] {
            want[k] = v;
        }
        assert_eq!(f, &want);
    }
    assert_eq!(some[0]["heads_own"], json!([true, false]));
    assert_eq!(some[1]["caps"], json!(["", "flat"]));
    assert_eq!(ed.road_of(&asked), vec![ids[1].clone(), ids[2].clone(), String::new(), ids[3].clone(), ids[1].clone()]);
    let own: Value = serde_json::from_str(&ed.own_ends_json(&heads, &caps).unwrap()).unwrap();
    assert_eq!(own, json!({ids[1].clone(): [["2.5", ""], ["", ""]], ids[2].clone(): [["", ""], ["", "flat"]]}));
    // levels_csv read back, each road's own numbers; a levels.csv without a road's edges gives none
    let levels: Vec<i64> = (0..4 * ids.len() as i64).map(|k| k % 7 - 3).collect();
    let csv = ed.levels_csv(&levels, "", "").unwrap();
    assert_eq!(ed.levels_of(&csv).unwrap().into_iter().map(i64::from).collect::<Vec<_>>(), levels);
    assert!(ed.levels_of(&csv.lines().take(2).collect::<Vec<_>>().join("\n")).is_none());
    // find: every road with an edge_ref that has the text in it (case not counted)
    let r = all.iter().find_map(|f| f["edge_ref"].as_str()).expect("a road with an edge_ref").to_string();
    let hits: Vec<Value> = serde_json::from_str(&ed.find(&r.to_uppercase())).unwrap();
    assert!(hits.iter().any(|h| h[1] == json!(r) && h[2] == json!(true)), "{hits:?}");
    assert_eq!(ed.edge_hash().len(), 32);
}
