//! The levels with compute_levels' keywords not at their defaults, and with solve_levels' edits and fixed numbers, against roadstyle's
//! own rows (Python, tests/make_goldens.py level_options_<area>). The edges are the roads in their order, as compute_levels reads them.

mod common;

use roadstyle_rs::levels::{levels, Edit, LevelEdge, LevelEdges, Method, Options, Order};
use serde_json::Value;

/// The roads of an area; `rank_col` (the row number modulo 5) as the order value and `layer` as the band.
fn edges(area: &str) -> LevelEdges {
    let p = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(format!("tests/data/{area}/roads.parquet"));
    let t = roadstyle_rs::read::read_roads(std::fs::read(p).unwrap(), "geometry").unwrap();
    let mut out = LevelEdges::default();
    for i in 0..t.len() {
        let text = |k: &str| t.get(i, k).and_then(roadstyle_rs::Cell::as_str).map(String::from);
        out.add(0, LevelEdge { edge_id: i as i64, highway: text("highway").unwrap_or_default(), tunnel: text("tunnel"), bridge: text("bridge"),
                               layer: text("layer"), junction: text("junction"), band: text("layer"), order: Some((i % 5) as f64),
                               geometry: t.line(i).unwrap().iter().map(|&[x, y]| (x, y)).collect() });
    }
    out
}

/// The options of a case of the golden (compute_levels' keywords, the edits, the fixed numbers).
fn options(case: &Value) -> Options {
    let mut o = Options { method: Method::Solve, ..Default::default() };
    for (k, v) in case["options"].as_object().into_iter().flatten() {
        match k.as_str() {
            "order" => o.order = match v.as_str() { None => Order::None, Some("class") => Order::Class, Some(_) => Order::Column },
            "band_col" => o.band_col = true,
            "band_dist" => o.band_dist = v.as_f64().unwrap(),
            "head_m" => o.head_m = v.as_f64().unwrap(),
            "max_level" => o.max_level = v.as_i64().unwrap(),
            "margin" => o.margin = v.as_f64().unwrap(),
            "min_positions" => o.min_positions = v.as_bool().unwrap(),
            "near_rules" => o.near_rules = v.as_bool().unwrap(),
            "time_limit" => {} // the Rust solver has no time limit
            _ => panic!("keyword {k}"),
        }
    }
    let text = |v: &Value| v.as_str().map(String::from);
    o.edits = case["edits"].as_array().into_iter().flatten().map(|e| Edit {
        relation: e["relation"].as_str().unwrap().into(), a: e["a"].as_str().unwrap().parse().unwrap(), b: e["b"].as_str().unwrap().parse().unwrap(),
        a_end: text(&e["a_end"]), b_end: text(&e["b_end"]), enabled: e["enabled"] != "false",
    }).collect();
    o.fixed = case["fixed"].as_array().into_iter().flatten().map(|f| {
        let v: Vec<i64> = f[1].as_array().unwrap().iter().map(|x| x.as_i64().unwrap()).collect();
        (f[0].as_i64().unwrap(), [v[0], v[1], v[2], v[3]])
    }).collect();
    o
}

/// For each case: the number of rows that are not Python's.
fn other_rows(area: &str) -> Vec<(String, usize)> {
    let golden = common::gz_json(&format!("{area}/golden_level_options.json.gz"));
    let edges = edges(area);
    let mut out = Vec::new();
    for (name, case) in golden.as_object().unwrap() {
        let lv = levels(&edges, &options(case)).unwrap().unwrap();
        let want = case["rows"].as_array().unwrap();
        assert_eq!(lv.rows.len(), want.len(), "{area} {name}: rows");
        let other = lv.rows.iter().zip(want).filter(|(r, w)| [r.casing_start, r.casing_level, r.casing_end, r.fill_level].iter()
            .zip(w.as_array().unwrap()).any(|(a, b)| Some(*a) != b.as_i64())).count();
        out.push((name.clone(), other));
    }
    out
}

/// Known differences on Monaco, as tests/areas.rs MONACO_SOLVE_OTHER_ROWS: the rows of a few roads. Both answers are equally good under
/// roadstyle's rules: the same steps of broken stack rules, order wishes and near rules, the same span and the same casing cost (checked
/// for each case on 2026-10-23). Python's solver (OR-tools, HiGHS) and the engine's min-cost flow take different answers among the best.
const MONACO_TIES: [(&str, usize); 12] = [("class", 2), ("no_order", 0), ("order_col", 10), ("band_col", 14), ("band_dist", 8), ("head_m", 14),
    ("max_level", 8), ("no_min_positions", 79), ("near_rules", 4), ("margin", 8), ("edits", 8), ("fixed", 8)];

#[test]
fn monaco_level_options_against_python() {
    let want: Vec<(String, usize)> = MONACO_TIES.iter().map(|(k, n)| (k.to_string(), *n)).collect();
    assert_eq!(other_rows("monaco"), want);
}

#[test]
fn sodermalm_level_options_against_python() {
    assert!(other_rows("sodermalm").iter().all(|(_, n)| *n == 0), "{:?}", other_rows("sodermalm"));
}

/// The browser's keyword `levels` (roads_sql.js makeRoads): the engine checks the stored levels' edge hash, or computes the tags rule.
#[test]
fn the_look_keyword_levels() {
    let o = common::gz_json("monaco/golden_options.json.gz");
    let roads = std::fs::read(std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/monaco/roads.parquet")).unwrap();
    let t = roadstyle_rs::read::read_roads(roads.clone(), "geometry").unwrap();
    let ids: Vec<i64> = (0..t.len()).map(|i| t.get(i, "edge_id").unwrap().to_value().as_str().unwrap().parse().unwrap()).collect();
    let style = |levels: Value| {
        let mut look = roadstyle_rs::look::make_look(&o).unwrap();
        look["args"]["levels"] = levels;
        roadstyle_rs::make_style(roads.clone(), &look.to_string(), None, None, None)
    };
    let meta = |hash: &str| serde_json::json!({"edge_hash": hash, "n_edges": ids.len()});
    assert!(style(meta(&roadstyle_rs::levels::edge_hash(&ids))).is_ok());
    assert!(style(meta("0123")).unwrap_err().contains("not the edges the stored levels were solved for"));
    assert!(style(Value::from("tags")).is_ok());
}
