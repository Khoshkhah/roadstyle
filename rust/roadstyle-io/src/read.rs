//! The roads from a GeoParquet file: every column an Arrow array of the table (as GeoPandas' GeoJSON writes its values), the
//! geometry a LineString from WKB.

use crate::Error;
use arrow_array::{cast::AsArray, types::*, Array, ArrayRef};
use arrow_schema::DataType;
use bytes::Bytes;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde_json::{Map, Value};

pub use roadstyle_model::{feature_table::FeatureTable, Lines, RoadTable, Row};

pub fn read_roads(data: Vec<u8>, geom_col: &str) -> Result<RoadTable, Error> {
    let mut lines = Lines::default();
    let (names, cols) = read_columns(data, geom_col, |g| {
        lines.push(g.and_then(wkb_line).as_deref());
        Ok(())
    })?;
    RoadTable::new(names, cols, lines).map_err(Error::Format)
}

/// The base map's (or any) features from a GeoParquet file: every column but the geometry an Arrow array, and the geometry of each row
/// (WKB: a point, a line, a polygon or a Multi type) in one coordinate buffer (roadstyle-model's FeatureTable; audit R10).
pub fn read_feature_table(data: Vec<u8>, geom_col: &str) -> Result<FeatureTable, Error> {
    let mut geoms = FeatureTable::geometries();
    let (names, cols) = read_columns(data, geom_col, |g| geoms.push_wkb(g).map_err(|e| Error::Format(format!("{geom_col}: {e}"))))?;
    FeatureTable::new(names, cols, geoms).map_err(Error::Format)
}

/// The columns of a Parquet file but `geom_col` (each one Arrow array of every row), and `geom` called with each row's geometry bytes
/// (None: no geometry column, or a null).
fn read_columns(data: Vec<u8>, geom_col: &str, mut geom: impl FnMut(Option<&[u8]>) -> Result<(), Error>)
                -> Result<(Vec<String>, Vec<ArrayRef>), Error> {
    let builder = ParquetRecordBatchReaderBuilder::try_new(Bytes::from(data)).map_err(|e| Error::Format(format!("not a Parquet file: {e}")))?;
    let schema = builder.schema().clone();
    let reader = builder.build().map_err(|e| Error::Format(format!("not a Parquet file: {e}")))?;
    let names: Vec<String> = schema.fields().iter().map(|f| f.name().clone()).filter(|n| n != geom_col).collect();
    let mut parts: Vec<Vec<ArrayRef>> = vec![Vec::new(); names.len()];
    for batch in reader {
        let batch = batch.map_err(|e| Error::Format(e.to_string()))?;
        let mut k = 0;
        for (field, col) in batch.schema().fields().iter().zip(batch.columns()) {
            if field.name() == geom_col {
                for r in 0..batch.num_rows() {
                    geom(binary(col, r))?;
                }
            } else {
                parts[k].push(col.clone());
                k += 1;
            }
        }
        if !schema.fields().iter().any(|f| f.name() == geom_col) {
            for _ in 0..batch.num_rows() {
                geom(None)?;
            }
        }
    }
    let cols = parts.into_iter().zip(&schema.fields().iter().filter(|f| f.name() != geom_col).collect::<Vec<_>>()).map(|(p, f)| {
        let refs: Vec<&dyn Array> = p.iter().map(|a| a.as_ref()).collect();
        if refs.is_empty() { Ok(arrow_array::new_empty_array(f.data_type())) } else { arrow_select::concat::concat(&refs).map_err(|e| Error::Format(e.to_string())) }
    }).collect::<Result<Vec<_>, Error>>()?;
    Ok((names, cols))
}

/// A GeoParquet file of lines only (its `geo` metadata names LineString alone, as stage 1's roads and pieces) as a `RoadTable` (audit
/// N5: the Arrow columns and the lines, no JSON per cell), with the names of its `roadstyle:json` columns (their text is JSON). None for
/// another file.
pub fn line_table(data: Vec<u8>) -> Result<Option<(RoadTable, std::collections::HashSet<String>)>, Error> {
    let builder = ParquetRecordBatchReaderBuilder::try_new(Bytes::from(data.clone())).map_err(|e| Error::Format(format!("not a Parquet file: {e}")))?;
    let schema = builder.schema().clone();
    let geo: Value = schema.metadata().get("geo").and_then(|g| serde_json::from_str(g).ok()).unwrap_or(Value::Null);
    // a list column (a native Parquet list) is not a RoadTable's: that file takes the JSON path
    if geo["columns"]["geometry"]["geometry_types"] != serde_json::json!(["LineString"])
        || schema.fields().iter().any(|f| matches!(f.data_type(), arrow_schema::DataType::List(_) | arrow_schema::DataType::LargeList(_))) {
        return Ok(None);
    }
    let json = schema.fields().iter().filter(|f| f.metadata().get("roadstyle:json").is_some_and(|v| v == "true")).map(|f| f.name().clone()).collect();
    Ok(Some((read_roads(data, "geometry")?, json)))
}

