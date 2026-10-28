//! The roads as columns (docs/design/rust_library.md, "The render model"): `RoadTable` keeps each column of the input as one Arrow
//! array and every line in one coordinate buffer, not a map of JSON values for each road. A value is read as a `Cell`, which borrows
//! from the table. The JSON text of a cell is the text of the `serde_json::Value` that the reader made before (GeoPandas' GeoJSON).

use arrow_array::{cast::AsArray, types::*, Array, ArrayRef, Int64Array};
use arrow_schema::DataType;
use serde_json::Value;
use std::sync::Arc;

/// An integer past 2**53 - 1: JavaScript rounds it, so the JSON forms write it as text.
/// The model and the Parquet files keep it as an integer (audit N1: duckOSM's edge ids stay BIGINT).
pub const JS_MAX_SAFE_INT: u64 = (1 << 53) - 1;

/// A JSON value as the JSON forms write it (GeoJSON text, the page's road table, the tiles): an integer past 2**53 - 1 as text.
pub struct JsSafe<'a>(pub &'a Value);

impl serde::Serialize for JsSafe<'_> {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        match self.0 {
            Value::Number(n) => match (n.as_i64(), n.as_u64()) {
                (Some(i), _) if i.unsigned_abs() > JS_MAX_SAFE_INT => s.collect_str(&i),
                (None, Some(u)) if u > JS_MAX_SAFE_INT => s.collect_str(&u),
                _ => n.serialize(s),
            },
            Value::Array(a) => s.collect_seq(a.iter().map(JsSafe)),
            Value::Object(o) => s.collect_map(o.iter().map(|(k, v)| (k, JsSafe(v)))),
            v => v.serialize(s),
        }
    }
}

/// `JsSafe` as a value (an integer past 2**53 - 1 as text), for the writers that take a `Value`.
pub fn js_value(v: Value) -> Value {
    match &v {
        Value::Number(n) if n.as_i64().map_or(n.as_u64().is_some(), |i| i.unsigned_abs() > JS_MAX_SAFE_INT) => Value::String(n.to_string()),
        _ => v,
    }
}

/// One value of a road: a cell of a column, or a value of the engine's (a JSON value).
#[derive(Clone, Copy, Debug)]
pub enum Cell<'a> {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(&'a str),
    Json(&'a Value),
}

impl<'a> Cell<'a> {
    /// The value as the reader wrote it into the JSON tree (a float NaN is null, as GeoPandas writes it).
    pub fn to_value(self) -> Value {
        match self {
            Cell::Null => Value::Null,
            Cell::Bool(b) => b.into(),
            Cell::Int(i) => i.into(),
            Cell::Float(f) => serde_json::Number::from_f64(f).map_or(Value::Null, Value::Number),
            Cell::Str(s) => s.into(),
            Cell::Json(v) => v.clone(),
        }
    }

    pub fn is_null(self) -> bool {
        match self {
            Cell::Null => true,
            Cell::Float(f) => f.is_nan(),
            Cell::Json(v) => v.is_null(),
            _ => false,
        }
    }

    pub fn as_str(self) -> Option<&'a str> {
        match self {
            Cell::Str(s) => Some(s),
            Cell::Json(v) => v.as_str(),
            _ => None,
        }
    }

    pub fn as_bool(self) -> Option<bool> {
        match self {
            Cell::Bool(b) => Some(b),
            Cell::Json(v) => v.as_bool(),
            _ => None,
        }
    }

    /// As `Value::as_f64`: a number (not a text that is one).
    pub fn as_f64(self) -> Option<f64> {
        match self {
            Cell::Int(i) => Some(i as f64),
            Cell::Float(f) => (!f.is_nan()).then_some(f),
            Cell::Json(v) => v.as_f64(),
            _ => None,
        }
    }

    /// As `Value::as_i64`: an integer (a float is not one).
    pub fn as_i64(self) -> Option<i64> {
        match self {
            Cell::Int(i) => Some(i),
            Cell::Json(v) => v.as_i64(),
            _ => None,
        }
    }

    pub fn as_u64(self) -> Option<u64> {
        match self {
            Cell::Int(i) => u64::try_from(i).ok(),
            Cell::Json(v) => v.as_u64(),
            _ => None,
        }
    }
}

