//! The roads that the stages draw: the input table (roadstyle-model's `RoadTable`) and the drawing values of each road (`Draw`), whose
//! properties are the `__rs_*` marks and `lvl` in the order that the stages set them (render_web.render's order). A road's property is
//! its mark, else its column: a mark takes the place of a column of the same name, as a dict's assignment does in Python. The output
//! writes the columns in their order and then the other marks, so the text is the text of the old JSON object of each road.

use roadstyle_model::mark;
use crate::draw::{Draw, Values};
use crate::props::Get;
use roadstyle_model::topology::Topology;
use roadstyle_model::{Cell, RoadKey, RoadTable, Role, Roles};
use serde_json::{Map, Value};

pub type Pt = [f64; 2];

pub struct Roads {
    pub table: RoadTable,
    pub draw: Vec<Draw>,
    /// the style values that the roads' `Draw` names by number
    pub values: Values,
    /// a view's palettes (palettes.rs): the marks that another palette sets to other values, after the road's own properties
    pub extra: Vec<Extra>,
    /// the column of the class filter (render's filter_col, else the class role's column): `__rs_cls` is its value
    pub cls: String,
    /// the roles of the table's columns (the class, the edge id, the flags, the levels): the stages read a role's cell by its index
    pub roles: Roles,
    /// the warnings of the stages (Python's warnings.warn in render_web), for the caller (`Styled::warnings`)
    pub warnings: Vec<String>,
    /// the drawing positions that the engine solved (casing_start, casing_level, casing_end, fill_level of each road), given under the
    /// contract names after the road's columns; None: the input has them (lib.rs compute_levels)
    pub solved: Option<Vec<[i16; 4]>>,
    /// the output's name of each column: its own, or `__rs_kept_<name>` for a column of a contract level name when the engine solved
    /// the levels (the solved ones take the contract names)
    out: Vec<String>,
    topo: std::sync::OnceLock<Box<Topology>>,
}

/// A mark in another palette (render_web._merge_palettes): `<mark>@<palette>` with each road's value there (None: that road has no
/// such mark in that palette).
pub struct Extra {
    pub name: String,
    pub key: String,
    pub vals: Vec<Option<Value>>,
}

impl Roads {
    /// The roads of `table`, with the roles of its columns and the levels that the engine solved (None: the input has them).
    pub fn new(table: RoadTable, roles: Roles, solved: Option<Vec<[i16; 4]>>) -> Roads {
        let draw = vec![Draw::default(); table.len()];
        let level = |n: &str| solved.is_some() && SOLVED.iter().any(|m| m.name() == n);
        let out = table.names().iter().map(|n| if level(n) { kept(n) } else { n.clone() }).collect();
        let cls = roles.name(&table, Role::Class).unwrap_or(Role::Class.name()).to_string();
        Roads { table, draw, values: Values::default(), extra: Vec::new(), cls, roles, warnings: Vec::new(), solved, out,
                topo: std::sync::OnceLock::new() }
    }

    pub fn len(&self) -> usize {
        self.table.len()
    }

    pub fn is_empty(&self) -> bool {
        self.table.is_empty()
    }

    pub fn road(&self, i: usize) -> Road<'_> {
        Road { t: &self.table, d: &self.draw[i], v: &self.values, x: &self.extra, c: &self.cls, ro: &self.roles, o: &self.out,
               s: self.solved.as_ref().map(|s| &s[i]), i }
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

    /// The role's cell of the road `i` (`Road::role`).
    pub fn role(&self, i: usize, r: Role) -> Option<Cell<'_>> {
        self.road(i).role(r)
    }

    pub fn line(&self, i: usize) -> Option<&[Pt]> {
        self.table.line(i)
    }

    /// The roads' nodes and their R-tree, made the first time a stage asks (the lines do not change after that).
    pub fn topo(&self) -> &Topology {
        self.topo.get_or_init(|| Box::new(Topology::new(&self.table)))
    }
}

/// One road: a view of its column values and its marks.
#[derive(Clone, Copy)]
pub struct Road<'a> {
    t: &'a RoadTable,
    d: &'a Draw,
    v: &'a Values,
    x: &'a [Extra],
    c: &'a str,
    ro: &'a Roles,
    /// the output's names of the columns
    o: &'a [String],
    /// its solved drawing positions (casing_start, casing_level, casing_end, fill_level), when the engine solved them
    s: Option<&'a [i16; 4]>,
    pub i: usize,
}

/// The contract names of the solved drawing positions, in their order.
const SOLVED: [mark::Mark; 4] = [mark::Mark::CasingStartColumn, mark::Mark::CasingLevelColumn, mark::Mark::CasingEndColumn, mark::Mark::FillLevelColumn];

