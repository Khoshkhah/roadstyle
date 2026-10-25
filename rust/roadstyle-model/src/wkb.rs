//! The one WKB reader (audit N19): every reader of a geometry (the roads' lines, the base map's features, a stage-1 file's geometry, the
//! engine's `geom::from_wkb`) reads WKB here. ISO WKB and EWKB (DuckDB, GeoPandas and shapely write them), in 2D: a Z or an M is left
//! out, so a 3D line draws on its x and y, as Python draws it.

use crate::feature_table::GeomType;

/// A geometry's parts: each a list of rings, each ring its points (a Point: one ring of one point; a LineString: one ring; a Polygon: one
/// part of its rings; a Multi type: a part for each member).
pub type Parts = Vec<Vec<Vec<[f64; 2]>>>;

/// The type and the parts of a WKB geometry; None: bytes that are not a WKB point, line, polygon or Multi type (a collection, for one).
pub fn read(b: &[u8]) -> Option<(GeomType, Parts)> {
    one(b, 0).map(|(kind, parts, _)| (kind, parts))
}

/// One WKB geometry at `i`: its type, its parts and the index after it.
fn one(b: &[u8], mut i: usize) -> Option<(GeomType, Parts, usize)> {
    let le = *b.get(i)? == 1;
    let u32_at = |i: usize| -> Option<u32> {
        let w: [u8; 4] = b.get(i..i + 4)?.try_into().ok()?;
        Some(if le { u32::from_le_bytes(w) } else { u32::from_be_bytes(w) })
    };
    let raw = u32_at(i + 1)?;
    // EWKB: flags in the high bits (a Z, an M, an SRID with its 4 bytes after the type); ISO WKB: 1000 more for a Z, 2000 for an M, 3000
    // for both
    let (z, m, srid) = (raw & 0x8000_0000 != 0, raw & 0x4000_0000 != 0, raw & 0x2000_0000 != 0);
    let code = raw & 0x0FFF_FFFF;
    let kind = GeomType::of(code)?;
    let iso = code / 1000;
    let dims = 2 + usize::from(z || iso == 1 || iso == 3) + usize::from(m || iso == 2 || iso == 3);
    i += 5 + if srid { 4 } else { 0 };
    let pt = |i: &mut usize| -> Option<[f64; 2]> {
        let f = |k: usize| -> Option<f64> {
            let w: [u8; 8] = b.get(k..k + 8)?.try_into().ok()?;
            Some(if le { f64::from_le_bytes(w) } else { f64::from_be_bytes(w) })
        };
        let p = [f(*i)?, f(*i + 8)?];
        *i += 8 * dims;
        Some(p)
    };
    let ring = |i: &mut usize| -> Option<Vec<[f64; 2]>> {
        let n = u32_at(*i)? as usize;
        *i += 4;
        (0..n).map(|_| pt(i)).collect()
    };
    let parts = match kind {
        GeomType::Point => vec![vec![vec![pt(&mut i)?]]],
        GeomType::LineString => vec![vec![ring(&mut i)?]],
        GeomType::Polygon => {
            let n = u32_at(i)? as usize;
            i += 4;
            vec![(0..n).map(|_| ring(&mut i)).collect::<Option<Vec<_>>>()?]
        }
        _ => {
            let n = u32_at(i)? as usize;
            i += 4;
            let mut out = Vec::with_capacity(n);
            for _ in 0..n {
                let (_, mut p, next) = one(b, i)?;
                i = next;
                out.append(&mut p);
            }
            out
        }
    };
    Some((kind, parts, i))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A little-endian WKB LineString of two points, with `code` (its type with the flags) and `extra` numbers after x and y of each point.
    fn line(code: u32, srid: Option<u32>, extra: usize) -> Vec<u8> {
        let mut b = vec![1u8];
        b.extend(code.to_le_bytes());
        if let Some(s) = srid {
            b.extend(s.to_le_bytes());
        }
        b.extend(2u32.to_le_bytes());
        for p in [[7.4f64, 43.7], [7.5, 43.8]] {
            b.extend(p[0].to_le_bytes());
            b.extend(p[1].to_le_bytes());
            (0..extra).for_each(|k| b.extend((10.0 + k as f64).to_le_bytes()));
        }
        b
    }

    #[test]
    fn a_z_or_an_m_is_left_out() {
        let want = Some((GeomType::LineString, vec![vec![vec![[7.4, 43.7], [7.5, 43.8]]]]));
        assert_eq!(read(&line(2, None, 0)), want, "2D");
        assert_eq!(read(&line(1002, None, 1)), want, "ISO Z (GeoPandas' to_arrow, DuckDB)");
        assert_eq!(read(&line(2002, None, 1)), want, "ISO M");
        assert_eq!(read(&line(3002, None, 2)), want, "ISO ZM");
        assert_eq!(read(&line(0x8000_0002, None, 1)), want, "EWKB Z (shapely's to_wkb)");
        assert_eq!(read(&line(0xC000_0002, None, 2)), want, "EWKB ZM");
        assert_eq!(read(&line(0xA000_0002, Some(4326), 1)), want, "EWKB Z with an SRID");
        assert_eq!(read(&line(7, None, 0)), None, "a collection");
    }
}
