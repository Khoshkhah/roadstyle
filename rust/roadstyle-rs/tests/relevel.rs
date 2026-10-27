//! The level editor's redraw (roadstyle::relevel): Monaco's tiled map after a head change, a cap change and a level change of a relation
//! edit has the same features in the tiles around the edits as a new map of the new values (the features' ids can differ).

mod common;

use roadstyle_rs::relevel::{LevelRow, LiveTiles};
use roadstyle_rs::RoadTable;
use serde_json::{json, Value};

const COLS: [&str; 8] = ["casing_start", "casing_level", "casing_end", "fill_level", "head_start_m", "head_end_m", "cap_start", "cap_end"];

/// Monaco's roads with the levels of a solve, 5 m heads and no caps of their own, in the columns that the look names.
fn roads() -> RoadTable {
    let p = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data/monaco/roads.parquet");
    let mut t = roadstyle_rs::read::read_roads(std::fs::read(p).unwrap(), "geometry").unwrap();
    let mut edges = roadstyle_rs::levels::LevelEdges::default();
    for i in 0..t.len() {
        let text = |k: &str| t.get(i, k).and_then(roadstyle_rs::Cell::as_str).map(String::from);
        edges.add(0, roadstyle_rs::levels::LevelEdge { edge_id: i as i64, highway: text("highway").unwrap_or_default(), tunnel: text("tunnel"),
            bridge: text("bridge"), layer: text("layer"), junction: text("junction"), band: None, order: None,
            geometry: t.line(i).unwrap().iter().map(|&[x, y]| (x, y)).collect() });
    }
    let lv = roadstyle_rs::levels::levels(&edges, &Default::default()).unwrap().unwrap();
    let col = |f: fn(&roadstyle_rs::levels::Row) -> i64| lv.rows.iter().map(|r| json!(f(r))).collect();
    for (name, v) in [("casing_start", col(|r| r.casing_start)), ("casing_level", col(|r| r.casing_level)), ("casing_end", col(|r| r.casing_end)),
                      ("fill_level", col(|r| r.fill_level))] {
        t.set_values(name, v).unwrap();
    }
    for name in ["head_start_m", "head_end_m"] {
        t.set_values(name, vec![json!(5.0); t.len()]).unwrap();
    }
    for name in ["cap_start", "cap_end"] {
        t.set_values(name, vec![Value::Null; t.len()]).unwrap();
    }
    t
}

fn look() -> roadstyle_rs::Look {
    let mut o = json!({"args": {"state": "live"}});
    for c in COLS {
        o["args"][format!("{c}_col")] = json!(c);
    }
    roadstyle_rs::Look::from_value(roadstyle_rs::Look::resolution_value(&roadstyle_rs::look::Options::from_value(&o).unwrap()).unwrap()).unwrap()
}

fn live(t: RoadTable) -> LiveTiles {
    let look = look();
    LiveTiles::new(roadstyle_rs::sources_of(t, &look, None, None, None).unwrap(), look, "x://", &[]).unwrap()
}

/// A row of the table as a LevelRow.
fn row(t: &RoadTable, i: usize) -> LevelRow {
    let n = |c: &str| t.get(i, c).unwrap();
    let id = t.get(i, "edge_id").unwrap().to_value();
    LevelRow { edge_id: id.as_i64().or_else(|| id.as_str()?.parse().ok()).unwrap(),
               levels: [0, 1, 2, 3].map(|k| n(COLS[k]).as_i64().unwrap()), heads: [n("head_start_m").as_f64(), n("head_end_m").as_f64()],
               caps: [n("cap_start").as_str().map(String::from), n("cap_end").as_str().map(String::from)] }
}

/// The tile's features of each layer, without their ids, in one order.
fn features(b: &[u8]) -> Vec<(String, Vec<String>)> {
    common::decode_tile(b).into_iter().map(|(k, fs)| {
        let mut v: Vec<String> = fs.into_iter().map(|(_, p, t, g)| serde_json::to_string(&(p, t, g)).unwrap()).collect();
        v.sort();
        (k, v)
    }).collect()
}

