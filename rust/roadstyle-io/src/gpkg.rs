//! The roads from a GeoPackage (the feature "gpkg": SQLite through rusqlite, a C build, so not in wasm). The same `RoadTable` as the
//! other readers: the features become GeoJSON for `geojson::read_roads`, so that every reader types a column by one rule.
//!
//! - The layer: the first feature table in gpkg_contents' order, as geopandas reads it. A file with more feature tables also gives
//!   geopandas' warning, which names them.
//! - The columns: the table's columns in their order, without its primary key (the fid, as GDAL reads it) and the geometry column.
//!   BOOLEAN gives true and false, the integer types whole numbers, REAL, FLOAT and DOUBLE numbers, the others text (a BLOB as hex).
//! - The line: a LineString (2D, Z, M or ZM; its x and y), in EPSG:4326 (`crs`, the CRS of gpkg_spatial_ref_sys: its EPSG code, else
//!   its WKT). Another geometry gives no line, as in the other readers: that road is not drawn.

use rusqlite::types::ValueRef;
use rusqlite::{Connection, OptionalExtension, MAIN_DB};
use serde_json::{json, Map, Value};

use crate::crs::{Crs, ToWgs84};
use crate::geojson;
pub use roadstyle_model::RoadTable;

/// The x, y of a LineString in WKB (ISO: the type 1002, 2002, 3002 for Z, M, ZM; EWKB: the flags 0x80000000 Z, 0x40000000 M and
/// 0x20000000 an SRID before the points). None for another geometry.
fn wkb_line(b: &[u8]) -> Option<Vec<[f64; 2]>> {
    let le = *b.first()? == 1;
    let u32_at = |i: usize| -> Option<u32> {
        let w: [u8; 4] = b.get(i..i + 4)?.try_into().ok()?;
        Some(if le { u32::from_le_bytes(w) } else { u32::from_be_bytes(w) })
    };
    let f64_at = |i: usize| -> Option<f64> {
        let w: [u8; 8] = b.get(i..i + 8)?.try_into().ok()?;
        Some(if le { f64::from_le_bytes(w) } else { f64::from_be_bytes(w) })
    };
    let t = u32_at(1)?;
    let (base, z, m) = ((t & 0x0FFF_FFFF) % 1000, t & 0x8000_0000 != 0 || matches!((t & 0x0FFF_FFFF) / 1000, 1 | 3),
                        t & 0x4000_0000 != 0 || matches!((t & 0x0FFF_FFFF) / 1000, 2 | 3));
    if base != 2 {
        return None;
    }
    let start = 5 + if t & 0x2000_0000 != 0 { 4 } else { 0 };
    let step = 8 * (2 + usize::from(z) + usize::from(m));
    let n = u32_at(start)? as usize;
    (0..n).map(|k| Some([f64_at(start + 4 + step * k)?, f64_at(start + 12 + step * k)?])).collect()
}

/// The WKB of a GeoPackage geometry: after "GP", the version, the flags (bit 0: the byte order; bits 1-3: the envelope, 0 / 32 / 48 / 48
/// / 64 bytes), the srs_id and the envelope.
fn gpkg_wkb(b: &[u8]) -> Option<&[u8]> {
    if b.get(..2)? != b"GP" {
        return None;
    }
    let env = match (b.get(3)? >> 1) & 7 {
        0 => 0,
        1 => 32,
        2 | 3 => 48,
        4 => 64,
        _ => return None,
    };
    b.get(8 + env..)
}

fn sql_err(what: &str) -> impl Fn(rusqlite::Error) -> String + '_ {
    move |e| format!("{what}: {e}")
}

