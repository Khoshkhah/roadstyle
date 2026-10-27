//! The tile size standard (docs/design/tile_contract.md, "The tile size standard"): the tiles of fixed views of Monaco and Tartu at
//! zoom 12 to 15, and the tiled style, must stay within the limits of tests/data/tile_budget.json. A number that is larger fails.
//! The limits only go down (scripts/tile_budget.py); a raise needs `--raise --why "..."` and the PR text must say why.
//!
//! For each view, for each tile layer, the largest tile: its features, its bytes (the layer's share of the tile), its keys and its
//! values (the value table: the distinct values). For the view: the bytes of all its tiles and of its largest tile. For the style: the
//! size of each filter, paint and layout (JSON characters) that is over `SMALL`, and the total.
//!
//! The view of an area is the 3 x 3 tiles around a fixed centre (the budget file keeps it, `center`). The keep list of the tiles is
//! empty: the numbers are the engine's own tiles, without a page's popup fields. Each area has two looks: `monaco` is the page's
//! (the lean look: the `simple` pieces and the slots) and `monaco-full` is `export_style`'s (it has the whole-road layer `roads` too).
//!
//! The hard limits (`HARD_*`) are absolute, as the ratchet is not: a tile, a feature count or an expression over one is a violation.
//! Today's violations are listed in the budget (`known_over`). A new one fails; so does one that is gone but still listed.
//!
//!     cargo test --release -p roadstyle-rs --test tile_budget -- --nocapture       (the table)
//!     ROADSTYLE_BURNABY_ROADS=<roads.parquet> cargo test --release -p roadstyle-rs --test tile_budget burnaby -- --ignored --nocapture

mod common;

use serde_json::{json, Map, Value};
use std::collections::BTreeMap;
use std::path::PathBuf;

/// A view: its name and its tiles (zoom, x, y).
type View = (String, Vec<(u32, u32, u32)>);

/// The first and the last zoom of the fixed views.
const ZOOMS: std::ops::RangeInclusive<u32> = 12..=15;
/// A filter, paint or layout of a style layer over this many JSON characters has its own limit; a smaller one has none.
const SMALL: usize = 256;
/// The hard limits (docs/design/tile_contract.md, "The tile size standard"): the bytes and the features of one tile (all its layers),
/// and the characters of one filter, paint or layout.
const HARD_TILE_BYTES: usize = 500_000;
const HARD_TILE_FEATURES: usize = 10_000;
const HARD_EXPRESSION: usize = 4096;

/// The areas of the budget: its name, the inputs' folder in tests/data, and whether it is the full look (`export_style`'s: the
/// whole-road layer `roads` too) or the lean look of the page.
const AREAS: [(&str, &str, bool); 4] = [("monaco", "monaco", false), ("monaco-full", "monaco", true), ("tartu", "tartu", false), ("tartu-full", "tartu", true)];

fn data(p: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)
}

/// An area's look: its options (golden_options.json.gz); `full`: as an export (areas.rs), with the whole-road layer `roads`.
fn look(area: &str, full: bool) -> roadstyle_rs::Look {
    let o = common::gz_json(&format!("{area}/golden_options.json.gz"));
    let mut look = roadstyle_rs::Look::resolution_value(&roadstyle_rs::look::Options::from_value(&o).unwrap()).unwrap();
    look["args"]["export"] = full.into();
    roadstyle_rs::Look::from_value(look).unwrap()
}

fn budget() -> Value {
    serde_json::from_str(&std::fs::read_to_string(data("tile_budget.json")).expect("tests/data/tile_budget.json")).unwrap()
}