#[test]
fn a_redraw_has_the_features_of_a_new_map() {
    let before = roads();
    let pick = |h: &str, not: usize| (0..before.len()).find(|&i| i != not && before.get(i, "highway").and_then(roadstyle_rs::Cell::as_str) == Some(h)).unwrap();
    // a head length shows only on a road whose start casing has another number than its main casing
    let n = |i: usize, c: &str| before.get(i, c).unwrap().as_i64().unwrap();
    let head = (0..before.len()).find(|&i| n(i, "casing_start") != n(i, "casing_level")).unwrap();
    let (cap, edit) = (pick("residential", head), pick("secondary", head));
    let mut after = before.clone();
    let cells = |c: &str, i: usize, v: Value| (after.col(c).unwrap(), vec![(i, v)]);
    let lv = |c: &str| before.get(edit, c).unwrap().as_i64().unwrap() + 1;
    for (c, cs) in [cells("head_start_m", head, json!(2.0)), cells("cap_end", cap, json!("flat")), cells("casing_start", edit, json!(lv("casing_start"))),
                    cells("casing_level", edit, json!(lv("casing_level"))), cells("casing_end", edit, json!(lv("casing_end"))),
                    cells("fill_level", edit, json!(lv("fill_level")))] {
        after.set_cells(c, &cs).unwrap();
    }
    let mut m = live(before);
    // a head and a cap (no fill level changes: the slots stay), then the levels of a relation edit
    for (rows, what) in [(vec![head, cap], "head and cap"), (vec![edit], "level change")] {
        let t = std::time::Instant::now();
        let done = m.relevel(&rows.iter().map(|&i| row(&after, i)).collect::<Vec<_>>()).unwrap();
        eprintln!("Monaco redraw, {what}: {:.0} ms, {done:?}", t.elapsed().as_secs_f64() * 1e3);
        assert!(done.edges >= rows.len() && !done.style_changed, "{done:?}");
    }
    let mut new = live(after.clone());
    for i in [head, cap, edit] {
        let [lon, lat] = after.line(i).unwrap()[0];
        for z in 14..=18u32 {
            let n = (1u64 << z) as f64;
            let x = ((lon + 180.0) / 360.0 * n) as u32;
            let y = ((1.0 - (lat.to_radians().tan() + 1.0 / lat.to_radians().cos()).ln() / std::f64::consts::PI) / 2.0 * n) as u32;
            assert_eq!(features(&m.tile(z, x, y)), features(&new.tile(z, x, y)), "row {i}, tile {z}/{x}/{y}");
        }
    }
}

/// The map whose pieces wait for their properties (LiveTiles) has the bytes of tile_made's tiles, at every tile of Monaco, the high
/// zooms asked first.
#[test]
fn the_waiting_pieces_give_the_tiles_of_tile_made() {
    let look = look();
    let s = roadstyle_rs::sources_of(roads(), &look, None, None, None).unwrap();
    let (_, made) = roadstyle_rs::tile_made(&s, "x://", &[]).unwrap();
    let mut m = LiveTiles::new(s, look, "x://", &[]).unwrap();
    let [w, so, e, no] = made.bounds().unwrap();
    let (z0, z1) = made.zooms();
    let mut tiles = 0;
    for z in (z0..=z1).rev() {
        let n = (1u64 << z) as f64;
        let x = |lon: f64| ((lon + 180.0) / 360.0 * n) as u32;
        let y = |lat: f64| ((1.0 - (lat.to_radians().tan() + 1.0 / lat.to_radians().cos()).ln() / std::f64::consts::PI) / 2.0 * n) as u32;
        for tx in x(w)..=x(e) {
            for ty in y(no)..=y(so) {
                let b = made.tile(z, tx, ty);
                assert_eq!(m.tile(z, tx, ty), b, "tile {z}/{tx}/{ty}");
                tiles += usize::from(!b.is_empty());
            }
        }
    }
    assert!(tiles > 50, "{tiles} tiles");
}
