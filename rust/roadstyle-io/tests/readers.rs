//! The Shapefile and GeoPackage readers give the RoadTable that Python's geopandas reads (the reference), in EPSG:4326.

use std::io::Cursor;

use roadstyle_io::shp;
use shapefile::dbase::{self, FieldValue, Record};

const MONACO: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../roadstyle-rs/tests/data/monaco/roads.parquet");
const WGS84_PRJ: &str = r#"GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]"#;
// pyproj: CRS(3006).to_wkt("WKT1_ESRI"), the .prj text of a SWEREF99 TM Shapefile
const SWEREF_PRJ: &str = r#"PROJCS["SWEREF99_TM",GEOGCS["GCS_SWEREF99",DATUM["D_SWEREF99",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",15.0],PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]"#;
// pyproj (Python's to_crs): these EPSG:3006 points are these lon, lat
const SWEREF: [[f64; 2]; 2] = [[674571.866, 6580743.008], [676681.353, 6578766.595]];
const PYPROJ: [[f64; 2]; 2] = [[18.068599992, 59.329299997], [18.104000008, 59.310700000]];

fn near(a: &[[f64; 2]], b: &[[f64; 2]], tol: f64) -> bool {
    a.len() == b.len() && a.iter().zip(b).all(|(p, q)| (p[0] - q[0]).abs() < tol && (p[1] - q[1]).abs() < tol)
}

/// A road of a test Shapefile: its line, highway (text), lanes (whole numbers), oneway (logical) and maxspeed (numbers).
type Road<'a> = (Vec<[f64; 2]>, &'a str, Option<f64>, bool, f64);

/// A Shapefile of `lines`: (.shp, .dbf).
fn shapefile_of(lines: &[Road]) -> (Vec<u8>, Vec<u8>) {
    let (mut shp, mut dbf) = (Vec::new(), Vec::new());
    {
        let table = dbase::TableWriterBuilder::new()
            .add_character_field("highway".try_into().unwrap(), 20)
            .add_numeric_field("lanes".try_into().unwrap(), 4, 0)
            .add_logical_field("oneway".try_into().unwrap())
            .add_numeric_field("maxspeed".try_into().unwrap(), 8, 1)
            .build_with_dest(Cursor::new(&mut dbf));
        let mut w = shapefile::Writer::new(shapefile::ShapeWriter::new(Cursor::new(&mut shp)), table);
        for (l, hw, lanes, oneway, speed) in lines {
            let pl = shapefile::Polyline::new(l.iter().map(|p| shapefile::Point::new(p[0], p[1])).collect());
            let mut r = Record::default();
            r.insert("highway".into(), FieldValue::Character(Some(hw.to_string())));
            r.insert("lanes".into(), FieldValue::Numeric(*lanes));
            r.insert("oneway".into(), FieldValue::Logical(Some(*oneway)));
            r.insert("maxspeed".into(), FieldValue::Numeric(Some(*speed)));
            w.write_shape_and_record(&pl, &r).unwrap();
        }
    }
    (shp, dbf)
}

#[test]
fn a_monaco_shapefile_is_its_roads() {
    let roads = roadstyle_io::read::read_roads(std::fs::read(MONACO).unwrap(), "geometry").unwrap();
    let hw = roads.col("highway").unwrap();
    let lines: Vec<_> = (0..200).filter_map(|r| Some((roads.line(r)?.to_vec(), roads.cell(hw, r).as_str()?, Some((r % 3) as f64), r % 2 == 0, 30.5))).collect();
    let (s, d) = shapefile_of(&lines);
    let t = shp::read_roads(&s, &d, Some(WGS84_PRJ), "monaco.shp").unwrap();
    assert_eq!(t.len(), lines.len());
    assert_eq!(t.names(), ["highway", "lanes", "oneway", "maxspeed"]);
    for (r, (l, h, lanes, oneway, speed)) in lines.iter().enumerate() {
        assert_eq!(t.line(r), Some(&l[..]), "row {r}: a WGS 84 file keeps its points as they are");
        assert_eq!(t.get(r, "highway").unwrap().as_str(), Some(*h));
        assert_eq!(t.get(r, "lanes").unwrap().as_i64(), lanes.map(|x| x as i64));    // N(4, 0): whole numbers, as GDAL reads them
        assert_eq!(t.get(r, "oneway").unwrap().as_bool(), Some(*oneway));
        assert_eq!(t.get(r, "maxspeed").unwrap().as_f64(), Some(*speed));
    }
    // no .prj: no CRS, an error as in Python (validate.to_wgs84)
    assert!(matches!(shp::read_roads(&s, &d, None, "monaco.shp").unwrap_err(), roadstyle_io::Error::Crs(m) if m.starts_with("monaco.shp has no CRS")));
}

#[test]
fn a_sweref99_shapefile_is_reprojected_as_pyproj() {
    let (s, d) = shapefile_of(&[(SWEREF.to_vec(), "primary", None, true, 50.0)]);
    let t = shp::read_roads(&s, &d, Some(SWEREF_PRJ), "x.shp").unwrap();
    assert!(near(t.line(0).unwrap(), &PYPROJ, 1e-8), "{:?}", t.line(0));
    assert!(t.get(0, "lanes").unwrap().is_null());
}

#[cfg(feature = "gpkg")]
mod gpkg {
    use super::*;
    use roadstyle_io::gpkg;

    const SODERMALM: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../notebooks/data/sodermalm_edges.gpkg");

