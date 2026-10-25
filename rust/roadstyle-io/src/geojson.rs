//! The roads from a GeoJSON file (RFC 7946: a FeatureCollection in EPSG:4326). The same output as `read::read_roads` (GeoParquet):
//! a `RoadTable`, one row for each feature, in the file's order. The other readers of road files (GeoPackage, Shapefile) give this shape.
//!
//! - The columns: each property name in the order in which the features first have it. A column's type is the type of all its values
//!   (null is no value): Boolean, Int64 (whole numbers), Float64 (numbers), else Utf8. A column with values of more than one type, or a
//!   list or a mapping, is Utf8: a text is kept as it is, another value is its JSON text.
//! - The line: a LineString's points (x, y; a third number is left out). Another geometry, or none, gives no line, as in the GeoParquet
//!   reader: that road is not drawn.

use crate::Error;
use arrow_array::{ArrayRef, BooleanArray, Float64Array, Int64Array, StringArray};
use serde_json::Value;
use std::sync::Arc;

pub use roadstyle_model::{Lines, RoadTable};

#[derive(Clone, Copy, PartialEq)]
enum Kind {
    None,
    Bool,
    Int,
    Float,
    Text,
}

fn kind(v: &Value) -> Kind {
    match v {
        Value::Null => Kind::None,
        Value::Bool(_) => Kind::Bool,
        Value::Number(n) if n.is_i64() => Kind::Int,
        Value::Number(_) => Kind::Float,
        _ => Kind::Text,
    }
}

/// The kind of a column that has values of kind `a` and `b`.
fn join(a: Kind, b: Kind) -> Kind {
    match (a, b) {
        (Kind::None, k) | (k, Kind::None) => k,
        (a, b) if a == b => a,
        (Kind::Int, Kind::Float) | (Kind::Float, Kind::Int) => Kind::Float,
        _ => Kind::Text,
    }
}

fn line(g: &Value) -> Option<Vec<[f64; 2]>> {
    if g["type"] != "LineString" {
        return None;
    }
    g["coordinates"].as_array()?.iter().map(|p| Some([p.get(0)?.as_f64()?, p.get(1)?.as_f64()?])).collect()
}

/// The roads of the GeoJSON text `data`: a FeatureCollection (or one Feature). An error for text that is not JSON or not GeoJSON.
pub fn read_roads(data: &[u8]) -> Result<RoadTable, Error> {
    let fc: Value = serde_json::from_slice(data).map_err(|e| Error::Format(format!("not a GeoJSON file: {e}")))?;
    let feats: Vec<&Value> = match fc["type"].as_str() {
        Some("FeatureCollection") => fc["features"].as_array().ok_or_else(|| Error::Format("GeoJSON: a FeatureCollection with no features list".into()))?.iter().collect(),
        Some("Feature") => vec![&fc],
        _ => return Err(Error::Format("GeoJSON: not a FeatureCollection or a Feature".into())),
    };
    let mut names: Vec<String> = Vec::new();
    let mut kinds: Vec<Kind> = Vec::new();
    let mut lines = Lines::default();
    for (i, f) in feats.iter().enumerate() {
        let props = match &f["properties"] {
            Value::Object(p) => p,
            Value::Null => &serde_json::Map::new(),
            _ => return Err(Error::Format(format!("GeoJSON feature {i}: its properties are not a mapping"))),
        };
        for (k, v) in props {
            match names.iter().position(|n| n == k) {
                Some(c) => kinds[c] = join(kinds[c], kind(v)),
                None => {
                    names.push(k.clone());
                    kinds.push(kind(v));
                }
            }
        }
        lines.push(line(&f["geometry"]).as_deref());
    }
    let cols = names.iter().zip(&kinds).map(|(n, k)| {
        let vals = feats.iter().map(|f| f["properties"].get(n).filter(|v| !v.is_null()));
        let col: ArrayRef = match k {
            Kind::Bool => Arc::new(vals.map(|v| v.and_then(Value::as_bool)).collect::<BooleanArray>()),
            Kind::Int => Arc::new(vals.map(|v| v.and_then(Value::as_i64)).collect::<Int64Array>()),
            Kind::Float => Arc::new(vals.map(|v| v.and_then(Value::as_f64)).collect::<Float64Array>()),
            Kind::Text | Kind::None => Arc::new(vals.map(|v| v.map(|v| v.as_str().map_or_else(|| v.to_string(), String::from)))
                .collect::<StringArray>()),
        };
        col
    }).collect();
    Ok(RoadTable::new(names, cols, lines)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_feature_collection_is_a_road_table() {
        let text = br#"{"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"highway": "primary", "lanes": 2, "oneway": true},
             "geometry": {"type": "LineString", "coordinates": [[18.0, 59.3, 4.0], [18.1, 59.31]]}},
            {"type": "Feature", "properties": {"highway": "footway", "lanes": 1.5, "name": "A", "tags": {"x": 1}},
             "geometry": {"type": "Point", "coordinates": [18.0, 59.3]}},
            {"type": "Feature", "properties": null, "geometry": null}]}"#;
        let t = read_roads(text).unwrap();
        assert_eq!(t.len(), 3);
        assert_eq!(t.names(), ["highway", "lanes", "oneway", "name", "tags"]);
        assert_eq!(t.line(0), Some(&[[18.0, 59.3], [18.1, 59.31]][..]));
        assert_eq!((t.line(1), t.line(2)), (None, None));
        assert_eq!(t.get(1, "lanes").unwrap().as_f64(), Some(1.5));       // a whole number and a fraction: Float64
        assert_eq!(t.get(0, "oneway").unwrap().as_bool(), Some(true));
        assert_eq!(t.get(1, "tags").unwrap().as_str(), Some(r#"{"x":1}"#));
        assert!(t.get(2, "highway").unwrap().is_null());
        assert!(matches!(read_roads(b"[1, 2]").unwrap_err(), Error::Format(m) if m.contains("not a FeatureCollection")));
        assert!(matches!(read_roads(b"{").unwrap_err(), Error::Format(m) if m.contains("not a GeoJSON file")));
    }
}
