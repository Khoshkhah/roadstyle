//! The roads that the stages draw: the input table (roadstyle-model's `RoadTable`) and the drawing values of each road (`Draw`), whose
//! properties are the `__rs_*` marks and `lvl` in the order that the stages set them (render_web.render's order). A road's property is
//! its mark, else its column: a mark takes the place of a column of the same name, as a dict's assignment does in Python. The output
//! writes the columns in their order and then the other marks, so the text is the text of the old JSON object of each road.

use crate::draw::{Draw, Values};
use crate::props::Get;
use roadstyle_model::{Cell, RoadTable};
use serde_json::{Map, Value};

pub type Pt = [f64; 2];

pub struct Roads {
    pub table: RoadTable,
    pub draw: Vec<Draw>,
    /// the style values that the roads' `Draw` names by number
    pub values: Values,
}

impl Roads {
    pub fn new(table: RoadTable) -> Roads {
        let draw = vec![Draw::default(); table.len()];
        Roads { table, draw, values: Values::default() }
    }

    pub fn len(&self) -> usize {
        self.table.len()
    }

    pub fn is_empty(&self) -> bool {
        self.table.is_empty()
    }

    pub fn road(&self, i: usize) -> Road<'_> {
        Road { t: &self.table, d: &self.draw[i], v: &self.values, i }
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
}

/// One road: a view of its column values and its marks.
#[derive(Clone, Copy)]
pub struct Road<'a> {
    t: &'a RoadTable,
    d: &'a Draw,
    v: &'a Values,
    pub i: usize,
}

impl<'a> Road<'a> {
    pub fn get(self, k: &str) -> Option<Cell<'a>> {
        self.d.get(self.v, k).or_else(|| self.t.get(self.i, k))
    }

    pub fn contains_key(self, k: &str) -> bool {
        self.get(k).is_some()
    }

    pub fn line(self) -> Option<&'a [Pt]> {
        self.t.line(self.i)
    }

    /// The road's drawing values.
    pub fn draw(self) -> &'a Draw {
        self.d
    }

    /// The properties in the output's order: the columns (a mark in the place of a column of its name), then the other marks.
    pub fn iter(self) -> impl Iterator<Item = (&'a str, Cell<'a>)> {
        let (t, d, v, i) = (self.t, self.d, self.v, self.i);
        t.names().iter().enumerate().map(move |(c, n)| (n.as_str(), d.get(v, n).unwrap_or_else(|| t.cell(c, i))))
            .chain(d.marks(v).into_iter().filter(move |(k, _)| t.col(k).is_none()))
    }

    pub fn to_map(self) -> Map<String, Value> {
        self.iter().map(|(k, v)| (k.to_string(), v.to_value())).collect()
    }

    /// The JSON text of the properties, as serde_json writes the `Map` of `to_map`, with the output's names (`name`), those that
    /// `keep` takes (by the output's name).
    pub fn write_json<'n>(self, out: &mut Vec<u8>, name: impl Fn(&'n str) -> &'n str, keep: impl Fn(&str) -> bool) where 'a: 'n {
        out.push(b'{');
        for (n, (k, v)) in self.iter().map(|(k, v)| (name(k), v)).filter(|(k, _)| keep(k)).enumerate() {
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
    /// the column keywords (ColumnMap): each column with an engine name (`own`) and the user's name for it
    pub names: Vec<(&'static str, String)>,
}

/// The name of a kept column (a column with an engine name that is not the named one) while the engine runs.
pub fn kept(own: &str) -> String {
    format!("__rs_kept_{own}")
}

impl RoadsSource {
    /// The output's name of a property: the user's name of an engine column, and a kept column's own name back.
    pub fn out_name<'n>(&'n self, k: &'n str) -> &'n str {
        if let Some((_, user)) = self.names.iter().find(|(own, _)| *own == k) {
            return user;
        }
        k.strip_prefix("__rs_kept_").and_then(|o| self.names.iter().find(|(own, _)| *own == o)).map_or(k, |(own, _)| own)
    }

    pub fn write_json(&self, out: &mut Vec<u8>) {
        out.extend_from_slice(br#"{"type":"geojson","data":"#);
        self.write_data(out, None);
        out.extend_from_slice(br#","tolerance":"#);
        serde_json::to_writer(&mut *out, &self.tolerance).unwrap();
        if let Some(z) = self.maxzoom {
            out.extend_from_slice(br#","maxzoom":"#);
            out.extend_from_slice(z.to_string().as_bytes());
        }
        out.push(b'}');
    }

    /// The FeatureCollection of the roads; `keep`: only these properties (by the output's name) and every `__rs_*` one.
    pub fn write_data(&self, out: &mut Vec<u8>, keep: Option<&std::collections::HashSet<String>>) {
        out.extend_from_slice(br#"{"type":"FeatureCollection","features":["#);
        for r in self.roads.iter() {
            if r.i > 0 {
                out.push(b',');
            }
            out.extend_from_slice(format!(r#"{{"id":{},"type":"Feature","properties":"#, r.i).as_bytes());
            r.write_json(out, |k| self.out_name(k), |k| keep.is_none_or(|s| k.starts_with("__rs_") || s.contains(k)));
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
        out.extend_from_slice(b"]}");
    }
}
