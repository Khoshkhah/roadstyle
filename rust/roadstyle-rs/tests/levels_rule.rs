//! Where the drawing positions come from (2026-10-25, lib.rs compute_levels): the named columns, else the input's contract columns
//! (casing_level, fill_level, ...: duckOSM's stored levels), else the solver. With levels "solve" or "tags" a user column of a contract
//! name is kept aside as __rs_kept_<name>, with a warning. Solved positions are not written into the table: the roads give them under the
//! contract names, after their columns.

use serde_json::{json, Value};
use std::path::PathBuf;

fn look(args: Value) -> roadstyle_rs::Look {
    let mut l: Value = serde_json::from_slice(&std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/look.json")).unwrap()).unwrap();
    for k in ["casing_start_col", "casing_level_col", "casing_end_col", "fill_level_col", "head_start_m_col", "head_end_m_col", "cap_start_col", "cap_end_col"] {
        l["args"].as_object_mut().unwrap().remove(k);
    }
    for (k, v) in args.as_object().unwrap() {
        l["args"][k] = v.clone();
    }
    roadstyle_rs::Look::from_value(l).unwrap()
}

/// Two crossing roads, a bridge over a street; with `stored`, each has the contract columns of a stored level (casing 7, fill 9).
fn roads(stored: bool) -> roadstyle_rs::RoadTable {
    let road = |id: i64, hw: &str, bridge: &str, c: [[f64; 2]; 2]| {
        let mut p = json!({"edge_id": id, "highway": hw, "bridge": bridge, "layer": if bridge == "yes" { "1" } else { "0" }});
        if stored {
            for (k, v) in [("casing_start", 7), ("casing_level", 7), ("casing_end", 7), ("fill_level", 9)] {
                p[k] = v.into();
            }
        }
        json!({"type": "Feature", "properties": p, "geometry": {"type": "LineString", "coordinates": c}})
    };
    let fc = json!({"type": "FeatureCollection", "features": [
        road(1, "primary", "yes", [[7.420, 43.730], [7.422, 43.732]]),
        road(2, "residential", "no", [[7.420, 43.732], [7.422, 43.730]]),
    ]});
    roadstyle_rs::geojson::read_roads(fc.to_string().as_bytes()).unwrap()
}

fn props(s: &roadstyle_rs::sources::Sources, i: usize) -> Vec<(String, Value)> {
    s.roads.roads.road(i).own().map(|(k, v)| (k.to_string(), v.to_value())).collect()
}

#[test]
fn the_contract_columns_are_the_level_input() {
    let s = roadstyle_rs::sources_of(roads(true), &look(json!({})), None, None, None).unwrap();
    assert_eq!(s.roads.roads.draw[0].levels, Some([7, 9, 7, 7]), "read, not solved");
    assert!(s.roads.roads.solved.is_none());
}

#[test]
fn solve_keeps_a_user_column_of_a_contract_name_aside() {
    let s = roadstyle_rs::sources_of(roads(true), &look(json!({"levels": "solve"})), None, None, None).unwrap();
    assert!(s.roads.roads.solved.is_some());
    let p = props(&s, 0);
    let names: Vec<&str> = p.iter().map(|(k, _)| k.as_str()).collect();
    let kept_name = format!("{}casing_level", roadstyle_rs::mark::KEPT);
    assert!(names.contains(&kept_name.as_str()) && names.contains(&"casing_level"), "{names:?}");
    let kept = p.iter().find(|(k, _)| *k == kept_name).unwrap();
    assert_eq!(kept.1, json!(7), "the user's value, kept");
    assert!(s.warnings.iter().any(|w| w.contains(&kept_name)), "{:?}", s.warnings);
}

#[test]
fn solved_positions_come_after_the_columns() {
    let s = roadstyle_rs::sources_of(roads(false), &look(json!({})), None, None, None).unwrap();
    let p = props(&s, 0);
    let names: Vec<&str> = p.iter().map(|(k, _)| k.as_str()).collect();
    let at = |n: &str| names.iter().position(|k| *k == n).unwrap_or_else(|| panic!("no {n}: {names:?}"));
    assert!(at("layer") < at("casing_start") && at("casing_start") < at("casing_level") && at("casing_end") < at("fill_level"), "{names:?}");
    assert!(at("fill_level") < at("__rs_cl"), "the solved columns before the marks: {names:?}");
    assert!(!s.roads.roads.table.names().iter().any(|n| n == "casing_level"), "not written into the table");
}
