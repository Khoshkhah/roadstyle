//! The writers: a table of rows (the road table, or a source's features) as Parquet; with a geometry column, GeoParquet (WKB in
//! `geometry`, the `geo` metadata of GeoParquet 1.1). A column's type is that of its values: text, a boolean, an integer, a float; a
//! column whose values are of more than one type (or are lists or objects) holds each value as its JSON text, and its field has the
//! metadata `roadstyle:json` = `true`, so the reader gives the same JSON values back. A missing value and a null are the same (null).

use arrow_array::builder::{BinaryBuilder, BooleanBuilder, Float64Builder, Int64Builder, StringBuilder};
use arrow_array::{ArrayRef, RecordBatch};
use arrow_schema::{DataType, Field, Schema};
use parquet::arrow::ArrowWriter;
use parquet::file::properties::WriterProperties;
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;

/// The rows of one write.
const BATCH: usize = 8_192;

/// The name of the column of a GeoJSON feature's `id`.
pub const FID: &str = "__fid";

/// One row: its feature id (a GeoJSON `id`), its properties in their order, and its geometry (GeoJSON; None: no geometry column).
pub struct Row {
    pub id: Option<i64>,
    pub props: Vec<(String, Value)>,
    pub geometry: Option<Value>,
}

#[derive(Clone, Copy, PartialEq, Debug)]
enum Kind {
    Null,
    Bool,
    Int,
    Float,
    Text,
    Json,
}

fn kind(v: &Value) -> Kind {
    match v {
        Value::Null => Kind::Null,
        Value::Bool(_) => Kind::Bool,
        Value::Number(n) if n.is_i64() => Kind::Int,
        Value::Number(n) if n.is_f64() => Kind::Float,
        Value::String(_) => Kind::Text,
        _ => Kind::Json,
    }
}

fn merge(a: Kind, b: Kind) -> Kind {
    match (a, b) {
        (Kind::Null, k) | (k, Kind::Null) => k,
        (x, y) if x == y => x,
        _ => Kind::Json,
    }
}

/// The rows as Parquet, in memory (`parquet_to`).
pub fn parquet<I: Iterator<Item = Row>>(rows: impl Fn() -> I, geometry: bool) -> Result<Vec<u8>, String> {
    parquet_to(Vec::new(), rows, geometry)
}

