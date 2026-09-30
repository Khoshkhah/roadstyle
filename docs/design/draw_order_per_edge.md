# Draw order per edge, not only by class and level

**Status:** approved by Kaveh 2026-09-30 and implemented (`render(order_col=, band_col=)`,
`_mark_order`, tests in `tests/test_render_web.py`). A roadstyle change asked for by Kaveh, an
exception to "roadstyle is not changed for mapstyle": any caller gets it.

## Problem

Which road draws over which is decided by two things only:

1. **the level** (`lvl`, from the OSM `layer`: `draw_order_from_layer.md`), which picks the band:
   tunnel, low, ground, high, bridge. Each band is a casing layer then a fill layer, so every road of
   a band has its casing under every fill of that band (junctions merge cleanly);
2. **the class** (`ROAD_Z[class]`, e.g. motorway 9, footway 1) inside a band, as the `line-sort-key`
   (`lvl * 1000 + ROAD_Z`); `rsColor` adds 500 to the roads it paints.

A caller can't say "this edge above that one" for any other reason. Two cases in duckOSM's Monaco
walking network (`walk_type`, per edge) show where that hurts:

| walk_type | edges | What it is | Wanted | Today (class footway) |
|---|---|---|---|---|
| `crossing` | 604 | the zebra: a footway across a street, at the street's level | **over** the street, halo included | under the street's fill (z 1), or, with mapstyle's walking look (z 9.5), its fill over the street but its halo under it |
| `sidewalk` | 1206 | a footway beside a street, often touching its edge | **under** the street, casing included | its fill over the street's casing, cutting the junction shape |

Both need a road in a *different band* than its level gives (crossing: above the ground roads;
sidewalk: below them), and a caller-chosen order inside a band (e.g. a route or a class the caller
cares about over the others) without inventing classes.

## Proposal: two optional columns, both named per call

```python
rs.render_edges(g, order_col="order", band_col="band")
```

1. **`band_col`**: `-1`, `0` or `1` per edge: which ground-level band it draws in:
   - `-1`: the **low** band (`roads-low-casing` / `roads-low-fill`): casing and fill under every
     ground road, plain look (sidewalks);
   - `0`: the ground band (`roads-casing` / `roads-fill`), as today;
   - `1`: the **high** band (`roads-high-casing` / `roads-high-fill`): casing and fill over every
     ground road, plain look, under bridges (crossings).

   Only for edges that are neither tunnel nor bridge: a structure keeps its band and look. Missing
   or null = today's rule (the sign of `lvl`). The layers exist already (added with the `layer`
   order); only which edges they draw changes: their filters read a baked `__rs_band` instead of
   the sign of `lvl`.
2. **`order_col`**: a number per edge: its order inside its band, instead of its class's
   `ROAD_Z`: `line-sort-key = lvl * 1000 + order`. Missing or null = the class's `ROAD_Z`, as today.
   Values are clamped to -400 … 400, so levels stay 1000 apart and `rsColor`'s +500 still lifts a
   painted road over every other on its level.

Nothing changes when neither keyword is given. Both are baked as feature properties
(`__rs_band`, `__rs_order`), so they work with `tiles=True` (the tile properties carry them) and
with `rsColor`'s lift.

## What stays

Layer ids and their order (host pages anchor on `roads-casing`, `roads-bridge-casing`,
`roads-highlight`); the bridge toggle (hides `lvl > 0`, not the high band); tunnel mouths and 3D
decks (structures only); arrows and labels keep following `lvl` (a crossing has no arrows; its
label, if any, stays in the ground tier).

## First user: mapstyle

mapstyle reads duckOSM's `walk_type` in `load_roads` and passes:

| walk_type | band | order |
|---|---|---|
| `crossing` | 1 | – |
| `sidewalk` | -1 | – |
| anything else | – | – |

and drops its walking look's "every path above every road" (`z_order` 9.5): with sidewalks under
and crossings over, the other paths meet roads only at their ends, where the class order (street
over path) is right, as in openstreetmap-carto. A mapstyle design note follows once this is in.

## Checks

- Tests (roadstyle): without the keywords the style is byte-identical to today's; `band_col`
  moves an edge between the low / ground / high filters, but never a tunnel or a bridge;
  `order_col` sets `line-sort-key` and clamps; both survive `tiles=True`; `rsColor` still lifts.
- In a browser (Monaco, via mapstyle), along Avenue Princesse Grace (48 crossings and 84 sidewalks
  within 20 m of it): the crossings drawn over the street with their halo, the sidewalks under
  the street's edge, junctions clean; before and after snapshots.
- Docs: a row each in `docs/reference/parameters.md`, SKILL.md (a caller needs to know it),
  CHANGELOG ("Added").
