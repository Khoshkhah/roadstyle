//! The "simple" source: simple mode's one road layer, every casing piece and every fill (the casing heads, the halves, the end stubs,
//! _simple_pieces), from the roads after their stages (roads::mark_roads). The geometry is computed as numpy computes it: a flat
//! projection at the line's first point, sequential sums, `hypot`, and numpy's rounding (`rint(x * 10^d) / 10^d`).
//! A piece is typed (`Piece`: its road, what it draws, its place in the road layer, its line); its JSON properties are made only at the
//! output (`Piece::props`), from its road, with its keys in one fixed order.

use roadstyle_model::mark::{self, Mark};
use crate::draw::Cap;
use crate::props::{Get, Props};
use crate::road::{Road, Roads};
use crate::roads::is_yes;
use roadstyle_model::Cell;
use serde_json::Value;
use std::collections::{HashMap, HashSet};

mod line;
mod mitre;
mod piece;
mod source;
mod stages;

pub use source::*;
pub(crate) use line::*;
pub(crate) use stages::*;
use mitre::*;
use piece::*;

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