impl<'a> From<&'a Value> for Cell<'a> {
    fn from(v: &'a Value) -> Cell<'a> {
        Cell::Json(v)
    }
}

impl<'a> From<&&'a Value> for Cell<'a> {
    fn from(v: &&'a Value) -> Cell<'a> {
        Cell::Json(v)
    }
}

/// The same value (as the two JSON values are the same).
impl PartialEq for Cell<'_> {
    fn eq(&self, other: &Self) -> bool {
        match (self, other) {
            (Cell::Str(a), Cell::Str(b)) => a == b,
            (Cell::Int(a), Cell::Int(b)) => a == b,
            (Cell::Bool(a), Cell::Bool(b)) => a == b,
            _ => self.to_value() == other.to_value(),
        }
    }
}

impl PartialEq<Value> for Cell<'_> {
    fn eq(&self, other: &Value) -> bool {
        self.to_value() == *other
    }
}

impl serde::Serialize for Cell<'_> {
    /// The text of `to_value()`, with no copy of the value.
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        match *self {
            Cell::Null => s.serialize_unit(),
            Cell::Bool(b) => s.serialize_bool(b),
            Cell::Int(i) if i.unsigned_abs() > JS_MAX_SAFE_INT => s.collect_str(&i),      // the JSON form: as text (`JsSafe`)
            Cell::Int(i) => s.serialize_i64(i),
            Cell::Float(f) if f.is_finite() => s.serialize_f64(f),
            Cell::Float(_) => s.serialize_unit(),
            Cell::Str(t) => s.serialize_str(t),
            Cell::Json(v) => v.serialize(s),
        }
    }
}

/// The lines of the roads: one coordinate buffer, with the end of each road's line in it. A road whose geometry is not a LineString
/// has none (the stages skip it, as roadstyle does).
#[derive(Clone, Debug, Default)]
pub struct Lines {
    pts: Vec<[f64; 2]>,
    end: Vec<u32>,
    some: Vec<bool>,
}

impl Lines {
    pub fn push(&mut self, line: Option<&[[f64; 2]]>) {
        if let Some(l) = line {
            self.pts.extend_from_slice(l);
        }
        self.end.push(self.pts.len() as u32);
        self.some.push(line.is_some());
    }

    pub fn len(&self) -> usize {
        self.end.len()
    }

    pub fn is_empty(&self) -> bool {
        self.end.is_empty()
    }

    /// The line of the road `row` (None: not a LineString).
    pub fn get(&self, row: usize) -> Option<&[[f64; 2]]> {
        if !self.some[row] {
            return None;
        }
        let start = if row == 0 { 0 } else { self.end[row - 1] as usize };
        Some(&self.pts[start..self.end[row] as usize])
    }
}

/// The roads: their columns (Arrow arrays, in the input's order) and their lines.
#[derive(Clone, Debug)]
pub struct RoadTable {
    names: Vec<String>,
    cols: Vec<ArrayRef>,
    lines: Lines,
}

/// The column types that the reader takes (the types of GeoPandas' GeoParquet).
fn readable(t: &DataType) -> bool {
    matches!(t, DataType::Null | DataType::Utf8 | DataType::LargeUtf8 | DataType::Utf8View | DataType::Boolean | DataType::Int32
                | DataType::Int64 | DataType::Float32 | DataType::Float64)
}

impl RoadTable {
    /// The table of the columns `names` (each as long as `lines`). An error for a column of another type or length.
    pub fn new(names: Vec<String>, cols: Vec<ArrayRef>, lines: Lines) -> Result<RoadTable, crate::Error> {
        for (n, c) in names.iter().zip(&cols) {
            if !readable(c.data_type()) {
                return Err(crate::error::column(n, format!("type {} is not read", c.data_type())));
            }
            if c.len() != lines.len() {
                return Err(crate::error::column(n, format!("{} rows, the roads have {}", c.len(), lines.len())));
            }
        }
        Ok(RoadTable { names, cols, lines })
    }