/// The rows as Parquet, written to `w` a batch at a time: `rows()` gives them again for each pass (the types, then the batches).
/// `geometry`: GeoParquet. Gives `w` back.
pub fn parquet_to<W: std::io::Write + Send, I: Iterator<Item = Row>>(w: W, rows: impl Fn() -> I, geometry: bool) -> Result<W, String> {
    let (mut names, mut kinds, mut at): (Vec<String>, Vec<Kind>, HashMap<String, usize>) = (Vec::new(), Vec::new(), HashMap::new());
    let (mut ids, mut types) = (false, std::collections::BTreeSet::new());
    for r in rows() {
        ids |= r.id.is_some();
        if let Some(t) = r.geometry.as_ref().and_then(|g| g["type"].as_str()) {
            types.insert(t.to_string());
        }
        for (k, v) in &r.props {
            let i = *at.entry(k.clone()).or_insert_with(|| {
                names.push(k.clone());
                kinds.push(Kind::Null);
                names.len() - 1
            });
            kinds[i] = merge(kinds[i], kind(v));
        }
    }
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
        };
        let f = Field::new(n, t, true);
        fields.push(if *k == Kind::Json { f.with_metadata(HashMap::from([("roadstyle:json".to_string(), "true".to_string())])) } else { f });
    }
    if geometry {
        fields.push(Field::new("geometry", DataType::Binary, true));
    }
    let mut meta = HashMap::new();
    if geometry {
        let geo = serde_json::json!({"version": "1.1.0", "primary_column": "geometry",
                                     "columns": {"geometry": {"encoding": "WKB", "geometry_types": types}}});
        meta.insert("geo".to_string(), geo.to_string());
    }
    let schema = Arc::new(Schema::new_with_metadata(fields, meta));
    let props = WriterProperties::builder().set_compression(parquet::basic::Compression::SNAPPY).build();
    let mut w = ArrowWriter::try_new(w, schema.clone(), Some(props)).map_err(|e| e.to_string())?;
    let mut it = rows().peekable();
    while it.peek().is_some() {
        let chunk: Vec<Row> = it.by_ref().take(BATCH).collect();
        let mut cols: Vec<ArrayRef> = Vec::new();
        if ids {
            let mut b = Int64Builder::new();
            chunk.iter().for_each(|r| b.append_option(r.id));
            cols.push(Arc::new(b.finish()));
        }
        let index: Vec<HashMap<&str, &Value>> = chunk.iter().map(|r| r.props.iter().map(|(k, v)| (k.as_str(), v)).collect()).collect();
        for (n, k) in names.iter().zip(&kinds) {
            let get = |i: usize| index[i].get(n.as_str()).copied().filter(|v| !v.is_null());
            let a: ArrayRef = match k {
                Kind::Bool => {
                    let mut b = BooleanBuilder::new();
                    (0..chunk.len()).for_each(|i| b.append_option(get(i).and_then(Value::as_bool)));
                    Arc::new(b.finish())
                }
                Kind::Int => {
                    let mut b = Int64Builder::new();
                    (0..chunk.len()).for_each(|i| b.append_option(get(i).and_then(Value::as_i64)));
                    Arc::new(b.finish())
                }
                Kind::Float => {
                    let mut b = Float64Builder::new();
                    (0..chunk.len()).for_each(|i| b.append_option(get(i).and_then(Value::as_f64)));
                    Arc::new(b.finish())
                }
                Kind::Null => Arc::new(arrow_array::NullArray::new(chunk.len())),
                Kind::Text => {
                    let mut b = StringBuilder::new();
                    (0..chunk.len()).for_each(|i| b.append_option(get(i).and_then(Value::as_str)));
                    Arc::new(b.finish())
                }
                Kind::Json => {
                    let mut b = StringBuilder::new();
                    (0..chunk.len()).for_each(|i| b.append_option(get(i).map(Value::to_string)));
                    Arc::new(b.finish())
                }
            };
            cols.push(a);
        }
        if geometry {
            let mut b = BinaryBuilder::new();
            for r in &chunk {
                b.append_option(r.geometry.as_ref().and_then(wkb));
            }
            cols.push(Arc::new(b.finish()));
        }
        w.write(&RecordBatch::try_new(schema.clone(), cols).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    }
    w.into_inner().map_err(|e| e.to_string())
}

/// A GeoJSON geometry as WKB (little endian, 2D); None for a geometry that it does not read.
pub fn wkb(g: &Value) -> Option<Vec<u8>> {
    fn pts(v: &Value) -> Option<Vec<[f64; 2]>> {
        v.as_array()?.iter().map(|p| Some([p.get(0)?.as_f64()?, p.get(1)?.as_f64()?])).collect()
    }
    fn head(out: &mut Vec<u8>, t: u32) {
        out.push(1);
        out.extend_from_slice(&t.to_le_bytes());
    }
    fn line(out: &mut Vec<u8>, p: &[[f64; 2]]) {
        out.extend_from_slice(&(p.len() as u32).to_le_bytes());
        p.iter().for_each(|q| q.iter().for_each(|x| out.extend_from_slice(&x.to_le_bytes())));
    }
    fn rings(out: &mut Vec<u8>, v: &Value) -> Option<()> {
        let rs = v.as_array()?;
        out.extend_from_slice(&(rs.len() as u32).to_le_bytes());
        for r in rs {
            line(out, &pts(r)?);
        }
        Some(())
    }
    let c = &g["coordinates"];
    let mut out = Vec::new();
    match g["type"].as_str()? {
        "Point" => {
            head(&mut out, 1);
            pts(&Value::Array(vec![c.clone()]))?[0].iter().for_each(|x| out.extend_from_slice(&x.to_le_bytes()));
        }
        "LineString" => {
            head(&mut out, 2);
            line(&mut out, &pts(c)?);
        }
        "Polygon" => {
            head(&mut out, 3);
            rings(&mut out, c)?;
        }
        t @ ("MultiPoint" | "MultiLineString" | "MultiPolygon") => {
            let (outer, inner) = match t { "MultiPoint" => (4, "Point"), "MultiLineString" => (5, "LineString"), _ => (6, "Polygon") };
            let parts = c.as_array()?;
            head(&mut out, outer);
            out.extend_from_slice(&(parts.len() as u32).to_le_bytes());
            for p in parts {
                out.extend(wkb(&serde_json::json!({"type": inner, "coordinates": p}))?);
            }
        }
        _ => return None,
    }
    Some(out)
}
