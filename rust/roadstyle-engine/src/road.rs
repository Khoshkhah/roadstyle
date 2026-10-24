//! The roads that the stages draw: the input table (roadstyle-model's `RoadTable`) and the marks of each road, the `__rs_*` properties
//! and `lvl` in the order that the stages set them (render_web.render's order). A road's property is its mark, else its column: a
//! mark takes the place of a column of the same name, as a dict's assignment does in Python. The output writes the columns in their
//! order and then the other marks, so the text is the text of the old JSON object of each road.

use crate::props::{Get, Props};
use roadstyle_model::{Cell, RoadTable};
use serde_json::{Map, Value};

pub type Pt = [f64; 2];

pub struct Roads {
    pub table: RoadTable,
    pub marks: Vec<Props>,
}

impl Roads {
    pub fn new(table: RoadTable) -> Roads {
        let marks = vec![Props::default(); table.len()];
        Roads { table, marks }
    }

    pub fn len(&self) -> usize {
        self.table.len()
    }

    pub fn is_empty(&self) -> bool {
        self.table.is_empty()
    }

    pub fn road(&self, i: usize) -> Road<'_> {
        Road { t: &self.table, m: &self.marks[i], i }
    }

    /// The road `i`, or None past the last road.
    pub fn at(&self, i: usize) -> Option<Road<'_>> {
        (i < self.len()).then(|| self.road(i))
    }

    pub fn iter(&self) -> impl ExactSizeIterator<Item = Road<'_>> + Clone {
        (0..self.len()).map(|i| self.road(i))
    }

    /// A property of the road `i` (its mark, else its column).
    pub fn get(&self, i: usize, k: &str) -> Option<Cell<'_>> {
        self.road(i).get(k)
    }

    pub fn line(&self, i: usize) -> Option<&[Pt]> {
        self.table.line(i)
    }

    /// The marks of the road `i` (its `__rs_*` properties and `lvl`).
    pub fn marks(&self, i: usize) -> &Props {
        &self.marks[i]
    }
}

/// One road: a view of its column values and its marks.
#[derive(Clone, Copy)]
pub struct Road<'a> {
    t: &'a RoadTable,
    m: &'a Props,
    pub i: usize,
}

impl<'a> Road<'a> {
    pub fn get(self, k: &str) -> Option<Cell<'a>> {
        self.m.cell(k).or_else(|| self.t.get(self.i, k))
    }

    pub fn contains_key(self, k: &str) -> bool {
        self.m.contains_key(k) || self.t.col(k).is_some()
    }

    pub fn line(self) -> Option<&'a [Pt]> {
        self.t.line(self.i)
    }

    pub fn marks(self) -> &'a Props {
        self.m
    }

    /// The properties in the output's order: the columns (a mark in the place of a column of its name), then the other marks.
    pub fn iter(self) -> impl Iterator<Item = (&'a str, Cell<'a>)> {
        let (t, m, i) = (self.t, self.m, self.i);
        t.names().iter().enumerate().map(move |(c, n)| (n.as_str(), m.cell(n).unwrap_or_else(|| t.cell(c, i))))
            .chain(m.iter().filter(move |(k, _)| t.col(k).is_none()).map(|(k, v)| (k, Cell::Json(v))))
    }

    pub fn to_map(self) -> Map<String, Value> {
        self.iter().map(|(k, v)| (k.to_string(), v.to_value())).collect()
    }

    /// The JSON text of the properties, as serde_json writes the `Map` of `to_map`.
    pub fn write_json(self, out: &mut Vec<u8>) {
        out.push(b'{');
        for (n, (k, v)) in self.iter().enumerate() {
            if n > 0 {
                out.push(b',');
            }
            serde_json::to_writer(&mut *out, k).unwrap();
            out.push(b':');
            serde_json::to_writer(&mut *out, &v).unwrap();
        }
        out.push(b'}');
    }
}

impl Get for Road<'_> {
    fn value(&self, k: &str) -> Option<Value> {
        self.get(k).map(Cell::to_value)
    }
}

/// The "roads" source: `{"type": "geojson", "data": {...}, "tolerance": t}` with each road as `{"id", "type", "properties", "geometry"}`
/// (the id is the road's index), written from the table and the marks.
pub struct RoadsSource {
    pub roads: Roads,
    pub tolerance: f64,
    /// render's data_maxzoom (None: MapLibre's default)
    pub maxzoom: Option<i64>,
}

impl RoadsSource {
    pub fn write_json(&self, out: &mut Vec<u8>) {
        out.extend_from_slice(br#"{"type":"geojson","data":{"type":"FeatureCollection","features":["#);
        for r in self.roads.iter() {
            if r.i > 0 {
                out.push(b',');
            }
            out.extend_from_slice(format!(r#"{{"id":{},"type":"Feature","properties":"#, r.i).as_bytes());
            r.write_json(out);
            out.extend_from_slice(br#","geometry":"#);
            match r.line() {
                None => out.extend_from_slice(b"null"),
                Some(c) => {
                    out.extend_from_slice(br#"{"type":"LineString","coordinates":"#);
                    serde_json::to_writer(&mut *out, c).unwrap();
                    out.push(b'}');
                }
            }
            out.push(b'}');
        }
        out.extend_from_slice(br#"]},"tolerance":"#);
        serde_json::to_writer(&mut *out, &self.tolerance).unwrap();
        if let Some(z) = self.maxzoom {
            out.extend_from_slice(br#","maxzoom":"#);
            out.extend_from_slice(z.to_string().as_bytes());
        }
        out.push(b'}');
    }
}
