# The level step: solver input, solver, and a renderer without band or order

**Status:** built (branch `levels`), waiting for Kaveh's review, 2026-10-06. Builds on
[Divided casing and one band](levels_split_casing.md) (the model) and the v2 test's pair tables (`docs/v2/pair-tables.md` on `v2-dev`).

## Why

The renderer took a band and an order and computed the levels itself, so a rule about drawing order ended up inside the drawing. Kaveh:
"the rendering engine shouldn't get order or band as input". Now there are two steps:

1. **the level step**: from the edges (any edges roadstyle draws, not only duckOSM's), the solver's input, then the four numbers per edge;
2. **the renderer**: draws the four numbers. `render_edges` takes no `band_col` and no `order` (passing one is an error that says to compute
   the levels first). Without level columns it still calls `compute_levels` with its defaults, so `rs.render_edges(edges)` keeps working.

## The rule: meet or cross

Two roads with **different bands** (a tunnel and a street, a bridge and the road it lands on):

- if they **cross**, or run within `band_dist` (10 m) of each other away from a node they share, the **band** decides: the higher band is
  over the lower one (a `stack` pair);
- if they **only meet** at a node (a tunnel mouth, a bridge end), the **priority** decides, as for two roads of one band: roundabout, then
  tunnel, then bridge, then the road class (an `order` wish).

With an explicit `band_col` the caller's bands decide over and under everywhere, also where roads only meet: a zebra crossing set over its
street stays over it (lanestyle, mapstyle).

A **short** road on top (shorter than `2 * head_m`, one casing number that meets the roads at both its ends) keeps its pair on its **fill**:
its fill is after the lower road's fill. Before, its pair was dropped, and short ground pieces over a tunnel could be drawn level with it.

## Files (one folder per area)

| file | what | written by |
|---|---|---|
| `roads.parquet` | one row per road (both directions of a segment together): `road` (the id of its first edge), `edges` / `reversed` (the ids of its edges running its way / the other way), `band`, `priority`, the line | `scripts/level_input.py` (`rs.level_input`), every run |
| `pairs.csv` | one row per relation: `relation`, `a`, `b`, `a_end`, `b_end` (below) | `scripts/level_input.py`, every run |
| `edits.csv` | your changes to the pairs, same columns plus `enabled`: `false` switches a pair off, anything else adds one; `a` / `b` may name either direction of a road | created empty once; you or a pair editor, never overwritten |
| `levels.csv` | the result, one row per edge: `edge`, `casing_start`, `casing_level`, `casing_end`, `fill_level` | `scripts/solve_levels.py` (`rs.solve_levels`) |

Relations: `meet` (the end `a_end` of `a` is the end `b_end` of `b`: each head is under the other road's fill), `stack` (`a` is over `b`) and
`order` (`a`'s fill after `b`'s where they meet, a wish the solver may give up). A manual `meet` row joins two roads that do not share a point.

```
python scripts/level_input.py edges.gpkg out/monaco                          # any geo file roadstyle reads
python scripts/level_input.py monaco.duckdb out/monaco --query "SELECT * EXCLUDE (geometry), ST_AsWKB(geometry) AS geometry FROM driving.edges"
python scripts/solve_levels.py out/monaco
```

In Python: `roads, pairs = rs.level_input(edges)`, `solved = rs.solve_levels(roads, pairs, edits=...)`; `rs.compute_levels(edges)` is both in
one call and returns the edges with the four columns.

## Compared on Monaco (2,765 driving edges, 2026-10-06)

| | v1, class order | v1, priority | v2 test (tiers) | this |
|---|---|---|---|---|
| seconds | 0.3 | 0.2 | 1.1 | 1.3 |
| drawing positions | 6 | 6 | 13 | 15 |
| roundabout on top where it meets a road | 147 / 354 | 350 / 354 | 354 / 354 | 354 / 354 |
| tunnel on top at its mouth | 0 / 350 | 0 / 350 | 267 / 350 | 223 / 350 |
| crossings drawn the wrong way round | 0 / 129 | 0 / 129 | 114 / 129 | 0 / 129 |

v2's tiers lifted every tunnel above every other road across the map, so a street crossing over a tunnel was drawn under it. Here a
crossing keeps the band. 33 order wishes are not kept (they conflict with over and under); no stack pair is given up.

## Limits

- More positions (15 against 6 on Monaco): more layers in the page.
- A mouth where the roads also run near each other beyond the junction (a ramp diverging at a small angle) is a stack pair: the band decides there.
