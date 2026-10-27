//! The "simple" source: simple mode's one road layer, every casing piece and every fill (render_web._casing_parts, _halves, _end_stub,
//! _simple_pieces), from the roads after their stages (roads::mark_roads). The geometry is computed as numpy computes it: a flat
//! projection at the line's first point, sequential sums, `hypot`, and numpy's rounding (`rint(x * 10^d) / 10^d`).
//! A piece is typed (`Piece`: its road, what it draws, its place in the road layer, its line); its JSON properties are made only at the
//! output (`Piece::props`), from its road, with render_web's keys in render_web's order.

use roadstyle_model::mark::{self, Mark};
use crate::draw::Cap;
use crate::props::{Get, Props};
use crate::road::{Road, Roads};
use crate::roads::truthy;
use roadstyle_model::Cell;
use serde_json::Value;
use std::collections::{HashMap, HashSet};

const SEAM_M: f64 = 0.5; // a seam reaches this far each way from its cut, at most a quarter of either piece
const LAP_M: f64 = 2.0; // a lap (the flat seam below zoom 17) reaches this far each way, at most half of either piece
const PIECES: usize = 24; // the most pieces of one edge (the feature id is edge * PIECES + n)
// the line-sort-key `__rs_s` is an integer, KEY_UNIT for each unit of the key (2 * position + the kind's step) and 1 for each edge: the
// tie-breaker per edge, so that a road redrawn in place keeps its place. An integer is a varint in a tile, a double 9 bytes.
pub(crate) const KEY_UNIT: f64 = 1e8;
const MAX_EDGES: usize = 1_000_000;
const ITEM_STEP: f64 = 0.01; // an item's step above its edge's fill, by its rank on the edge
const MAX_ITEMS: usize = 38; // the most items of one edge between its fill and the next casings

pub type Pt = [f64; 2];

/// A piece's properties: its road's cells and its marks, with no copy (`Props::to_values`: the JSON form).
pub type Cells<'a> = Props<'a, Cell<'a>>;

/// An item on a road (an overlay's line in metres, render's items=): its own properties and its line.
pub struct Item {
    pub props: Props<'static>,
    pub coords: Option<Vec<Pt>>,
}

/// What a piece draws of its road.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Part {
    /// the road's whole casing (no cut)
    Casing,
    /// a cut part of the casing (0 the start head, 1 the main part, 2 the end head), with its casing number
    Cut(u8, i64),
    /// a seam at a cut (at the lower number of its two parts), and the flat lap under it
    Seam(i64),
    Lap(i64),
    /// the road's whole fill, or a half of it (0 or 1: an edge with two different ends)
    Fill,
    Half(u8),
}

/// _end_stub: a piece as it is, the piece drawn flat (its stub has the road end's shape), or that stub.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum End {
    AsIs,
    Flat,
    Stub,
}

/// The place of a piece in simple mode's one road layer (docs/design/rust_library.md, "The order of the whole map: DrawKey"): its kind
/// (`__rs_k`: 0 casing, 1 fill, 2 bridge shadow, 3 tunnel gap, 4 tunnel dashes) and its sort key before the edge's tie-breaker.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct DrawKey {
    pub kind: i64,
    pub key: f64,
}

/// A piece's line (audit R11): its road's line, with no copy, or a line of its own (a cut, a half, a seam, a stub, a mitred end),
/// shared by the pieces of one cut (the bridge shadow, the tunnel's gap and dashes).
#[derive(Clone, Debug)]
pub enum PieceLine {
    None,
    Road,
    Own(std::sync::Arc<Vec<Pt>>),
}

impl PieceLine {
    fn own(c: Vec<Pt>) -> PieceLine {
        PieceLine::Own(std::sync::Arc::new(c))
    }
}

/// A piece of a road: the road's row, what it draws, its line, and its place in the road layer (simple mode only).
#[derive(Clone, Debug)]
pub struct Piece {
    pub edge: u32,
    pub part: Part,
    pub end: End,
    pub draw: Option<DrawKey>,
    pub coords: PieceLine,
}

/// The columns that the pieces keep besides the marks: the class role's, the class filter's (render's filter_col) and the metre width's
/// (width_m_col), each by its own name in the table.
#[derive(Clone, Debug)]
pub struct Cols {
    pub class: String,
    pub fcol: String,
    pub width: Option<String>,
}

impl Cols {
    pub fn new(class: &str, fcol: &str, width: Option<&str>) -> Cols {
        Cols { class: class.into(), fcol: fcol.into(), width: width.map(String::from) }
    }

    /// A property of a casing piece: the class, lvl, the metre width's column and every mark but the fills.
    fn casing(&self, k: &str) -> bool {
        k == self.class || k == self.fcol || k == "lvl" || Some(k) == self.width.as_deref() || (k.starts_with(mark::PREFIX) && !mark::is_fill(k))
    }

    /// The piece of `part` has the road's property `k` (a fill's keys, else a casing's).
    pub(crate) fn keeps(&self, part: Part, k: &str) -> bool {
        if matches!(part, Part::Fill | Part::Half(_)) { self.fill(k) } else { self.casing(k) }
    }

    /// A property of a fill piece in simple mode: the same, with the fills.
    fn fill(&self, k: &str) -> bool {
        k == self.class || k == self.fcol || k == "lvl" || Some(k) == self.width.as_deref() || k.starts_with(mark::PREFIX)
    }
}

/// The properties of a road as its cells (no copy), those that `keep` takes. The road's own `__rs_cls` (set later, for the roads source) is
/// not one: a piece marks its class itself, as the last property.
/// `only`: the keys to read (the others are not read), None: all.
fn road_props<'a>(r: Road<'a>, only: Option<&[&str]>, keep: impl Fn(&str) -> bool) -> Cells<'a> {
    let keep = |k: &str| own_keeps(k, &keep);
    match only {
        None => r.own_where(&keep).collect(),
        Some(ks) => {
            let mut q = Props::default();
            for k in ks.iter().filter(|k| keep(k)) {
                if let Some(v) = r.own_get(k) {
                    q.insert(k, v);
                }
            }
            q
        }
    }
}

/// A road's own `__rs_cls` is not a piece's (`road_props`).
fn own_keeps(k: &str, keep: impl Fn(&str) -> bool) -> bool {
    k != Mark::Class.name() && keep(k)
}

