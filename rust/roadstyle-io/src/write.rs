//! The rows writer: a table of rows (the road table, or a source's features) as Parquet, through the one Parquet writer
//! (columns.rs); with a geometry column, GeoParquet. A column's type is that of its values: text, a boolean, an integer, a float, or a
//! list of one of them (a native Parquet list); a column whose values are of more than one type (or are objects) holds each value as its
//! JSON text, and its field has the metadata `roadstyle:json` = `true`, so the reader gives the same JSON values back. A missing value
//! and a null are the same (null); in a list column they are an empty list.

use crate::columns::Column;
use arrow_schema::{DataType, Field};
use roadstyle_model::Cell;
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;

/// The rows of one write.
const BATCH: usize = 8_192;

/// The name of the column of a GeoJSON feature's `id`.
pub const FID: &str = "__fid";

/// A value of a row (audit N5): a cell of the roads' Arrow columns, with no copy, or a JSON value (a piece's, a JSON source's).
#[derive(Clone, Debug)]
pub enum Val<'a> {
    Cell(Cell<'a>),
    Json(Value),
}

impl From<Value> for Val<'_> {
    fn from(v: Value) -> Self {
        Val::Json(v)
    }
}

impl Val<'_> {
    fn json(&self) -> Option<&Value> {
        match self {
            Val::Json(v) => Some(v),
            Val::Cell(Cell::Json(v)) => Some(v),
            _ => None,
        }
    }

    fn kind(&self) -> Kind {
        match self {
            Val::Cell(Cell::Null) => Kind::Null,
            Val::Cell(Cell::Bool(_)) => Kind::Bool,
            Val::Cell(Cell::Int(_)) => Kind::Int,
            Val::Cell(Cell::Float(f)) => if f.is_nan() { Kind::Null } else { Kind::Float },
            Val::Cell(Cell::Str(_)) => Kind::Text,
            v => kind(v.json().unwrap()),
        }
    }

    fn as_bool(&self) -> Option<bool> {
        match self { Val::Cell(Cell::Bool(b)) => Some(*b), v => v.json().and_then(Value::as_bool) }
    }

    fn as_i64(&self) -> Option<i64> {
        match self { Val::Cell(Cell::Int(i)) => Some(*i), v => v.json().and_then(Value::as_i64) }
    }

    fn as_f64(&self) -> Option<f64> {
        match self { Val::Cell(Cell::Float(f)) => Some(*f).filter(|f| !f.is_nan()), v => v.json().and_then(Value::as_f64) }
    }

    fn as_str(&self) -> Option<&str> {
        match self { Val::Cell(Cell::Str(s)) => Some(s), v => v.json().and_then(Value::as_str) }
    }

    /// The JSON text of a value in a column of mixed values (the value itself, not its JSON form for JavaScript).
    fn text(&self) -> String {
        match self { Val::Cell(c) => c.to_value().to_string(), Val::Json(v) => v.to_string() }
    }

    fn is_null(&self) -> bool {
        self.kind() == Kind::Null
    }
}

/// A row's geometry: a road's or a piece's line (written as WKB with no copy), or a GeoJSON geometry.
#[derive(Clone, Debug)]
pub enum Geometry<'a> {
    Line(&'a [[f64; 2]]),
    Json(std::borrow::Cow<'a, Value>),
}

impl From<Value> for Geometry<'_> {
    fn from(v: Value) -> Self {
        Geometry::Json(std::borrow::Cow::Owned(v))
    }
}

impl Geometry<'_> {
    fn kind(&self) -> Option<&str> {
        match self { Geometry::Line(_) => Some("LineString"), Geometry::Json(g) => g["type"].as_str() }
    }

    fn wkb(&self) -> Option<Vec<u8>> {
        match self { Geometry::Line(c) => Some(crate::columns::line_wkb(c)), Geometry::Json(g) => crate::columns::wkb(g) }
    }
}

/// One row: its feature id (a GeoJSON `id`), its properties in their order, and its geometry (None: no geometry column).
#[derive(Clone, Debug)]
pub struct Row<'a> {
    pub id: Option<i64>,
    pub props: Vec<(std::borrow::Cow<'a, str>, Val<'a>)>,
    pub geometry: Option<Geometry<'a>>,
}

/// The kind of a column: a scalar kind, a list of one scalar kind (a native Parquet list), or JSON text (values of more than one kind, or
/// objects: `roadstyle:json`).
#[derive(Clone, Copy, PartialEq, Debug)]
enum Kind {
    Null,
    Bool,
    Int,
    Float,
    Text,
    List(Item),
    Json,
}

/// The kind of a list's items.
#[derive(Clone, Copy, PartialEq, Debug)]
enum Item {
    Null,
    Bool,
    Int,
    Float,
    Text,
}

fn scalar(v: &Value) -> Option<Item> {
    Some(match v {
        Value::Null => Item::Null,
        Value::Bool(_) => Item::Bool,
        Value::Number(n) if n.is_i64() => Item::Int,
        Value::Number(n) if n.is_f64() => Item::Float,
        Value::String(_) => Item::Text,
        _ => return None,
    })
}

fn merge_item(a: Item, b: Item) -> Option<Item> {
    match (a, b) {
        (Item::Null, k) | (k, Item::Null) => Some(k),
        (x, y) if x == y => Some(x),
        _ => None,
    }
}

fn kind(v: &Value) -> Kind {
    match v {
        Value::Array(a) => a.iter().try_fold(Item::Null, |k, x| merge_item(k, scalar(x)?)).map_or(Kind::Json, Kind::List),
        v => match scalar(v) {
            Some(Item::Null) => Kind::Null,
            Some(Item::Bool) => Kind::Bool,
            Some(Item::Int) => Kind::Int,
            Some(Item::Float) => Kind::Float,
            Some(Item::Text) => Kind::Text,
            None => Kind::Json,
        },
    }
}