/// Any Parquet table as rows: the columns as properties, the binary column `blob` kept as its bytes.
pub fn read_table(data: Vec<u8>, blob: &str) -> Result<Vec<Row>, Error> {
    let reader = ParquetRecordBatchReaderBuilder::try_new(Bytes::from(data))
        .and_then(|b| b.build())
        .map_err(|e| Error::Format(format!("not a Parquet file: {e}")))?;
    let mut out = Vec::new();
    for batch in reader {
        let batch = batch.map_err(|e| Error::Format(e.to_string()))?;
        let schema = batch.schema();
        let start = out.len();
        out.extend((0..batch.num_rows()).map(|_| Row { cols: Map::new(), blob: None }));
        for (field, col) in schema.fields().iter().zip(batch.columns()) {
            for (r, row) in out[start..].iter_mut().enumerate() {
                if field.name() == blob {
                    row.blob = binary(col, r).map(<[u8]>::to_vec);
                } else {
                    row.cols.insert(field.name().clone(), value(col, r)?);
                }
            }
        }
    }
    Ok(out)
}

fn value(col: &ArrayRef, r: usize) -> Result<Value, Error> {
    if col.is_null(r) {
        return Ok(Value::Null);
    }
    Ok(match col.data_type() {
        DataType::Null => Value::Null, // a column that is null in every row (pyarrow writes it so)
        DataType::Utf8 => col.as_string::<i32>().value(r).into(),
        DataType::LargeUtf8 => col.as_string::<i64>().value(r).into(),
        DataType::Utf8View => col.as_string_view().value(r).into(),
        DataType::Boolean => col.as_boolean().value(r).into(),
        DataType::Int32 => col.as_primitive::<Int32Type>().value(r).into(),
        DataType::Int64 => col.as_primitive::<Int64Type>().value(r).into(),
        DataType::Float32 => float(col.as_primitive::<Float32Type>().value(r) as f64),
        DataType::Float64 => float(col.as_primitive::<Float64Type>().value(r)),
        // a list (a level area's edges and reversed): a JSON array
        DataType::List(_) => {
            let v = col.as_list::<i32>().value(r);
            Value::Array((0..v.len()).map(|i| value(&v, i)).collect::<Result<_, _>>()?)
        }
        DataType::LargeList(_) => {
            let v = col.as_list::<i64>().value(r);
            Value::Array((0..v.len()).map(|i| value(&v, i)).collect::<Result<_, _>>()?)
        }
        t => return Err(Error::Format(format!("column type {t} is not read"))),
    })
}

/// A float as GeoPandas writes it: NaN is null.
fn float(v: f64) -> Value {
    serde_json::Number::from_f64(v).map_or(Value::Null, Value::Number)
}

fn binary(col: &ArrayRef, r: usize) -> Option<&[u8]> {
    if col.is_null(r) {
        return None;
    }
    match col.data_type() {
        DataType::Binary => Some(col.as_binary::<i32>().value(r)),
        DataType::LargeBinary => Some(col.as_binary::<i64>().value(r)),
        DataType::BinaryView => Some(col.as_binary_view().value(r)),
        _ => None,
    }
}

/// The points of a 2D WKB LineString; None for any other geometry.
pub fn wkb_line(b: &[u8]) -> Option<Vec<[f64; 2]>> {
    let le = *b.first()? == 1;
    let u32_at = |i: usize| -> Option<u32> {
        let w: [u8; 4] = b.get(i..i + 4)?.try_into().ok()?;
        Some(if le { u32::from_le_bytes(w) } else { u32::from_be_bytes(w) })
    };
    let f64_at = |i: usize| -> Option<f64> {
        let w: [u8; 8] = b.get(i..i + 8)?.try_into().ok()?;
        Some(if le { f64::from_le_bytes(w) } else { f64::from_be_bytes(w) })
    };
    if u32_at(1)? != 2 {
        return None;
    }
    let n = u32_at(5)? as usize;
    (0..n).map(|k| Some([f64_at(9 + 16 * k)?, f64_at(17 + 16 * k)?])).collect()
}