impl Piece {
    fn road<'a>(&self, roads: &'a Roads) -> Road<'a> {
        roads.road(self.edge as usize)
    }

    /// The piece's line: its own, or its road's.
    pub fn points<'a>(&'a self, roads: &'a Roads) -> Option<&'a [Pt]> {
        match &self.coords {
            PieceLine::None => None,
            PieceLine::Road => roads.line(self.edge as usize),
            PieceLine::Own(c) => Some(c),
        }
    }

    /// The cap of the piece (None: round, there is no `__rs_cap`).
    pub fn cap(&self, roads: &Roads) -> Option<Cap> {
        if self.end == End::Flat {
            return Some(Cap::Flat);
        }
        let d = self.road(roads).draw();
        let c = match self.part {
            Part::Casing | Part::Fill => d.cap,
            Part::Cut(1, _) | Part::Lap(_) => Some(Cap::Flat),
            Part::Cut(k, _) => d.split.map_or(d.cap, |s| Some(s[usize::from(k != 0)])),
            Part::Seam(_) => None,
            Part::Half(k) => d.split.map(|s| s[k as usize]),
        };
        c.filter(|c| *c != Cap::Round)
    }

    /// A seam or its lap (`__rs_seam`).
    pub fn seam(&self) -> bool {
        matches!(self.part, Part::Seam(_) | Part::Lap(_))
    }

    /// The casing number: a cut part's or a seam's, else the road's.
    pub fn cl(&self, roads: &Roads) -> i64 {
        match self.part {
            Part::Cut(_, n) | Part::Seam(n) | Part::Lap(n) => n,
            _ => self.road(roads).draw().levels64().map_or(0, |l| l[0]),
        }
    }

    /// The properties of the piece as render_web makes them, with its keys in its order, and the road layer's `__rs_k`, `__rs_s` (with
    /// the edge's tie-breaker) and `__rs_cls`.
    pub fn props<'a>(&self, roads: &'a Roads, cols: &Cols) -> Props<'a> {
        self.over(roads, cols, self.base(roads, cols, None, None), None).to_values()
    }

    /// What the piece takes of its road's properties.
    fn base_kind(&self) -> Base {
        match self.part {
            Part::Fill => Base::Fill,
            Part::Half(_) => Base::Half,
            _ => Base::Casing,
        }
    }

    /// The road's cells that the piece starts from (the same for each piece of the road of its `base_kind`), with only the road's cells
    /// of the keys `only` (None: all). `read`: no road cell of another key (the road's class stays: the class index reads it), in the
    /// road's order; a slim piece (SimpleSource::slim) then drops nothing more than without it, and a tile's first show makes no value
    /// that goes (Tartu z11).
    fn base<'a>(&self, roads: &'a Roads, cols: &Cols, only: Option<&[&str]>, read: Option<&HashSet<String>>) -> Cells<'a> {
        road_props(self.road(roads), only, self.base_kind().keeps(cols, read))
    }

    /// The piece's properties: its road's cells (`base`) and its own marks. `read`: no mark that is not read (`Run::marks`).
    fn over<'a>(&self, roads: &'a Roads, cols: &Cols, mut q: Cells<'a>, read: Option<&[bool]>) -> Cells<'a> {
        let put = |q: &mut Cells<'a>, k: Mark, v: Cell<'a>| if read.is_none_or(|r| r[k as usize]) {
            q.insert_name(k.name(), v);
        };
        let r = self.road(roads);
        let d = r.draw();
        let (edge, key) = (self.edge as i64, crate::road::key(self.edge as usize).get() as i64);      // the row (the sort key's tie-breaker), the road's key
        match self.part {
            Part::Fill => {}
            Part::Half(k) => {
                put(&mut q, Mark::Edge, Cell::Int(key));
                if let Some(c) = d.split.map(|s| s[k as usize]).filter(|c| *c != Cap::Round) {
                    put(&mut q, Mark::Cap, c.cell());
                }
            }
            _ => {
                put(&mut q, Mark::Edge, Cell::Int(key));
                if let Some(tw) = d.twin {
                    put(&mut q, Mark::Pair, Cell::Bool(true));
                    put(&mut q, Mark::Edge2, Cell::Int(crate::road::key(tw.get()).get() as i64));
                }
                match self.part {
                    Part::Cut(k, num) => {
                        put(&mut q, Mark::CasingLevel, Cell::Int(num));
                        if k == 1 {
                            // the main piece ends at two cuts: flat ends
                            put(&mut q, Mark::Cap, Cell::Bool(true));
                            put(&mut q, Mark::Main, Cell::Bool(true));
                        } else if let Some(s) = d.split {
                            // a head of an edge with two different ends: that end's cap
                            put(&mut q, Mark::Cap, s[usize::from(k != 0)].cell());
                        }
                        if q.get(Mark::Cap.name()).is_none_or(|c| c.to_value().is_null()) {
                            q.shift_remove(Mark::Cap.name());
                        }
                    }
                    Part::Seam(num) | Part::Lap(num) => {
                        put(&mut q, Mark::CasingLevel, Cell::Int(num));
                        put(&mut q, Mark::Seam, Cell::Bool(true));
                        q.shift_remove(Mark::Cap.name());
                        if matches!(self.part, Part::Lap(_)) {
                            put(&mut q, Mark::Cap, Cell::Bool(true));
                            put(&mut q, Mark::Lap, Cell::Bool(true));
                        }
                    }
                    _ => {}
                }
            }
        }
        match self.end {
            End::Flat => put(&mut q, Mark::Cap, Cell::Bool(true)),
            End::Stub => put(&mut q, Mark::Stub, Cell::Bool(true)),
            End::AsIs => {}
        }
        if matches!(self.part, Part::Half(_)) {
            q.retain(|k, _| cols.fill(k));
        }
        if let Some(dk) = self.draw {
            put(&mut q, Mark::PieceKind, Cell::Int(dk.kind));
            put(&mut q, Mark::Sort, Cell::Int(sort_key(dk.key, edge)));
        }
        put(&mut q, Mark::Class, r.cls_cell());
        q
    }
}