/// The fields of a protobuf message: (field number, wire type, varint value, bytes).
fn fields(b: &[u8]) -> Vec<(u64, u64, u64, &[u8])> {
    let varint = |i: &mut usize| {
        let (mut v, mut s) = (0u64, 0);
        loop {
            let x = b[*i];
            *i += 1;
            v |= ((x & 0x7f) as u64) << s;
            s += 7;
            if x < 0x80 {
                return v;
            }
        }
    };
    let (mut i, mut out) = (0, Vec::new());
    while i < b.len() {
        let k = varint(&mut i);
        match k & 7 {
            0 => out.push((k >> 3, 0, varint(&mut i), &b[0..0])),
            1 | 5 => {
                let n = if k & 7 == 1 { 8 } else { 4 };
                out.push((k >> 3, k & 7, 0, &b[i..i + n]));
                i += n;
            }
            2 => {
                let l = varint(&mut i) as usize;
                out.push((k >> 3, 2, 0, &b[i..i + l]));
                i += l;
            }
            w => panic!("wire type {w}"),
        }
    }
    out
}

/// The layers of a vector tile: (name, features, bytes, keys, values). The bytes are the layer's share of the tile (tag, length, message).
fn layers_of(tile: &[u8]) -> Vec<(String, usize, usize, usize, usize)> {
    fields(tile).into_iter().filter(|f| f.0 == 3).map(|(_, _, _, layer)| {
        let (mut name, mut n) = (String::new(), [0usize; 3]);
        for (f, _, _, d) in fields(layer) {
            match f {
                1 => name = String::from_utf8(d.to_vec()).unwrap(),
                2 => n[0] += 1,
                3 => n[1] += 1,
                4 => n[2] += 1,
                _ => {}
            }
        }
        let head = 1 + (64 - (layer.len() as u64 | 1).leading_zeros() as usize).div_ceil(7);
        (name, n[0], head + layer.len(), n[1], n[2])
    }).collect()
}

/// The size of each filter, paint and layout of the style's layers (JSON characters): those over `SMALL`, and the total.
fn style_sizes(style: &Value) -> Value {
    let (mut total, mut big) = (0usize, Map::new());
    let layers = style["layers"].as_array().cloned().unwrap_or_default();
    for l in &layers {
        let mut props: Vec<(String, &Value)> = Vec::new();
        if let Some(f) = l.get("filter") {
            props.push(("filter".into(), f));
        }
        for part in ["paint", "layout"] {
            props.extend(l[part].as_object().into_iter().flatten().map(|(k, v)| (format!("{part}.{k}"), v)));
        }
        for (k, v) in props {
            let n = serde_json::to_string(v).unwrap().len();
            total += n;
            if n > SMALL {
                big.entry(l["id"].as_str().unwrap_or("?").to_string()).or_insert_with(|| json!({}))[k] = n.into();
            }
        }
    }
    json!({"layers": layers.len(), "expressions_total": total, "expressions": big})
}

/// The 3 x 3 tiles around (lon, lat) at zoom z.
fn square(z: u32, lon: f64, lat: f64) -> Vec<(u32, u32, u32)> {
    let n = (1u64 << z) as f64;
    let x = ((lon + 180.0) / 360.0 * n) as i64;
    let y = ((1.0 - lat.to_radians().tan().asinh() / std::f64::consts::PI) / 2.0 * n) as i64;
    (-1..=1).flat_map(|dx| (-1..=1).map(move |dy| (z, (x + dx) as u32, (y + dy) as u32))).collect()
}

/// The middle of the roads' box, rounded to 5 decimals (about 1 m).
fn center_of(roads: &[u8]) -> [f64; 2] {
    let t = roadstyle_rs::read::read_roads(roads.to_vec(), "geometry").unwrap();
    let (mut lo, mut hi) = ([f64::INFINITY; 2], [f64::NEG_INFINITY; 2]);
    for p in (0..t.len()).filter_map(|r| t.line(r)).flatten() {
        (lo, hi) = ([lo[0].min(p[0]), lo[1].min(p[1])], [hi[0].max(p[0]), hi[1].max(p[1])]);
    }
    let r = |x: f64| (x * 1e5).round() / 1e5;
    [r((lo[0] + hi[0]) / 2.0), r((lo[1] + hi[1]) / 2.0)]
}

