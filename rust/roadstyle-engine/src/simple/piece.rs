//! A piece of the road layer: its keys, its sort key and the properties it writes.

use super::*;

impl Piece {
    pub(crate) fn road<'a>(&self, roads: &'a Roads) -> Road<'a> {
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

    /// The properties of the piece, with its keys in its order, and the road layer's `__rs_k`, `r` (the style
    /// adds the road's key, the feature id, as the tie-breaker) and `__rs_cls`.
    pub fn props<'a>(&self, roads: &'a Roads, cols: &Cols) -> Props<'a> {
        self.over(roads, cols, self.base(roads, cols, None, None), None).to_values()
    }

    /// What the piece takes of its road's properties.
    pub(crate) fn base_kind(&self) -> Base {
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
    pub(crate) fn base<'a>(&self, roads: &'a Roads, cols: &Cols, only: Option<&[&str]>, read: Option<&HashSet<String>>) -> Cells<'a> {
        road_props(self.road(roads), only, self.base_kind().keeps(cols, read))
    }

    /// The piece's properties: its road's cells (`base`) and its own marks. `read`: no mark that is not read (`Run::marks`).
    pub(crate) fn over<'a>(&self, roads: &'a Roads, cols: &Cols, mut q: Cells<'a>, read: Option<&[bool]>) -> Cells<'a> {
        let put = |q: &mut Cells<'a>, k: Mark, v: Cell<'a>| if read.is_none_or(|r| r[k as usize]) {
            q.insert_name(k.name(), v);
        };
        let r = self.road(roads);
        let d = r.draw();
        let key = crate::road::key(self.edge as usize).get() as i64;      // the road's key
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
            put(&mut q, Mark::Rank, Cell::Int(rank(dk.key)));
        }
        put(&mut q, Mark::Class, r.cls_cell());
        q
    }
}

impl Base {
    /// The road's keys that a piece of this kind takes (`Piece::base`).
    pub(crate) fn keeps<'c>(self, cols: &'c Cols, read: Option<&'c HashSet<String>>) -> impl Fn(&str) -> bool + 'c {
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
pub(crate) struct Run<'a> {
    pub(crate) last: Option<((u32, Base), Cells<'a>, Option<usize>)>,
    /// the plan of each kind's `Piece::base` (Fill, Half, Casing), made when a piece first needs it
    pub(crate) plans: [Option<crate::road::OwnPlan>; 3],
    pub(crate) marks: Option<Vec<bool>>,
    pub(crate) class: bool,
}

/// What a piece takes of its road's properties: a fill's, a half's (a fill's after its marks) or a casing's.
#[derive(Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) enum Base {
    Fill,
    Half,
    Casing,
}
