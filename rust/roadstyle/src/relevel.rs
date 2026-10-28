//! The level editor's redraw (docs/rust/browser.md, "The editor on your map"): a tiled map whose roads get new levels, heads and caps.
//! Stage 1 runs again for the whole area (`roadstyle_engine::restyle`). Only the edges that changed and the edges at their end nodes
//! (the ring: a road's caps and joins come from the roads at its nodes) are compared; stage 2 replaces the pieces of those whose
//! pieces changed (`Tiles::replace_lines`), and a slots or decks source only when it changed. The tiles then have the same features
//! as a new map of the new values (tests/relevel.rs). The slots read only the fill levels: with no new fill level they stay as they
//! are (`restyle_same_fills`). The pieces wait for their properties until a tile shows them (`Tiles::add_waiting`): a large area's
//! map starts without them (`LiveTiles::tile` makes them). Monaco: a head or a cap about 70 ms, a level change about 120 ms (stage 1 is most of it).
//! ponytail: stage 1 of the whole area; stage 1 of the ring alone (global keys) when a large area is too slow.

use crate::{sources, tiles, Look};
use roadstyle_engine::sources::Source;
use roadstyle_engine::Src;
use roadstyle_model::Role;
use serde_json::Value;
use std::collections::{HashMap, HashSet};

/// One edge's new drawing values (a row of levels.csv): the levels in the order casing_start, casing_level, casing_end, fill_level; the
/// head lengths in metres and the caps (start, end; None: null).
pub struct LevelRow {
    pub edge_id: i64,
    pub levels: [i64; 4],
    pub heads: [Option<f64>; 2],
    pub caps: [Option<String>; 2],
}

/// What a redraw changed: the edges whose pieces changed, the pieces that went, the other sources made again, and whether the
/// style's layers changed (then the page must set the new style: `LiveTiles::style`).
#[derive(Debug, Default, serde::Serialize)]
pub struct Redrawn {
    pub edges: usize,
    pub pieces_gone: usize,
    pub sources: Vec<String>,
    pub style_changed: bool,
}

/// A tiled map of stage 1 that keeps it (`styled`), for redraws with new levels.
pub struct LiveTiles {
    pub styled: sources::Styled,
    pub tiles: tiles::Tiles,
    style: String,
    look: Look,
    options: tiles::stage::TileOptions,
    rows: HashMap<i64, usize>,
    /// the rows at each end node (the line's first and last point)
    at_node: HashMap<[u64; 2], Vec<u32>>,
    /// each simple source's place of each piece id (the tag of a waiting piece), made when a tile first asks; a redraw clears it
    piece_at: HashMap<String, HashMap<u64, usize>>,
}

impl LiveTiles {
    /// Stage 2 of `s` (`tiles_of_sources`'s), made by the look `look`, which a redraw runs stage 1 with again.
    pub fn new(s: sources::Styled, look: Look, prefix: &str, keep: &[String]) -> Result<LiveTiles, crate::Error> {
        let mut options = tiles::stage::TileOptions::new(&s.layers, &s.metadata, &s.saved[tiles::stage::TILES], &s.saved[tiles::stage::COLUMNS], keep)?;
        options.wait = true;
        // tiles_of_sources's stage 2, with the pieces that wait
        let (style, tiles) = crate::tile_stage(&s, &options, &crate::xyz_at(prefix), sources::SourceMode::INLINE)?;
        let style = crate::style_text(&s, &style);
        let r = &s.roads.roads;
        let id = r.roles.col(Role::EdgeId).ok_or_else(|| crate::error::edits("redraw: the roads have no edge id column"))?;
        let rows = (0..r.table.len()).filter_map(|i| r.table.cell(id, i).as_i64().or_else(|| r.table.cell(id, i).as_str()?.parse().ok()).map(|e| (e, i))).collect();
        let mut at_node: HashMap<[u64; 2], Vec<u32>> = HashMap::new();
        for i in 0..r.table.len() {
            for p in ends(r.table.line(i)) {
                at_node.entry(p).or_default().push(i as u32);
            }
        }
        Ok(LiveTiles { styled: s, tiles, style, look, options, rows, at_node, piece_at: HashMap::new() })
    }

