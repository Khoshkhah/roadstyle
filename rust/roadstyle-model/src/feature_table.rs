//! The base map's and the overlays' features as one typed table (audit R10, docs/design/r10_feature_table.md): the properties as Arrow
//! columns (a `RoadTable` with no lines, so its column types and its `Cell` reads are the one rule) and the geometry of every feature in
//! one coordinate buffer, with the offsets of its parts and rings (GeoArrow's form). No JSON tree for each feature.

use crate::geom::Geom;
use crate::table::{Cell, JsSafe, Lines, RoadTable};
use arrow_array::{ArrayRef, BooleanArray, Float64Array, Int64Array, NullArray, StringArray};
use serde_json::{json, Value};
use std::sync::Arc;

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
        self.push_slices(kind, parts.iter().map(|rings| rings.iter().map(Vec::as_slice)));
    }

    fn push_slices<'a, R: IntoIterator<Item = &'a [[f64; 2]]>>(&mut self, kind: GeomType, parts: impl IntoIterator<Item = R>) {
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

    /// The feature `row` of `from`, as it is.
    pub fn push_copy(&mut self, from: &Geometries, row: usize) {
        match from.kinds[row] {
            None => self.push_none(),
            Some(kind) => self.push_slices(kind, from.parts(row)),
        }
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

    /// The feature `row`'s geometry as the engine's `Geom` (a copy; None: it has none).
    pub fn geom(&self, row: usize) -> Option<Geom> {
        let parts: Parts = self.parts(row).map(|rings| rings.map(<[_]>::to_vec).collect()).collect();
        let firsts = || parts.iter().map(|p| p[0].clone());      // the one ring of each part of a MultiPoint or a MultiLineString
        Some(match self.kinds[row]? {
            GeomType::Point => Geom::Point(parts[0][0][0]),
            GeomType::LineString => Geom::LineString(parts[0][0].clone()),
            GeomType::Polygon => Geom::Polygon(parts[0].clone()),
            GeomType::MultiPoint => Geom::MultiPoint(firsts().map(|r| r[0]).collect()),
            GeomType::MultiLineString => Geom::MultiLineString(firsts().collect()),
            GeomType::MultiPolygon => Geom::MultiPolygon(parts),
        })
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

/// The features: their properties (`props`, a `RoadTable` with no lines) and their geometries, one of each for each feature. Each
/// column has its rule for GeoJSON (`Rule`).
#[derive(Clone, Debug)]
pub struct FeatureTable {
    names: Vec<String>,
    cols: Vec<ArrayRef>, // the arrays of `props` (shared), to add a column
    rules: Vec<Rule>,
    props: RoadTable,
    geoms: Geometries,
}

/// How a column goes into a GeoJSON feature: `nulls`: a null is written (`"name": null`), else the feature has no such key; `ints`: the
/// rows of a Float64 column that hold an integer (Python's int beside its floats, as mapstyle's heights: 6 from the kind's table, 9.0
/// from a tag), written as integers.
#[derive(Clone, Debug, Default)]
struct Rule {
    nulls: bool,
    ints: Option<Vec<bool>>,
}

impl FeatureTable {
    /// The table of the columns `names` (each as long as `geoms`), each null left out of a GeoJSON feature. An error for a column of
    /// another type or length.
    pub fn new(names: Vec<String>, cols: Vec<ArrayRef>, geoms: Geometries) -> Result<FeatureTable, String> {
        let rules = vec![Rule::default(); names.len()];
        let props = RoadTable::new(names.clone(), cols.clone(), no_lines(geoms.len()))?;
        Ok(FeatureTable { names, cols, rules, props, geoms })
    }

    /// An empty builder of the geometries, for `new`.
    pub fn geometries() -> Geometries {
        Geometries::new()
    }

    /// The table with the geometries `geoms` in place of its own (one for each feature).
    pub fn with_geometries(mut self, geoms: Geometries) -> Result<FeatureTable, String> {
        if geoms.len() != self.len() {
            return Err(format!("{} geometries for {} features", geoms.len(), self.len()));
        }
        self.geoms = geoms;
        Ok(self)
    }

    /// Set the column `name` to `cells` (one for each feature; in its place when it is there, else as the last column), its type from
    /// the cells: text, true/false, integers, or numbers (integers and floats: a Float64 column that knows its integers). `nulls`: a null
    /// is written in GeoJSON. An error for cells of two other types or a JSON array or object.
    pub fn set_column(&mut self, name: &str, cells: &[Cell], nulls: bool) -> Result<(), String> {
        if cells.len() != self.len() {
            return Err(format!("column {name}: {} values for {} features", cells.len(), self.len()));
        }
        let cells: Vec<Cell> = cells.iter().map(|c| plain(*c)).collect::<Result<_, _>>().map_err(|e| format!("column {name}: {e}"))?;
        let has = |f: fn(&Cell) -> bool| cells.iter().any(f);
        let (text, bool, int, float) = (has(|c| matches!(c, Cell::Str(_))), has(|c| matches!(c, Cell::Bool(_))),
                                        has(|c| matches!(c, Cell::Int(_))), has(|c| matches!(c, Cell::Float(_))));
        let mut ints = None;
        let array: ArrayRef = match (text, bool, int, float) {
            (false, false, false, false) => Arc::new(NullArray::new(cells.len())),
            (true, false, false, false) => Arc::new(cells.iter().map(|c| c.as_str()).collect::<StringArray>()),
            (false, true, false, false) => Arc::new(cells.iter().map(|c| c.as_bool()).collect::<BooleanArray>()),
            (false, false, true, false) => Arc::new(cells.iter().map(|c| c.as_i64()).collect::<Int64Array>()),
            (false, false, _, true) => {
                // ponytail: an integer past 2**53 in a column of numbers loses its last digits; none of the base map's is one
                ints = int.then(|| cells.iter().map(|c| matches!(c, Cell::Int(_))).collect());
                Arc::new(cells.iter().map(|c| match c { Cell::Float(f) => Some(*f), c => c.as_f64() }).collect::<Float64Array>())
            }
            _ => return Err(format!("column {name}: values of more than one type")),
        };
        let rule = Rule { nulls, ints };
        match self.names.iter().position(|n| n == name) {
            Some(i) => (self.cols[i], self.rules[i]) = (array, rule),
            None => {
                self.names.push(name.to_string());
                self.cols.push(array);
                self.rules.push(rule);
            }
        }
        self.props = RoadTable::new(self.names.clone(), self.cols.clone(), no_lines(self.len()))?;
        Ok(())
    }

    pub fn len(&self) -> usize {
        self.geoms.len()
    }

    pub fn is_empty(&self) -> bool {
        self.geoms.is_empty()
    }

    pub fn names(&self) -> &[String] {
        &self.names
    }

    /// The property `name` of the feature `row` (None: no such column).
    pub fn get(&self, row: usize, name: &str) -> Option<Cell<'_>> {
        let c = self.props.col(name)?;
        Some(match (self.props.cell(c, row), &self.rules[c].ints) {
            (Cell::Float(f), Some(ints)) if ints[row] => Cell::Int(f as i64),
            (cell, _) => cell,
        })
    }

    pub fn geometries_of(&self) -> &Geometries {
        &self.geoms
    }

    /// The GeoJSON feature `row` has the key `name` (its column, with a value or a null that is written).
    pub fn has_key(&self, row: usize, name: &str) -> bool {
        self.props.col(name).is_some_and(|c| self.rules[c].nulls || !self.props.cell(c, row).is_null())
    }

    /// The feature `row` as a GeoJSON feature: its properties (by each column's rule) and its geometry.
    pub fn to_geojson(&self, row: usize) -> Value {
        let props: serde_json::Map<String, Value> = self.names.iter().filter(|n| self.has_key(row, n))
            .filter_map(|n| self.get(row, n).map(|c| (n.clone(), c.to_value()))).collect();
        json!({"type": "Feature", "properties": props, "geometry": self.geoms.to_geojson(row)})
    }

    /// The features as a GeoJSON FeatureCollection, written to `w` a feature at a time (an integer past 2**53 - 1 as text, `JsSafe`).
    /// ponytail: a JSON value for each feature on the way; write the cells straight when the writer shows in a profile.
    pub fn write_geojson<W: std::io::Write>(&self, w: &mut W) -> std::io::Result<()> {
        w.write_all(br#"{"type":"FeatureCollection","features":["#)?;
        for row in 0..self.len() {
            if row > 0 {
                w.write_all(b",")?;
            }
            serde_json::to_writer(&mut *w, &JsSafe(&self.to_geojson(row)))?;
        }
        w.write_all(b"]}")
    }

    /// The features as a GeoJSON FeatureCollection value.
    pub fn to_value(&self) -> Value {
        json!({"type": "FeatureCollection", "features": (0..self.len()).map(|r| self.to_geojson(r)).collect::<Vec<_>>()})
    }
}

/// The lines of a RoadTable of `n` rows with none (the props of a FeatureTable).
fn no_lines(n: usize) -> Lines {
    let mut lines = Lines::default();
    (0..n).for_each(|_| lines.push(None));
    lines
}

/// A cell as a column holds it: a JSON value (an engine value) as its plain kind.
fn plain(c: Cell) -> Result<Cell, String> {
    let Cell::Json(v) = c else { return Ok(c) };
    Ok(match v {
        Value::Null => Cell::Null,
        Value::Bool(b) => Cell::Bool(*b),
        Value::Number(n) => n.as_i64().map_or_else(|| Cell::Float(n.as_f64().unwrap_or(f64::NAN)), Cell::Int),
        Value::String(s) => Cell::Str(s),
        _ => return Err("a JSON array or object".into()),
    })
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

    #[test]
    fn a_column_keeps_its_integers_and_its_rule_for_nulls() {
        let mut g = FeatureTable::geometries();
        g.push(GeomType::Point, &[vec![vec![[1.0, 2.0]]]]);
        g.push_none();
        let mut t = FeatureTable::new(Vec::new(), Vec::new(), g).unwrap();
        let six = json!(6);
        t.set_column("name", &[Cell::Null, Cell::Str("A")], true).unwrap();
        t.set_column("height", &[Cell::from(&six), Cell::Float(9.0)], true).unwrap();
        t.set_column("bearing", &[Cell::Float(90.0), Cell::Null], false).unwrap();
        let text = |r: usize| serde_json::to_string(&t.to_geojson(r)["properties"]).unwrap();
        // mapstyle's heights: 6 from the kind's table, 9.0 from a tag; a null name is written, a missing bearing is no key
        assert_eq!(text(0), r#"{"name":null,"height":6,"bearing":90.0}"#);
        assert_eq!(text(1), r#"{"name":"A","height":9.0}"#);
        let mut out = Vec::new();
        t.write_geojson(&mut out).unwrap();
        assert_eq!(serde_json::from_slice::<Value>(&out).unwrap(), t.to_value());
        assert!(t.set_column("x", &[Cell::Str("a"), Cell::Int(1)], true).is_err(), "text and numbers");
        assert!(t.set_column("x", &[Cell::Null], true).is_err(), "one value for two features");
        let mut c = FeatureTable::geometries();
        c.push_copy(t.geometries_of(), 0);
        c.push_copy(t.geometries_of(), 1);
        assert_eq!((c.to_geojson(0), c.to_geojson(1)), (t.geometries_of().to_geojson(0), Value::Null));
        assert!(matches!(t.geometries_of().geom(0), Some(Geom::Point([1.0, 2.0]))));
    }
}
