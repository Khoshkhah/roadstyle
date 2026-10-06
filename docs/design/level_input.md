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

**A over B** (Kaveh 2026-10-06): every part of A's casing (start head, main part, end head; a short road's one number) and its fill come after
B's fill. Before, only A's main part did: where B passed under A close to one of its ends, B's fill hid A's outline there (Monaco: the bridge
95449780#1f over 4229327#1f). A head that **joins** B, or joins a road that joins B (the next piece of the tunnel A runs into at its mouth),
is left out: it is a junction, where the head is under the fills it joins. Two ramps, each over one tube of a tunnel and joining the other
tube, still make a loop of four rules no order keeps; the solver gives one of their pairs up and reports it (Monaco 16, Södermalm 27).

**One part of A** (an edit): a `stack` edit may name a part of A's casing in `a_end`: `start`, `main` or `end` (empty: the whole road, the
rule above). Added, that part comes after B's fill even where its head joins B (a junction the rule leaves out). Switched off
(`enabled=false`), only that part is left out of a found whole pair; the rest of the pair stays. A part named on an edge that runs against its
road is turned to the road's way, as a meet's end is.

## Files (one folder per area)

| file | what | written by |
|---|---|---|
| `roads.parquet` | one row per road (both directions of a segment together): `road` (the id of its first edge), `edges` / `reversed` (the ids of its edges running its way / the other way), `band`, `priority`, the line | `scripts/level_input.py` (`rs.level_input`), every run |
| `pairs.csv` | one row per relation: `relation`, `a`, `b`, `a_end`, `b_end` (below) | `scripts/level_input.py`, every run |
| `edits.csv` | your changes to the pairs, same columns plus `enabled`: `false` switches a pair off, anything else adds one; `a` / `b` may name either direction of a road | created empty once; you, or `scripts/edit_levels.py`; never overwritten by the input step |
| `caps.csv` | each road's two ends (`road`, `start`, `end`: empty = round, `square`, `flat`), for `render_edges(cap_start_col=..., cap_end_col=...)` (`docs/design/square_ends.md`): drawing only, the solver does not read it | `scripts/edit_levels.py` (the *start* / *end* choices in a road's card) |
| `levels.csv` | the result, one row per edge: `edge`, `casing_start`, `casing_level`, `casing_end`, `fill_level` | `scripts/solve_levels.py` (`rs.solve_levels`) |

Relations: `meet` (the end `a_end` of `a` is the end `b_end` of `b`: each head is under the other road's fill), `stack` (`a` is over `b`) and
`order` (`a`'s fill after `b`'s where they meet, a wish the solver may give up). A manual `meet` row joins two roads that do not share a point.

```
python scripts/level_input.py edges.gpkg out/monaco                          # any geo file roadstyle reads
python scripts/level_input.py monaco.duckdb out/monaco --query "SELECT * EXCLUDE (geometry), ST_AsWKB(geometry) AS geometry FROM driving.edges"
python scripts/solve_levels.py out/monaco
```

**The editor** (`python scripts/edit_levels.py out/monaco`, a local page at http://localhost:8780/) writes `edits.csv`: click two roads, or find
them in the search box by an edge id (either direction) or an edge_ref (or a part of one) (road 1 orange, road 2 blue; their start and end points are marked), see every pair between them (the found ones, with *switch off*, and your edits,
with *delete*), and add one (`order` or `stack`: you choose which of the two is on top, for each new pair (no default); a stack on the whole road or one part of it, which
can also switch that part off in a found pair; `meet`: the chosen end of each). An order against an active stack the other way would be
given up, since a stack outranks an order: the panel warns before you add it and points to the stack to switch off first. Changes wait in a
list (kept over a reload of the page) until you press *Apply and solve*: then they are solved together while the map shows that it is
working, and the page reloads with the new levels, keeping the view and the picked roads; `levels.csv` is written too. If one change is
wrong or the solver refuses them (an unknown
road, nothing to switch off), nothing is saved, the list stays, and the panel says why. The `edits.csv` before each apply is kept as `edits.csv.bak`. A road's card also has *start* / *end*: round / square / flat for
each end (`caps.csv`); flat is for an end whose round end reaches across a narrower road it ends on, square keeps the drawn length. The list of
your edits shows each one's two roads when clicked. It is written for this page alone (the roadstyle map and its `rs*` API); the v2 test's
pair editor is not used.

In Python: `roads, pairs = rs.level_input(edges)`, `solved = rs.solve_levels(roads, pairs, edits=...)`; `rs.compute_levels(edges)` is both in
one call and returns the edges with the four columns.

## Compared on Monaco (2,765 driving edges, 2026-10-06)

| | v1, class order | v1, priority | v2 test (tiers) | this |
|---|---|---|---|---|
| seconds | 0.3 | 0.2 | 1.1 | 1.3 |
| drawing positions | 6 | 6 | 13 | 9 |
| roundabout on top where it meets a road | 147 / 354 | 350 / 354 | 354 / 354 | 354 / 354 |
| tunnel on top at its mouth | 0 / 350 | 0 / 350 | 267 / 350 | 223 / 350 |
| crossings drawn the wrong way round | 0 / 129 | 0 / 129 | 114 / 129 | 0 / 129 |

v2's tiers lifted every tunnel above every other road across the map, so a street crossing over a tunnel was drawn under it. Here a
crossing keeps the band. 33 order wishes are not kept (they conflict with over and under); no stack pair is given up.

## Whole numbers, and a bound on the positions

The numbers are whole multiples of `margin` (integer programming, HiGHS through `scipy.optimize.milp`). When every wish can be kept the
problem is pure difference rows and a flow gives whole numbers anyway; when some must be given up, the stages (slacks, and rows that hold
each stage's result) have fractional corners, and the LP returned values between two numbers, each one more drawing position (Monaco: 15
numbers in a span of 9). `solve_levels(max_positions=K)` (`--max-positions`) bounds the positions: a hard bound, the wishes give way first,
then the stack pairs. Monaco:

| bound | positions | stack given up | wishes not kept | tunnel on top at its mouth |
|---|---|---|---|---|
| none | 9 | 0 | 33 | 223 / 350 |
| 8 | 8 | 0 | 34 | 222 / 350 |
| 6 | 6 | 0 | 38 | 212 / 350 |
| 4 | 4 | 2 | 66 | 188 / 350 |

A bound at or above the minimum changes nothing.

## Limits

- More positions (9 against 6 on Monaco): more layers in the page.
- A mouth where the roads also run near each other beyond the junction (a ramp diverging at a small angle) is a stack pair: the band decides there.
