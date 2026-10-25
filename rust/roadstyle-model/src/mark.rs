//! The marks: the one list of the properties that the engine writes on a feature (target_architecture.md (c), N30). Each has its name
//! in the outputs (the `__rs_*` names of 0.25, and four names of the slots with no prefix) and the features on which the page reads it.
//! The page's declaration `static/dashboard/reads.json` is made from this list (`page_reads_json`; a test fails when the file differs).

use std::borrow::Cow;

/// The fill of colour option `i` (option 0: `Mark::Fill`, `__rs_fill`; then `__rs_fill__<i>`).
pub fn option_fill(i: usize) -> Cow<'static, str> {
    if i == 0 { Cow::Borrowed(Mark::Fill.name()) } else { Cow::Owned(format!("__rs_fill__{i}")) }
}

/// A property of a view's palette (palettes.rs: `<property>@<palette>`, the copy that the palette changes).
pub fn in_palette(property: &str, palette: &str) -> String {
    format!("{property}@{palette}")
}

/// A fill of the road: the active option's (`__rs_fill`), another option's (`__rs_fill__<i>`) or a view palette's (`__rs_fill@<palette>`).
pub fn is_fill(name: &str) -> bool {
    name.starts_with(Mark::Fill.name())
}

/// The option of a fill's name (`option_fill`), None: not one.
pub fn option_of_fill(name: &str) -> Option<usize> {
    if name == Mark::Fill.name() { Some(0) } else { name.strip_prefix("__rs_fill__")?.parse().ok().filter(|i| *i > 0) }
}

/// The features on which a page reads a mark or a column (reads.json's lists).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    /// a feature of the road layer: a road piece or an item
    Pieces,
    /// a 3D deck or its shadow
    Decks,
    /// a name or arrow slot
    Slots,
    /// a row of the road table
    Table,
}

impl Kind {
    pub const ALL: [Kind; 4] = [Kind::Pieces, Kind::Decks, Kind::Slots, Kind::Table];

    pub fn name(self) -> &'static str {
        match self {
            Kind::Pieces => "pieces",
            Kind::Decks => "decks",
            Kind::Slots => "slots",
            Kind::Table => "table",
        }
    }
}

