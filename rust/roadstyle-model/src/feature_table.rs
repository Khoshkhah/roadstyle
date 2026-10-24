//! The base map's and the overlays' features as one typed table (audit R10, docs/design/r10_feature_table.md): the properties as Arrow
//! columns (a `RoadTable` with no lines, so its column types and its `Cell` reads are the one rule) and the geometry of every feature in
//! one coordinate buffer, with the offsets of its parts and rings (GeoArrow's form). No JSON tree for each feature.

use crate::table::{Cell, Lines, RoadTable};
use arrow_array::ArrayRef;
use serde_json::{json, Value};

/// The type of a feature's geometry, as WKB numbers it.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum GeomType {
    Point = 1,
    LineString = 2,
    Polygon = 3,
    MultiPoint = 4,
    MultiLineString = 5,
    MultiPolygon = 6,
}

impl GeomType {
    fn of(code: u32) -> Option<GeomType> {
        use GeomType::*;
        // ISO WKB: 1000 more for a Z, 2000 for an M, 3000 for both; the coordinates past x and y are left out
        Some(match code % 1000 {
            1 => Point,
            2 => LineString,
            3 => Polygon,
            4 => MultiPoint,
            5 => MultiLineString,
            6 => MultiPolygon,
            _ => return None,
        })
    }

    /// GeoJSON's name of the type.
    pub fn name(self) -> &'static str {
        ["Point", "LineString", "Polygon", "MultiPoint", "MultiLineString", "MultiPolygon"][self as usize - 1]
    }
}

/// The geometries of the features: feature -> parts -> rings -> points (a Point or a LineString is one part of one ring; a Polygon one
/// part of its rings; a Multi type a part for each member).
#[derive(Clone, Debug, Default)]
pub struct Geometries {
    kinds: Vec<Option<GeomType>>, // None: the feature has no geometry
    feat: Vec<u32>,               // the start of each feature's parts in `part`, and the end
    part: Vec<u32>,               // the start of each part's rings in `ring`, and the end
    ring: Vec<u32>,               // the start of each ring's points in `pts`, and the end
    pts: Vec<[f64; 2]>,
}

impl Geometries {
    fn new() -> Geometries {
        Geometries { feat: vec![0], part: vec![0], ring: vec![0], ..Default::default() }
    }

    pub fn len(&self) -> usize {
        self.kinds.len()
    }

    pub fn is_empty(&self) -> bool {
        self.kinds.is_empty()
    }

    /// A feature with no geometry.
    pub fn push_none(&mut self) {
        self.kinds.push(None);
        self.feat.push(*self.feat.last().unwrap());
    }

    /// A feature from its parts, each a list of rings (a Point: one ring of one point).
    pub fn push(&mut self, kind: GeomType, parts: &[Vec<Vec<[f64; 2]>>]) {
        for rings in parts {
            for r in rings {
                self.pts.extend_from_slice(r);
                self.ring.push(self.pts.len() as u32);
            }
            self.part.push(self.ring.len() as u32 - 1);
        }
        self.kinds.push(Some(kind));
        self.feat.push(self.part.len() as u32 - 1);
    }

    /// A feature from its WKB (None or empty bytes: no geometry). An error for bytes that are not a WKB geometry.
    pub fn push_wkb(&mut self, bytes: Option<&[u8]>) -> Result<(), String> {
        let Some(b) = bytes.filter(|b| !b.is_empty()) else {
            self.push_none();
            return Ok(());
        };
        let (kind, parts, _) = wkb(b, 0).ok_or("a geometry that is not WKB")?;
        self.push(kind, &parts);
        Ok(())
    }

    /// The type of the feature `row`'s geometry (None: it has none).
    pub fn kind(&self, row: usize) -> Option<GeomType> {
        self.kinds[row]
    }

    /// The parts of the feature `row`, each as its rings (slices of the one buffer).
    pub fn parts(&self, row: usize) -> impl Iterator<Item = impl Iterator<Item = &[[f64; 2]]> + '_> + '_ {
        (self.feat[row] as usize..self.feat[row + 1] as usize).map(move |p| {
            (self.part[p] as usize..self.part[p + 1] as usize).map(move |r| &self.pts[self.ring[r] as usize..self.ring[r + 1] as usize])
        })
    }

    /// The number of points of every feature.
    pub fn points(&self) -> usize {
        self.pts.len()
    }

    /// The feature `row`'s geometry as GeoJSON (null: none).
    pub fn to_geojson(&self, row: usize) -> Value {
        let Some(kind) = self.kinds[row] else { return Value::Null };
        let parts: Vec<Vec<Vec<[f64; 2]>>> = self.parts(row).map(|rings| rings.map(<[_]>::to_vec).collect()).collect();
        let c = match kind {
            GeomType::Point => json!(parts[0][0][0]),
            GeomType::LineString => json!(parts[0][0]),
            GeomType::Polygon => json!(parts[0]),
            GeomType::MultiPoint => json!(parts.iter().map(|p| p[0][0]).collect::<Vec<_>>()),
            GeomType::MultiLineString => json!(parts.iter().map(|p| &p[0]).collect::<Vec<_>>()),
            GeomType::MultiPolygon => json!(parts),
        };
        json!({"type": kind.name(), "coordinates": c})
    }
}

