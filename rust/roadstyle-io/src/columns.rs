//! The one Parquet writer: typed columns as Parquet, a batch at a time; with a WKB column, GeoParquet (the `geo` metadata of
//! GeoParquet 1.1). Text, whole numbers, numbers, booleans, lists of them (native Parquet lists: GeoPandas and DuckDB read them as
//! lists) and the WKB geometry. `write::parquet_to` (rows of JSON values or Arrow cells) and a level area's roads.parquet use it.

use crate::Error;
use arrow_array::builder::{BinaryBuilder, BooleanBuilder, Float64Builder, Int64Builder, ListBuilder, StringBuilder};
use arrow_array::{ArrayRef, RecordBatch};
use arrow_schema::{DataType, Field, Schema};
use parquet::arrow::ArrowWriter;
use parquet::file::properties::WriterProperties;
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;

/// One column of a batch, a value (or null) for each row.
pub enum Column {
    Text(Vec<Option<String>>),
    Int(Vec<Option<i64>>),
    Float(Vec<Option<f64>>),
    Bool(Vec<Option<bool>>),
    TextList(Vec<Vec<Option<String>>>),
    IntList(Vec<Vec<Option<i64>>>),
    FloatList(Vec<Vec<Option<f64>>>),
    BoolList(Vec<Vec<Option<bool>>>),
    /// geometries as WKB: the GeoParquet geometry (no CRS: OGC:CRS84, longitude and latitude)
    Wkb(Vec<Option<Vec<u8>>>),
    /// a column with no value in any row, of this many rows
    Null(usize),
}

impl Column {
    /// The column's Arrow type (a list's items are nullable, as ListBuilder makes them).
    pub fn data_type(&self) -> DataType {
        let list = |t: DataType| DataType::List(Arc::new(Field::new("item", t, true)));
        match self {
            Column::Text(_) => DataType::Utf8,
            Column::Int(_) => DataType::Int64,
            Column::Float(_) => DataType::Float64,
            Column::Bool(_) => DataType::Boolean,
            Column::TextList(_) => list(DataType::Utf8),
            Column::IntList(_) => list(DataType::Int64),
            Column::FloatList(_) => list(DataType::Float64),
            Column::BoolList(_) => list(DataType::Boolean),
            Column::Wkb(_) => DataType::Binary,
            Column::Null(_) => DataType::Null,
        }
    }

    fn array(self) -> ArrayRef {
        macro_rules! list {
            ($v:expr, $b:expr) => {{
                let mut b = ListBuilder::new($b);
                for row in $v {
                    for x in row {
                        b.values().append_option(x);
                    }
                    b.append(true);
                }
                Arc::new(b.finish()) as ArrayRef
            }};
        }
        match self {
            Column::Text(v) => Arc::new(v.into_iter().collect::<arrow_array::StringArray>()),
            Column::Int(v) => Arc::new(v.into_iter().collect::<arrow_array::Int64Array>()),
            Column::Float(v) => Arc::new(v.into_iter().collect::<arrow_array::Float64Array>()),
            Column::Bool(v) => Arc::new(v.into_iter().collect::<arrow_array::BooleanArray>()),
            Column::TextList(v) => list!(v, StringBuilder::new()),
            Column::IntList(v) => list!(v, Int64Builder::new()),
            Column::FloatList(v) => list!(v, Float64Builder::new()),
            Column::BoolList(v) => list!(v, BooleanBuilder::new()),
            Column::Wkb(v) => {
                let mut b = BinaryBuilder::new();
                v.iter().for_each(|x| b.append_option(x.as_deref()));
                Arc::new(b.finish())
            }
            Column::Null(n) => Arc::new(arrow_array::NullArray::new(n)),
        }
    }
}

/// A Parquet file written a batch of columns at a time, to `W`.
pub struct Writer<W: std::io::Write + Send> {
    w: ArrowWriter<W>,
    schema: Arc<Schema>,
}

