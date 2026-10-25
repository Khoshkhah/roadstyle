//! The drawing levels of Monaco in duckosm-rust's form (its test `duckosm-build/tests/levels.rs`): the sample file cut to its boundary,
//! three modes. `data/monaco/level_edges.parquet` holds the edges and private edges of the three modes with their rank. The goldens are
//! the engine's (common::levels_summary, `ROADSTYLE_BLESS=1` writes them): the counts, the rows' hash of the tags rule, and a solve's
//! stages; every solve is feasible (the solver checks each hard rule of its answer).

mod common;

use roadstyle_rs::levels::{levels, LevelEdge, LevelEdges, Method, Options};
use roadstyle_rs::read::read_roads;
use std::path::PathBuf;

fn edges() -> LevelEdges {
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/monaco/level_edges.parquet");
    let t = read_roads(std::fs::read(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display())), "geometry").unwrap();
    let mut out = LevelEdges::default();
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

#[test]
fn monaco_of_three_modes_is_its_goldens() {
    for (method, name) in [(Method::Tags, "tags"), (Method::Solve, "solve")] {
        let lv = levels(&edges(), &Options { method, ..Default::default() }).unwrap().unwrap();
        common::golden(&format!("monaco/rust_levels_modes_{name}.json"), &common::levels_summary(&lv));
    }
}
