# Edge items: one mechanism for everything that belongs to a road

**Status:** design, 2026-10-07, waiting for review. Step 1 (the label) built on branch `edge-label`, step 2 (the lookup) on branch `edge-lookup`. Builds on [A general core](core_model_and_views.md) and
[Overlays attached to edges](edge_overlays.md).

## Why

A road is drawn from many pieces, and two separate bookkeeping systems say which pieces belong to which road:

| Pieces | How a piece names its road |
|---|---|
| roadstyle's fill, hover, click | the feature's own id (`roads` source) |
| outline parts, seams, fill halves | `__rs_road` |
| two-way end caps, street names, arrows | `__rs_road` + `__rs_road2` |
| 3D bridge decks | their own ids and a list |
| bridge shadows | nothing (a shadow line covers several edges) |
| items attached with `Overlay(edge_col=...)` (lanestyle's lanes, mapstyle's crossings) | the overlay's own column, through another code path |

The drawing order is already the same for both (at each position: every casing, then every fill and every item
attached to a road there). But hiding, colouring and highlighting a road go through each system separately, so a
piece gets forgotten: the fill halves stayed when their road was filtered out (2026-10-07), and `rsFilter` on the
roads never hides an overlay's lanes. "roadstyle alone" and "roadstyle + items + `road_fill=False`" should be one
mechanism, not two that agree by luck.

## The model

```
Edges     the input of render_edges: line, tags, levels (casing start / main / end, fill), ends
Items     everything that belongs to an edge, each carrying its edge's label
            built in:  fill (and its halves), outline parts, seams, end caps, names, arrows, shadows, decks
            yours:     Overlay(edge_col=...)  lanes, markings, crossings, ...
Overlays  only what belongs to no road: zones, points, lines of your own (placement under / over)
```

- **One label.** Every item of every source carries `__rs_edge` (the id of its edge as the page knows it), and
  `__rs_edge2` when it belongs to both directions of a two-way road (an end cap, a name). A shadow line, which
  covers several edges, carries their list (`__rs_edges`).
- **One lookup.** One function in the page turns "these edges" into a filter / colour / highlight for every item
  layer, built-in or yours; `rsFilter`, the class, bridge and tunnel switches, the editor's mode boxes, colour by
  data, hover and selection all go through it. A shadow line shows while any of its edges is shown (decided in the
  page: the list is short).
- **The built-in fill is an item.** It is the item roadstyle attaches to every edge by default; `road_fill=False`
  leaves it out, and a library's lanes take its place. Same placement, same label, same lookup.
- **Overlays** keep their own `rsFilter(ids, layer)`, for things that are not part of a road.

## Steps (each one a branch, the look identical, checked in a real page)

1. **The label:** every built-in piece carries `__rs_edge` / `__rs_edge2` / `__rs_edges` (`__rs_road` and the
   feature-id uses go). A test walks every source of a page and fails on any road piece without the label.
2. **The lookup:** one function used by every show / hide / colour / highlight; items attached with `edge_col` get
   the label from that column and follow it (hiding a road hides its lanes; clicking a lane selects its road).
3. **The fill as an item:** the built-in fill drawn through the same item path; `road_fill=False` = no fill item.

## Not changed

The drawing order, the levels, the look of every piece, the `Overlay` API for things that are not roads.