    /// A table of no roads.
    pub fn empty() -> RoadTable {
        RoadTable { names: Vec::new(), cols: Vec::new(), lines: Lines::default() }
    }

    pub fn len(&self) -> usize {
        self.lines.len()
    }

    pub fn is_empty(&self) -> bool {
        self.lines.is_empty()
    }

    /// The column names, in their order.
    pub fn names(&self) -> &[String] {
        &self.names
    }

    pub fn col(&self, name: &str) -> Option<usize> {
        self.names.iter().position(|n| n == name)
    }

    pub fn line(&self, row: usize) -> Option<&[[f64; 2]]> {
        self.lines.get(row)
    }

    /// The value of the column `col` of the road `row`.
    pub fn cell(&self, col: usize, row: usize) -> Cell<'_> {
        let c = &self.cols[col];
        if c.is_null(row) {
            return Cell::Null;
        }
        match c.data_type() {
            DataType::Utf8 => Cell::Str(c.as_string::<i32>().value(row)),
            DataType::LargeUtf8 => Cell::Str(c.as_string::<i64>().value(row)),
            DataType::Utf8View => Cell::Str(c.as_string_view().value(row)),
            DataType::Boolean => Cell::Bool(c.as_boolean().value(row)),
            DataType::Int32 => Cell::Int(c.as_primitive::<Int32Type>().value(row) as i64),
            DataType::Int64 => {
                let i = c.as_primitive::<Int64Type>().value(row);
                Cell::Int(i)
            }
            DataType::Float32 => Cell::Float(c.as_primitive::<Float32Type>().value(row) as f64),
            DataType::Float64 => Cell::Float(c.as_primitive::<Float64Type>().value(row)),
            _ => Cell::Null, // DataType::Null: a column that is null in every row (pyarrow writes it so)
        }
    }

    /// The value of the column `name` of the road `row`; None: no such column.
    pub fn get(&self, row: usize, name: &str) -> Option<Cell<'_>> {
        self.col(name).map(|c| self.cell(c, row))
    }

    /// Give the column `from` the name `to`, in its place (a column `to` that is there goes away). False: no column `from`.
    pub fn rename(&mut self, from: &str, to: &str) -> bool {
        let Some(i) = self.col(from) else { return false };
        if let Some(j) = self.col(to).filter(|&j| j != i) {
            self.names.remove(j);
            self.cols.remove(j);
            return self.rename(from, to);
        }
        self.names[i] = to.to_string();
        true
    }

    /// Set some cells of the column `col` (`cells`: each row and its new value; null is Value::Null), as `set_values` sets a column.
    pub fn set_cells(&mut self, col: usize, cells: &[(usize, Value)]) -> Result<(), crate::Error> {
        let name = self.names[col].clone();
        let mut vals: Vec<Value> = (0..self.len()).map(|r| self.cell(col, r).to_value()).collect();
        for (r, v) in cells {
            *vals.get_mut(*r).ok_or_else(|| crate::Error::Column { column: name.clone(), message: format!("no road {r}") })? = v.clone();
        }
        self.set_values(&name, vals)
    }

    /// Set the column `name` (in its place, else as the last column) to `values`, one for each road: integers when every value is a whole
    /// number or null, else numbers, or texts. A boolean or a mix of texts and numbers is an error.
    pub fn set_values(&mut self, name: &str, values: Vec<Value>) -> Result<(), crate::Error> {
        if values.len() != self.len() {
            return Err(crate::Error::Column { column: name.into(), message: format!("{} values, the roads are {}", values.len(), self.len()) });
        }
        let given = || values.iter().filter(|v| !v.is_null());
        let a: ArrayRef = if given().all(|v| v.is_i64()) {
            Arc::new(values.iter().map(Value::as_i64).collect::<Int64Array>())
        } else if given().all(Value::is_number) {
            Arc::new(values.iter().map(Value::as_f64).collect::<arrow_array::Float64Array>())
        } else if given().all(Value::is_string) {
            Arc::new(values.iter().map(Value::as_str).collect::<arrow_array::StringArray>())
        } else {
            return Err(crate::Error::Column { column: name.into(), message: "values of more than one kind (texts and numbers), or booleans".into() });
        };
        match self.col(name) {
            Some(i) => self.cols[i] = a,
            None => {
                self.names.push(name.to_string());
                self.cols.push(a);
            }
        }
        Ok(())
    }

    /// Set the column `name` to integers: in its place when it is there, else as the last column.
    pub fn set_ints(&mut self, name: &str, values: Vec<i64>) {
        assert_eq!(values.len(), self.len(), "a column of {name} for each road");
        let a: ArrayRef = Arc::new(Int64Array::from(values));
        match self.col(name) {
            Some(i) => self.cols[i] = a,
            None => {
                self.names.push(name.to_string());
                self.cols.push(a);
            }
        }
    }

}