/// A GeoParquet file (as `write::parquet` writes it, or any with a WKB `geometry` column) as a GeoJSON FeatureCollection: each row a
/// feature, `__fid` its id, the other columns its properties in their order (a null is left out; a `roadstyle:json` column's text is
/// its JSON value).
pub fn features(data: Vec<u8>) -> Result<Value, Error> {
    let reader = ParquetRecordBatchReaderBuilder::try_new(Bytes::from(data))
        .and_then(|b| b.build())
        .map_err(|e| Error::Format(format!("not a Parquet file: {e}")))?;
    let mut out = Vec::new();
    for batch in reader {
        let batch = batch.map_err(|e| Error::Format(e.to_string()))?;
        let schema = batch.schema();
        let start = out.len();
        out.extend((0..batch.num_rows()).map(|_| (Map::new(), Value::Null, Value::Null)));
        for (field, col) in schema.fields().iter().zip(batch.columns()) {
            let json = field.metadata().get("roadstyle:json").is_some_and(|v| v == "true");
            for (r, f) in out[start..].iter_mut().enumerate() {
                match field.name().as_str() {
                    "geometry" => f.2 = binary(col, r).and_then(wkb_geometry).unwrap_or(Value::Null),
                    crate::write::FID => f.1 = value(col, r)?,
                    name => {
                        let v = value(col, r)?;
                        let v = match v { Value::String(s) if json => serde_json::from_str(&s).map_err(|e| Error::Data(format!("{name}: {e}")))?, v => v };
                        if !v.is_null() {
                            f.0.insert(name.to_string(), v);
                        }
                    }
                }
            }
        }
    }
    let features: Vec<Value> = out.into_iter().map(|(p, id, g)| {
        let mut f = Map::new();
        f.insert("type".into(), "Feature".into());
        if !id.is_null() {
            f.insert("id".into(), id);
        }
        f.insert("properties".into(), Value::Object(p));
        f.insert("geometry".into(), g);
        Value::Object(f)
    }).collect();
    Ok(serde_json::json!({"type": "FeatureCollection", "features": features}))
}

/// A 2D WKB geometry as GeoJSON (Point, LineString, Polygon and their Multi kinds); None for another.
pub(crate) fn wkb_geometry(b: &[u8]) -> Option<Value> {
    fn at(b: &[u8], i: &mut usize, le: bool) -> Option<u32> {
        let w: [u8; 4] = b.get(*i..*i + 4)?.try_into().ok()?;
        *i += 4;
        Some(if le { u32::from_le_bytes(w) } else { u32::from_be_bytes(w) })
    }
    fn f(b: &[u8], i: &mut usize, le: bool) -> Option<f64> {
        let w: [u8; 8] = b.get(*i..*i + 8)?.try_into().ok()?;
        *i += 8;
        Some(if le { f64::from_le_bytes(w) } else { f64::from_be_bytes(w) })
    }
    fn pt(b: &[u8], i: &mut usize, le: bool) -> Option<Value> {
        Some(serde_json::json!([f(b, i, le)?, f(b, i, le)?]))
    }
    fn pts(b: &[u8], i: &mut usize, le: bool) -> Option<Value> {
        let n = at(b, i, le)?;
        (0..n).map(|_| pt(b, i, le)).collect::<Option<Vec<_>>>().map(Value::Array)
    }
    fn one(b: &[u8], i: &mut usize) -> Option<(&'static str, Value)> {
        let le = *b.get(*i)? == 1;
        *i += 1;
        let t = at(b, i, le)?;
        let rings = |i: &mut usize| -> Option<Value> { let n = at(b, i, le)?; (0..n).map(|_| pts(b, i, le)).collect::<Option<Vec<_>>>().map(Value::Array) };
        Some(match t {
            1 => ("Point", pt(b, i, le)?),
            2 => ("LineString", pts(b, i, le)?),
            3 => ("Polygon", rings(i)?),
            4..=6 => {
                let n = at(b, i, le)?;
                let parts = (0..n).map(|_| one(b, i).map(|p| p.1)).collect::<Option<Vec<_>>>()?;
                ([("MultiPoint"), "MultiLineString", "MultiPolygon"][t as usize - 4], Value::Array(parts))
            }
            _ => return None,
        })
    }
    let (t, c) = one(b, &mut 0)?;
    Some(serde_json::json!({"type": t, "coordinates": c}))
}
