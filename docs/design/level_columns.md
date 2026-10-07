# The drawing order of each edge (`casing_level_col`, `fill_level_col`)

**Status:** approved 2026-10-02 as part of mapstyle's `docs/design/node_levels.md` (Approach B, "go ahead"); a roadstyle
feature asked for, an exception to "roadstyle is not changed for mapstyle".

## Rule

Two integer columns name, for each edge, the **position** in the drawing order at which its casing is drawn and the position at which
its fill is drawn (the casing position is the lower, if they are given the other way round they are swapped; null = 0). At each position
**every casing of the position is drawn first, then every fill.** So:

- edges that share a node, whose intervals `[casing, fill]` intersect, have each casing under the other's fill: they merge cleanly;
- an edge whose positions are higher than another edge's (disjoint intervals) is drawn completely over it, casing included: an overpass;
- a ramp (casing position lower than its fill position) has its casing with the lower position's casings (under the roads it meets
  there) and its fill with the higher position's fills.

## Position only

With the columns the position alone orders the drawing: see [Divided casing and one band](levels_split_casing.md).

## How

For each position that occurs (0 always) the ground band's layers are repeated, in position order: the casing layers (`roads-casing`,
`-sq`, `-dash`) with the filter `__rs_cl == position`, the fill layers (`roads-fill`, `-sq`, `-pat`, the dashed classes'
`roads-fill-dash<n>`) with `__rs_fl == position`. Position 0 keeps the layer ids; others are `roads-casing-lv<n>`, `roads-fill-lv<n>`
(`-lv-2` for a negative position) with the usual suffix after it. Every edge is in band 0, so the low, high and bridge layers match nothing. Then every road layer that no feature can draw is left out (`_drop_empty_layers`: its filter, read on the distinct
properties of its source, holds for no feature at any zoom), so a position without a bridge has no bridge layers and one without square
ends no `-sq` layers; the page's code looks a layer up before it touches it, and `roads-fill` stays always (its line offset is read). The page recolours the fill layers of every position (`RS_FILL_LAYERS` is built from the style). The arrow tiers
skip a tier with no layers. `tiles=True` is refused for now.

## Checks

Tests: the layers and their filters for each position, the order (casings before fills, position by position), position 0 keeping the ids,
the tunnel look and the dashed classes at their positions, nothing without the columns, `tiles=True` refused.
