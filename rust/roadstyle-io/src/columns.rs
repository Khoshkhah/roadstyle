//! A table of typed columns as GeoParquet (a level area's roads.parquet): text, whole numbers, numbers, booleans, lists of them, and the
//! WKB column `geometry`. Lists stay Parquet lists (GeoPandas reads them as lists), not the JSON text of `write::parquet`.

use arrow_array::builder::{BinaryBuilder, BooleanBuilder, Float64Builder, Int64Builder, ListBuilder, StringBuilder};
use arrow_array::{ArrayRef, RecordBatch};
use arrow_schema::{Field, Schema};
use parquet::arrow::ArrowWriter;
use parquet::file::properties::WriterProperties;
use std::collections::HashMap;
use std::sync::Arc;

/// One column, a value (or null) for each row.
pub enum Column {
    Text(Vec<Option<String>>),
    Int(Vec<Option<i64>>),
    Float(Vec<Option<f64>>),
    Bool(Vec<Option<bool>>),
    TextList(Vec<Vec<Option<String>>>),
    IntList(Vec<Vec<Option<i64>>>),
    FloatList(Vec<Vec<Option<f64>>>),
    BoolList(Vec<Vec<Option<bool>>>),
    /// LineStrings as WKB: the GeoParquet geometry (no CRS: OGC:CRS84, longitude and latitude)
    Wkb(Vec<Option<Vec<u8>>>),
}

/// The columns as one Parquet file, in their order; a `Wkb` column makes it GeoParquet (its primary column).
pub fn write_columns(cols: Vec<(String, Column)>) -> Result<Vec<u8>, String> {
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
    let mut geo = None;
    let arrays: Vec<(String, ArrayRef)> = cols.into_iter().map(|(name, c)| {
        let a: ArrayRef = match c {
            Column::Text(v) => Arc::new(v.into_iter().collect::<arrow_array::StringArray>()),
            Column::Int(v) => Arc::new(v.into_iter().collect::<arrow_array::Int64Array>()),
            Column::Float(v) => Arc::new(v.into_iter().collect::<arrow_array::Float64Array>()),
            Column::Bool(v) => Arc::new(v.into_iter().collect::<arrow_array::BooleanArray>()),
            Column::TextList(v) => list!(v, StringBuilder::new()),
            Column::IntList(v) => list!(v, Int64Builder::new()),
            Column::FloatList(v) => list!(v, Float64Builder::new()),
            Column::BoolList(v) => list!(v, BooleanBuilder::new()),
            Column::Wkb(v) => {
                geo = Some(name.clone());
                let mut b = BinaryBuilder::new();
                v.iter().for_each(|x| b.append_option(x.as_deref()));
                Arc::new(b.finish())
            }
        };
        (name, a)
    }).collect();
    let fields: Vec<Field> = arrays.iter().map(|(n, a)| Field::new(n, a.data_type().clone(), true)).collect();
    let mut meta = HashMap::new();
    if let Some(g) = &geo {
        let v = serde_json::json!({"version": "1.1.0", "primary_column": g, "columns": {g: {"encoding": "WKB", "geometry_types": ["LineString"]}}});
        meta.insert("geo".to_string(), v.to_string());
    }
    let schema = Arc::new(Schema::new_with_metadata(fields, meta));
    let batch = RecordBatch::try_new(schema.clone(), arrays.into_iter().map(|(_, a)| a).collect()).map_err(|e| e.to_string())?;
    let props = WriterProperties::builder().set_compression(parquet::basic::Compression::SNAPPY).build();
    let mut w = ArrowWriter::try_new(Vec::new(), schema, Some(props)).map_err(|e| e.to_string())?;
    w.write(&batch).map_err(|e| e.to_string())?;
    w.into_inner().map_err(|e| e.to_string())
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
}
