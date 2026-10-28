//! The roads from a Shapefile: the .shp (the lines), the .dbf (the fields) and the .prj (the CRS) as bytes, so that wasm reads them too.
//! The same `RoadTable` as the other readers: the features become GeoJSON for `geojson::read_roads`, so that every reader types a column
//! by one rule.
//!
//! - The columns: the .dbf fields in their order. A number field with no decimals (and fewer than 19 digits) gives whole numbers, as
//!   GDAL reads it; with decimals, numbers. A logical field gives true and false, a date its "YYYY-MM-DD" text. The texts are read as UTF-8.
//! - The line: a polyline of one part (its x and y; the z and m are left out), in EPSG:4326 (`crs`). A polyline of more parts or another
//!   shape gives no line, as a MultiLineString in the other readers: that road is not drawn.

use crate::Error;
use std::io::Cursor;

use shapefile::dbase::{self, FieldValue};
use serde_json::{json, Map, Value};
use shapefile::Shape;

use crate::crs::{Crs, ToWgs84};
use crate::geojson;
pub use roadstyle_model::RoadTable;

/// The .dbf header's fields: name and whether they hold whole numbers (dBase: the type byte 11, the length byte 16, the decimals byte
/// 17 of each 32-byte descriptor, from byte 32 to the byte 0x0D). The dbase crate does not give the decimals.
fn whole_number_fields(dbf: &[u8]) -> Vec<(String, bool)> {
    dbf.get(32..).unwrap_or_default().chunks(32).take_while(|d| d.first() != Some(&0x0D) && d.len() == 32).map(|d| {
        let name = String::from_utf8_lossy(&d[..11]).trim_end_matches('\0').to_string();
        (name, d[11] == b'N' && d[17] == 0 && d[16] < 19)
    }).collect()
}

fn value(v: &FieldValue, whole: bool) -> Value {
    match v {
        FieldValue::Character(s) => s.clone().map_or(Value::Null, Value::from),
        FieldValue::Memo(s) => s.clone().into(),
        FieldValue::Numeric(n) => match n {
            Some(x) if whole && x.fract() == 0.0 => json!(*x as i64),
            Some(x) => json!(x),
            None => Value::Null,
        },
        FieldValue::Float(n) => n.map_or(Value::Null, |x| json!(x as f64)),
        FieldValue::Logical(b) => b.map_or(Value::Null, Value::from),
        FieldValue::Integer(i) => json!(i),
        FieldValue::Currency(x) | FieldValue::Double(x) => json!(x),
        FieldValue::Date(d) => d.as_ref().map_or(Value::Null, |d| format!("{:04}-{:02}-{:02}", d.year(), d.month(), d.day()).into()),
        FieldValue::DateTime(t) => {
            let (d, h) = (t.date(), t.time());
            format!("{:04}-{:02}-{:02}T{:02}:{:02}:{:02}", d.year(), d.month(), d.day(), h.hours(), h.minutes(), h.seconds()).into()
        }
    }
}

fn line(shape: &Shape) -> Option<Vec<[f64; 2]>> {
    let one = |parts: Vec<Vec<[f64; 2]>>| if parts.len() == 1 { parts.into_iter().next() } else { None };
    match shape {
        Shape::Polyline(l) => one(l.parts().iter().map(|p| p.iter().map(|q| [q.x, q.y]).collect()).collect()),
        Shape::PolylineM(l) => one(l.parts().iter().map(|p| p.iter().map(|q| [q.x, q.y]).collect()).collect()),
        Shape::PolylineZ(l) => one(l.parts().iter().map(|p| p.iter().map(|q| [q.x, q.y]).collect()).collect()),
        _ => None,
    }
}

/// The roads of a Shapefile: `shp` and `dbf` its two files, `prj` the text of its .prj file (None: the file has none, an error, as in
/// the Python binding). `what` names the file in the errors.
pub fn read_roads(shp: &[u8], dbf: &[u8], prj: Option<&str>, what: &str) -> Result<RoadTable, Error> {
    let to84 = ToWgs84::new(prj.map(|w| Crs::Wkt(w.to_string())), what)?;
    let fields = whole_number_fields(dbf);
    let shapes = shapefile::ShapeReader::new(Cursor::new(shp)).map_err(|e| Error::Format(format!("{what}: not a Shapefile (.shp): {e}")))?;
    let records = dbase::Reader::new(Cursor::new(dbf)).map_err(|e| Error::Format(format!("{what}: not a dBase file (.dbf): {e}")))?;
    let mut reader = shapefile::Reader::new(shapes, records);
    let mut feats = Vec::new();
    for (i, r) in reader.iter_shapes_and_records().enumerate() {
        let (shape, rec) = r.map_err(|e| Error::Format(format!("{what}: record {i}: {e}")))?;
        let props: Map<String, Value> = fields.iter().map(|(n, whole)| (n.clone(), rec.get(n).map_or(Value::Null, |v| value(v, *whole)))).collect();
        let geom = match line(&shape) {
            Some(mut l) => {
                to84.line(&mut l)?;
                json!({"type": "LineString", "coordinates": l})
            }
            None => Value::Null,
        };
        feats.push(json!({"type": "Feature", "properties": props, "geometry": geom}));
    }
    let fc = json!({"type": "FeatureCollection", "features": feats});
    geojson::read_roads(&serde_json::to_vec(&fc).map_err(|e| Error::Format(e.to_string()))?)
}
