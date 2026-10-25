//! What the golden tests share: the first differences of two JSON values, as paths.
#![allow(dead_code)] // each test file uses some of these

use serde_json::{json, Value};

/// The first differences of two JSON values, as paths (key order counts).
pub fn diff(a: &Value, b: &Value, path: &str, out: &mut Vec<String>) {
    if out.len() >= 8 {
        return;
    }
    match (a, b) {
        (Value::Object(x), Value::Object(y)) => {
            let (kx, ky): (Vec<&String>, Vec<&String>) = (x.keys().collect(), y.keys().collect());
            if kx != ky {
                out.push(format!("{path}: keys {kx:?} != {ky:?}"));
                return;
            }
            x.iter().for_each(|(k, v)| diff(v, &y[k], &format!("{path}.{k}"), out));
        }
        (Value::Array(x), Value::Array(y)) if x.len() == y.len() => {
            x.iter().zip(y).enumerate().for_each(|(i, (u, v))| diff(u, v, &format!("{path}[{i}]"), out));
        }
        _ if *a != *b => out.push(format!("{path}: {} != {}", cut(a), cut(b))),
        _ => {}
    }
}

fn cut(v: &Value) -> String {
    let s = v.to_string();
    if s.len() > 160 { format!("{}...", &s[..160]) } else { s }
}

/// A gzipped JSON file of tests/data.
pub fn gz_json(name: &str) -> Value {
    use std::io::Read;
    let p = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(name);
    let mut text = String::new();
    flate2::read::GzDecoder::new(std::fs::File::open(&p).unwrap_or_else(|e| panic!("{}: {e} (a large golden: run tests/get_goldens.sh)", p.display()))).read_to_string(&mut text).unwrap();
    serde_json::from_str(&text).unwrap()
}

/// All differences of two JSON values, counted by path with the indexes left out ("sources.roads.data.features[].properties.x"), in
/// the order they are found.
pub fn diff_summary(a: &Value, b: &Value) -> Vec<(String, usize)> {
    fn walk(a: &Value, b: &Value, path: &str, out: &mut indexmap::IndexMap<String, usize>) {
        match (a, b) {
            (Value::Object(x), Value::Object(y)) => {
                let (kx, ky): (Vec<&String>, Vec<&String>) = (x.keys().collect(), y.keys().collect());
                if kx != ky {
                    let (only_a, only_b): (Vec<_>, Vec<_>) = (kx.iter().filter(|k| !y.contains_key(**k)).collect(), ky.iter().filter(|k| !x.contains_key(**k)).collect());
                    *out.entry(format!("{path}: keys (only Rust {only_a:?}, only Python {only_b:?})")).or_default() += 1;
                }
                for (k, v) in x {
                    if let Some(w) = y.get(k) {
                        walk(v, w, &format!("{path}.{k}"), out);
                    }
                }
            }
            (Value::Array(x), Value::Array(y)) => {
                if x.len() != y.len() {
                    *out.entry(format!("{path}: length")).or_default() += 1;
                }
                let p = format!("{path}[]");
                x.iter().zip(y).for_each(|(u, v)| walk(u, v, &p, out));
            }
            _ if *a != *b => *out.entry(path.to_string()).or_default() += 1,
            _ => {}
        }
    }
    let mut out = indexmap::IndexMap::new();
    walk(a, b, "", &mut out);
    out.into_iter().collect()
}

/// A decoded vector tile (MVT 2.1): for each layer, its features as (id, properties, geometry type, the commands' points per part).
pub type Tile = indexmap::IndexMap<String, Vec<(Option<u64>, serde_json::Map<String, Value>, u64, Vec<Vec<[i64; 2]>>)>>;