impl Base {
    /// The road's keys that a piece of this kind takes (`Piece::base`).
    fn keeps<'c>(self, cols: &'c Cols, read: Option<&'c HashSet<String>>) -> impl Fn(&str) -> bool + 'c {
        let read = move |k: &str| read.is_none_or(|r| r.contains(k) || k == cols.class);
        move |k: &str| read(k) && match self {
            Base::Fill => cols.fill(k),
            Base::Half => !matches!(Mark::of(k), Some(Mark::Cap0 | Mark::Cap1 | Mark::Split)),
            Base::Casing => cols.casing(k),
        }
    }
}

/// What the pieces of one call share: the last piece's road cells (key, cells, class index), and what is read (None: all): each
/// mark (by its place in `Mark::ALL`) and the class.
struct Run<'a> {
    last: Option<((u32, Base), Cells<'a>, Option<usize>)>,
    /// the plan of each kind's `Piece::base` (Fill, Half, Casing), made when a piece first needs it
    plans: [Option<crate::road::OwnPlan>; 3],
    marks: Option<Vec<bool>>,
    class: bool,
}

/// What a piece takes of its road's properties: a fill's, a half's (a fill's after its marks) or a casing's.
#[derive(Clone, Copy, PartialEq, Eq, Hash)]
enum Base {
    Fill,
    Half,
    Casing,
}

/// np.round(x, d) for d > 0: rint(x * 10^d) / 10^d.
fn np_round(x: f64, scale: f64) -> f64 {
    (x * scale).round_ties_even() / scale
}

/// A line in metres from its first point (as _casing_parts and _halves project it), with its cumulative lengths.
pub(crate) struct Line {
    pub(crate) xy: Vec<Pt>,
    pub(crate) cum: Vec<f64>,
    pub(crate) lon0: f64,
    pub(crate) lat0: f64,
    pub(crate) kx: f64,
}

pub(crate) const KY: f64 = 111320.0;

impl Line {
    pub(crate) fn new(c: &[Pt]) -> Line {
        let (lon0, lat0) = (c[0][0], c[0][1]);
        let kx = 111320.0 * lat0.to_radians().cos();
        let xy: Vec<Pt> = c.iter().map(|p| [(p[0] - lon0) * kx, (p[1] - lat0) * KY]).collect();
        let mut cum = Vec::with_capacity(xy.len());
        let mut s = 0.0;
        cum.push(0.0);
        for w in xy.windows(2) {
            s += (w[1][0] - w[0][0]).hypot(w[1][1] - w[0][1]);
            cum.push(s);
        }
        Line { xy, cum, lon0, lat0, kx }
    }

    pub(crate) fn len(&self) -> f64 {
        self.cum[self.cum.len() - 1]
    }

    // np.searchsorted(cum, d, side="right") / side="left"
    fn right(&self, d: f64) -> usize {
        self.cum.partition_point(|&x| x <= d)
    }
    fn left(&self, d: f64) -> usize {
        self.cum.partition_point(|&x| x < d)
    }

    /// _at: the point at the distance d.
    pub(crate) fn at(&self, d: f64) -> Pt {
        let j = (self.right(d) as isize - 1).clamp(0, self.cum.len() as isize - 2) as usize;
        let w = self.cum[j + 1] - self.cum[j];
        let t = if w > 0.0 { (d - self.cum[j]) / w } else { 0.0 };
        let (p, q) = (self.xy[j], self.xy[j + 1]);
        [p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])]
    }

    /// _part: the cut points at a and b and the vertices between them.
    pub(crate) fn part(&self, a: f64, b: f64) -> Vec<Pt> {
        let mut out = vec![self.at(a)];
        let (i, j) = (self.right(a), self.left(b));
        if i < j {
            out.extend_from_slice(&self.xy[i..j]);
        }
        out.push(self.at(b));
        out
    }

    /// Back to lon / lat, rounded as numpy rounds (scale 1e7 or 1e8).
    pub(crate) fn lonlat(&self, pts: &[Pt], scale: f64) -> Vec<Pt> {
        pts.iter().map(|p| [np_round(p[0] / self.kx + self.lon0, scale), np_round(p[1] / KY + self.lat0, scale)]).collect()
    }
}

/// `__rs_s`: the key in KEY_UNITs and the edge's tie-breaker (render_web._piece_key).
fn sort_key(key: f64, edge: i64) -> i64 {
    (key * KEY_UNIT).round() as i64 + edge
}

fn int(p: &Props, k: &str) -> i64 {
    p.get(k).and_then(Value::as_i64).unwrap_or(0)
}

