//! The simple source: the pieces of all roads, their properties and the source's features.

use super::*;

/// The "simple" source: simple mode's pieces with their feature ids (edge * PIECES + n), then the items.
pub struct SimpleSource {
    pub pieces: Vec<(usize, Piece)>,
    pub items: Vec<(usize, Item)>,
    pub cols: Cols,
    pub tolerance: f64,
    /// render's data_maxzoom (None: MapLibre's default)
    pub maxzoom: Option<i64>,
    /// a view's palettes (palettes.rs): the roads' `Extra` that the pieces differ in, in the order of the copies on each piece
    pub palette: Vec<usize>,
    /// R1: the only properties that a piece keeps (what the layers and the page read; `Styled::set_reads`), None: all
    pub read: Option<std::collections::HashSet<String>>,
    /// R8: the classes of the road layer's class index (`__rs_ci`, the last property of every feature), None: no index
    pub classes: Option<Vec<String>>,
    /// the road layer draws the class's colours for a piece that has no colour of its own: a piece whose fill or casing is its class's
    /// has none (tile_v2_plan.md, step 6)
    pub class_colours: Option<crate::colors::ClassColours>,
    /// the other colour modes: a piece holds the place of its fill and casing colour in a table of the style, never the colour text
    pub colours: Option<Box<crate::colors::ColourTable>>,
    /// the colour tables of a view's other palettes (palettes.rs), for the pieces' copies of the colours that differ
    pub palette_colours: Vec<(String, crate::colors::ColourTable)>,
}

impl SimpleSource {
    pub fn empty(cols: Cols) -> SimpleSource {
        SimpleSource { pieces: Vec::new(), items: Vec::new(), cols, tolerance: 0.05, maxzoom: None, palette: Vec::new(), read: None, classes: None, class_colours: None, colours: None, palette_colours: Vec::new() }
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
    pub(crate) fn run<'a>(&self) -> Run<'a> {
        let marks = self.read.as_ref().map(|r| Mark::ALL.iter().map(|m| r.contains(m.name())).collect());
        let class = self.read.as_ref().is_none_or(|r| r.contains(&self.cols.class));
        Run { last: None, plans: Default::default(), marks, class }
    }

    pub(crate) fn piece_feature<'a>(&'a self, roads: &'a Roads, q: &'a (usize, Piece), only: Option<&[&str]>, run: &mut Run<'a>) -> (usize, Props<'a>, Option<&'a [Pt]>) {
        let (id, p, c) = self.cells(roads, q, only, run);
        (id, p.to_values(), c)
    }