fn merge(a: Kind, b: Kind) -> Kind {
    match (a, b) {
        (Kind::Null, k) | (k, Kind::Null) => k,
        (Kind::List(x), Kind::List(y)) => merge_item(x, y).map_or(Kind::Json, Kind::List),
        (x, y) if x == y => x,
        _ => Kind::Json,
    }
}

/// The rows as Parquet, in memory (`parquet_to`).
pub fn parquet<'a, I: Iterator<Item = Row<'a>>>(rows: impl Fn() -> I, geometry: bool) -> Result<Vec<u8>, String> {
    parquet_to(Vec::new(), rows, geometry)
}

/// The rows as Parquet, written to `w` a batch at a time: `rows()` gives them again for each pass (the types, then the batches).
/// `geometry`: GeoParquet. Gives `w` back.
pub fn parquet_to<'a, W: std::io::Write + Send, I: Iterator<Item = Row<'a>>>(w: W, rows: impl Fn() -> I, geometry: bool) -> Result<W, String> {
    let (mut names, mut kinds, mut at): (Vec<String>, Vec<Kind>, HashMap<String, usize>) = (Vec::new(), Vec::new(), HashMap::new());
    let (mut ids, mut types) = (false, std::collections::BTreeSet::new());
    for r in rows() {
        ids |= r.id.is_some();
        if let Some(t) = r.geometry.as_ref().and_then(Geometry::kind) {
            types.insert(t.to_string());
        }
        for (k, v) in &r.props {
            let i = *at.entry(k.to_string()).or_insert_with(|| {
                names.push(k.to_string());
                kinds.push(Kind::Null);
                names.len() - 1
            });
            kinds[i] = merge(kinds[i], v.kind());
        }
    }
    let list = |t: DataType| DataType::List(Arc::new(Field::new("item", t, true)));
    let mut fields: Vec<Field> = Vec::new();
    if ids {
        fields.push(Field::new(FID, DataType::Int64, true));
    }
    for (n, k) in names.iter().zip(&kinds) {
        let t = match k {
            Kind::Bool => DataType::Boolean,
            Kind::Int => DataType::Int64,
            Kind::Float => DataType::Float64,
            Kind::Null => DataType::Null,
            Kind::Text | Kind::Json => DataType::Utf8,
            Kind::List(Item::Text | Item::Null) => list(DataType::Utf8),
            Kind::List(Item::Bool) => list(DataType::Boolean),
            Kind::List(Item::Int) => list(DataType::Int64),
            Kind::List(Item::Float) => list(DataType::Float64),
        };
        let f = Field::new(n, t, true);
        fields.push(if *k == Kind::Json { f.with_metadata(HashMap::from([("roadstyle:json".to_string(), "true".to_string())])) } else { f });
    }
    if geometry {
        fields.push(Field::new("geometry", DataType::Binary, true));
    }
    let mut w = crate::columns::Writer::new(w, fields, geometry.then(|| ("geometry", types.into_iter().collect())))?;
    let mut it = rows().peekable();
    while it.peek().is_some() {
        let chunk: Vec<Row> = it.by_ref().take(BATCH).collect();
        let mut cols: Vec<Column> = Vec::new();
        if ids {
            cols.push(Column::Int(chunk.iter().map(|r| r.id).collect()));
        }
        let index: Vec<HashMap<&str, &Val>> = chunk.iter().map(|r| r.props.iter().map(|(k, v)| (k.as_ref(), v)).collect()).collect();
        for (n, k) in names.iter().zip(&kinds) {
            let get = |i: usize| index[i].get(n.as_str()).copied().filter(|v| !v.is_null());
            // a list column's rows (a missing value: an empty list)
            let items = || -> Vec<Vec<Value>> {
                (0..chunk.len()).map(|i| get(i).and_then(Val::json).and_then(Value::as_array).cloned().unwrap_or_default()).collect()
            };
            cols.push(match k {
                Kind::Bool => Column::Bool((0..chunk.len()).map(|i| get(i).and_then(Val::as_bool)).collect()),
                Kind::Int => Column::Int((0..chunk.len()).map(|i| get(i).and_then(Val::as_i64)).collect()),
                Kind::Float => Column::Float((0..chunk.len()).map(|i| get(i).and_then(Val::as_f64)).collect()),
                Kind::Null => Column::Null(chunk.len()),
                Kind::Text => Column::Text((0..chunk.len()).map(|i| get(i).and_then(Val::as_str).map(String::from)).collect()),
                Kind::Json => Column::Text((0..chunk.len()).map(|i| get(i).map(Val::text)).collect()),
                Kind::List(Item::Bool) => Column::BoolList(items().iter().map(|r| r.iter().map(Value::as_bool).collect()).collect()),
                Kind::List(Item::Int) => Column::IntList(items().iter().map(|r| r.iter().map(Value::as_i64).collect()).collect()),
                Kind::List(Item::Float) => Column::FloatList(items().iter().map(|r| r.iter().map(Value::as_f64).collect()).collect()),
                Kind::List(Item::Text | Item::Null) => Column::TextList(items().iter().map(|r| r.iter().map(|x| x.as_str().map(String::from)).collect()).collect()),
            });
        }
        if geometry {
            cols.push(Column::Wkb(chunk.iter().map(|r| r.geometry.as_ref().and_then(Geometry::wkb)).collect()));
        }
        w.write(cols)?;
    }
    w.finish()
}