pub fn decode_tile(b: &[u8]) -> Tile {
    fn varint(b: &[u8], i: &mut usize) -> u64 {
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
    }
    /// The fields of a message: (field number, wire type, varint value or the bytes).
    fn fields(b: &[u8]) -> Vec<(u64, u64, u64, &[u8])> {
        let (mut i, mut out) = (0, Vec::new());
        while i < b.len() {
            let k = varint(b, &mut i);
            match k & 7 {
                0 => out.push((k >> 3, 0, varint(b, &mut i), &b[0..0])),
                1 => {
                    out.push((k >> 3, 1, 0, &b[i..i + 8]));
                    i += 8;
                }
                2 => {
                    let l = varint(b, &mut i) as usize;
                    out.push((k >> 3, 2, 0, &b[i..i + l]));
                    i += l;
                }
                5 => {
                    out.push((k >> 3, 5, 0, &b[i..i + 4]));
                    i += 4;
                }
                w => panic!("wire type {w}"),
            }
        }
        out
    }
    let packed = |b: &[u8]| -> Vec<u64> {
        let mut i = 0;
        let mut v = Vec::new();
        while i < b.len() {
            v.push(varint(b, &mut i));
        }
        v
    };
    let mut tile = Tile::new();
    for (n, _, _, layer) in fields(b) {
        assert_eq!(n, 3, "a tile holds layers");
        let (mut name, mut keys, mut vals, mut feats) = (String::new(), Vec::new(), Vec::new(), Vec::new());
        for (f, _, _, d) in fields(layer) {
            match f {
                1 => name = String::from_utf8(d.to_vec()).unwrap(),
                2 => feats.push(d),
                3 => keys.push(String::from_utf8(d.to_vec()).unwrap()),
                4 => {
                    let (k, w, v, d) = fields(d)[0];
                    vals.push(match (k, w) {
                        (1, _) => Value::from(String::from_utf8(d.to_vec()).unwrap()),
                        (2, _) => json!(f32::from_le_bytes(d.try_into().unwrap()) as f64),
                        (3, _) => json!(f64::from_le_bytes(d.try_into().unwrap())),
                        (4, _) => json!(v as i64),
                        (5, _) => json!(v),
                        (6, _) => json!(((v >> 1) as i64) ^ -((v & 1) as i64)),
                        (7, _) => json!(v != 0),
                        other => panic!("value {other:?}"),
                    });
                }
                _ => {}
            }
        }
        let mut out = Vec::new();
        for fb in feats {
            let (mut id, mut props, mut kind, mut parts) = (None, serde_json::Map::new(), 0, Vec::new());
            for (f, _, v, d) in fields(fb) {
                match f {
                    1 => id = Some(v),
                    2 => {
                        for t in packed(d).chunks(2) {
                            props.insert(keys[t[0] as usize].clone(), vals[t[1] as usize].clone());
                        }
                    }
                    3 => kind = v,
                    4 => {
                        let cmds = packed(d);
                        let (mut i, mut at, mut part) = (0, [0i64, 0], Vec::new());
                        while i < cmds.len() {
                            let (c, n) = (cmds[i] & 7, cmds[i] >> 3);
                            i += 1;
                            if c == 7 {
                                continue;
                            }
                            if c == 1 && !part.is_empty() {
                                parts.push(std::mem::take(&mut part));
                            }
                            for _ in 0..n {
                                let z = |u: u64| ((u >> 1) as i64) ^ -((u & 1) as i64);
                                at = [at[0] + z(cmds[i]), at[1] + z(cmds[i + 1])];
                                i += 2;
                                part.push(at);
                            }
                        }
                        if !part.is_empty() {
                            parts.push(part);
                        }
                    }
                    _ => {}
                }
            }
            out.push((id, props, kind, parts));
        }
        tile.insert(name, out);
    }
    tile
}

/// The first 16 hex characters of the SHA-256 of a value's JSON text (a short name for a part of an output in a golden).
pub fn hash16(v: &Value) -> String {
    use sha2::{Digest, Sha256};
    Sha256::digest(v.to_string().as_bytes()).iter().take(8).map(|b| format!("{b:02x}")).collect()
}

