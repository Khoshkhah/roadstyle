//! A road file's coordinates to EPSG:4326 (lon, lat), with the rule of Python's `validate.to_wgs84`: a file with no CRS is an error,
//! EPSG:4326 stays as it is, another CRS is reprojected. proj4rs reprojects (pure Rust, also in wasm); an EPSG code becomes a proj string
//! through crs-definitions, a WKT text (a .prj file, a GeoPackage definition) through proj4wkt. A CRS that they cannot read is an error
//! that names it: the reader does not guess.

use crate::Error;
use proj4rs::Proj;

/// The CRS of a road file, as the file gives it.
pub enum Crs {
    Epsg(u16),
    Wkt(String),
}

/// The reprojection of one file: None when its CRS is EPSG:4326 (or the same longlat WGS 84).
pub struct ToWgs84(Option<(Proj, Proj)>);

/// Whether a proj string is longlat on WGS 84 (Python's crs.to_epsg() == 4326: no reprojection): the datum or the ellipsoid WGS84, or
/// its axis 6378137 and its flattening 298.257223563 (proj4wkt's form), with no datum shift and no other prime meridian.
fn is_wgs84(proj: &str) -> bool {
    let p: std::collections::HashMap<&str, &str> = proj.split_whitespace().filter_map(|t| t.strip_prefix('+')?.split_once('=')).collect();
    let num = |k: &str, v: f64| p.get(k).and_then(|x| x.parse::<f64>().ok()) == Some(v);
    p.get("proj") == Some(&"longlat")
        && (p.get("datum") == Some(&"WGS84") || p.get("ellps") == Some(&"WGS84") || (num("a", 6378137.0) && num("rf", 298.257223563)))
        && p.get("towgs84").is_none_or(|t| t.split(',').all(|x| x.parse::<f64>() == Ok(0.0)))
        && p.get("pm").is_none_or(|m| *m == "greenwich" || *m == "0")
}

impl ToWgs84 {
    /// `what` names the file in the errors.
    pub fn new(crs: Option<Crs>, what: &str) -> Result<ToWgs84, Error> {
        let proj = match crs {
            None => return Err(Error::Crs(format!("{what} has no CRS, so it cannot be reprojected to EPSG:4326. Give the file a CRS (a .prj file, \
                                        the GeoPackage's srs_id)"))),
            Some(Crs::Epsg(4326)) => return Ok(ToWgs84(None)),
            Some(Crs::Epsg(c)) => crs_definitions::from_code(c).map(|d| d.proj4.to_string())
                .ok_or_else(|| Error::Crs(format!("{what}: its CRS EPSG:{c} is not known to the reader (crs-definitions)")))?,
            Some(Crs::Wkt(w)) => proj4wkt::wkt_to_projstring(&w)
                .map_err(|e| Error::Crs(format!("{what}: its CRS cannot be read ({e}): {}", w.chars().take(120).collect::<String>())))?,
        };
        if is_wgs84(&proj) {
            return Ok(ToWgs84(None));
        }
        let src = Proj::from_proj_string(&proj).map_err(|e| Error::Crs(format!("{what}: its CRS {proj:?} cannot be used ({e})")))?;
        let dst = Proj::from_proj_string("+proj=longlat +datum=WGS84 +no_defs").map_err(|e| Error::Crs(e.to_string()))?;
        Ok(ToWgs84(Some((src, dst))))
    }

    /// The points of a line in EPSG:4326.
    pub fn line(&self, pts: &mut [[f64; 2]]) -> Result<(), Error> {
        let Some((src, dst)) = &self.0 else { return Ok(()) };
        for p in pts.iter_mut() {
            // proj4rs: the angles of a longlat CRS in radians
            let mut q = if src.is_latlong() { (p[0].to_radians(), p[1].to_radians()) } else { (p[0], p[1]) };
            proj4rs::transform::transform(src, dst, &mut q).map_err(|e| Error::Crs(format!("reprojection of ({}, {}): {e}", p[0], p[1])))?;
            *p = [q.0.to_degrees(), q.1.to_degrees()];
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// pyproj's lon, lat (9 decimals) of the two EPSG:3006 points of the tests
    pub const PYPROJ: [[f64; 2]; 2] = [[18.068599992, 59.329299997], [18.104000008, 59.310700000]];

    #[test]
    fn sweref99_tm_to_wgs84_as_pyproj() {
        // pyproj (Python's to_crs) gives these lon, lat for the EPSG:3006 points
        let t = ToWgs84::new(Some(Crs::Epsg(3006)), "x").unwrap();
        let mut l = [[674571.866, 6580743.008], [676681.353, 6578766.595]];
        t.line(&mut l).unwrap();
        for (a, b) in l.iter().zip(PYPROJ) {
            assert!((a[0] - b[0]).abs() < 1e-8 && (a[1] - b[1]).abs() < 1e-8, "{a:?} {b:?}");
        }
        assert!(ToWgs84::new(Some(Crs::Epsg(4326)), "x").unwrap().0.is_none());
        let wgs84_prj = r#"GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]"#;
        assert!(ToWgs84::new(Some(Crs::Wkt(wgs84_prj.into())), "x").unwrap().0.is_none());
        assert!(matches!(ToWgs84::new(None, "roads.shp").err().unwrap(), Error::Crs(m) if m.starts_with("roads.shp has no CRS")));
        assert!(matches!(ToWgs84::new(Some(Crs::Wkt("NOT A CRS".into())), "x").err().unwrap(), Error::Crs(m) if m.contains("NOT A CRS")));
    }
}