macro_rules! marks {
    ($($(#[$doc:meta])* $v:ident = $name:literal $([$($k:ident),*])?;)*) => {
        /// A property that the engine writes on a feature.
        #[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
        #[non_exhaustive]
        pub enum Mark {
            $($(#[$doc])* $v,)*
        }

        impl Mark {
            /// Every mark, in the order of this list (the colour options' fills after the first: `option_fill`).
            pub const ALL: &'static [Mark] = &[$(Mark::$v),*];

            /// The property's name in the outputs.
            pub const fn name(self) -> &'static str {
                match self {
                    $(Mark::$v => $name,)*
                }
            }

            /// The features on which the page reads the mark.
            pub fn page_reads(self) -> &'static [Kind] {
                match self {
                    $(Mark::$v => &[$($(Kind::$k),*)?],)*
                }
            }
        }
    };
}

marks! {
    /// the road's key (RoadKey): the pieces' feature id (promoteId) and a slot's road
    Edge = "__rs_edge" [Pieces, Slots];
    /// the key of a two-way road's other edge
    Edge2 = "__rs_edge2" [Pieces, Table];
    /// the keys of a deck's roads
    Edges = "__rs_edges" [Decks];
    /// a piece's kind: 0 casing, 1 fill, 2 shadow, 3 tunnel gap, 4 tunnel dash, 5 item
    PieceKind = "__rs_k" [Pieces];
    /// a piece's sort key (an integer)
    Sort = "__rs_s" [Pieces];
    /// the class filter's value
    Class = "__rs_cls" [Pieces, Table];
    /// the class index of the road layer's lookups
    ClassIndex = "__rs_ci";
    /// the road's grade (the position of its fill, as a number)
    Lvl = "lvl" [Pieces, Table];
    /// an item's road's grade
    ItemLvl = "__rs_lvl" [Pieces];
    /// access_col: the road's access kind
    Access = "__rs_access" [Pieces, Table];
    /// a picked item (clicked and lit as itself)
    Pick = "__rs_pick" [Pieces];
    /// a deck's casing slab
    CasingSlab = "__rs_casing_slab" [Decks];
    /// a two-way road
    Twoway = "__rs_twoway" [Table];
    /// a one-way road
    Oneway = "__rs_oneway";
    /// a reverse pair of a single-line class: the later edge
    Dup = "__rs_dup" [Table];
    /// a two-way pair's one casing
    Pair = "__rs_pair";
    /// the twin's row
    Twin = "__rs_twin";
    Bridge = "__rs_bridge";
    Tunnel = "__rs_tunnel";
    /// the road's own colour (color_table)
    Color = "__rs_color";
    /// the fill of the active colour option (bake_props)
    Fill = "__rs_fill";
    Width = "__rs_w";
    Opacity = "__rs_op";
    Dash = "__rs_dash";
    Casing = "__rs_casing";
    CasingWidth = "__rs_cw";
    CasingOpacity = "__rs_cop";
    /// the style class of bake_props
    StyleClass = "__rs_class";
    /// the cap of both ends (when not round)
    Cap = "__rs_cap";
    Cap0 = "__rs_cap0";
    Cap1 = "__rs_cap1";
    /// two different ends
    Split = "__rs_split";
    /// the head lengths in metres
    HeadStart = "__rs_hs";
    HeadEnd = "__rs_he";
    /// the casing number of the main part, the fill level, the casing numbers of the heads, the band
    CasingLevel = "__rs_cl";
    FillLevel = "__rs_fl";
    CasingStart = "__rs_cs";
    CasingEnd = "__rs_ce";
    Band = "__rs_band";
    /// metre widths: the width, the casing, the twin's width (over cos(latitude))
    WidthM = "__rs_wm";
    CasingM = "__rs_cm";
    TwinWidthM = "__rs_twm";
    /// a casing piece: a seam at a cut, its lap below zoom 17, the main part, an end's stub
    Seam = "__rs_seam";
    Lap = "__rs_lap";
    Main = "__rs_main";
    Stub = "__rs_stub";
    /// an item: its overlay, its number, its order, its colour, its width and offset in metres, its first zoom
    ItemOverlay = "__rs_ov";
    Item = "__rs_item";
    ItemOrder = "__rs_ord";
    ItemColor = "__rs_ic";
    ItemWidthM = "__rs_iwm";
    ItemOffsetM = "__rs_iom";
    ItemMinZoom = "__rs_imz";
    /// a deck: its base, its top, its chain
    DeckBase = "__rs_base";
    DeckHeight = "__rs_height";
    DeckChain = "__rs_chain";
    /// a slot: its arrow, its chain, its number and its rank
    SlotArrow = "__rs_arw";
    SlotChain = "chain" [Slots];
    Slot = "slot" [Slots];
    SlotRank = "rank" [Slots];
}

/// The contract columns (duckOSM's names) that the page reads on a kind of feature, beside the marks.
pub const PAGE_COLUMNS: &[(Kind, &[&str])] = &[
    (Kind::Slots, &["oneway", "highway", "name"]),
    (Kind::Table, &["name", "highway", "bridge", "tunnel", "edge_ref", "driving", "walking", "cycling"]),
];

/// The prefix of the marks' names (not of the slots' chain, slot and rank, and lvl): a property with it is the engine's, not a user's.
pub const PREFIX: &str = "__rs_";

/// The prefix of a user column that has a mark's name (it is kept aside as `__rs_kept_<name>` until Roles: R6 part 3).
pub const KEPT: &str = "__rs_kept_";

impl Mark {
    /// The mark of a property name (None: not a mark; a colour option's fill: `option_of_fill`).
    pub fn of(name: &str) -> Option<Mark> {
        Mark::ALL.iter().copied().find(|m| m.name() == name)
    }
}

/// What the page reads on `kind`: the marks, then the contract columns.
pub fn page_reads(kind: Kind) -> Vec<String> {
    let marks = Mark::ALL.iter().filter(|m| m.page_reads().contains(&kind)).map(|m| m.name().to_string());
    let cols = PAGE_COLUMNS.iter().filter(|(k, _)| *k == kind).flat_map(|(_, c)| c.iter().map(|s| s.to_string()));
    marks.chain(cols).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_name_is_one_mark() {
        let mut names: Vec<_> = Mark::ALL.iter().map(|m| m.name()).collect();
        let n = names.len();
        names.sort();
        names.dedup();
        assert_eq!(names.len(), n, "a name of two marks");
        for &m in Mark::ALL {
            assert_eq!(Mark::of(m.name()), Some(m));
        }
        assert_eq!(Mark::of("highway"), None);
        assert_eq!((option_of_fill(&option_fill(0)), option_of_fill(&option_fill(3)), option_of_fill("__rs_fill__x")), (Some(0), Some(3), None));
    }
}
