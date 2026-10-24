//! The drawing levels of Monaco must be the rows of duckosm-rust at commit 60dbede (its test `duckosm-build/tests/levels.rs`): the
//! sample file cut to its boundary, three modes. `data/monaco/level_edges.parquet` holds the edges and private edges of the three
//! modes with their rank; `levels_tags.parquet` and `levels_solve.parquet` are duckosm-rust's `edge_levels_visualization.parquet`.

use roadstyle_rs::levels::{levels, LevelEdge, LevelEdges, Method, Options, Row};
use roadstyle_rs::read::{read_roads, read_table};
use serde_json::{json, Map, Value};
use std::path::PathBuf;

fn data(name: &str) -> Vec<u8> {
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/monaco").join(name);
    std::fs::read(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

fn edges() -> LevelEdges {
    let mut out = LevelEdges::default();
    let t = read_roads(data("level_edges.parquet"), "geometry").unwrap();
    for i in 0..t.len() {
        let text = |k: &str| t.get(i, k).unwrap().as_str().map(String::from);
        out.add(t.get(i, "rank").unwrap().as_u64().unwrap() as u8, LevelEdge {
            edge_id: t.get(i, "edge_id").unwrap().as_i64().unwrap(),
            highway: text("highway").unwrap(),
            tunnel: text("tunnel"),
            bridge: text("bridge"),
            layer: text("layer"),
            junction: text("junction"),
            geometry: t.line(i).unwrap().iter().map(|&[x, y]| (x, y)).collect(),
            ..Default::default()
        });
    }
    out
}

fn as_map(r: &Row) -> Map<String, Value> {
    let Value::Object(m) = json!({"edge_id": r.edge_id, "casing_start": r.casing_start, "casing_level": r.casing_level,
        "casing_end": r.casing_end, "fill_level": r.fill_level, "head_start_m": r.head_start_m, "head_end_m": r.head_end_m,
        "cap_start": r.cap_start, "cap_end": r.cap_end}) else { unreachable!() };
    m
}

fn check(method: Method, golden: &str) -> roadstyle_rs::levels::Levels {
    let lv = levels(&edges(), &Options { method, ..Default::default() }).unwrap().unwrap();
    let want: Vec<Map<String, Value>> = read_table(data(golden), "").unwrap().into_iter().map(|r| r.cols).collect();
    let got: Vec<Map<String, Value>> = lv.rows.iter().map(as_map).collect();
    assert_eq!(got.len(), want.len(), "number of rows");
    let bad: Vec<_> = got.iter().zip(&want).filter(|(g, w)| g != w).collect();
    assert!(bad.is_empty(), "{} different rows, first: {:?}", bad.len(), &bad[..bad.len().min(3)]);
    assert_eq!(lv.edge_hash, "615c9155ab37a030dbfa80da2f7fcc09");
    assert_eq!(lv.roads, 6830);
    lv
}

#[test]
fn monaco_tags_equal_duckosm_rust() {
    check(Method::Tags, "levels_tags.parquet");
}

#[test]
fn monaco_solve_equals_duckosm_rust() {
    let lv = check(Method::Solve, "levels_solve.parquet");
    assert_eq!((lv.given_up, lv.orders_not_kept, lv.stages), (0, 16, [0, 37, 0, 6562870]));
}
