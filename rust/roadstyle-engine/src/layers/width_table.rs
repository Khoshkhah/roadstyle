//! The road width as a table lookup (docs/design/tile_speed.md, "The road width expression").
//!
//! The width of a piece depends on its kind, on three flags (pair, bridge, two-way) and on its class. The `case` form of `width_curve`
//! repeats the class tables at each stop. MapLibre takes 20 to 25 ms for each tile at z11 to z13 to parse it. Here, a `let` finds the
//! row of the piece (kind and flags) and the group of its class one time. Each stop is then one `at` in a table of rows. A group is
//! classes that have the same width in all rows and stops. The tables come from the `case` form: the form is evaluated for each row,
//! class and stop. The widths are the same (width_tests.rs).

use super::eval::{ev, Ev};
use super::*;

/// The piece kinds (`__rs_k` 0 to 5). The row of a piece is `kind * 8` plus its flags (pair 4, bridge 2, two-way 1).
const KINDS: usize = 6;
pub(super) const ROW_VAR: &str = "row";

/// True if the expression reads only the marks and the class column of the row. A value that a feature sets (the metre width) is not in a table.
fn reads_only_row(e: &Value, hw: &str) -> bool {
    let Value::Array(a) = e else { return true };
    if let [op, Value::String(name)] = a.as_slice() {
        if op == "get" || op == "has" {
            let own = [Mark::PieceKind, Mark::Pair, Mark::Bridge, Mark::Twoway, Mark::ClassIndex];
            return name == hw || own.iter().any(|m| m.name() == name);
        }
    }
    a.iter().all(|x| reads_only_row(x, hw))
}

/// The properties of a piece of this row and class: the kind and flags, the class column and the class index. The last class is the fallback.
pub(super) fn piece(row: usize, class: usize, hw: &str, classes: &[String]) -> Map<String, Value> {
    let mut p = Map::new();
    p.insert(Mark::PieceKind.name().into(), (row / 8).into());
    for (bit, m) in [(4, Mark::Pair), (2, Mark::Bridge), (1, Mark::Twoway)] {
        if row & bit != 0 {
            p.insert(m.name().into(), true.into());
        }
    }
    if let Some(c) = classes.get(class) {
        p.insert(hw.into(), c.as_str().into());
    }
    p.insert(Mark::ClassIndex.name().into(), class.into());
    p
}

/// The expression for the row of a piece.
fn row_code() -> Value {
    let flag = |m: Mark, bit: i64| json!(["case", ["to-boolean", ["get", m.name()]], bit, 0]);
    json!(["+", ["*", ["get", Mark::PieceKind.name()], 8], flag(Mark::Pair, 4), flag(Mark::Bridge, 2), flag(Mark::Twoway, 1)])
}

/// The place of each item in the list of the different items, and that list. Equal items have the same place.
fn dedupe<T: PartialEq>(items: Vec<T>) -> (Vec<usize>, Vec<T>) {
    let (mut place, mut unique) = (Vec::new(), Vec::new());
    for x in items {
        place.push(unique.iter().position(|u| *u == x).unwrap_or_else(|| { unique.push(x); unique.len() - 1 }));
    }
    (place, unique)
}

/// `curve` (a zoom curve of widths by piece) as `["let", row, <row and class group>, <the curve of lookups>]`, with the value of each stop
/// times `live`. Gives None if the curve reads more than the row and the class, or if a value is not a number for some piece. The
/// caller then keeps `curve`.
pub(super) fn table_form(curve: &Value, hw: &str, classes: &[String], live: &Value) -> Option<Value> {
    let c = curve.as_array()?;
    if !reads_only_row(curve, hw) {
        return None;
    }
    let (stops, nc) = (c[3..].len() / 2, classes.len() + 1);
    // the width of every row, stop and class: widths[row][stop][class]
    let mut widths = Vec::with_capacity(KINDS * 8);
    for row in 0..KINDS * 8 {
        let mut by_stop = Vec::with_capacity(stops);
        for s in 0..stops {
            let mut by_class = Vec::with_capacity(nc);
            for class in 0..nc {
                let Ev::V(v) = ev(&c[4 + 2 * s], &piece(row, class, hw, classes)) else { return None };
                by_class.push(round_to(v.as_f64()?, 6));
            }
            by_stop.push(by_class);
        }
        widths.push(by_stop);
    }
    let (group_of, firsts) = dedupe((0..nc).map(|k| widths.iter().flatten().map(|stop| stop[k]).collect::<Vec<f64>>()).collect());
    let first_class: Vec<usize> = (0..firsts.len()).map(|g| group_of.iter().position(|x| *x == g).unwrap()).collect();
    let (row_of, rows) = dedupe(widths.iter().map(|r| r.iter().map(|stop| first_class.iter().map(|k| stop[*k]).collect()).collect::<Vec<Vec<f64>>>()).collect());
    let ng = first_class.len();
    let index = json!(["+", ["*", ["at", row_code(), ["literal", row_of]], ng], ["at", ["get", Mark::ClassIndex.name()], ["literal", group_of]]]);
    let mut zoom = c[..3].to_vec();
    for s in 0..stops {
        let table: Vec<f64> = rows.iter().flat_map(|r| r[s].iter().copied()).collect();
        zoom.extend([c[3 + 2 * s].clone(), json!(["*", ["at", ["var", ROW_VAR], ["literal", table]], live])]);
    }
    Some(json!(["let", ROW_VAR, index, Value::Array(zoom)]))
}
