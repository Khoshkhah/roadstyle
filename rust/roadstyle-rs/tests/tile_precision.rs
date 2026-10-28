//! The tiles' last zoom (config tiles.maxzoom, 18 since 2026-10-25): MapLibre scales the last zoom's tiles up for every zoom after it,
//! and the casing pieces' cut points round to that zoom's grid on their own. At zoom 15 a casing piece stood up to 4–5 px off its
//! fill's line at zoom 22 (Burnaby's casing seams); at 18 the rounding is about 1 px.

mod common;

use serde_json::Value;
use std::path::PathBuf;

fn data(p: &str) -> Vec<u8> {
    std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)).unwrap()
}

/// The distance of p from the polyline `l`, in tile units.
fn to_line(p: [i64; 2], l: &[[i64; 2]]) -> f64 {
    let p = [p[0] as f64, p[1] as f64];
    l.windows(2).map(|w| {
        let (a, b) = ([w[0][0] as f64, w[0][1] as f64], [w[1][0] as f64, w[1][1] as f64]);
        let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
        let t = if dx == 0.0 && dy == 0.0 { 0.0 } else { (((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)).clamp(0.0, 1.0) };
        (p[0] - a[0] - t * dx).hypot(p[1] - a[1] - t * dy)
    }).fold(f64::INFINITY, f64::min)
}

/// The 99th percentile and the largest distance, in px at zoom 22, of a vertex of a casing piece from its road's fill in the tiles of Monaco's center at the
/// tiles' last zoom `last`, with the levels solved (no level columns: every main road has heads, so its casing is cut into pieces).
fn casing_off_fill(last: u32) -> (f64, f64, usize) {
    let mut look: Value = serde_json::from_slice(&data("look.json")).unwrap();
    for k in ["casing_start_col", "casing_level_col", "casing_end_col", "fill_level_col", "head_start_m_col", "head_end_m_col", "cap_start_col", "cap_end_col"] {
        look["args"].as_object_mut().unwrap().remove(k);
    }
    look["config"]["tiles"]["maxzoom"] = last.into();
    let look = roadstyle_rs::Look::from_value(look).unwrap();
    let (_, tiles, _) = roadstyle_rs::tiled_from_parquet(data("monaco/roads.parquet"), &look, None, None, "rs://", &[]).unwrap();
    // 7.4235, 43.7387: Monaco's center; the tiles of a 600 m square around it
    let n = (1u64 << last) as f64;
    let tx = |lon: f64| ((lon + 180.0) / 360.0 * n) as u32;
    let ty = |lat: f64| ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n) as u32;
    let px = 512.0 / 4096.0 * 2f64.powi(22 - last as i32);       // one tile unit in px at zoom 22
    let (mut worst, mut pieces) = (0.0f64, 0);
    let mut all = Vec::new();
    for x in tx(7.420)..=tx(7.427) {
        for y in ty(43.741)..=ty(43.736) {
            let t = common::decode_tile(&tiles.tile(last, x, y));
            let Some(simple) = t.get("simple") else { continue };
            let k = |p: &serde_json::Map<String, Value>| p.get("__rs_k").and_then(Value::as_i64);
            let edge = |p: &serde_json::Map<String, Value>| p.get("__rs_edge").and_then(Value::as_i64);
            // a cut piece has a flat end (__rs_cap): the main piece between two cuts, a head drawn flat with a stub at its road end
            for (_, p, _, parts) in simple.iter().filter(|f| k(&f.1) == Some(0) && f.1.get("__rs_cap").is_some()) {
                let fills: Vec<&Vec<[i64; 2]>> = simple.iter().filter(|f| k(&f.1) == Some(1) && edge(&f.1) == edge(p)).flat_map(|f| &f.3).collect();
                if fills.is_empty() {
                    continue;
                }
                pieces += 1;
                for v in parts.iter().flatten() {
                    let d = fills.iter().map(|l| to_line(*v, l)).fold(f64::INFINITY, f64::min) * px;
                    all.push(d);
                    worst = worst.max(d);
                }
            }
        }
    }
    all.sort_by(f64::total_cmp);
    (all[all.len() * 99 / 100], worst, pieces)
}

#[test]
fn a_casing_piece_stays_on_its_fill_at_zoom_22() {
    // 2026-10-25 on Monaco: zoom 15, 99 % within 13.3 px; zoom 18, median 0.1 px, 99 % within 1.7 px, the largest 2.4 px (both lines
    // round to the grid, so up to about 1.4 tile units: 2.8 px at zoom 22)
    let (p15, _, n15) = casing_off_fill(15);
    let (p18, max18, n18) = casing_off_fill(18);
    assert!(n15 > 50 && n18 > 50, "cut casing pieces: {n15}, {n18}");
    assert!(p15 > 4.0, "zoom 15 tiles: 99 % within {p15:.1} px (the fault this test is for)");
    assert!(p18 <= 2.0 && max18 <= 2.8, "zoom 18 tiles: 99 % within {p18:.1} px, the largest {max18:.1} px");
}