impl<W: std::io::Write + Send> Writer<W> {
    /// The file of the columns `fields` (their order is the batches'); `geometry`: GeoParquet, the name of its WKB column and the
    /// geometry types in it.
    pub fn new(w: W, fields: Vec<Field>, geometry: Option<(&str, Vec<String>)>) -> Result<Self, Error> {
        let mut meta = HashMap::new();
        if let Some((g, types)) = geometry {
            let geo = serde_json::json!({"version": "1.1.0", "primary_column": g, "columns": {g: {"encoding": "WKB", "geometry_types": types}}});
            meta.insert("geo".to_string(), geo.to_string());
        }
        let schema = Arc::new(Schema::new_with_metadata(fields, meta));
        let props = WriterProperties::builder().set_compression(parquet::basic::Compression::SNAPPY).build();
        let w = ArrowWriter::try_new(w, schema.clone(), Some(props)).map_err(|e| Error::Write(e.to_string()))?;
        Ok(Writer { w, schema })
    }

    /// One batch: a column for each field, in the fields' order.
    pub fn write(&mut self, cols: Vec<Column>) -> Result<(), Error> {
        let batch = RecordBatch::try_new(self.schema.clone(), cols.into_iter().map(Column::array).collect()).map_err(|e| Error::Write(e.to_string()))?;
        self.w.write(&batch).map_err(|e| Error::Write(e.to_string()))
    }

    pub fn finish(self) -> Result<W, Error> {
        self.w.into_inner().map_err(|e| Error::Write(e.to_string()))
    }
}

/// The columns as one Parquet file (one batch), in their order; a `Wkb` column makes it GeoParquet (its primary column, lines).
pub fn write_columns(cols: Vec<(String, Column)>) -> Result<Vec<u8>, Error> {
    let fields: Vec<Field> = cols.iter().map(|(n, c)| Field::new(n, c.data_type(), true)).collect();
    let geo = cols.iter().find(|(_, c)| matches!(c, Column::Wkb(_))).map(|(n, _)| (n.as_str(), vec!["LineString".to_string()]));
    let mut w = Writer::new(Vec::new(), fields, geo)?;
    w.write(cols.into_iter().map(|(_, c)| c).collect())?;
    w.finish()
}

/// A line as WKB (little endian, 2D).
pub fn line_wkb(c: &[[f64; 2]]) -> Vec<u8> {
    let mut out = Vec::with_capacity(9 + 16 * c.len());
    out.push(1);
    out.extend_from_slice(&2u32.to_le_bytes());
    out.extend_from_slice(&(c.len() as u32).to_le_bytes());
    c.iter().for_each(|q| q.iter().for_each(|x| out.extend_from_slice(&x.to_le_bytes())));
    out
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
        "LineString" => return Some(line_wkb(&pts(c)?)),
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lists_stay_lists() {
        let bytes = write_columns(vec![
            ("road".into(), Column::Text(vec![Some("7".into())])),
            ("edges".into(), Column::TextList(vec![vec![Some("7".into()), Some("9".into())]])),
            ("edges_oneway".into(), Column::BoolList(vec![vec![Some(true), None]])),
        ]).unwrap();
        let rows = crate::read::read_table(bytes, "geometry").unwrap();
        assert_eq!(rows[0].cols["edges"], serde_json::json!(["7", "9"]));
        assert_eq!(rows[0].cols["edges_oneway"], serde_json::json!([true, null]));
    }

    #[test]
    fn the_rows_writer_writes_native_lists() {
        use crate::write::{parquet, Row, Val};
        let row = |e: Value, m: Value| Row { id: None, props: vec![("edges".into(), Val::Json(e)), ("mixed".into(), Val::Json(m))], geometry: None };
        let bytes = parquet(|| vec![row(serde_json::json!([3, 4]), serde_json::json!(1)), row(serde_json::json!([5]), serde_json::json!("a"))].into_iter(), false).unwrap();
        let schema = parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder::try_new(bytes::Bytes::from(bytes.clone())).unwrap().schema().clone();
        assert!(matches!(schema.field_with_name("edges").unwrap().data_type(), DataType::List(_)), "a list is a native Parquet list");
        assert_eq!(schema.field_with_name("mixed").unwrap().metadata().get("roadstyle:json").map(String::as_str), Some("true"));
        let rows = crate::read::read_table(bytes, "geometry").unwrap();
        assert_eq!((rows[0].cols["edges"].clone(), rows[1].cols["edges"].clone()), (serde_json::json!([3, 4]), serde_json::json!([5])));
    }
}