    /// The tile z/x/y of the tile source (`Tiles::tile`), after its waiting pieces got their properties.
    pub fn tile(&mut self, z: u32, x: u32, y: u32) -> Vec<u8> {
        let roads = &self.styled.roads.roads;
        for (k, src) in &self.styled.sources {
            let Src::Simple(p) = src else { continue };
            let wait = self.tiles.waiting(k, z, x, y);
            if wait.is_empty() {
                continue;
            }
            let at = self.piece_at.entry(k.clone()).or_insert_with(|| p.pieces.iter().enumerate().map(|(i, (id, _))| (*id as u64, i)).collect());
            let (keep, ..) = self.options.rule(k, Default::default);
            let feats = wait.iter().zip(p.piece_cells(roads, wait.iter().map(|(_, tag)| at[tag])))
                .map(|(&(i, _), (_, props, c))| (i, c.expect("a waiting piece has a line"), props.into_iter()));
            self.tiles.make(k, feats, &keep);
        }
        self.tiles.tile(z, x, y)
    }

    /// The tiled style (JSON text).
    pub fn style(&self) -> &str {
        &self.style
    }

    /// The stage 1 that the map holds (its road table's rows and lines; a redraw does not change the lines).
    pub fn sources(&self) -> &sources::Styled {
        &self.styled
    }

    /// Give the edges of `rows` their new levels, heads and caps, and change the tiles where the drawing changed.
    pub fn relevel(&mut self, rows: &[LevelRow]) -> Result<Redrawn, crate::Error> {
        let fills = self.fills_change(rows);
        self.set_rows(rows)?;
        // the ring: the changed edges and the edges at their end nodes (a road's caps and joins come from the roads at its nodes)
        let table = &self.styled.roads.roads.table;
        let ring: HashSet<u32> = rows.iter().map(|x| self.rows[&x.edge_id]).flat_map(|i| {
            std::iter::once(i as u32).chain(ends(table.line(i)).into_iter().flat_map(|p| self.at_node[&p].iter().copied()))
        }).collect();
        let new = if fills { roadstyle_engine::restyle(&self.styled, &self.look)? } else { roadstyle_engine::restyle_same_fills(&self.styled, &self.look)? };
        let mut out = Redrawn { style_changed: new.layers != self.styled.layers, ..Default::default() };
        let mut new_sources: HashMap<String, Src> = new.sources.into_iter().collect();
        for i in 0..self.styled.sources.len() {
            let k = self.styled.sources[i].0.clone();
            if !self.options.wants(&k) {
                continue;
            }
            match (&self.styled.sources[i].1, new_sources.remove(&k)) {
                (Src::Simple(old), Some(Src::Simple(mut now))) => {
                    if !old.items.is_empty() {
                        return Err(crate::error::edits(format!("redraw: the source {k} has line items, which a redraw does not make: draw the map again")));
                    }
                    (now.read, now.palette, now.classes, now.promote, now.cols) = (old.read.clone(), old.palette.clone(), old.classes.clone(), old.promote, old.cols.clone());
                    let (was, is) = (by_edge(old.features_of(&self.styled.roads.roads, &ring)), by_edge(now.features_of(&new.roads.roads, &ring)));
                    let changed: HashSet<u64> = was.keys().chain(is.keys()).filter(|e| was.get(e) != is.get(e)).copied().collect();
                    if !changed.is_empty() {
                        let (keep, whole, _) = self.options.rule(&k, Default::default);
                        let feats = now.features_of(&new.roads.roads, &ring).filter(|(_, p, _)| edge(p).is_some_and(|e| changed.contains(&e)));
                        out.pieces_gone += self.tiles.replace_lines(&k, &changed, feats.map(|(_, p, c)| (c, p.into_iter())), &keep, whole)?;
                        out.edges += changed.len();
                    }
                    self.styled.sources[i].1 = Src::Simple(now);
                }
                (Src::Json(old), Some(Src::Json(now))) if *old != now => {
                    crate::tile_source(&mut self.tiles, &self.styled, &self.options, &k, Source::Json(&now));
                    out.sources.push(k);
                    self.styled.sources[i].1 = Src::Json(now);
                }
                _ => {}       // a base-map layer or an overlay: a redraw does not change it (restyle has none)
            }
        }
        self.styled.roads = new.roads;
        self.piece_at.clear();
        Ok(out)
    }

