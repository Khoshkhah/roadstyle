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

/// The decided changes of design step (g) (2026-10-23 and 2026-10-24), on a golden of roadstyle 0.24.3 (the file does not change):
/// the export (not a page) keeps the roads' pick and highlight layers shown in both ways (before: hidden when the data was inline), and
/// every style's pieces have their road's row as their feature id (`promoteId`), so a dashboard lights a road's pieces in any style
/// (the glow of 0.24.3's inline styles is in every style).
pub fn as_decided(mut want: Value) -> Value {
    for l in want["layers"].as_array_mut().into_iter().flatten() {
        if matches!(l["id"].as_str(), Some("roads-fill" | "roads-highlight")) {
            l["layout"].as_object_mut().map(|o| o.shift_remove("visibility"));
        }
    }
    if let Some(s) = want["sources"]["simple"].as_object_mut() {
        s.insert("promoteId".into(), "__rs_edge".into());
    }
    want
}
