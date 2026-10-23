//! What the golden tests share: the first differences of two JSON values, as paths.

use serde_json::Value;

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
        _ if a.to_string() != b.to_string() => out.push(format!("{path}: {} != {}", cut(a), cut(b))),
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
    flate2::read::GzDecoder::new(std::fs::File::open(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))).read_to_string(&mut text).unwrap();
    serde_json::from_str(&text).unwrap()
}
