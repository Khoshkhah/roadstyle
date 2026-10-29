//! The tile size standard (docs/design/tile_contract.md, "The tile size standard"): the tile algorithm applies every reduction that keeps
//! the map the same. This test measures each reduction rule on the tiles of fixed views of Monaco and Tartu at zoom 12 to 15, and on the
//! tiled style, and compares the numbers with the limits of tests/data/tile_budget.json: a number that is larger fails. The limits only
//! go down (scripts/tile_budget.py); a raise needs `--raise --why "..."` and the PR text must say why. Two rules are done, so their
//! numbers are 0 (the test asserts it): no feature outside its zoom span (rule 1, where a layer's filter has a zoom rule) and no
//! value or key twice in a layer (rule 5). The numbers of the other rules go down to 0 or to their best as the rules land.
//!
//! For each view, for each tile layer, the largest tile: its features, bytes, keys and values (the distinct values), and
//! `keys_unread` (rule 2: keys that no style layer on the layer reads), `no_id` (rule 3: features without an MVT id), `strings` and
//! `string_bytes` (rule 4: values that are text), `short_segments` (rule 6: line segments under 1 px) and `tiny` (rule 7: features whose
//! box is under 1 px). For the view: the bytes of all its tiles and the bytes and features of its largest tile. For the style: the size
//! of each filter, paint and layout (JSON characters) that is over `SMALL`, and the total.
//!
//! The view of an area is the 3 x 3 tiles around a fixed centre (the budget file keeps it, `center`), at zoom 9 to 15. The keep list of the
//! tiles is empty: the numbers are the engine's own tiles, without a page's popup fields. Each area has two looks: `monaco` is the page's
//! (the lean look: the `simple` pieces and the slots) and `monaco-full` is `export_style`'s (it has the whole-road layer `roads` too).
//! `monaco-base` and `tartu-base` are the page's look with the area's base map (land, water, paved areas, buildings): at the low zooms it is
//! most of a tile.
//!
//!     cargo test --release -p roadstyle-rs --test tile_budget -- --nocapture       (the table)
//!     ROADSTYLE_BURNABY_ROADS=<roads.parquet> cargo test --release -p roadstyle-rs --test tile_budget burnaby -- --ignored --nocapture

mod common;

use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::PathBuf;

/// A view: its name and its tiles (zoom, x, y).
type View = (String, Vec<(u32, u32, u32)>);

/// The first and the last zoom of the fixed views.
const ZOOMS: std::ops::RangeInclusive<u32> = 9..=15;
/// A filter, paint or layout of a style layer over this many JSON characters has its own limit; a smaller one has none.
const SMALL: usize = 256;
/// One pixel in tile units (512 px tiles, extent 4096).
const PIXEL: i64 = 8;

/// What an area's tiles are made from: the page's lean look (`Lean`), the look of `export_style` (`Full`: the whole-road layer `roads` too),
/// or the lean look with the area's base map (`Base`: tests/data/look.json and the area's `features.parquet`).
#[derive(Clone, Copy, PartialEq)]
enum Kind {
    Lean,
    Full,
    Base,
}

/// The areas of the budget: its name, the inputs' folder in tests/data, and its look.
const AREAS: [(&str, &str, Kind); 6] = [("monaco", "monaco", Kind::Lean), ("monaco-full", "monaco", Kind::Full), ("monaco-base", "monaco", Kind::Base),
                                        ("tartu", "tartu", Kind::Lean), ("tartu-full", "tartu", Kind::Full), ("tartu-base", "tartu", Kind::Base)];

fn data(p: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(p)
}