/// _casing_parts: the casing of every edge as pieces. An edge whose three casing numbers differ (or with two different ends) is cut into
/// its start head, its main part and its end head, with a seam (and a lap, not on a dashed or tunnel casing) at each cut inside it.
pub(crate) fn casing_parts(roads: &Roads, head_m: f64) -> Vec<Piece> {
    let mut out = Vec::new();
    for p in roads.iter() {
        let d = p.draw();
        if d.dup {
            continue; // one line for a reverse pair: its twin draws it
        }
        let edge = p.i as u32;
        if d.twin.is_some_and(|tw| tw.get() < edge as usize) {
            continue; // a two-way pair's one casing: the first edge's pieces
        }
        let piece = |part: Part, coords: PieceLine| Piece { edge, part, end: End::AsIs, draw: None, coords };
        let [cm, _, cs, ce] = d.levels64().unwrap_or_default();
        let split = d.split.is_some();
        let c = match p.line() {
            Some(c) if c.len() >= 2 && !(cs == cm && cm == ce && !split) => c,
            _ => {
                out.push(piece(Part::Casing, if p.line().is_some() { PieceLine::Road } else { PieceLine::None }));
                continue;
            }
        };
        let line = Line::new(c);
        let n = line.len();
        let (h0, h1) = (d.head(&roads.values, 0).unwrap_or(head_m), d.head(&roads.values, 1).unwrap_or(head_m));
        // k: 0 the start head, 1 the main part, 2 the end head. A short road is cut once, in the heads' ratio (roadstyle after 0.24.2,
        // short_road_heads.md "One cut"): two cuts at h0 and n - h1 are one point only in exact arithmetic
        let cuts: Vec<(f64, f64, i64, u8)> = if h0 + h1 >= n - 0.05 {
            let h0 = n * h0 / (h0 + h1);
            vec![(0.0, h0, cs, 0), (h0, n, ce, 2)]
        } else {
            vec![(0.0, h0, cs, 0), (h0, n - h1, cm, 1), (n - h1, n, ce, 2)]
        };
        for &(a, b, num, k) in &cuts {
            let pts = line.part(a, b);
            if pts.len() < 2 || !pts.windows(2).any(|w| w[0] != w[1]) {
                continue;
            }
            out.push(piece(Part::Cut(k, num), PieceLine::own(line.lonlat(&pts, 1e7))));
        }
        // a seam at each cut inside the edge, at the lower of the two pieces' numbers; below zoom 17 a flat lap instead
        let mut cut_at: Vec<f64> = cuts[1..].iter().map(|c| c.0).collect();
        cut_at.retain(|&x| x != 0.0 && x != n);
        cut_at.sort_by(f64::total_cmp);
        cut_at.dedup_by(|a, b| a == b);
        let solid = !truthy(p.get(Mark::Dash.name())) && !truthy(p.get(Mark::Tunnel.name()));
        for &cut in &cut_at {
            let near: Vec<&(f64, f64, i64, u8)> = cuts.iter().filter(|(a, b, _, _)| b - a > 1e-9 && ((b - cut).abs() < 1e-9 || (a - cut).abs() < 1e-9)).collect();
            let half = near.iter().map(|(a, b, _, _)| (b - a) / 4.0).fold(SEAM_M, f64::min);
            let pts = line.part((cut - half).max(0.0), (cut + half).min(n));
            if near.len() < 2 || pts.len() < 2 {
                continue;
            }
            let num = near.iter().map(|x| x.2).min().unwrap();
            out.push(piece(Part::Seam(num), PieceLine::own(line.lonlat(&pts, 1e8))));
            if !solid {
                continue; // a solid lap would fill a dashed casing's gaps
            }
            let half = near.iter().map(|(a, b, _, _)| (b - a) / 2.0).fold(LAP_M, f64::min);
            let pts = line.part((cut - half).max(0.0), (cut + half).min(n));
            out.push(piece(Part::Lap(num), PieceLine::own(line.lonlat(&pts, 1e7))));
        }
    }
    out
}

/// _halves: the fill of every edge with two different ends (__rs_split) as two halves cut at the middle, each with its end's cap.
pub(crate) fn halves(roads: &Roads) -> HashMap<i64, Vec<Piece>> {
    let mut out: HashMap<i64, Vec<Piece>> = HashMap::new();
    for p in roads.iter() {
        let Some(c) = p.line().filter(|c| c.len() >= 2) else { continue };
        if p.draw().split.is_none() || p.draw().dup {
            continue;
        }
        let line = Line::new(c);
        let n = line.len();
        for (k, (a, b)) in [(0.0, n / 2.0), (n / 2.0, n)].into_iter().enumerate() {
            out.entry(p.i as i64).or_default().push(Piece { edge: p.i as u32, part: Part::Half(k as u8), end: End::AsIs, draw: None,
                                                             coords: PieceLine::own(line.lonlat(&line.part(a, b), 1e7)) });
        }
    }
    out
}

/// _end_stub: a piece with one road end and one cut whose road end is not flat is drawn flat, plus a short stub at the road end that
/// carries the end's shape (0.5 m for a square end, 5 cm for a round one). Any other piece as it is.
fn end_stub(q: Piece, roads: &Roads) -> Vec<Piece> {
    let at = |a: &Pt, b: &Pt| (a[0] - b[0]).abs() < 1e-6 && (a[1] - b[1]).abs() < 1e-6;
    let (Some(c), Some(e)) = (q.points(roads), roads.line(q.edge as usize)) else { return vec![q] };
    if c.len() < 2 || e.len() < 2 || at(&c[0], &e[0]) == at(&c[c.len() - 1], &e[e.len() - 1]) {
        return vec![q];
    }
    let first = at(&c[0], &e[0]);
    let (end, prev) = if first { (c[0], c[1]) } else { (c[c.len() - 1], c[c.len() - 2]) };
    let m = if q.cap(roads) == Some(Cap::Square) { 0.5 } else { 0.05 };
    let d = ((prev[0] - end[0]) * 111320.0 * end[1].to_radians().cos()).hypot((prev[1] - end[1]) * 111320.0);
    let k = (m / d.max(1e-6)).min(1.0);
    let inner = [end[0] + (prev[0] - end[0]) * k, end[1] + (prev[1] - end[1]) * k];
    let stub = if first { vec![end, inner] } else { vec![inner, end] };
    vec![Piece { end: End::Flat, ..q.clone() }, Piece { end: End::Stub, coords: PieceLine::own(stub), ..q }]
}

/// The "simple" source: simple mode's pieces with their feature ids (edge * PIECES + n), then the items.
pub struct SimpleSource {
    pub pieces: Vec<(usize, Piece)>,
    pub items: Vec<(usize, Item)>,
    pub cols: Cols,
    pub tolerance: f64,
    /// render's data_maxzoom (None: MapLibre's default)
    pub maxzoom: Option<i64>,
    /// a page: `promoteId` Mark::Edge.name() (every piece of a road has its row, so one feature state lights them all)
    pub promote: bool,
    /// a view's palettes (palettes.rs): the roads' `Extra` that the pieces differ in, in the order of the copies on each piece
    pub palette: Vec<usize>,
    /// R1: the only properties that a piece keeps (what the layers and the page read; `Styled::set_reads`), None: all
    pub read: Option<std::collections::HashSet<String>>,
    /// R8: the classes of the road layer's class index (`__rs_ci`, the last property of every feature), None: no index
    pub classes: Option<Vec<String>>,
}

impl SimpleSource {
    pub fn empty(cols: Cols) -> SimpleSource {
        SimpleSource { pieces: Vec::new(), items: Vec::new(), cols, tolerance: 0.05, maxzoom: None, promote: false, palette: Vec::new(), read: None, classes: None }
    }

    pub fn is_empty(&self) -> bool {
        self.pieces.is_empty() && self.items.is_empty()
    }

    /// The features in their order, each as (id, properties, line).
    pub fn features<'a>(&'a self, roads: &'a Roads) -> impl Iterator<Item = (usize, Props<'a>, Option<&'a [Pt]>)> + 'a {
        let mut run = self.run();
        self.pieces.iter().map(move |q| self.piece_feature(roads, q, None, &mut run))
            .chain(self.items.iter().map(move |(id, it)| (*id, self.slim_item(self.with_index(it.props.clone())), it.coords.as_deref())))
    }