/// The roads of the GeoPackage `data` (the file's bytes), and the warning when the file has more than one feature table. `what` names
/// the file in the errors and the warning.
pub fn read_roads(data: &[u8], what: &str) -> Result<(RoadTable, Option<String>), String> {
    let mut db = Connection::open_in_memory().map_err(sql_err(what))?;
    db.deserialize_read_exact(MAIN_DB, data, data.len(), true).map_err(|e| format!("{what}: not a GeoPackage: {e}"))?;
    let err = sql_err(what);
    let tables: Vec<String> = db.prepare("SELECT table_name FROM gpkg_contents WHERE data_type = 'features' ORDER BY rowid")
        .and_then(|mut s| s.query_map([], |r| r.get(0))?.collect()).map_err(|e| format!("{what}: not a GeoPackage: {e}"))?;
    let table = tables.first().cloned().ok_or_else(|| format!("{what}: the GeoPackage has no feature table"))?;
    // geopandas' (pyogrio's) warning, in its words
    let warning = (tables.len() > 1).then(|| {
        let names: Vec<String> = tables.iter().enumerate().map(|(i, t)| if i == 0 { format!("'{t}' (default)") } else { format!("'{t}'") }).collect();
        format!("More than one layer found in '{what}': {}. Specify layer parameter to avoid this warning.", names.join(", "))
    });
    let (geom, srs): (String, i64) = db.query_row("SELECT column_name, srs_id FROM gpkg_geometry_columns WHERE table_name = ?1", [&table],
                                                  |r| Ok((r.get(0)?, r.get(1)?))).map_err(&err)?;
    let crs = db.query_row("SELECT organization, organization_coordsys_id, definition FROM gpkg_spatial_ref_sys WHERE srs_id = ?1", [srs],
                           |r| Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?, r.get::<_, String>(2)?))).optional().map_err(&err)?;
    let crs = match crs {
        Some((org, code, _)) if org.eq_ignore_ascii_case("EPSG") && code > 0 => Some(Crs::Epsg(u16::try_from(code).map_err(|_| format!("{what}: EPSG:{code}"))?)),
        Some((_, _, def)) if def != "undefined" => Some(Crs::Wkt(def)),
        _ => None,
    };
    let to84 = ToWgs84::new(crs, what)?;
    // the columns: (name, its declared type), without the primary key and the geometry
    let cols: Vec<(String, String)> = db.prepare(&format!("PRAGMA table_info(\"{}\")", table.replace('"', "\"\"")))
        .and_then(|mut s| s.query_map([], |r| Ok((r.get::<_, String>(1)?, r.get::<_, String>(2)?, r.get::<_, i64>(5)?)))?.collect::<Result<Vec<_>, _>>())
        .map_err(&err)?.into_iter().filter(|(n, _, pk)| *pk == 0 && *n != geom).map(|(n, t, _)| (n, t.to_uppercase())).collect();
    let quote = |n: &str| format!("\"{}\"", n.replace('"', "\"\""));
    let select = format!("SELECT {}, {} FROM {} ORDER BY rowid", quote(&geom),
                         cols.iter().map(|(n, _)| quote(n)).collect::<Vec<_>>().join(", "), quote(&table));
    let mut stmt = db.prepare(&select).map_err(&err)?;
    let mut rows = stmt.query([]).map_err(&err)?;
    let mut feats = Vec::new();
    while let Some(row) = rows.next().map_err(&err)? {
        let mut props = Map::new();
        for (k, (name, ty)) in cols.iter().enumerate() {
            let v = match row.get_ref(k + 1).map_err(&err)? {
                ValueRef::Null => Value::Null,
                ValueRef::Integer(i) if ty == "BOOLEAN" => Value::Bool(i != 0),
                ValueRef::Integer(i) if matches!(ty.as_str(), "REAL" | "FLOAT" | "DOUBLE") => json!(i as f64),
                ValueRef::Integer(i) => json!(i),
                ValueRef::Real(x) => json!(x),
                ValueRef::Text(t) => String::from_utf8_lossy(t).into(),
                ValueRef::Blob(b) => b.iter().map(|x| format!("{x:02x}")).collect::<String>().into(),
            };
            props.insert(name.clone(), v);
        }
        let line = match row.get_ref(0).map_err(&err)? {
            ValueRef::Blob(b) => gpkg_wkb(b).and_then(wkb_line),
            _ => None,
        };
        let geom = match line {
            Some(mut l) => {
                to84.line(&mut l)?;
                json!({"type": "LineString", "coordinates": l})
            }
            None => Value::Null,
        };
        feats.push(json!({"type": "Feature", "properties": props, "geometry": geom}));
    }
    let fc = json!({"type": "FeatureCollection", "features": feats});
    Ok((geojson::read_roads(&serde_json::to_vec(&fc).map_err(|e| e.to_string())?)?, warning))
}