    /// The piece's properties: its road's cells (`Piece::base`, the run's when the last piece had the same), its marks, its palette's,
    /// the class index (R8), and only those that are read (R1), in their order.
    pub(crate) fn cells<'a>(&'a self, roads: &'a Roads, (id, p): &'a (usize, Piece), only: Option<&[&str]>, run: &mut Run<'a>) -> (usize, Cells<'a>, Option<&'a [Pt]>) {
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
        if let Some(colours) = &self.class_colours {
            let of = colours.of_class(q.get(&self.cols.class).and_then(|c| c.as_str()));
            for (mark, own) in [(Mark::Fill, &of[0]), (Mark::Casing, &of[1])] {
                if q.get(mark.name()).is_some_and(|v| v.to_value() == *own) {
                    q.shift_remove(mark.name());
                }
            }
        }
        if let Some(t) = &self.colours {
            t.put_places(&mut q, None);
        }
        for (n, t) in &self.palette_colours {
            t.put_places(&mut q, Some(n));
        }
        if !run.class {
            q.shift_remove(&self.cols.class);      // the class index read it
        }
        (*id, q, p.points(roads))
    }

    /// The properties with the class index last (R8): the place of the feature's class (the class role's column) in the classes, else
    /// their number.
    pub(crate) fn with_index<'a>(&self, mut q: Props<'a>) -> Props<'a> {
        if let Some(i) = self.class_index(q.get(&self.cols.class).and_then(Value::as_str)) {
            q.insert(crate::layers::CLASS_INDEX, i.into());
        }
        q
    }

    /// The class index of a feature of the class `c` (R8; None: no index).
    pub(crate) fn class_index(&self, c: Option<&str>) -> Option<usize> {
        self.classes.as_ref().map(|cs| cs.iter().position(|x| Some(x.as_str()) == c).unwrap_or(cs.len()))
    }

    /// An item's: its own fields (a picked item's popup fields: the item has no others) and the stage values that are read.
    pub(crate) fn slim_item<'a>(&self, q: Props<'a>) -> Props<'a> {
        match &self.read {
            Some(r) => q.into_iter().filter(|(k, _)| !k.starts_with(mark::PREFIX) || r.contains(k.as_ref())).collect(),
            None => q,
        }
    }

    /// The JSON text, written to `w` a part at a time: each feature as `{"type", "geometry", "properties", "id"}`, its id the road's key.
    pub fn write_json<W: std::io::Write>(&self, w: &mut W, roads: &Roads) -> std::io::Result<()> {
        w.write_all(br#"{"type":"geojson","data":"#)?;
        self.write_data(w, roads)?;
        w.write_all(br#","tolerance":"#)?;
        serde_json::to_writer(&mut *w, &self.tolerance)?;
        if let Some(z) = self.maxzoom {
            write!(w, r#","maxzoom":{z}"#)?;
        }
        w.write_all(b"}")
    }

    /// The FeatureCollection, written to `w` a part at a time.
    pub fn write_data<W: std::io::Write>(&self, w: &mut W, roads: &Roads) -> std::io::Result<()> {
        let mut out = Vec::new();
        out.extend_from_slice(br#"{"type":"FeatureCollection","features":["#);
        for (i, (id, mut props, coords)) in self.features(roads).enumerate() {
            // the road's key is the feature id (every piece of a road has it, so one feature state lights them all), not a property
            let id = props.shift_remove(Mark::Edge.name()).and_then(|e| e.as_u64()).unwrap_or(id as u64);
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
    pub(crate) src: &'a SimpleSource,
    pub(crate) roads: &'a Roads,
    pub(crate) i: usize,
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
            if is_yes(r.get(Mark::Dash.name())) || (q.seam() && is_yes(r.get(Mark::Tunnel.name()))) {
                continue; // a dashed class has no casing; a tunnel's casing is its dashes alone
            }
            let bridge = is_yes(r.get(Mark::Bridge.name()));
            let cl = q.cl(roads);
            let k = 2.0 * cl as f64 + if bridge { 0.25 } else { 0.0 };
            let [_, _, cs, ce] = r.draw().levels64().unwrap_or_default();
            let whole = cs == cl && cl == ce;
            if shadows && bridge && (matches!(q.part, Part::Cut(1, _)) || whole) {
                out.push(key(&q, 2, k - 0.1));
            }
            if is_yes(r.get(Mark::Tunnel.name())) && !bridge {
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
        let s = 2.0 * fl as f64 + if is_yes(p.get(Mark::Dash.name())) { -0.5 } else { 1.0 };
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
    let mut per_edge: HashMap<i64, usize> = HashMap::new();
    let mut placed = Vec::with_capacity(items.len());
    for mut f in items {
        let e = f.props.get(Mark::Edge.name()).and_then(Value::as_u64).and_then(crate::road::row_of).unwrap_or(0) as i64;
        let r = per_edge.entry(e).or_default();
        *r += 1;
        if *r > MAX_ITEMS {
            return Err(crate::Error::Limit { what: crate::Limit::Items { edge: e as usize }, found: *r, max: MAX_ITEMS });
        }
        let id = MAX_EDGES * PIECES + e as usize * MAX_ITEMS + *r - 1;
        f.props.insert(Mark::Rank.name(), rank(2.0 * int(&f.props, Mark::FillLevel.name()) as f64 + 1.0 + *r as f64 * ITEM_STEP).into());
        // _mark_cls: the class and the access of the item's road
        let road = roads.at(e as usize);
        f.props.insert(Mark::Class.name(), road.map(Road::cls).unwrap_or(Value::Null));
        if let Some(a) = road.and_then(|p| p.get(Mark::Access.name())).filter(|a| !a.is_null()) {
            f.props.insert(Mark::Access.name(), a.to_value());
        }
        placed.push((id, f));
    }
    Ok(SimpleSource { pieces, items: placed, cols: Cols::new(roads.roles.name(&roads.table, roadstyle_model::Role::Class).unwrap_or(roadstyle_model::Role::Class.name()), &roads.cls, width_col), tolerance: 0.05, maxzoom: None, palette: Vec::new(), read: None, classes: None, class_colours: None, colours: None, palette_colours: Vec::new() })
}
