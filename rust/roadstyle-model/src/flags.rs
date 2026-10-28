//! The road flags (audit R6): the one rule is roadstyle_levels::flags (the leaf crate, N26), re-exported here, with the forms that need
//! data: `yes` of a cell or a JSON value and the MapLibre expression, made from the same `NO` table.

pub use roadstyle_levels::flags::*;
use crate::Cell;
use serde_json::{json, Value};

/// Whether a data value is yes: the one rule for a cell, a JSON value or a tag text. Null (and NaN) is no; a boolean is itself; a number
/// is yes when it is not 0; a text is yes by `yes_text`; any other value (a list, an object) is yes.
pub fn yes<'a, C: Into<Cell<'a>>>(v: C) -> bool {
    match v.into() {
        Cell::Null | Cell::Json(Value::Null) => false,
        Cell::Bool(b) => b,
        Cell::Json(Value::Bool(b)) => *b,
        Cell::Int(i) => i != 0,
        Cell::Float(f) => f != 0.0 && !f.is_nan(),
        Cell::Str(s) => yes_text(s),
        Cell::Json(Value::String(s)) => yes_text(s),
        Cell::Json(Value::Number(n)) => n.as_f64() != Some(0.0),
        Cell::Json(_) => true,
    }
}

/// `yes` of a value that may be missing (a missing value is no).
pub fn is_yes<'a, C: Into<Cell<'a>>>(v: Option<C>) -> bool {
    v.is_some_and(yes)
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