/// An area's look: its options (golden_options.json.gz), as an export (areas.rs) with the whole-road layer `roads` for `Full`; the page's
/// look (look.json) for `Base`.
fn look(area: &str, kind: Kind) -> roadstyle_rs::Look {
    if kind == Kind::Base {
        return roadstyle_rs::Look::from_value(serde_json::from_slice(&std::fs::read(data("look.json")).unwrap()).unwrap()).unwrap();
    }
    let o = common::gz_json(&format!("{area}/golden_options.json.gz"));
    let mut look = roadstyle_rs::Look::resolution_value(&roadstyle_rs::look::Options::from_value(&o).unwrap()).unwrap();
    look["args"]["export"] = (kind == Kind::Full).into();
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

/// What the layer's own tables say: `features`, `bytes` (the layer's share of the tile: tag, length, message), `keys`, `values`,
/// `strings` and `string_bytes` (the text values), and `dup` (a key or a value twice, rule 5).
#[derive(Default)]
struct Tables {
    features: usize,
    bytes: usize,
    keys: usize,
    values: usize,
    strings: usize,
    string_bytes: usize,
    dup: usize,
}

fn layers_of(tile: &[u8]) -> Vec<(String, Tables)> {
    fields(tile).into_iter().filter(|f| f.0 == 3).map(|(_, _, _, layer)| {
        let (mut name, mut t) = (String::new(), Tables::default());
        let (mut keys, mut values): (HashSet<&[u8]>, HashSet<&[u8]>) = (HashSet::new(), HashSet::new());
        for (f, _, _, d) in fields(layer) {
            match f {
                1 => name = String::from_utf8(d.to_vec()).unwrap(),
                2 => t.features += 1,
                3 => {
                    t.keys += 1;
                    t.dup += usize::from(!keys.insert(d));
                }
                4 => {
                    t.values += 1;
                    t.dup += usize::from(!values.insert(d));
                    if fields(d).first().is_some_and(|v| v.0 == 1) {
                        t.strings += 1;
                        t.string_bytes += d.len();
                    }
                }
                _ => {}
            }
        }
        let head = 1 + (64 - (layer.len() as u64 | 1).leading_zeros() as usize).div_ceil(7);
        t.bytes = head + layer.len();
        (name, t)
    }).collect()
}

/// The properties that the style's layers read, for each tile layer: `["get", k]` and `["has", k]` in the filter, paint and layout, the
/// `{k}` of a text field, the vector source's `promoteId` and the dashboard's filter keys.
fn style_reads(style: &Value) -> HashMap<String, HashSet<String>> {
    fn walk(v: &Value, out: &mut HashSet<String>) {
        match v {
            Value::Array(a) => {
                if let [op, Value::String(k)] = a.as_slice() {
                    if op == "get" || op == "has" {
                        out.insert(k.clone());
                    }
                }
                a.iter().for_each(|x| walk(x, out));
            }
            Value::Object(o) => o.values().for_each(|x| walk(x, out)),
            Value::String(t) => t.split('{').skip(1).filter_map(|r| r.split_once('}')).for_each(|(k, _)| {
                out.insert(k.to_string());
            }),
            _ => {}
        }
    }
    let mut out: HashMap<String, HashSet<String>> = HashMap::new();
    for l in style["layers"].as_array().into_iter().flatten() {
        let name = l["source-layer"].as_str().or(l["source"].as_str()).unwrap_or("").to_string();
        let e = out.entry(name).or_default();
        for part in ["filter", "paint", "layout"] {
            walk(&l[part], e);
        }
    }
    for layer in ["simple", "slots"] {          // the dashboard's filters read these (mark::filter_keys)
        out.entry(layer.into()).or_default().extend(roadstyle_rs::mark::filter_keys().map(String::from));
    }
    for src in style["sources"].as_object().into_iter().flatten().map(|(_, s)| &s["promoteId"]) {
        for (layer, k) in src.as_object().into_iter().flatten() {
            out.entry(layer.clone()).or_default().extend(k.as_str().map(String::from));
        }
    }
    out
}

/// The numbers of one tile layer that the reduction rules (docs/design/tile_contract.md) are about, from its decoded features.
#[derive(Default)]
struct Rules {
    keys_unread: usize,
    no_id: usize,
    short_segments: usize,
    tiny: usize,
    /// features outside their zoom span (rule 1; only for a layer with a zoom rule)
    undrawn: usize,
}

/// `last`: the tiles' last zoom: its tiles have every feature that a layer draws at or after it (MapLibre scales them up).
fn rules_of(z: u32, last: u32, feats: &[common::Feature], reads: Option<&HashSet<String>>,
            zoom: &roadstyle_rs::tiles::rules::ZoomRules) -> Rules {
    let mut r = Rules::default();
    let mut used: HashSet<&str> = HashSet::new();
    for (id, props, kind, parts) in feats {
        used.extend(props.keys().map(String::as_str));
        r.no_id += usize::from(id.is_none());
        if !zoom.is_empty() {
            let (from, until) = zoom.span(props);
            r.undrawn += usize::from(!((z == last || z as f64 + 1.0 > from) && (z as f64) < until));
        }
        if *kind != 1 {
            let pts: Vec<[i64; 2]> = parts.iter().flatten().copied().collect();
            let range = |i: usize| pts.iter().map(|p| p[i]).max().unwrap_or(0) - pts.iter().map(|p| p[i]).min().unwrap_or(0);
            r.tiny += usize::from(range(0) < PIXEL && range(1) < PIXEL);
            r.short_segments += parts.iter().flat_map(|l| l.windows(2)).filter(|w| (w[1][0] - w[0][0]).abs().max((w[1][1] - w[0][1]).abs()) < PIXEL).count();
        }
    }
    r.keys_unread = used.iter().filter(|k| !reads.is_some_and(|s| s.contains(**k))).count();
    r
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

/// The numbers of an area: for each view, its tiles' sizes and the numbers of the reduction rules; and the style's. `views`: the name and the
/// tiles of each. A rule that is done and not 0 (rules 1 and 5) is in `broken`.
fn measure(roads: Vec<u8>, features: Option<Vec<u8>>, look: &roadstyle_rs::Look, center: [f64; 2], views: Vec<View>, broken: &mut Vec<String>) -> Value {
    let (style, tiles, _) = roadstyle_rs::tiled_from_parquet(roads, look, features, None, "rs://", &[]).unwrap();
    let style: Value = serde_json::from_str(&style).unwrap();
    let reads = style_reads(&style);
    let layers_json = style["layers"].as_array().cloned().unwrap_or_default();
    let last = serde_json::to_value(&look.sections.tiles).unwrap()["maxzoom"].as_f64().unwrap_or(f64::MAX) as u32;
    let mut zoom: HashMap<String, roadstyle_rs::tiles::rules::ZoomRules> = HashMap::new();
    let mut out = Map::new();
    out.insert("center".into(), json!(center));
    for (name, view) in views {
        let (mut bytes, mut features, mut biggest, mut most) = (0usize, 0usize, 0usize, 0usize);
        let mut layers: BTreeMap<String, [usize; 10]> = BTreeMap::new();
        for (z, x, y) in view {
            let t = tiles.tile(z, x, y);
            bytes += t.len();
            biggest = biggest.max(t.len());
            let decoded = common::decode_tile(&t);
            let tables = layers_of(&t);
            most = most.max(tables.iter().map(|l| l.1.features).sum());
            for (l, tb) in tables {
                features += tb.features;
                let zr = zoom.entry(l.clone()).or_insert_with(|| roadstyle_rs::tiles::rules::ZoomRules::of(&layers_json, &l));
                let r = rules_of(z, last, &decoded[&l], reads.get(&l), zr);
                for (what, n) in [("undrawn", r.undrawn), ("duplicates", tb.dup)] {
                    if n > 0 {
                        broken.push(format!("{name} {l} {z}/{x}/{y}: {n} {what} (rule {})", if what == "undrawn" { 1 } else { 5 }));
                    }
                }
                let e = layers.entry(l).or_default();
                let now = [tb.features, tb.bytes, tb.values, tb.keys, r.keys_unread, r.no_id, tb.strings, tb.string_bytes, r.short_segments, r.tiny];
                e.iter_mut().zip(now).for_each(|(m, n)| *m = (*m).max(n));
            }
        }
        let layers: Map<String, Value> = layers.into_iter().map(|(k, n)| (k, json!({"features": n[0], "bytes": n[1], "values": n[2], "keys": n[3],
            "keys_unread": n[4], "no_id": n[5], "strings": n[6], "string_bytes": n[7], "short_segments": n[8], "tiny": n[9]}))).collect();
        out.insert(name, json!({"view_bytes": bytes, "view_features": features, "max_tile_bytes": biggest, "max_tile_features": most, "layers": layers}));
    }
    out.insert("style".into(), style_sizes(&style));
    Value::Object(out)
}

/// The areas of the budget: the fixed views of the area's roads (the budget's centre, else the roads' middle).
fn measure_area(dir: &str, kind: Kind, saved: &Value, broken: &mut Vec<String>) -> Value {
    let roads = std::fs::read(data(&format!("{dir}/roads.parquet"))).unwrap();
    let center = saved["center"].as_array().map(|c| [c[0].as_f64().unwrap(), c[1].as_f64().unwrap()]).unwrap_or_else(|| center_of(&roads));
    let views = ZOOMS.map(|z| (format!("z{z}"), square(z, center[0], center[1]))).collect();
    // the golden looks have no layers_yaml: only `Base` has the base map (Burnaby's is measured by the local gate)
    let features = (kind == Kind::Base).then(|| std::fs::read(data(&format!("{dir}/features.parquet"))).unwrap());
    measure(roads, features, &look(dir, kind), center, views, broken)
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
    let mut s = format!("{area}: the largest tile of each layer (measured/limit)\n{:<6}{:<8}{:>20}{:>9}{:>9}{:>9}{:>9}{:>9}{:>9}{:>9}\n",
                        "view", "layer", "bytes", "feat.", "values", "unread", "no_id", "strings", "short", "tiny");
    for (view, v) in got.as_object().into_iter().flatten().filter(|(k, _)| *k != "center" && *k != "style") {
        for (layer, m) in v["layers"].as_object().into_iter().flatten() {
            let l = &limit[view]["layers"][layer];
            s += &format!("{view:<6}{layer:<8}{:>20}{:>9}{:>9}{:>9}{:>9}{:>9}{:>9}{:>9}\n", cell(&m["bytes"], &l["bytes"]), m["features"].to_string(), m["values"].to_string(),
                          m["keys_unread"].to_string(), m["no_id"].to_string(), m["strings"].to_string(), m["short_segments"].to_string(), m["tiny"].to_string());
        }
        let l = &limit[view];
        s += &format!("{view:<6}{:<8}{:>20}   all tiles {} features; largest tile {} bytes, {} features\n", "(all)", cell(&v["view_bytes"], &l["view_bytes"]),
                      v["view_features"], cell(&v["max_tile_bytes"], &l["max_tile_bytes"]), cell(&v["max_tile_features"], &l["max_tile_features"]));
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

/// The tiles and the style of Monaco and Tartu (the page's look and the full look) are within the budget, and the done rules (1 and 5) hold.
/// `ROADSTYLE_TILE_BUDGET_OUT=<file>` writes the numbers there first (scripts/tile_budget.py reads them).
#[test]
fn the_tiles_stay_within_their_budget() {
    let budget = budget();
    let (mut got, mut errors) = (Map::new(), Vec::new());
    for (name, dir, kind) in AREAS.into_iter().filter(|(_, dir, _)| has(dir)) {
        let m = measure_area(dir, kind, &budget["areas"][name], &mut errors);
        println!("{}", table(name, &m, &budget["areas"][name]));
        over(&m, &budget["areas"][name], name, &mut errors);
        got.insert(name.into(), m);
    }
    if let Some(out) = std::env::var_os("ROADSTYLE_TILE_BUDGET_OUT") {
        std::fs::write(out, serde_json::to_string_pretty(&Value::Object(got)).unwrap()).unwrap();
    }
    assert!(errors.is_empty(), "the tiles break a reduction rule or are over their budget (docs/design/tile_contract.md, 'The tile size \
            standard'). A change that makes the tiles smaller is the aim. To raise a limit, the PR text must say why and Kaveh must agree: \
            scripts/tile_budget.py --raise --why '...'\n{}", errors.join("\n"));
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
    let mut errors = Vec::new();
    let m = measure(roads, features, &look, center, views, &mut errors);
    println!("{}", table("burnaby", &m, saved));
    if saved.is_object() {
        over(&m, saved, "burnaby", &mut errors);
    }
    assert!(errors.is_empty(), "Burnaby is over its budget:\n{}", errors.join("\n"));
}
