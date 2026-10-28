//! The nearest known name, and the explanation of an unknown key.

use serde_json::Value;

/// `"; did you mean \"x\"?"` with the known name nearest `k` (`nearest_name`), or "".
pub fn nearest<'a>(k: &str, known: impl IntoIterator<Item = &'a str>) -> String {
    nearest_name(k, known).map_or_else(String::new, |n| format!("; did you mean \"{n}\"?"))
}

/// The known name nearest `k` (Jaro-Winkler 0.75 or more: a common start counts more, so "by_column" finds "by"), or none.
pub fn nearest_name<'a>(k: &str, known: impl IntoIterator<Item = &'a str>) -> Option<&'a str> {
    known.into_iter().map(|n| (strsim::jaro_winkler(k, n), n)).filter(|(s, _)| *s >= 0.75).max_by(|a, b| a.0.total_cmp(&b.0)).map(|(_, n)| n)
}

/// serde's error of the nested options, explained: an unknown key with its path and the nearest known key; another error as it is.
pub(super) fn explain(v: &Value, e: &str) -> String {
    let unknown = e.strip_prefix("unknown field `").or_else(|| e.strip_prefix("unknown variant `"));
    let Some((key, expected)) = unknown.and_then(|r| r.split_once('`')) else { return format!("map options: {e}") };
    // the known names: the ones that serde names after "expected"
    let known: Vec<&str> = expected.split('`').skip(1).step_by(2).collect();
    let path = find(v, key, &known, "").unwrap_or_else(|| key.to_string());
    format!("\"{path}\": unknown key{}", nearest(key, known.iter().copied()))
}

/// The path of the first mapping in `v` that has the key `key` beside keys that are all `known` (the struct that serde read), or of the
/// first text `key` (a variant).
fn find(v: &Value, key: &str, known: &[&str], at: &str) -> Option<String> {
    let join = |k: &str| if at.is_empty() { k.to_string() } else { format!("{at}.{k}") };
    match v {
        Value::Object(m) => {
            if m.contains_key(key) && m.keys().all(|k| k == key || known.contains(&k.as_str())) {
                return Some(join(key));
            }
            m.iter().find_map(|(k, x)| find(x, key, known, &join(k)))
        }
        Value::Array(l) => l.iter().enumerate().find_map(|(i, x)| find(x, key, known, &format!("{at}[{i}]"))),
        Value::String(s) if s == key => Some(at.to_string()),
        _ => None,
    }
}