/// A style as a golden sees it (review D5): each layer's id, type and source with short hashes of its filter, paint and layout; each
/// source's type, feature count and hash; the metadata's keys with the hash of each value; and the hash of the whole style. A change
/// names the layer, source or metadata key that changed, and the golden stays a few KB.
pub fn summary(style: &Value) -> Value {
    let layers: Vec<Value> = style["layers"].as_array().into_iter().flatten().map(|l| json!([l["id"], l["type"], l["source"],
        hash16(&l["filter"]), hash16(&l["paint"]), hash16(&l["layout"])])).collect();
    let sources: serde_json::Map<String, Value> = style["sources"].as_object().into_iter().flatten().map(|(k, s)| (k.clone(), json!([
        s["type"], s["data"]["features"].as_array().map(Vec::len), hash16(s)]))).collect();
    let metadata: serde_json::Map<String, Value> = style["metadata"].as_object().into_iter().flatten().map(|(k, v)| (k.clone(), json!(hash16(v)))).collect();
    let keys: Vec<&String> = style.as_object().map(|o| o.keys().collect()).unwrap_or_default();
    json!({"keys": keys, "layers": layers, "sources": sources, "metadata": metadata, "hash": hash16(style)})
}

/// A golden (tests/data/<name>): with ROADSTYLE_BLESS=1 the test writes `got` there; otherwise it compares, and a difference fails with
/// the paths of the first differences. One mechanism for every golden that the Rust engine makes (no Python, no program of its own).
pub fn golden(name: &str, got: &Value) {
    let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/data").join(name);
    if std::env::var_os("ROADSTYLE_BLESS").is_some() {
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, serde_json::to_string_pretty(got).unwrap() + "\n").unwrap();
        return;
    }
    let text = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e} (ROADSTYLE_BLESS=1 cargo test writes it)", path.display()));
    let want: Value = serde_json::from_str(&text).unwrap();
    let mut out = Vec::new();
    diff(got, &want, "$", &mut out);
    assert!(out.is_empty(), "{name}: not the golden (got | golden); ROADSTYLE_BLESS=1 writes it again:\n{}", out[..out.len().min(12)].join("\n"));
}

/// The levels of an area as a golden sees them (review D5; no Python): its counts. Every solve is feasible, because the solver checks
/// every hard rule of its answer (`levels` gives an error otherwise). The tags rule is deterministic: the hash of its rows and how many
/// casings and fills are at each level. A solve keeps its counts and the best value of each stage, not its rows: an equally good answer
/// may move a row (2026-10-23: the tests check feasibility; the optimum still counts, through the stages).
pub fn levels_summary(lv: &roadstyle_rs::levels::Levels) -> Value {
    use roadstyle_rs::levels::Method;
    let mut s = json!({"method": format!("{:?}", lv.method), "rows": lv.rows.len(), "roads": lv.roads, "edge_hash": lv.edge_hash});
    if lv.method == Method::Tags {
        let rows: Vec<Value> = lv.rows.iter().map(|r| json!([r.edge_id, r.casing_start, r.casing_level, r.casing_end, r.fill_level])).collect();
        let count = |f: fn(&roadstyle_rs::levels::Row) -> i64| {
            let mut m = std::collections::BTreeMap::new();
            lv.rows.iter().for_each(|r| *m.entry(f(r).to_string()).or_insert(0usize) += 1);
            json!(m)
        };
        s["rows_hash"] = json!(hash16(&Value::Array(rows)));
        s["casing_levels"] = count(|r| r.casing_level);
        s["fill_levels"] = count(|r| r.fill_level);
    } else {
        s["pairs"] = json!(lv.pairs);
        s["order_pairs"] = json!(lv.order_pairs);
        s["given_up"] = json!(lv.given_up);
        s["orders_not_kept"] = json!(lv.orders_not_kept);
        s["near_not_kept"] = json!(lv.near_not_kept.len());
        s["stages"] = json!(lv.stages);
    }
    s
}
