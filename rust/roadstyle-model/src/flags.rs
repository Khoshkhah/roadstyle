//! The road flags (audit R6): the one rule is roadstyle_levels::flags (the leaf crate, N26), re-exported here, with the forms that need
//! JSON: a JSON value's yes and the MapLibre expression, made from the same `NO` table.

pub use roadstyle_levels::flags::*;
use serde_json::{json, Value};

/// Whether a value is yes: a boolean; a number that is not 0; a text by `yes_text`; null is no.
pub fn yes(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64() != Some(0.0),
        Value::String(s) => yes_text(s),
        _ => true,
    }
}

/// The rule as a MapLibre expression on the value `get` (for example `["get", "bridge"]`). MapLibre has no trim, so a text with spaces
/// around "no" is yes there.
pub fn maplibre_yes(get: Value) -> Value {
    json!(["!", ["in", ["downcase", ["to-string", get]], ["literal", NO]]])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_json_forms() {
        assert!(yes(&json!(true)) && yes(&json!(1)) && !yes(&json!(0)) && !yes(&Value::Null) && !yes(&json!("no")) && yes(&json!("viaduct")));
        assert_eq!(maplibre_yes(json!(["get", "bridge"])), json!(["!", ["in", ["downcase", ["to-string", ["get", "bridge"]]], ["literal", ["", "no", "false", "0"]]]]));
    }
}
