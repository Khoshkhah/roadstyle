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

**A over B** (Kaveh 2026-10-06): every part of A's casing (start head, main part, end head) and its fill come after
B's fill. Before, only A's main part did: where B passed under A close to one of its ends, B's fill hid A's outline there (Monaco: the bridge
95449780#1f over 4229327#1f). A head that **joins** B, or joins a road that joins B (the next piece of the tunnel A runs into at its mouth),
is left out: it is a junction, where the head is under the fills it joins. Two ramps, each over one tube of a tunnel and joining the other
tube, still make a loop of four rules no order keeps; the solver gives one of their pairs up and reports it.

**Three parts for every road, no length in the solver** (Kaveh 2026-10-06). Every road has a start head, a main part and an end head,
whatever its length; the drawing gives them their metres (`head_m`, or a road's own in `heads.csv` / `head_start_m_col` /
`head_end_m_col`), and a road shorter than its two heads has a main part of no length. The solver takes no metres, only which roads
have an empty main part (`rs.empty_mains(roads, head_m, heads)` -> `solve_levels(empty_main=...)`): a stack never lifts an empty main
part, since a rule on a part nobody sees would cost real ones (without it Monaco gave up 23 pairs, 7 of them for invisible parts).

A stack rule is **real** when that part of A crosses B (they meet at a point that is not an end of either road), and **near** when
it only comes near (the pair was found by `band_dist`, or this part is away from the crossing): `rs.casing_parts(roads, head_m, heads)`
gives the parts as drawn, and `solve_levels(parts=...)` tells them apart, with no length in the solver itself. The solver keeps, in
this order: the real crossings, the order wishes, the near rules, then the cost and fewest positions (Kaveh 2026-10-06: a near rule has
the lowest weight; it must never cost a real crossing). A **given-up** pair is a real crossing that broke: a flaw on the map. A near
rule that broke is a **warning** (`attrs["levels_near"]`), shown apart in the editor. Monaco: 0 given up, 87 near warnings, 4 order
wishes not kept (was 47), 15 positions (was 10); with the near rules above the order wishes instead it would be 0 / 22 / 47 / 10.
Before, every rule counted as a crossing: 22 given up, 20 of them near-only and the 2 others a head 7 and 18 m from the crossing.

**Automatic heads and caps** (`rs.auto_ends`, Kaveh 2026-10-06: better than one number and one cap for all), for the widths the page
draws at zoom 18 (street level; widths are pixels, so lower zooms are wider on the ground):

- *head length* (before solving, geometry only): from the node along the road until its line is `(own width + the other's) / 2` from every
  road joined at that end, so as far as the two drawings overlap (a right angle: 2-3 m; a narrow merge: 10 m and more); a dead end 0.5 m;
  start + end never more than the road.
- *cap* (after solving, geometry and levels): round where the round end of the fill lies inside the fills of the joined roads drawn at its
  level or above, else flat: a road going on into a lower piece would show its round end as a bump on it, and a wide road ending on a
  narrower one would cross its outline (Tunnel Aureglia into Rue Grimaldi). Square never helps there (it covers the round end and more).

Yours in `heads.csv` / `caps.csv` go on top (empty: automatic); `levels.csv` has the ends as drawn. On Monaco the caps matched 5 of the 6
flat ends set by hand (the sixth is under a road drawn above it); the head lengths come out a little shorter than the ones set by hand.

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
| `caps.csv` | your caps per road end (`road`, `start`, `end`: empty = automatic, `round`, `square`, `flat`) | `scripts/edit_levels.py` (the *start* / *end* choices in a road's card) |
| `heads.csv` | your head lengths per road end (`road`, `start_m`, `end_m`; empty = automatic) | `scripts/edit_levels.py` (the *heads* sliders in a road's card) |
| `levels.csv` | the result, one row per edge: `edge`, `casing_start`, `casing_level`, `casing_end`, `fill_level`, and its ends as drawn: `head_start_m`, `head_end_m`, `cap_start`, `cap_end` (render_edges' `head_start_m_col` / `head_end_m_col` / `cap_start_col` / `cap_end_col`) | `scripts/solve_levels.py` |

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
each end (`caps.csv`); flat is for an end whose round end reaches across a narrower road it ends on, square keeps the drawn length.
And *heads*: each end's head length in metres (`heads.csv`, solved with the rest).
The *Issues* tab lists the crossing pairs the solver could not keep, with A's parts at or under B's fill in red; a
row opens the pair, to fix by hand. The list of
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