/// The numbers of an area: for each view, its tiles' sizes; and the style's. `views`: the name and the tiles of each.
fn measure(roads: Vec<u8>, features: Option<Vec<u8>>, look: &roadstyle_rs::Look, center: [f64; 2], views: Vec<View>) -> Value {
    let (style, tiles, _) = roadstyle_rs::make_tiled(roads, look, features, None, "rs://", &[]).unwrap();
    let mut out = Map::new();
    out.insert("center".into(), json!(center));
    for (name, view) in views {
        let (mut bytes, mut features, mut biggest, mut most) = (0usize, 0usize, 0usize, 0usize);
        let mut layers: BTreeMap<String, [usize; 4]> = BTreeMap::new();
        for (z, x, y) in view {
            let t = tiles.tile(z, x, y);
            bytes += t.len();
            biggest = biggest.max(t.len());
            most = most.max(layers_of(&t).iter().map(|l| l.1).sum());
            for (l, f, b, k, v) in layers_of(&t) {
                features += f;
                let e = layers.entry(l).or_default();
                *e = [e[0].max(f), e[1].max(b), e[2].max(v), e[3].max(k)];
            }
        }
        let layers: Map<String, Value> = layers.into_iter().map(|(k, [f, b, v, n])| (k, json!({"features": f, "bytes": b, "values": v, "keys": n}))).collect();
        out.insert(name, json!({"view_bytes": bytes, "view_features": features, "max_tile_bytes": biggest, "max_tile_features": most, "layers": layers}));
    }
    out.insert("style".into(), style_sizes(&serde_json::from_str(&style).unwrap()));
    Value::Object(out)
}

/// The areas of the budget: the fixed views of the area's roads (the budget's centre, else the roads' middle).
fn measure_area(dir: &str, full: bool, saved: &Value) -> Value {
    let roads = std::fs::read(data(&format!("{dir}/roads.parquet"))).unwrap();
    let center = saved["center"].as_array().map(|c| [c[0].as_f64().unwrap(), c[1].as_f64().unwrap()]).unwrap_or_else(|| center_of(&roads));
    let views = ZOOMS.map(|z| (format!("z{z}"), square(z, center[0], center[1]))).collect();
    // no base-map features: the areas' golden looks have no layers_yaml (the overlays are measured by the local Burnaby gate)
    measure(roads, None, &look(dir, full), center, views)
}

/// The hard limits that an area's numbers break, as names: `<area>.<view>.max_tile_bytes`, `<area>.<view>.max_tile_features` and
/// `<area>.style.<layer>.<property>`.
fn hard_violations(area: &str, got: &Value) -> Vec<String> {
    let mut out = Vec::new();
    for (view, v) in got.as_object().into_iter().flatten().filter(|(k, _)| *k != "center" && *k != "style") {
        for (key, max) in [("max_tile_bytes", HARD_TILE_BYTES), ("max_tile_features", HARD_TILE_FEATURES)] {
            if v[key].as_u64() > Some(max as u64) {
                out.push(format!("{area}.{view}.{key}"));
            }
        }
    }
    for (id, props) in got["style"]["expressions"].as_object().into_iter().flatten() {
        out.extend(props.as_object().into_iter().flatten().filter(|(_, n)| n.as_u64() > Some(HARD_EXPRESSION as u64)).map(|(p, _)| format!("{area}.style.{id}.{p}")));
    }
    out
}

/// Every number of `got` that is larger than its limit in `limit`, or has none: as lines.
fn over(got: &Value, limit: &Value, path: &str, out: &mut Vec<String>) {
    for (k, v) in got.as_object().into_iter().flatten().filter(|(k, _)| *k != "center") {
        let at = format!("{path}.{k}");
        match (v, &limit[k]) {
            (Value::Number(n), Value::Number(l)) if n.as_u64() > l.as_u64() => out.push(format!("{at}: {n} is over the limit {l}")),
            (Value::Number(_), Value::Number(_)) => {}
            (Value::Number(n), _) => out.push(format!("{at}: {n}, and the budget has no limit for it")),
            (Value::Object(_), Value::Object(_)) => over(v, &limit[k], &at, out),
            (Value::Object(_), _) => out.push(format!("{at}: the budget has no limits for it")),
            _ => {}
        }
    }
}