type Parts = Vec<Vec<Vec<[f64; 2]>>>;

/// One WKB geometry at `i`: its type, its parts and the index after it.
fn wkb(b: &[u8], mut i: usize) -> Option<(GeomType, Parts, usize)> {
    let le = *b.get(i)? == 1;
    let u32_at = |i: usize| -> Option<u32> {
        let w: [u8; 4] = b.get(i..i + 4)?.try_into().ok()?;
        Some(if le { u32::from_le_bytes(w) } else { u32::from_be_bytes(w) })
    };
    let code = u32_at(i + 1)?;
    let kind = GeomType::of(code)?;
    let dims = match code / 1000 { 1 | 2 => 3, 3 => 4, _ => 2 };
    i += 5;
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
                let (_, mut p, next) = wkb(b, i)?;
                i = next;
                out.append(&mut p);
            }
            out
        }
    };
    Some((kind, parts, i))
}

/// The features: their properties (`props`, a `RoadTable` with no lines) and their geometries, one of each for each feature.
#[derive(Clone, Debug)]
pub struct FeatureTable {
    props: RoadTable,
    geoms: Geometries,
}

impl FeatureTable {
    /// The table of the columns `names` (each as long as `geoms`). An error for a column of another type or length.
    pub fn new(names: Vec<String>, cols: Vec<ArrayRef>, geoms: Geometries) -> Result<FeatureTable, String> {
        let mut lines = Lines::default();
        (0..geoms.len()).for_each(|_| lines.push(None));
        Ok(FeatureTable { props: RoadTable::new(names, cols, lines)?, geoms })
    }

    /// An empty builder of the geometries, for `new`.
    pub fn geometries() -> Geometries {
        Geometries::new()
    }

    pub fn len(&self) -> usize {
        self.geoms.len()
    }

    pub fn is_empty(&self) -> bool {
        self.geoms.is_empty()
    }

    pub fn names(&self) -> &[String] {
        self.props.names()
    }

    /// The property `name` of the feature `row` (None: no such column).
    pub fn get(&self, row: usize, name: &str) -> Option<Cell<'_>> {
        self.props.get(row, name)
    }

    pub fn geometries_of(&self) -> &Geometries {
        &self.geoms
    }

    /// The feature `row` as a GeoJSON feature: its properties (a null is left out) and its geometry.
    pub fn to_geojson(&self, row: usize) -> Value {
        let props: serde_json::Map<String, Value> = self.names().iter()
            .filter_map(|n| self.get(row, n).filter(|c| !c.is_null()).map(|c| (n.clone(), c.to_value()))).collect();
        json!({"type": "Feature", "properties": props, "geometry": self.geoms.to_geojson(row)})
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn le_wkb(code: u32, body: &[f64], counts: &[u32]) -> Vec<u8> {
        // a little-endian WKB of one geometry: the counts first (the rings, then the points of each), then the numbers
        let mut b = vec![1u8];
        b.extend(code.to_le_bytes());
        counts.iter().for_each(|c| b.extend(c.to_le_bytes()));
        body.iter().for_each(|x| b.extend(x.to_le_bytes()));
        b
    }

    #[test]
    fn wkb_geometries_in_one_buffer() {
        let mut g = FeatureTable::geometries();
        g.push_wkb(Some(&le_wkb(1, &[7.4, 43.7], &[]))).unwrap();
        g.push_wkb(Some(&le_wkb(2, &[0.0, 0.0, 1.0, 1.0], &[2]))).unwrap();
        g.push_wkb(None).unwrap();
        // a polygon of one ring of 4 points: the ring count, then the point count, then the points
        let mut poly = vec![1u8];
        poly.extend(3u32.to_le_bytes());
        poly.extend(1u32.to_le_bytes());
        poly.extend(4u32.to_le_bytes());
        [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0f64].iter().for_each(|x| poly.extend(x.to_le_bytes()));
        g.push_wkb(Some(&poly)).unwrap();
        assert_eq!(g.len(), 4);
        assert_eq!(g.to_geojson(0), json!({"type": "Point", "coordinates": [7.4, 43.7]}));
        assert_eq!(g.to_geojson(1), json!({"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]}));
        assert_eq!(g.to_geojson(2), Value::Null);
        assert_eq!(g.to_geojson(3)["coordinates"][0].as_array().unwrap().len(), 4);
        assert_eq!(g.points(), 1 + 2 + 4);
        assert!(g.push_wkb(Some(&[1, 9, 0, 0, 0])).is_err());
    }
}