impl<'a> Road<'a> {
    /// A property by its output name (`own`): its mark, a solved level, its column, else its mark in another palette.
    pub fn get(self, k: &str) -> Option<Cell<'a>> {
        self.d.get(self.v, self.i, k)
            .or_else(|| self.s.and_then(|s| SOLVED.iter().position(|m| m.name() == k).map(|j| Cell::Int(s[j].into()))))
            .or_else(|| self.o.iter().position(|n| n == k).map(|c| self.t.cell(c, self.i)))
            .or_else(|| self.x.iter().find(|e| e.name == k).and_then(|e| e.vals[self.i].as_ref().map(Cell::Json)))
    }

    /// The road's cell of a role: a solved level when the engine solved the levels, else the role's column (None: the table has none).
    pub fn role(self, r: Role) -> Option<Cell<'a>> {
        let level = [Role::CasingStart, Role::CasingLevel, Role::CasingEnd, Role::FillLevel].iter().position(|l| *l == r);
        match (self.s, level) {
            (Some(s), Some(j)) => Some(Cell::Int(s[j].into())),
            _ => self.ro.cell(self.t, r, self.i),
        }
    }

    /// The road's value of the class filter (render's fcol).
    pub fn cls(self) -> Value {
        self.get(self.c).map_or(Value::Null, Cell::to_value)
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

    /// The road's own properties in the output's order: the columns (a mark in the place of a column of its name), then the other marks.
    pub fn own(self) -> impl Iterator<Item = (&'a str, Cell<'a>)> {
        let (t, d, v, i) = (self.t, self.d, self.v, self.i);
        let solved = self.s.into_iter().flat_map(|s| SOLVED.iter().zip(s).map(|(m, x)| (m.name(), Cell::Int((*x).into()))));
        let o = self.o;
        t.names().iter().enumerate().map(move |(c, n)| (o[c].as_str(), d.get(v, i, n).unwrap_or_else(|| t.cell(c, i))))
            .chain(solved)
            .chain(d.marks(v, i).into_iter().filter(move |(k, _)| t.col(k).is_none()))
    }

    /// The properties in the output's order: its own, then its marks in the other palettes of the views.
    pub fn iter(self) -> impl Iterator<Item = (&'a str, Cell<'a>)> {
        let i = self.i;
        self.own().chain(self.x.iter().filter_map(move |e| e.vals[i].as_ref().map(|v| (e.name.as_str(), Cell::Json(v)))))
    }

    pub fn to_map(self) -> Map<String, Value> {
        self.iter().map(|(k, v)| (k.to_string(), v.to_value())).collect()
    }

}

/// The JSON text of a road's properties, as serde_json writes them as a `Map`.
fn write_props<'a>(out: &mut Vec<u8>, props: impl Iterator<Item = (&'a str, Cell<'a>)>) {
    out.push(b'{');
    for (n, (k, v)) in props.enumerate() {
        if n > 0 {
            out.push(b',');
        }
        serde_json::to_writer(&mut *out, k).unwrap();
        out.push(b':');
        serde_json::to_writer(&mut *out, &v).unwrap();
    }
    out.push(b'}');
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
    /// the style has the source `roads` (the export); a page has none: its pieces draw, and the road table has the fields and the lines
    pub in_style: bool,
    /// R1: the only stage values (`__rs_*`) that a road keeps (`Styled::set_reads`), None: all; its fields stay
    pub read: Option<std::collections::HashSet<String>>,
}

/// The key of the road in the row `row` (`__rs_edge`): table 0, as a build has one road table (make_parts keeps the rows below
/// MAX_ROADS, so a row fits in 32 bits).
pub fn key(row: usize) -> RoadKey {
    RoadKey::of_row(row as u32)
}

/// The row of a road from its key's number (`__rs_edge`, `__rs_edge2`).
pub fn row_of(key: u64) -> Option<usize> {
    RoadKey::from_u64(key).map(|k| k.row() as usize)
}

/// The output's name of a column of a contract level name when the engine solved the levels (`Roads::new`).
pub fn kept(own: &str) -> String {
    format!("{}{own}", mark::KEPT)
}

impl RoadsSource {
    /// A road's properties, as the roads source writes them in every form (GeoJSON, GeoParquet, tiles): its fields that `keep` takes
    /// (None: all), and the stage values that are read (R1: `read`).
    pub fn props<'a>(&'a self, r: Road<'a>, keep: Option<&'a std::collections::HashSet<String>>) -> impl Iterator<Item = (&'a str, Cell<'a>)> + 'a {
        r.iter().filter(move |(k, _)| {
            if k.starts_with(mark::PREFIX) { self.read.as_ref().is_none_or(|s| s.contains(*k)) } else { keep.is_none_or(|s| s.contains(*k)) }
        })
    }

    /// The source as JSON text, written to `w` a part at a time.
    pub fn write_json<W: std::io::Write>(&self, w: &mut W) -> std::io::Result<()> {
        w.write_all(br#"{"type":"geojson","data":"#)?;
        self.write_data(w, None, true)?;
        w.write_all(br#","tolerance":"#)?;
        serde_json::to_writer(&mut *w, &self.tolerance)?;
        if let Some(z) = self.maxzoom {
            write!(w, r#","maxzoom":{z}"#)?;
        }
        w.write_all(b"}")
    }

    /// The FeatureCollection of the roads, written to `w` a part at a time; `keep`: only these properties (by the output's name) and
    /// every `__rs_*` one; `lines`: the roads' lines (else each geometry is null: the road table has them).
    pub fn write_data<W: std::io::Write>(&self, w: &mut W, keep: Option<&std::collections::HashSet<String>>, lines: bool) -> std::io::Result<()> {
        let mut out = Vec::new();
        out.extend_from_slice(br#"{"type":"FeatureCollection","features":["#);
        for r in self.roads.iter() {
            if out.len() > 1 << 16 {
                w.write_all(&out)?;
                out.clear();
            }
            if r.i > 0 {
                out.push(b',');
            }
            out.extend_from_slice(format!(r#"{{"id":{},"type":"Feature","properties":"#, r.i).as_bytes());
            write_props(&mut out, self.props(r, keep));
            out.extend_from_slice(br#","geometry":"#);
            match r.line().filter(|_| lines) {
                None => out.extend_from_slice(b"null"),
                Some(c) => {
                    out.extend_from_slice(br#"{"type":"LineString","coordinates":"#);
                    serde_json::to_writer(&mut out, c).unwrap();
                    out.push(b'}');
                }
            }
            out.push(b'}');
        }
        out.extend_from_slice(b"]}");
        w.write_all(&out)
    }
}