/// The table of an area: for each view and tile layer, the largest tile's numbers against their limits.
fn table(area: &str, got: &Value, limit: &Value) -> String {
    let cell = |g: &Value, l: &Value| match l.as_u64() {
        Some(l) => format!("{}/{}", g, l),
        None => g.to_string(),
    };
    let mut s = format!("{area}: the largest tile of each layer (measured/limit)\n{:<12}{:<16}{:>16}{:>16}{:>16}{:>12}\n",
                        "view", "layer", "features", "bytes", "values", "keys");
    for (view, v) in got.as_object().into_iter().flatten().filter(|(k, _)| *k != "center" && *k != "style") {
        for (layer, m) in v["layers"].as_object().into_iter().flatten() {
            let l = &limit[view]["layers"][layer];
            s += &format!("{view:<12}{layer:<16}{:>16}{:>16}{:>16}{:>12}\n", cell(&m["features"], &l["features"]), cell(&m["bytes"], &l["bytes"]),
                          cell(&m["values"], &l["values"]), cell(&m["keys"], &l["keys"]));
        }
        let l = &limit[view];
        s += &format!("{view:<12}{:<16}{:>16}{:>16}   largest tile {} bytes, {} features\n", "(all tiles)", cell(&v["view_features"], &l["view_features"]),
                      cell(&v["view_bytes"], &l["view_bytes"]), cell(&v["max_tile_bytes"], &l["max_tile_bytes"]),
                      cell(&v["max_tile_features"], &l["max_tile_features"]));
    }
    let st = &got["style"];
    s += &format!("style: {} layers, expressions {} characters ({} over {SMALL})\n", cell(&st["layers"], &limit["style"]["layers"]),
                  cell(&st["expressions_total"], &limit["style"]["expressions_total"]), st["expressions"].as_object().map_or(0, Map::len));
    for (id, props) in st["expressions"].as_object().into_iter().flatten() {
        for (p, n) in props.as_object().into_iter().flatten() {
            s += &format!("    {id} {p}: {}\n", cell(n, &limit["style"]["expressions"][id][p]));
        }
    }
    s
}

/// An area's inputs are in tests/data (Monaco: git; Tartu: tests/get_goldens.sh). CI always has them; elsewhere a missing area is skipped.
fn has(area: &str) -> bool {
    let there = data(&format!("{area}/roads.parquet")).exists() && data(&format!("{area}/golden_options.json.gz")).exists();
    assert!(there || std::env::var_os("CI").is_none(), "no {area} inputs in CI: run tests/get_goldens.sh");
    if !there {
        eprintln!("{area}: no inputs (tests/get_goldens.sh), skipped");
    }
    there
}