    /// The pieces of the edges `rows` (no items), as `features` gives them (the level editor's redraw compares these alone).
    pub fn features_of<'a>(&'a self, roads: &'a Roads, rows: &'a std::collections::HashSet<u32>) -> impl Iterator<Item = (usize, Props<'a>, Option<&'a [Pt]>)> + 'a {
        let mut run = self.run();
        self.pieces.iter().filter(move |(_, p)| rows.contains(&p.edge)).map(move |q| self.piece_feature(roads, q, None, &mut run))
    }

    /// The pieces (no items), each with only the properties `keys` of those that `features` gives it (a road's other cells are not
    /// read: the level editor's tiles read a tile's first zoom from these, and the rest when a tile shows the piece).
    pub fn pieces_with<'a>(&'a self, roads: &'a Roads, keys: &'a [String]) -> impl Iterator<Item = (usize, Props<'a>, Option<&'a [Pt]>)> + 'a {
        // the class too: the class index reads it
        let only: Vec<&str> = keys.iter().map(String::as_str).chain([self.cols.class.as_str()]).collect();
        let mut run = self.run();
        self.pieces.iter().map(move |q| {
            let (id, p, c) = self.piece_feature(roads, q, Some(&only), &mut run);
            (id, p.into_iter().filter(|(k, _)| keys.iter().any(|x| x == k)).collect(), c)
        })
    }

    /// The piece at `i` in `pieces`, as `features` gives it.
    pub fn piece<'a>(&'a self, roads: &'a Roads, i: usize) -> (usize, Props<'a>, Option<&'a [Pt]>) {
        self.piece_feature(roads, &self.pieces[i], None, &mut self.run())
    }

    /// The pieces at the places `at` in `pieces` (in their order: the pieces of a road are one after another), as `piece` gives them,
    /// with their roads' cells (no JSON values: a tile's interning reads them). Each road's cells are read once for all its pieces.
    pub fn piece_cells<'a>(&'a self, roads: &'a Roads, at: impl Iterator<Item = usize>) -> impl Iterator<Item = (usize, Cells<'a>, Option<&'a [Pt]>)> {
        let mut run = self.run();
        at.map(move |i| self.cells(roads, &self.pieces[i], None, &mut run))
    }

    /// A run of pieces with nothing read yet.
    fn run<'a>(&self) -> Run<'a> {
        let marks = self.read.as_ref().map(|r| Mark::ALL.iter().map(|m| r.contains(m.name())).collect());
        let class = self.read.as_ref().is_none_or(|r| r.contains(&self.cols.class));
        Run { last: None, plans: Default::default(), marks, class }
    }

    fn piece_feature<'a>(&'a self, roads: &'a Roads, q: &'a (usize, Piece), only: Option<&[&str]>, run: &mut Run<'a>) -> (usize, Props<'a>, Option<&'a [Pt]>) {
        let (id, p, c) = self.cells(roads, q, only, run);
        (id, p.to_values(), c)
    }

    /// The piece's properties: its road's cells (`Piece::base`, the run's when the last piece had the same), its marks, its palette's,
    /// the class index (R8), and only those that are read (R1), in their order.
    fn cells<'a>(&'a self, roads: &'a Roads, (id, p): &'a (usize, Piece), only: Option<&[&str]>, run: &mut Run<'a>) -> (usize, Cells<'a>, Option<&'a [Pt]>) {
        let key = (p.edge, p.base_kind());
        if run.last.as_ref().is_none_or(|l| l.0 != key) {
            let kind = p.base_kind();
            let base = match only {
                Some(_) => p.base(roads, &self.cols, only, self.read.as_ref()),
                None => {
                    let plan = run.plans[kind as usize].get_or_insert_with(|| roads.own_plan(|k| own_keeps(k, kind.keeps(&self.cols, self.read.as_ref()))));
                    roads.road(p.edge as usize).own_by(plan).collect()
                }
            };
            let index = self.class_index(base.get(&self.cols.class).and_then(|c| c.as_str()));
            run.last = Some((key, base, index));
        }
        let (_, base, index) = run.last.as_ref().expect("the run's last road");
        let mut q = p.over(roads, &self.cols, base.clone(), run.marks.as_deref());
        for (k, v) in self.palette_props(p, roads) {
            if self.read.as_ref().is_none_or(|r| r.contains(k)) {
                q.insert_name(k, v);
            }
        }
        if let Some(i) = index.filter(|_| run.marks.as_ref().is_none_or(|r| r[Mark::ClassIndex as usize])) {
            q.insert_name(crate::layers::CLASS_INDEX, Cell::Int(i as i64));
        }
        if !run.class {
            q.shift_remove(&self.cols.class);      // the class index read it
        }
        (*id, q, p.points(roads))
    }

    /// The properties with the class index last (R8): the place of the feature's class (the class role's column) in the classes, else
    /// their number.
    fn with_index<'a>(&self, mut q: Props<'a>) -> Props<'a> {
        if let Some(i) = self.class_index(q.get(&self.cols.class).and_then(Value::as_str)) {
            q.insert(crate::layers::CLASS_INDEX, i.into());
        }
        q
    }

    /// The class index of a feature of the class `c` (R8; None: no index).
    fn class_index(&self, c: Option<&str>) -> Option<usize> {
        self.classes.as_ref().map(|cs| cs.iter().position(|x| Some(x.as_str()) == c).unwrap_or(cs.len()))
    }

    /// An item's: its own fields (a picked item's popup fields: the item has no others) and the stage values that are read.
    fn slim_item<'a>(&self, q: Props<'a>) -> Props<'a> {
        match &self.read {
            Some(r) => q.into_iter().filter(|(k, _)| !k.starts_with(mark::PREFIX) || r.contains(k.as_ref())).collect(),
            None => q,
        }
    }

    /// The JSON text, written to `w` a part at a time: each feature as `{"type", "geometry", "properties", "id"}`.
    pub fn write_json<W: std::io::Write>(&self, w: &mut W, roads: &Roads) -> std::io::Result<()> {
        w.write_all(br#"{"type":"geojson","data":"#)?;
        self.write_data(w, roads)?;
        w.write_all(br#","tolerance":"#)?;
        serde_json::to_writer(&mut *w, &self.tolerance)?;
        if self.promote {
            w.write_all(br#","promoteId":Mark::Edge.name()"#)?;
        }
        if let Some(z) = self.maxzoom {
            write!(w, r#","maxzoom":{z}"#)?;
        }
        w.write_all(b"}")
    }

    /// The FeatureCollection, written to `w` a part at a time.
    pub fn write_data<W: std::io::Write>(&self, w: &mut W, roads: &Roads) -> std::io::Result<()> {
        let mut out = Vec::new();
        out.extend_from_slice(br#"{"type":"FeatureCollection","features":["#);
        for (i, (id, props, coords)) in self.features(roads).enumerate() {
            if out.len() > 1 << 16 {
                w.write_all(&out)?;
                out.clear();
            }
            if i > 0 {
                out.push(b',');
            }
            out.extend_from_slice(br#"{"type":"Feature","geometry":"#);
            match coords {
                None => out.extend_from_slice(b"null"),
                Some(c) => {
                    out.extend_from_slice(br#"{"type":"LineString","coordinates":"#);
                    serde_json::to_writer(&mut out, c).unwrap();
                    out.push(b'}');
                }
            }
            out.extend_from_slice(br#","properties":"#);
            props.write_json(&mut out);
            out.extend_from_slice(format!(r#","id":{id}}}"#).as_bytes());
        }
        out.extend_from_slice(b"]}");
        w.write_all(&out)
    }
}

/// A feature of the simple source for the layers' checks (`Get`): its properties are made when one is read.
pub struct SimpleFeature<'a> {
    src: &'a SimpleSource,
    roads: &'a Roads,
    i: usize,
}

impl Get for SimpleFeature<'_> {
    fn value(&self, k: &str) -> Option<Value> {
        match self.src.pieces.get(self.i) {
            Some((_, p)) => p.props(self.roads, &self.src.cols).get(k).cloned(),
            None => self.src.items[self.i - self.src.pieces.len()].1.props.get(k).cloned(),
        }
    }
}

impl SimpleSource {
    /// Every feature, for the layers' checks.
    pub fn gets<'a>(&'a self, roads: &'a Roads) -> Vec<SimpleFeature<'a>> {
        (0..self.pieces.len() + self.items.len()).map(|i| SimpleFeature { src: self, roads, i }).collect()
    }
}

/// The "simple" source: _simple_pieces (casing pieces __rs_k 0, bridge shadows 2, tunnel gap 3 and dashes 4, fills 1), the feature ids
/// (edge * PIECES + n), the tie-breaker per edge and __rs_cls (_mark_cls).
/// `width_col`: render's width_m_col, which the pieces keep (the layer's `cols`).
/// `items`: the line items on the edges (_item_pieces, `__rs_k` 5), each over its edge's fill, by its rank on the edge.
pub fn simple_source(roads: &Roads, head_m: f64, shadows: bool, width_col: Option<&str>, items: Vec<Item>) -> Result<SimpleSource, crate::Error> {
    let line_of: Vec<Option<&[Pt]>> = roads.iter().map(|f| f.line()).collect();
    let mut halves = halves(roads);
    let mut out: Vec<Piece> = Vec::new();
    let key = |q: &Piece, kind: i64, key: f64| Piece { draw: Some(DrawKey { kind, key }), ..q.clone() };
    for q0 in casing_parts(roads, head_m) {
        let stub = q0.cap(roads) != Some(Cap::Flat) && !q0.seam();
        for q in if stub { end_stub(q0, roads) } else { vec![q0] } {
            let r = roads.road(q.edge as usize);
            if truthy(r.get(Mark::Dash.name())) || (q.seam() && truthy(r.get(Mark::Tunnel.name()))) {
                continue; // a dashed class has no casing; a tunnel's casing is its dashes alone
            }
            let bridge = truthy(r.get(Mark::Bridge.name()));
            let cl = q.cl(roads);
            let k = 2.0 * cl as f64 + if bridge { 0.25 } else { 0.0 };
            let [_, _, cs, ce] = r.draw().levels64().unwrap_or_default();
            let whole = cs == cl && cl == ce;
            if shadows && bridge && (matches!(q.part, Part::Cut(1, _)) || whole) {
                out.push(key(&q, 2, k - 0.1));
            }
            if truthy(r.get(Mark::Tunnel.name())) && !bridge {
                out.push(key(&q, 3, k));
                out.push(key(&q, 4, k + 0.1));
            } else {
                out.push(key(&q, 0, k));
            }
        }
    }
    for p in roads.iter() {
        if p.draw().dup {
            continue;
        }
        let fills: Vec<Piece> = if p.draw().split.is_some() {
            halves.remove(&(p.i as i64)).unwrap_or_default().into_iter()
                .flat_map(|h| if h.cap(roads) == Some(Cap::Flat) { vec![h] } else { end_stub(h, roads) }).collect()
        } else {
            vec![Piece { edge: p.i as u32, part: Part::Fill, end: End::AsIs, draw: None,
                         coords: if p.line().is_some() { PieceLine::Road } else { PieceLine::None } }]
        };
        let fl = p.draw().levels.map_or(0, |l| l[1]);
        let s = 2.0 * fl as f64 + if truthy(p.get(Mark::Dash.name())) { -0.5 } else { 1.0 };
        out.extend(fills.into_iter().map(|h| Piece { draw: Some(DrawKey { kind: 1, key: s }), ..h }));
    }
    let mut items = items;
    mitre_ends(&mut out, &line_of, roads, &mut items);
    let mut n: HashMap<u32, usize> = HashMap::new();
    let mut pieces = Vec::with_capacity(out.len());
    for f in out {
        let e = f.edge;
        let c = n.entry(e).or_default();
        if *c == PIECES {
            return Err(crate::Error::Limit { what: crate::Limit::Pieces { edge: e as usize }, found: PIECES + 1, max: PIECES });
        }
        if e as usize >= MAX_EDGES {
            return Err(crate::Error::Limit { what: crate::Limit::Edges, found: e as usize + 1, max: MAX_EDGES });
        }
        let id = e as usize * PIECES + *c;
        *c += 1;
        pieces.push((id, f));
    }
    // the items, by edge, order, overlay and feature: an id per edge and rank, and a sort key over the edge's fill
    items.sort_by_key(|f| [Mark::Edge.name(), Mark::ItemOrder.name(), Mark::ItemOverlay.name(), Mark::Item.name()].map(|k| f.props.get(k).and_then(Value::as_i64).unwrap_or(0)));
    let mut rank: HashMap<i64, usize> = HashMap::new();
    let mut placed = Vec::with_capacity(items.len());
    for mut f in items {
        let e = f.props.get(Mark::Edge.name()).and_then(Value::as_u64).and_then(crate::road::row_of).unwrap_or(0) as i64;
        let r = rank.entry(e).or_default();
        *r += 1;
        if *r > MAX_ITEMS {
            return Err(crate::Error::Limit { what: crate::Limit::Items { edge: e as usize }, found: *r, max: MAX_ITEMS });
        }
        let id = MAX_EDGES * PIECES + e as usize * MAX_ITEMS + *r - 1;
        let s = sort_key(2.0 * int(&f.props, Mark::FillLevel.name()) as f64 + 1.0 + *r as f64 * ITEM_STEP, e);
        f.props.insert(Mark::Sort.name(), s.into());
        // _mark_cls: the class and the access of the item's road
        let road = roads.at(e as usize);
        f.props.insert(Mark::Class.name(), road.map(Road::cls).unwrap_or(Value::Null));
        if let Some(a) = road.and_then(|p| p.get(Mark::Access.name())).filter(|a| !a.is_null()) {
            f.props.insert(Mark::Access.name(), a.to_value());
        }
        placed.push((id, f));
    }
    Ok(SimpleSource { pieces, items: placed, cols: Cols::new(roads.roles.name(&roads.table, roadstyle_model::Role::Class).unwrap_or(roadstyle_model::Role::Class.name()), &roads.cls, width_col), tolerance: 0.05, maxzoom: None, promote: false, palette: Vec::new(), read: None, classes: None })
}

// _mitre_ends: a flat end where another road with metre widths goes on is pushed on to close the corner with the road that goes on most
// straight, turning _MITRE_MAX degrees at most; an item's end where an item of its colour and dash goes on (within _ITEM_JOIN_M) too.
const MITRE_MAX: f64 = 60.0;
const ITEM_JOIN_M: f64 = 2.0;

/// _unit: the unit vector from a to b in metres east and north, and its length.
fn unit(a: &Pt, b: &Pt, lat: f64) -> ((f64, f64), f64) {
    let (x, y) = ((b[0] - a[0]) * 111320.0 * lat.to_radians().cos(), (b[1] - a[1]) * 111320.0);
    let n = x.hypot(y);
    (if n > 0.0 { (x / n, y / n) } else { (0.0, 0.0) }, n)
}

/// _heading: the way a line runs at its first or last point, from a point at least 0.5 m away.
fn heading(c: &[Pt], first: bool) -> (f64, f64) {
    let pts: Vec<&Pt> = if first { c.iter().rev().collect() } else { c.iter().collect() };
    let last = pts[pts.len() - 1];
    let flip = |u: (f64, f64)| if first { (-u.0, -u.1) } else { u };
    for q in pts[..pts.len() - 1].iter().rev() {
        let (u, n) = unit(q, last, last[1]);
        if n >= 0.5 {
            return flip(u);
        }
    }
    flip(unit(pts[0], last, last[1]).0)
}

/// _reach: how far a flat end goes on to close the corner with the line that goes on (None: not a corner to close).
fn reach(own: ((f64, f64), (f64, f64), f64, f64), oth: ((f64, f64), (f64, f64), f64, f64)) -> Option<f64> {
    let ((p, u, h, o), (q, v, k, w)) = (own, oth);
    let cos = (u.0 * v.0 + u.1 * v.1).clamp(-1.0, 1.0);
    let turn = cos.acos().to_degrees();
    if !(0.5..=MITRE_MAX).contains(&turn) {
        return None;
    }
    let rn = |d: (f64, f64), x: f64| (d.1 * x, -d.0 * x);
    let (pa, pb) = ((p.0 + rn(u, o).0, p.1 + rn(u, o).1), (q.0 + rn(v, w).0, q.1 + rn(v, w).1));
    let det = u.0 * v.1 - u.1 * v.0;
    let (dx, dy) = (pb.0 - pa.0, pb.1 - pa.1);
    let (s, t) = ((dx * v.1 - dy * v.0) / det, (u.0 * dy - u.1 * dx) / det);
    if s.abs().max(t.abs()) > ITEM_JOIN_M {
        return None;
    }
    let sin = turn.to_radians().sin();
    Some(s.max(0.0) + ((k - h * cos) / sin).max(0.0).min(h * (turn.to_radians() / 2.0).tan()))
}

/// _push: the line with its first or last point pushed `m` metres straight on.
fn push(c: &mut Vec<Pt>, first: bool, m: f64) {
    let u = heading(c, first);
    let u = if first { (-u.0, -u.1) } else { u };
    let end = if first { c[0] } else { c[c.len() - 1] };
    let pt = [crate::layers::py_round(end[0] + u.0 * m / (111320.0 * end[1].to_radians().cos()), 7), crate::layers::py_round(end[1] + u.1 * m / 111320.0, 7)];
    if first { c.insert(0, pt) } else { c.push(pt) }
}

fn mitre_ends(out: &mut [Piece], line_of: &[Option<&[Pt]>], roads: &Roads, items: &mut [Item]) {
    let topo = roads.topo();
    let mut wide: indexmap::IndexMap<i64, (f64, f64)> = indexmap::IndexMap::new();
    for p in roads.iter() {
        let (Some(wm), Some(c)) = (p.get(Mark::WidthM.name()).and_then(Cell::as_f64), p.line().filter(|c| c.len() >= 2)) else { continue };
        if truthy(p.get(Mark::Dup.name())) {
            continue;
        }
        let k = c[0][1].to_radians().cos();
        let cm = p.get(Mark::CasingM.name()).and_then(Cell::as_f64).unwrap_or(0.0);
        wide.insert(p.get(Mark::Edge.name()).and_then(Cell::as_u64).and_then(crate::road::row_of).unwrap_or(p.i) as i64, (wm * k, (wm - 2.0 * cm) * k));
    }
    let line = |e: i64| line_of.get(e as usize).copied().flatten();
    // the ends of the metre roads at each node (a road end's node: Topology)
    let node_of = |e: i64, first: bool| topo.ends.get(e as usize).copied().flatten().map(|n| n[usize::from(!first)]);
    let mut ends: HashMap<u32, Vec<(i64, bool)>> = HashMap::new();
    for &e in wide.keys() {
        for first in [true, false] {
            if let Some(n) = node_of(e, first) {
                ends.entry(n).or_default().push((e, first));
            }
        }
    }
    let at = |a: &Pt, b: &Pt| (a[0] - b[0]).abs() < 1e-6 && (a[1] - b[1]).abs() < 1e-6;
    // one latitude for all the metres (two points' own ones put them metres apart): the first item's, else the first road's
    let lat0 = items.first().and_then(|f| f.coords.as_ref()).and_then(|c| c.first()).map(|p| p[1])
        .or_else(|| line_of.iter().flatten().find(|c| !c.is_empty()).map(|c| c[0][1])).unwrap_or(0.0);
    let k0 = 111320.0 * lat0.to_radians().cos();
    let xy = |pt: &Pt| (pt[0] * k0, pt[1] * 111320.0);
    for f in out.iter_mut() {
        let edge = f.edge as i64;
        if !wide.contains_key(&edge) || f.cap(roads) != Some(Cap::Flat) || f.seam() {
            continue;
        }
        let j = if f.draw.map(|d| d.kind) == Some(1) { 1 } else { 0 };
        let (Some(c), Some(e)) = (f.points(roads).filter(|c| c.len() >= 2), line(edge)) else { continue };
        let mut pushes = Vec::new();        // the ends that reach further, put on the piece's own copy after (R11)
        for first in [true, false] {
            let (cp, ep) = if first { (&c[0], &e[0]) } else { (&c[c.len() - 1], &e[e.len() - 1]) };
            if !at(cp, ep) {
                continue;
            }
            let node = *ep;
            let u = heading(e, first);
            let u = if first { (-u.0, -u.1) } else { u };
            let mut best: Option<(f64, f64)> = None;
            for &(o, ofirst) in node_of(edge, first).and_then(|n| ends.get(&n)).into_iter().flatten() {
                if o == edge {
                    continue;
                }
                let Some(oc) = line(o) else { continue };
                let v = heading(oc, ofirst);
                let v = if ofirst { v } else { (-v.0, -v.1) };
                let pick = |x: (f64, f64)| if j == 1 { x.1 } else { x.0 };
                let m = reach((xy(&node), u, pick(wide[&edge]) / 2.0, 0.0), (xy(&node), v, pick(wide[&o]) / 2.0, 0.0));
                let dot = u.0 * v.0 + u.1 * v.1;
                if let Some(m) = m {
                    if best.is_none_or(|b| dot > b.0) {
                        best = Some((dot, m));
                    }
                }
            }
            if let Some((_, m)) = best.filter(|b| b.1 > 0.0) {
                pushes.push((first, m));
            }
        }
        if !pushes.is_empty() {
            let mut own = f.points(roads).unwrap_or_default().to_vec();
            for (first, m) in pushes {
                push(&mut own, first, m);
            }
            f.coords = PieceLine::own(own);
        }
    }
    // the items: an end with the items of its colour and dash that start within ITEM_JOIN_M (and a start with those that end there)
    let lines: Vec<usize> = (0..items.len()).filter(|&k| items[k].coords.as_ref().is_some_and(|c| c.len() >= 2)).collect();
    let text = |f: &Item, k: &str| f.props.get(k).filter(|v| !v.is_null()).map(Value::to_string);     // Python's None: missing or null
    let key = |f: &Item| (text(f, Mark::ItemColor.name()), text(f, Mark::Dash.name()));
    let cell = |p: &Pt| ((p[0] / 3e-5).floor() as i64, (p[1] / 3e-5).floor() as i64);
    let end_of = |c: &Vec<Pt>, first: bool| if first { c[0] } else { c[c.len() - 1] };
    let mut by: HashMap<_, Vec<usize>> = HashMap::new();
    for &k in &lines {
        let c = items[k].coords.as_ref().unwrap();
        for first in [true, false] {
            by.entry((key(&items[k]), first, cell(&end_of(c, first)))).or_default().push(k);
        }
    }
    let num = |p: &Props, k: &str| p.get(k).and_then(Value::as_f64).unwrap_or(0.0);
    let side = |f: &Item, first: bool| {
        let c = f.coords.as_ref().unwrap();
        let cl = c[0][1].to_radians().cos();
        let u = heading(c, first);
        let out_u = if first { (-u.0, -u.1) } else { u };
        let o = num(&f.props, Mark::ItemOffsetM.name()) * cl;
        (xy(&end_of(c, first)), out_u, num(&f.props, Mark::ItemWidthM.name()) * cl / 2.0, if first { -o } else { o })
    };
    let mut pushes = Vec::new();
    for &k in &lines {
        for first in [true, false] {
            let (p, u, h, o) = side(&items[k], first);
            let (x, y) = cell(&end_of(items[k].coords.as_ref().unwrap(), first));
            let mut best: Option<(f64, f64)> = None;
            for dx in [-1, 0, 1] {
                for dy in [-1, 0, 1] {
                    for &j in by.get(&(key(&items[k]), !first, (x + dx, y + dy))).into_iter().flatten() {
                        if j == k {
                            continue;
                        }
                        let (q, v, kk, w) = side(&items[j], !first);
                        let (v, w) = ((-v.0, -v.1), -w);
                        if (q.0 - p.0).hypot(q.1 - p.1) > ITEM_JOIN_M {
                            continue;
                        }
                        let dot = u.0 * v.0 + u.1 * v.1;
                        if let Some(m) = reach((p, u, h, o), (q, v, kk, w)) {
                            if best.is_none_or(|b| dot > b.0) {
                                best = Some((dot, m));
                            }
                        }
                    }
                }
            }
            if let Some((_, m)) = best.filter(|b| b.1 > 0.0) {
                pushes.push((k, first, m));
            }
        }
    }
    for (k, first, m) in pushes {
        push(items[k].coords.as_mut().unwrap(), first, m);
    }
}
