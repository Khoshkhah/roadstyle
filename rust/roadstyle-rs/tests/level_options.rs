//! The levels with compute_levels' keywords not at their defaults, and with solve_levels' edits and fixed numbers: each answer is feasible
//! (the solver checks every hard rule of its answer). The edges are the roads in their order, as compute_levels reads them.

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

/// The cases: each keyword of compute_levels not at its default, solve_levels' edits (a stack rule off, an order wish off and the other
/// way; rules of the area's roads, by the row of a road's first edge) and fixed numbers (every 50th road at the numbers of the solve
/// without them).
fn cases(edges: &LevelEdges, edits: [(i64, i64, &str); 2]) -> Vec<(&'static str, Options)> {
    let o = |f: fn(&mut Options)| {
        let mut o = Options::default();
        f(&mut o);
        o
    };
    let mut out = vec![
        ("class", o(|o| o.order = Order::Class)), ("no_order", o(|o| o.order = Order::None)), ("order_col", o(|o| o.order = Order::Column)),
        ("band_col", o(|o| o.band_col = true)), ("band_dist", o(|o| o.band_dist = 20.0)), ("head_m", o(|o| o.head_m = 10.0)),
        ("max_level", o(|o| o.max_level = 2)), ("no_min_positions", o(|o| o.min_positions = false)), ("near_rules", o(|o| o.near_rules = true)),
        ("margin", o(|o| o.margin = 2.0)), ("tags", o(|o| o.method = Method::Tags)),
    ];
    let [(su, sl, part), (ox, oy, _)] = edits;
    let edit = |relation: &str, a, b, a_end: Option<&str>, enabled| Edit { relation: relation.into(), a, b, a_end: a_end.map(String::from), b_end: None, enabled };
    out.push(("edits", Options { edits: vec![edit("stack", su, sl, Some(part), false), edit("order", ox, oy, None, false), edit("order", oy, ox, None, true)],
                                 ..Default::default() }));
    let base = levels(edges, &Options::default()).unwrap().unwrap();
    let fixed = base.rows.iter().step_by(50).map(|r| (r.edge_id, [r.casing_start, r.casing_level, r.casing_end, r.fill_level])).collect();
    out.push(("fixed", Options { fixed, ..Default::default() }));
    out
}

/// Each case gives an answer (the solver checks its hard rules), and no edge's casing is over its fill.
fn feasible(area: &str, edits: [(i64, i64, &str); 2]) {
    let edges = edges(area);
    for (name, o) in cases(&edges, edits) {
        let lv = levels(&edges, &o).unwrap_or_else(|e| panic!("{area} {name}: {e}")).unwrap();
        let over = lv.rows.iter().filter(|r| r.casing_start.max(r.casing_level).max(r.casing_end) > r.fill_level).count();
        assert_eq!(over, 0, "{area} {name}: edges with a casing over the fill");
        if name == "max_level" {
            assert!(lv.rows.iter().all(|r| r.fill_level.abs() <= 2 && r.casing_start.abs() <= 2), "{area} {name}: a number out of the box");
        }
    }
}

#[test]
fn monaco_level_options_are_feasible() {
    feasible("monaco", [(7, 4743, "end"), (0, 756, "")]);
}

#[test]
fn sodermalm_level_options_are_feasible() {
    feasible("sodermalm", [(1089, 13, "main"), (1, 243, "")]);
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
        roadstyle_rs::make_style(roads.clone(), &roadstyle_rs::Look::from_value(look.clone()).unwrap(), None, None, None)
    };
    let meta = |hash: &str| serde_json::json!({"edge_hash": hash, "n_edges": ids.len()});
    assert!(style(meta(&roadstyle_rs::levels::edge_hash(&ids))).is_ok());
    assert!(style(meta("0123")).unwrap_err().contains("not the edges the stored levels were solved for"));
    assert!(style(Value::from("tags")).is_ok());
}