    /// A row gives an edge another fill level (then the slots are made again).
    fn fills_change(&self, rows: &[LevelRow]) -> bool {
        let r = &self.styled.roads.roads;
        rows.iter().any(|x| self.rows.get(&x.edge_id).is_none_or(|&i| match &r.solved {
            Some(s) => i64::from(s[i][3]) != x.levels[3],
            None => r.roles.col(Role::FillLevel).is_none_or(|c| r.table.cell(c, i).as_i64() != Some(x.levels[3])),
        }))
    }

    /// The new values in the roads' table (the solved levels when the engine solved them, else the level columns) for the next stage 1.
    fn set_rows(&mut self, rows: &[LevelRow]) -> Result<(), crate::Error> {
        let r = &mut self.styled.roads.roads;
        let at: Vec<usize> = rows.iter().map(|x| self.rows.get(&x.edge_id).copied()
            .ok_or_else(|| crate::error::edits(format!("redraw: {} is not an edge of the map", x.edge_id)))).collect::<Result<_, _>>()?;
        let mut cols: Vec<(Role, Vec<(usize, Value)>)> = Vec::new();
        let mut put = |role: Role, row: usize, v: Value| match cols.iter_mut().find(|(r, _)| *r == role) {
            Some((_, c)) => c.push((row, v)),
            None => cols.push((role, vec![(row, v)])),
        };
        for (x, &row) in rows.iter().zip(&at) {
            match &mut r.solved {
                Some(s) => s[row] = x.levels.map(|l| l.clamp(i16::MIN.into(), i16::MAX.into()) as i16),
                None => for (role, l) in [Role::CasingStart, Role::CasingLevel, Role::CasingEnd, Role::FillLevel].into_iter().zip(x.levels) {
                    put(role, row, l.into());
                },
            }
            for (role, h) in [Role::HeadStartM, Role::HeadEndM].into_iter().zip(x.heads) {
                put(role, row, h.map_or(Value::Null, Value::from));
            }
            for (role, c) in [Role::CapStart, Role::CapEnd].into_iter().zip(&x.caps) {
                put(role, row, c.clone().map_or(Value::Null, Value::from));
            }
        }
        for (role, cells) in cols {
            let c = r.roles.col(role).ok_or_else(|| crate::error::edits(format!("redraw: the map has no column of the role {role:?} (give it in the look)")))?;
            r.table.set_cells(c, &cells).map_err(crate::Error::Model)?;
        }
        Ok(())
    }
}

/// The end nodes of a line (its first and last point, as bits).
fn ends(line: Option<&[[f64; 2]]>) -> Vec<[u64; 2]> {
    line.filter(|l| !l.is_empty()).map_or(Vec::new(), |l| [l[0], l[l.len() - 1]].map(|p| p.map(f64::to_bits)).to_vec())
}

/// A piece's road (`__rs_edge`).
fn edge(p: &roadstyle_model::props::Props) -> Option<u64> {
    p.get(roadstyle_model::mark::Mark::Edge.name()).and_then(Value::as_u64)
}

/// Each edge's pieces (properties and line), to find the edges whose drawing changed.
type Pieces<'a> = HashMap<u64, Vec<(roadstyle_model::props::Props<'a>, Option<&'a [[f64; 2]]>)>>;

fn by_edge<'a>(feats: impl Iterator<Item = (usize, roadstyle_model::props::Props<'a>, Option<&'a [[f64; 2]]>)>) -> Pieces<'a> {
    let mut out: Pieces = HashMap::new();
    for (_, p, c) in feats {
        if let Some(e) = edge(&p) {
            out.entry(e).or_default().push((p, c));
        }
    }
    out
}
