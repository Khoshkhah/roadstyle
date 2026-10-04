# Overlays attached to edges

**Status:** design, then code. Builds on [Divided casing and one band](levels_split_casing.md).

An overlay is an extra layer drawn with the roads: zones, points of interest. Until now it could be placed only **under all roads** or **over all roads** (`placement`). A thing that belongs to one road, such as a lane,
a lane marking, a zebra crossing, a sign, or an arrow painted on a lane, must be drawn **at the place of its road in the drawing order**: over the road's fill, under every road that lies above, and in the right order among
the things of its own road.

The roads are drawn by their casing and fill numbers, position by position. An overlay **attached to edges** is drawn at the position of its edge's **fill number**, after the fills, in the order the data gives.

## Three ways to use it

1. **Roadstyle alone.** No extra input: roadstyle draws the casing and the fill of each road.
2. **A library that adds items to the roads** (mapstyle). The roads keep their casing and fill, and the extra items (`Overlay` with `edge_col`) are drawn at the place of their road, over its fill.
3. **A library that draws the fill itself** (lanestyle). roadstyle draws the **casing** of each road, and **not its fill** (`road_fill=False`): the lanes, dash lines, connectors and other items attached to the road with `edge_col` and `order_col` are the fill.

With `road_fill=False` the road's own fill layers stay in the page but are invisible (opacity 0, the end caps' fills too), so that a click or a hover still finds the road, and the tunnel and bridge looks of the road's fill are not drawn.
The road's casing, its position and its heads are unchanged: it is a solid band under the items. A road drawn wider than its items shows the band around them.

## The data

An overlay is a table of features (lines, polygons or points). Two columns make it attached to edges:

| Argument of `Overlay` | Meaning |
|---|---|
| `edge_col` | the property that holds the **id of the feature's edge**. The ids are the values of the roads' own id column (`edge_id_col` of `render_edges`, default `edge_id`) |
| `order_col` | the property that holds a whole number, the **order** of the feature: the lower is drawn first. Null is 0. Without `order_col`, every feature has order 0 |
| `color_col` | optional: the property that holds a colour (CSS) per feature; null or missing: the overlay's `color` |

```python
lanes = rs.Overlay(lane_polygons, edge_col="edge_id", order_col="order", color_col="color", kind="fill")
rs.render_edges(edges, overlays=[lanes, markings, signs])
```

`placement` is not used for an overlay with `edge_col`: its place is its edge's.

## The order

The key of a feature is the pair **(fill number of its edge, order)**. Features are drawn by the fill number first and, inside the same fill number, by `order`. In one position the layers are, from the bottom:

1. the casings,
2. the fills,
3. the edge overlays, by `order` (ties: the overlay that comes first in `overlays`),
4. the one-way arrows,
5. the street names.

So a feature is over the fill of its own edge and under every road above (a higher fill number), whatever the order inside the position. The order is **global**, not per edge: the same number orders the features of different edges at the same position.

One map layer is made for each `(fill number, order)` that occurs in an overlay, for each kind of layer of the overlay (a polygon overlay has a fill and an outline). Their number is the number of positions times the number of orders: small.

## What roadstyle does

1. The roads' fill numbers are known (computed, or given in `fill_level_col`). A lookup `edge id -> fill number` is made from the roads' `edge_id_col` (as text, so ids past 2**53 match).
2. For each overlay with `edge_col`: every feature gets the property `__rs_fl` (its edge's fill number) and `__rs_ord` (its order). An edge id that is not among the roads is an **error** that names the number of such features and the first few ids; no feature is drawn at a default position.
   A roads table without `edge_id_col` is an error too, when an overlay needs it.
3. The layers of the overlay are made for each `(fill number, order)` that occurs, with the filter `__rs_fl == position and __rs_ord == order`, and put in the stack between the fills of that position and its arrows (or, without arrows, its names, or, without those, right after its fills).
4. The page keeps what overlays do now: the Layers toggle shows and hides all the layers of the overlay; hover and click highlight and popups work across the layers (the source is one, with `generateId`); `rsColor` colours them. `rsFilter(ids, overlay)` **combines** its filter with the layers' own
   (it must not remove the position and order of a layer).

## The arrows and street names of roadstyle

roadstyle draws the one-way arrows and the street names itself, from small pieces of road (**slots**) cut along chains of edges. They are at the end of each position (the order above), and a slot had the fill number of its group. They were **not connected to a road**: a slot did not know its edge,
so `rsFilter` on the roads and the road filters did not reach them. They now follow the same rule as an overlay attached to edges:

- A slot belongs to **one edge**: the edge that lies under its middle point. The slot carries `__rs_road`, the feature index of that edge, and, for a two-way street, `__rs_road2`, the index of the twin edge (the same two properties as the end caps of two-way pairs).
- Its fill number is that of its edge: the chains already do not join edges of different fill numbers, so this is the group's number, now by construction.
- **They follow the filters.** When the roads are filtered (`rsFilter(ids)`, which shows only some edges), the arrows and names of the edges that are not shown are hidden too: a slot stays while either of its two edges is shown. The class filter and the colour options work as before.
- The order of a position is unchanged: casings, fills, the overlays by order, the arrows, the names. A position's names are over its arrows because they are the last layers of the position.

`tiles=True`: the slots are a tile layer of the archive and carry the same two properties.

## Not in this change

- No data-driven width or icons: an overlay has one `width`, `radius`, `kind`. Symbols (icons, text) on an overlay are not a kind of `Overlay` yet.
- `tiles=True`: an overlay is a GeoJSON source of its own, not in the archive; with edge overlays it works the same.
- The casing of an overlay's thing is not placed apart; an overlay is drawn after the fill.

## Tests

- The place of the layers: for each position, the overlays are after its fills and before its arrows, by order; a feature of an edge at a higher fill number is above (in a later layer) one of a lower number.
- The numbers: a feature gets the fill number of its edge, with computed numbers and with given columns; an unknown edge id is an error that lists ids; no `edge_id_col` is an error.
- `order_col`: two orders in one position are two layers in that order; null is 0; ties follow the order of `overlays`.
- `color_col`: the paint reads the property.
- `rsFilter` on an edge overlay keeps the position and order of each layer (browser check).
- The slots: each carries the edge under its middle point (`__rs_road`, and `__rs_road2` for a two-way street), with the same fill number as that edge; after `rsFilter(ids)` the arrow and name layers filter by those properties (browser check).
- Without `edge_col` nothing changes: `under` and `over` as before.

## Open points

1. Symbols (icons and text) for lane arrows and signs: an overlay kind for them.
2. An overlay of casings (a thing that must be drawn with a position's casings, before its fills).