    #[test]
    fn the_sodermalm_geopackage_is_what_geopandas_reads() {
        let (t, warning) = gpkg::read_roads(&std::fs::read(SODERMALM).unwrap(), "sodermalm_edges.gpkg").unwrap();
        assert_eq!(warning, None);
        // geopandas.read_file: 4563 rows, these columns (the fid is the index), every geometry a LineString
        assert_eq!(t.len(), 4563);
        assert_eq!(t.names(), ["edge_id", "osm_id", "edge_ref", "highway", "name", "lanes", "oneway", "maxspeed_kmh", "length_m", "tunnel",
                               "bridge", "layer"]);
        assert_eq!(t.get(0, "edge_id").unwrap().as_str(), Some("6379011699359957301"));
        assert_eq!(t.get(0, "osm_id").unwrap().as_i64(), Some(4080398));
        assert_eq!(t.get(0, "lanes").unwrap().as_i64(), Some(1));
        assert_eq!(t.get(0, "oneway").unwrap().as_bool(), Some(false));
        assert_eq!(t.get(0, "maxspeed_kmh").unwrap().as_f64(), Some(30.0));
        assert!(t.get(0, "tunnel").unwrap().is_null());
        assert_eq!(&t.line(0).unwrap()[..2], &[[18.096010500000002, 59.3110645], [18.0970626, 59.3109186]]);
        let (mut lo, mut hi) = ([f64::MAX; 2], [f64::MIN; 2]);
        for r in 0..t.len() {
            for p in t.line(r).unwrap() {
                (0..2).for_each(|i| { lo[i] = lo[i].min(p[i]); hi[i] = hi[i].max(p[i]); });
            }
        }
        assert_eq!([lo[0], lo[1], hi[0], hi[1]], [18.0244041, 59.3013592, 18.106223800000002, 59.3267523]);   // geopandas' total_bounds
    }

    /// A GeoPackage with one road in `srs` (an EPSG code) at `line`, as its bytes.
    fn geopackage(srs: i64, line: &[[f64; 2]], tables: &[&str]) -> Vec<u8> {
        let db = rusqlite::Connection::open_in_memory().unwrap();
        db.execute_batch("CREATE TABLE gpkg_spatial_ref_sys (srs_name TEXT, srs_id INTEGER PRIMARY KEY, organization TEXT,
                          organization_coordsys_id INTEGER, definition TEXT, description TEXT);
                          CREATE TABLE gpkg_contents (table_name TEXT PRIMARY KEY, data_type TEXT, identifier TEXT, srs_id INTEGER);
                          CREATE TABLE gpkg_geometry_columns (table_name TEXT, column_name TEXT, geometry_type_name TEXT, srs_id INTEGER,
                          z INTEGER, m INTEGER);").unwrap();
        db.execute("INSERT INTO gpkg_spatial_ref_sys VALUES ('x', ?1, 'EPSG', ?1, 'a WKT', '')", [srs]).unwrap();
        let mut blob = b"GP\x00\x01".to_vec();                     // version 0, flags: little-endian, no envelope
        blob.extend((srs as i32).to_le_bytes());
        blob.extend([1u8, 2, 0, 0, 0]);                           // WKB: little-endian LineString
        blob.extend((line.len() as u32).to_le_bytes());
        line.iter().for_each(|p| { blob.extend(p[0].to_le_bytes()); blob.extend(p[1].to_le_bytes()); });
        for t in tables {
            db.execute_batch(&format!("CREATE TABLE {t} (fid INTEGER PRIMARY KEY, geom BLOB, highway TEXT, lanes MEDIUMINT, oneway BOOLEAN,
                                       speed FLOAT);")).unwrap();
            db.execute(&format!("INSERT INTO gpkg_contents VALUES ('{t}', 'features', '{t}', ?1)"), [srs]).unwrap();
            db.execute(&format!("INSERT INTO gpkg_geometry_columns VALUES ('{t}', 'geom', 'LINESTRING', ?1, 0, 0)"), [srs]).unwrap();
            db.execute(&format!("INSERT INTO {t} VALUES (1, ?1, '{t}-road', 2, 1, 50)"), [&blob]).unwrap();
        }
        db.serialize(rusqlite::MAIN_DB).unwrap().to_vec()
    }

    #[test]
    fn a_sweref99_geopackage_is_reprojected_as_pyproj() {
        let (t, warning) = gpkg::read_roads(&geopackage(3006, &SWEREF, &["roads"]), "x.gpkg").unwrap();
        assert_eq!((t.names(), warning), (&["highway", "lanes", "oneway", "speed"].map(String::from)[..], None));
        assert!(near(t.line(0).unwrap(), &PYPROJ, 1e-8), "{:?}", t.line(0));
        assert_eq!((t.get(0, "oneway").unwrap().as_bool(), t.get(0, "speed").unwrap().as_f64()), (Some(true), Some(50.0)));
        // two tables, written b then a: geopandas reads b (gpkg_contents' order, not the names') and warns with these words
        let (t, warning) = gpkg::read_roads(&geopackage(3006, &SWEREF, &["b", "a"]), "two.gpkg").unwrap();
        assert_eq!(t.get(0, "highway").unwrap().as_str(), Some("b-road"));
        assert_eq!(warning.as_deref(), Some("More than one layer found in 'two.gpkg': 'b' (default), 'a'. Specify layer parameter to avoid this warning."));
        assert!(matches!(gpkg::read_roads(b"not a file", "x.gpkg").unwrap_err(), roadstyle_io::Error::Format(m) if m.starts_with("x.gpkg: not a GeoPackage")));
    }
}