#[cfg(test)]
mod tests {
    use super::*;
    use arrow_array::{BooleanArray, Float64Array, StringArray};

    fn table() -> RoadTable {
        let mut lines = Lines::default();
        lines.push(Some(&[[1.0, 2.0], [3.0, 4.0]]));
        lines.push(None);
        let cols: Vec<ArrayRef> = vec![Arc::new(StringArray::from(vec![Some("primary"), None])),
                                       Arc::new(Int64Array::from(vec![1i64 << 60, 7])),
                                       Arc::new(Float64Array::from(vec![f64::NAN, 2.5])),
                                       Arc::new(BooleanArray::from(vec![true, false]))];
        RoadTable::new(["highway", "edge_id", "w", "bridge"].map(String::from).to_vec(), cols, lines).unwrap()
    }

    #[test]
    fn a_column_that_the_model_does_not_take_is_an_error_with_its_name() {
        let lines = || { let mut l = Lines::default(); l.push(None); l };
        let date: ArrayRef = Arc::new(arrow_array::Date32Array::from(vec![1]));
        let e = RoadTable::new(vec!["day".into()], vec![date], lines()).unwrap_err();
        assert!(matches!(&e, crate::Error::Column { column, .. } if column == "day"), "{e}");
        let two: ArrayRef = Arc::new(Int64Array::from(vec![1i64, 2]));
        assert_eq!(RoadTable::new(vec!["n".into()], vec![two], lines()).unwrap_err().to_string(), "column n: 2 rows, the roads have 1");
    }

    #[test]
    fn the_cells_are_the_json_values_of_the_reader() {
        let mut t = table();
        assert_eq!(t.line(0), Some(&[[1.0, 2.0], [3.0, 4.0]][..]));
        assert_eq!(t.line(1), None);
        assert_eq!(t.get(0, "highway").and_then(Cell::as_str), Some("primary"));
        assert!(t.get(1, "highway").unwrap().is_null() && t.get(0, "nothing").is_none());
        assert_eq!(t.get(0, "w").unwrap().to_value(), Value::Null, "NaN is null");
        let text = |c: Cell| serde_json::to_string(&c).unwrap();
        // N1: the model keeps an integer past 2**53 - 1 (the Parquet files write it as one); its JSON form is text (JavaScript)
        assert_eq!((text(t.cell(1, 0)), text(t.cell(2, 1)), text(t.cell(3, 0))), ("\"1152921504606846976\"".into(), "2.5".into(), "true".into()));
        assert_eq!(t.cell(1, 0).to_value(), Value::from(1152921504606846976_i64));
        assert_eq!(serde_json::to_string(&crate::table::JsSafe(&serde_json::json!([1152921504606846976_i64, 7]))).unwrap(), "[\"1152921504606846976\",7]");
        assert_eq!(text(t.cell(1, 1)), "7");
        assert!(t.rename("w", "highway") && t.names() == ["edge_id", "highway", "bridge"]);
        t.set_ints("lvl", vec![1, 2]);
        t.set_ints("edge_id", vec![3, 4]);
        assert_eq!(t.names(), ["edge_id", "highway", "bridge", "lvl"]);
        assert_eq!(t.get(1, "edge_id").and_then(Cell::as_i64), Some(4));
    }
}
