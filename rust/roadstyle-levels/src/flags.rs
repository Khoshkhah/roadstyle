//! The road flags, one rule (audit R6; the web map's rule, render_web._truthy, lower-cased and stripped): a yes/no tag (bridge, tunnel,
//! oneway, driving, cycling, directed) is yes when it is set and not one of `NO` (OSM's "no", and "", "false", "0"); so bridge=viaduct
//! is a bridge and oneway=-1 is one way. The layer, the level from the tags and is_directed follow, and the SQL form. It is here, in the
//! leaf crate (N26), so that the levels need no other crate; roadstyle_model::flags re-exports it with the JSON and MapLibre forms.

/// The texts that mean "not set" for a yes/no tag, after lower-case and strip.
pub const NO: [&str; 4] = ["", "no", "false", "0"];

/// Whether a tag's text is yes.
pub fn yes_text(s: &str) -> bool {
    !NO.contains(&s.trim().to_lowercase().as_str())
}

/// The layer tag: its whole part (Python's int(float(layer)), truncated toward 0); 0 when it is not a number.
pub fn layer(s: Option<&str>) -> i64 {
    s.and_then(|s| s.trim().parse::<f64>().ok()).filter(|v| v.is_finite()).map_or(0, |v| v.trunc() as i64)
}

/// The OSM level of an edge: a non-zero layer, else 1 for a bridge, -1 for a tunnel, else 0.
pub fn level(layer: i64, bridge: bool, tunnel: bool) -> i64 {
    if layer != 0 {
        layer
    } else if bridge {
        1
    } else if tunnel {
        -1
    } else {
        0
    }
}

/// Whether an edge is a direction of travel of its own (roadstyle's is_directed): open to cars or bikes and not a path (`path`: its
/// class is a single-line class). None (null) when it is not a path and neither flag says yes but one is not known.
pub fn directed(driving: Option<bool>, cycling: Option<bool>, path: bool) -> Option<bool> {
    if path {
        return Some(false);
    }
    match (driving, cycling) {
        (Some(true), _) | (_, Some(true)) => Some(true),
        (Some(false), Some(false)) => Some(false),
        _ => None,
    }
}

/// The rule in SQL (DuckDB) for the column `col`: a boolean expression.
pub fn sql_yes(col: &str) -> String {
    let no: Vec<String> = NO.iter().map(|s| format!("'{s}'")).collect();
    format!("({col} IS NOT NULL AND lower(trim(CAST({col} AS VARCHAR))) NOT IN ({}))", no.join(", "))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_rule() {
        for (v, want) in [("yes", true), ("viaduct", true), ("-1", true), ("y", true), ("No", false), (" FALSE ", false), ("0", false),
                          ("", false)] {
            assert_eq!(yes_text(v), want, "{v:?}");
        }
        assert_eq!((layer(Some("2.7")), layer(Some("-1")), layer(Some("x")), layer(None)), (2, -1, 0, 0));
        assert_eq!((level(0, true, false), level(0, false, true), level(3, false, true)), (1, -1, 3));
        assert_eq!((directed(Some(false), Some(true), false), directed(Some(true), None, true), directed(None, Some(false), false)),
                   (Some(true), Some(false), None));
        assert_eq!(sql_yes("bridge"), "(bridge IS NOT NULL AND lower(trim(CAST(bridge AS VARCHAR))) NOT IN ('', 'no', 'false', '0'))");
    }
}