/// The tiles and the style of Monaco and Tartu (the page's look and the full look) are within the budget, and break no hard limit
/// that the budget's `known_over` does not list. `ROADSTYLE_TILE_BUDGET_OUT=<file>` writes the numbers there first
/// (scripts/tile_budget.py reads them; `hard_violations` is the list of the hard limits that they break).
#[test]
fn the_tiles_stay_within_their_budget() {
    let budget = budget();
    let (mut got, mut errors, mut broken) = (Map::new(), Vec::new(), Vec::new());
    for (name, dir, full) in AREAS.into_iter().filter(|(_, dir, _)| has(dir)) {
        let m = measure_area(dir, full, &budget["areas"][name]);
        println!("{}", table(name, &m, &budget["areas"][name]));
        over(&m, &budget["areas"][name], name, &mut errors);
        broken.extend(hard_violations(name, &m));
        got.insert(name.into(), m);
    }
    let known: Vec<String> = budget["known_over"].as_array().into_iter().flatten().filter_map(|v| v.as_str().map(String::from)).collect();
    // an area that was not measured (no inputs here) keeps its known violations
    let measured = |k: &String| got.keys().any(|a| k.starts_with(&format!("{a}.")));
    errors.extend(broken.iter().filter(|b| !known.contains(b)).map(|b| format!("{b}: over a hard limit, and not in known_over")));
    errors.extend(known.iter().filter(|k| measured(k) && !broken.contains(k)).map(|k| format!("{k}: no longer over a hard limit: scripts/tile_budget.py removes it from known_over")));
    println!("over a hard limit ({HARD_TILE_BYTES} bytes or {HARD_TILE_FEATURES} features for a tile, {HARD_EXPRESSION} characters for an expression):\n  {}", broken.join("\n  "));
    got.insert("hard_violations".into(), json!(broken));
    if let Some(out) = std::env::var_os("ROADSTYLE_TILE_BUDGET_OUT") {
        std::fs::write(out, serde_json::to_string_pretty(&Value::Object(got)).unwrap()).unwrap();
    }
    assert!(errors.is_empty(), "the tiles are over their budget (docs/design/tile_contract.md, 'The tile size standard'). A change that makes the \
            tiles smaller is the aim. To raise a limit, the PR text must say why and Kaveh must agree: scripts/tile_budget.py --raise --why \
            '...'\n{}", errors.join("\n"));
}

/// The local gate for Burnaby (its roads are not in the repository): the same table, and the limits of `areas.burnaby` if the budget has
/// them. `ROADSTYLE_BURNABY_ROADS`: roads.parquet; `ROADSTYLE_BURNABY_LOOK`: a look (default tests/data/look.json);
/// `ROADSTYLE_BURNABY_VIEWS`: more views, [[name, [[z, x, y], ...]], ...] (bench_live's views.json, for the tilted view).
#[test]
#[ignore = "local: needs ROADSTYLE_BURNABY_ROADS"]
fn burnaby_gate() {
    // `cargo test -- --ignored` (the nightly Tartu job) runs this too: with no Burnaby roads there is nothing to measure
    let Some(path) = std::env::var_os("ROADSTYLE_BURNABY_ROADS") else {
        eprintln!("no ROADSTYLE_BURNABY_ROADS=<roads.parquet>: skipped");
        return;
    };
    let roads = std::fs::read(path).unwrap();
    let look = match std::env::var_os("ROADSTYLE_BURNABY_LOOK") {
        Some(p) => roadstyle_rs::Look::from_value(serde_json::from_slice(&std::fs::read(p).unwrap()).unwrap()).unwrap(),
        None => roadstyle_rs::Look::from_value(serde_json::from_slice(&std::fs::read(data("look.json")).unwrap()).unwrap()).unwrap(),
    };
    let saved = &budget()["areas"]["burnaby"];
    let center = saved["center"].as_array().map(|c| [c[0].as_f64().unwrap(), c[1].as_f64().unwrap()]).unwrap_or_else(|| center_of(&roads));
    let mut views: Vec<View> = ZOOMS.map(|z| (format!("z{z}"), square(z, center[0], center[1]))).collect();
    if let Some(p) = std::env::var_os("ROADSTYLE_BURNABY_VIEWS") {
        let v: Vec<(String, Vec<[u32; 3]>)> = serde_json::from_slice(&std::fs::read(p).unwrap()).unwrap();
        views.extend(v.into_iter().map(|(n, t)| (n, t.into_iter().map(|[z, x, y]| (z, x, y)).collect())));
    }
    let features = std::env::var_os("ROADSTYLE_BURNABY_FEATURES").map(|p| std::fs::read(p).unwrap());
    let m = measure(roads, features, &look, center, views);
    println!("{}", table("burnaby", &m, saved));
    println!("over a hard limit: {:?}", hard_violations("burnaby", &m));
    let mut errors = Vec::new();
    if saved.is_object() {
        over(&m, saved, "burnaby", &mut errors);
    }
    assert!(errors.is_empty(), "Burnaby is over its budget:\n{}", errors.join("\n"));
}
