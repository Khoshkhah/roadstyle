# The level step: solver input, solver, and a renderer without band or order

**Status:** built, reviewed and merged, 2026-10-06. Builds on
[Divided casing and one band](levels_split_casing.md) (the model) and the v2 test's pair tables (`docs/v2/pair-tables.md` on `v2-dev`).

## Why

The renderer took a band and an order and computed the levels itself, so a rule about drawing order ended up inside the drawing. The request:
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

**A over B** (2026-10-06): every part of A's casing (start head, main part, end head) and its fill come after
B's fill. Before, only A's main part did: where B passed under A close to one of its ends, B's fill hid A's outline there (Monaco: the bridge
95449780#1f over 4229327#1f). A head that **joins** B, or joins a road that joins B (the next piece of the tunnel A runs into at its mouth),
is left out: it is a junction, where the head is under the fills it joins. Two ramps, each over one tube of a tunnel and joining the other
tube, still make a loop of four rules no order keeps; the solver gives one of their pairs up and reports it.

**Three parts for every road, no length in the solver** (2026-10-06). Every road has a start head, a main part and an end head,
whatever its length; the drawing gives them their metres (`head_m`, or a road's own in `heads.csv` / `head_start_m_col` /
`head_end_m_col`), and a road shorter than its two heads has a main part of no length. The solver takes no metres, only which roads
have an empty main part (`rs.empty_mains(roads, head_m, heads)` -> `solve_levels(empty_main=...)`): a stack never lifts an empty main
part, since a rule on a part nobody sees would cost real ones (without it Monaco gave up 23 pairs, 7 of them for invisible parts).
(2026-10-08: decided at make, with the stack rows; the solver takes no list of them, below.)

A stack rule is **real** when that part of A crosses B (they meet at a point that is not an end of either road), and **near** when
it only comes near (the pair was found by `band_dist`, or this part is away from the crossing): `rs.casing_parts(roads, head_m, heads)`
gives the parts as drawn, and (since 2026-10-08) `level_input` tells them apart once, at make, into `stack` / `near` rows. The solver keeps, in
this order: the real crossings, the order wishes, the near rules, then the cost and fewest positions (2026-10-06: a near rule has
the lowest weight; it must never cost a real crossing). A stack you add (`edits.csv`) is always real, even where the two roads only come near: you asked for it (2026-10-06). The order
wishes the solver let go are named (`attrs["levels_orders_not_kept"]`, levels_info.json `orders_not_kept`) and listed in the editor's
Issues tab, so two edits that disagree show which one lost. A **given-up** pair is a real crossing that broke: a flaw on the map. A near
rule that broke is a **warning** (`attrs["levels_near"]`), shown apart in the editor. Monaco: 0 given up, 87 near warnings, 4 order
wishes not kept (was 47), 15 positions (was 10); with the near rules above the order wishes instead it would be 0 / 22 / 47 / 10.
Before, every rule counted as a crossing: 22 given up, 20 of them near-only and the 2 others a head 7 and 18 m from the crossing.

**Near rules are off by default since 2026-10-08** (`near_rules=False`; since 2026-10-08 in `level_input` / `compute_levels`, `make --near-rules`
on the CLI turns them on). A near part is then not lifted at all (no row); stage 3 has nothing and is skipped, and
`attrs["levels_near"]` is empty. Why: on Monaco all modes (6,825 roads) the near rules cost 45.9 s, 27 positions and 11,911 near rules,
1,477 of them broken anyway; without them 14.4 s, 9 positions, 0 given up. Both maps had small spots to fix by hand, so the simpler and
faster one won. A road's stretch beside another that you want over it is an `edits.csv` stack (always real).

**The solver works from the tables only** (2026-10-08). Which parts of A cross B is decided once, when the area is made
(`roadstyle-levels make`, `duckosm levels`, `rs.level_input`, and inside `compute_levels`), with the heads of that time (the folder's
`heads.csv` if there is one, else `head_m`, 5 m), by the rules above: a part that crosses B, not a head at a junction with B, not an empty
main part. Each is **one stack row** in `pairs.csv`, `a_end` = `start` / `main` / `end`; a crossing over a head and the main part is two
rows. There is no whole-road stack row any more. The solver lifts exactly the named parts of the enabled rows: no geometry, no head
lengths, so a head changed later never needs a solve (the editor saves and draws it). An empty main part is decided at make too: it gets no
row (it crosses nothing), so the solver needs no list of them; a later head change that empties a main part leaves its row, which is
harmless (a lifted part of no length is never drawn). With `near_rules=True` (make: `--near-rules`) the parts that only come near are
written as `near` rows, which the solver keeps last. Monaco all modes: 4,918 whole-road rows became 487 part rows (main 319, start 89, end
79) on 479 pairs; the other pairs had no crossing part and lifted nothing before either. Solved again: 14.8 s, 9 positions, 0 given up,
22 wishes not kept, as before.

**Rows union.** Several stack rows of one pair lift each named part; an edit row adds a part; an edit with `enabled=false` switches off
exactly that row (pair and part). Nothing overrides anything else. To override a found stack, switch off all its rows (the editor has one
action for it) and add your own parts. A `pairs.csv` made before 2026-10-08 (a stack row with no part) is an error that says to make the
area again; an edit stack with no part is an error too.

**The editor's guard** (`rs.levels.rule_conflicts`, 2026-10-08): before a rule is added, the editor checks it against the enabled rules
(found, `edits.csv`, the list waiting to be applied): an exact duplicate, or a **loop**: the solver's rules are difference rules
`x_i - x_j <= w` between the four numbers of the roads (w 0 or -margin, the same builder the solver uses, `_difference_rules`), and a new
rule that closes a cycle with at least one strict step can never hold with the others. A breadth-first search from the new rule's one end
back to its other finds the shortest such cycle; its rules are named in plain words. You may add the rule anyway (the solver then gives one
up, as before).

**Automatic heads and caps** (`rs.auto_ends`, 2026-10-06: better than one number and one cap for all), for the widths the page
draws at zoom 18 (street level; widths are pixels, so lower zooms are wider on the ground):

- *head length* (before solving, geometry only): from the node along the road until its line is `(own width + the other's) / 2` from every
  road joined at that end, so as far as the two drawings overlap (a right angle: 2-3 m; a narrow merge: 10 m and more); a dead end 0.5 m;
  start + end never more than the road.
- *cap* (after solving, geometry and levels): round where the round end of the fill lies inside the fills of the joined roads drawn at its
  level or above, else flat: a road going on into a lower piece would show its round end as a bump on it, and a wide road ending on a
  narrower one would cross its outline (Tunnel Aureglia into Rue Grimaldi). Square never helps there (it covers the round end and more).

**The default caps are round** (2026-10-06). Flat where exactly two roads meet was tried and dropped: two flat ends close only on
a perfectly straight line and left small breaks at most joints. A road with two different ends is drawn from two fill halves that only
paint; its own fill layer keeps it, transparent, so a click and a selection find the road itself. A bridge's heavier casing keeps the
cap of each of its pieces (it was always flat, so two bridge pieces could not close), and at each cut inside a road (between a head and
the main part) a round seam of casing at the lower of the two numbers closes the outline on a curve.

**Not the default** (2026-10-06): heads made for zoom 18 were too short at lower zooms, where the roads are wider on the ground,
and the main casing (a higher level) showed in the joined roads' fills everywhere. The default is back to 5 m heads and round caps
(`roadstyle-levels solve --auto-ends` for the automatic ones). Yours in `heads.csv` / `caps.csv` go on top (empty: the default);
`levels.csv` has the ends as drawn. On Monaco the caps matched 5 of the 6
flat ends set by hand (the sixth is under a road drawn above it); the head lengths come out a little shorter than the ones set by hand.

**One part of A** (an edit): a `stack` edit names a part of A's casing in `a_end`: `start`, `main` or `end`. Added, that part comes after
B's fill even where its head joins B (a junction the rule leaves out). Switched off (`enabled=false`), that row of `pairs.csv` is left out.
A part named on an edge that runs against its road is turned to the road's way, as a meet's end is.

## Files (one folder per area)

| file | what | written by |
|---|---|---|
| `roads.parquet` | one row per road (both directions of a segment together): `road` (the id of its first edge), `edges` / `reversed` (the ids of its edges running its way / the other way), `band`, `priority`, the line | `roadstyle-levels make` (`rs.level_input`), every run |
| `pairs.csv` | one row per relation: `relation`, `a`, `b`, `a_end`, `b_end` (below); a stack one row per part of `a` | `roadstyle-levels make`, every run (with `heads.csv`'s heads) |
| `edits.csv` | your changes to the pairs, same columns plus `enabled`: `false` switches a pair off, anything else adds one; `a` / `b` may name either direction of a road | created empty once; you, or `roadstyle-levels edit`; never overwritten by the input step |
| `caps.csv` | your caps per road end (`road`, `start`, `end`: empty = automatic, `round`, `square`, `flat`) | `roadstyle-levels edit` (the *start* / *end* choices in a road's card) |
| `heads.csv` | your head lengths per road end (`road`, `start_m`, `end_m`; empty = automatic) | `roadstyle-levels edit` (the *heads* sliders in a road's card) |
| `levels.csv` | the result, one row per edge: `edge`, `casing_start`, `casing_level`, `casing_end`, `fill_level`, and its ends as drawn: `head_start_m`, `head_end_m`, `cap_start`, `cap_end` (render_edges' `head_start_m_col` / `head_end_m_col` / `cap_start_col` / `cap_end_col`) | `roadstyle-levels solve` |

Relations: `meet` (the end `a_end` of `a` is the end `b_end` of `b`: each head is under the other road's fill), `stack` (the part `a_end` of
`a`'s casing, `start` / `main` / `end`, is over `b`'s fill), `near` (the same, a part that only comes near: with `--near-rules`, kept last) and
`order` (`a`'s fill after `b`'s where they meet, a wish the solver may give up). A manual `meet` row joins two roads that do not share a point.

```
roadstyle-levels make edges.gpkg out/monaco                          # any geo file roadstyle reads
roadstyle-levels make monaco.duckdb out/monaco --query "SELECT * EXCLUDE (geometry), ST_AsWKB(geometry) AS geometry FROM driving.edges"
roadstyle-levels solve out/monaco
```

**The editor** (`roadstyle-levels edit out/monaco`, a local page at http://localhost:8780/) writes `edits.csv`: click two roads, or find
them in the search box by an edge id (either direction) or an edge_ref (or a part of one) (road 1 orange, road 2 blue; their start and end points are marked), see every pair between them (the found ones, with *switch off*, and your edits,
with *delete*), and add one (`order` or `stack`: you choose which of the two is on top, for each new pair (no default); a stack on one or more parts of the
upper road, one row each (*whole road* is a shortcut for all three); `meet`: the chosen end of each). *Switch off all found stack rows of
this pair* puts one switch-off per found row in the list, to override a found stack with your own parts. Before a rule goes into the list
the page asks the server whether it conflicts with the rules there are (a duplicate, or a loop: above) and says which rules; you may add it
anyway. Changes wait in a
list (kept over a reload of the page) until you press *Apply and solve*: then they are solved together while the map shows that it is
working, and the open page takes the new levels in place: the server compares what is drawn of each road (its four numbers, head
lengths and caps) before and after, and sends the features of the roads that changed, built by render's own code (`render(_edges=...)`:
the roads, their pieces in simple mode's one layer, the names and arrows again when a fill number changed), which the page swaps by
feature id (`GeoJSONSource.updateData`); the panel's facts follow. More than `PARTIAL_MAX` (1,500) changed roads: the page reloads,
keeping the view and the picked roads, and the status line says why. `levels.csv` is written too. If one change is
wrong or the solver refuses them (an unknown
road, nothing to switch off), nothing is saved, the list stays, and the panel says why. The `edits.csv` before each apply is kept as `edits.csv.bak`. A road's card also has *start* / *end*: round / square / flat for
each end (`caps.csv`); flat is for an end whose round end reaches across a narrower road it ends on, square keeps the drawn length.
And *heads*: each end's head length in metres (`heads.csv`; drawing only since 2026-10-08: no solve, and `make` reads it to decide the stack rows).
The *Issues* tab lists the crossing pairs the solver could not keep, with A's parts at or under B's fill in red; a
row opens the pair, to fix by hand. The list of
your edits shows each one's two roads when clicked. It is written for this page alone (the roadstyle map and its `rs*` API); the v2 test's
pair editor is not used.

In Python: `roads, pairs = rs.level_input(edges)`, `solved = rs.solve_levels(roads, pairs, edits=...)`; `rs.compute_levels(edges)` is both in
one call and returns the edges with the four columns.

## The editor re-solves only the roads around a change (2026-10-07)

On the all-modes Monaco area (6,594 roads, 4,949 stack pairs, one connected graph) a whole solve takes about 50 s, nearly all of it in the
last stage (cost and fewest positions). *Apply and solve* now solves only the roads around the change (`level_area.solve_local`): the roads
the change names (the edit rows added or taken out, the roads whose heads changed) and every road within **three relations** of them (meet,
stack, order, in the pairs and the edits) are solved again; every other road keeps its numbers (`solve_levels(fixed=...)`: bounds, the same
model and stages). Three, since a rule reaches its roads' neighbours through the meets (a head under the fills it joins) and the next ring
gives them room; two gave up one order wish more than three in one of six edits, four was slower and no better.

No silent fallback: the local result is not used, and the whole area is solved, when it gives up a crossing part the previous result kept,
has more order wishes not kept, more near warnings or more drawing positions than the previous one, or the solver fails; the toast after the
reload says which solve it was and why (`levels_info["resolve"]`: `how` local / full, `why`, `free`, `seconds`). `roadstyle-levels solve`
stays a whole solve. Monaco, eight edits (a stack pair switched off, a stack on one part added, an order turned round, a head changed; two
of each):

| | local (3 relations) | whole solve |
|---|---|---|
| seconds | 1.9-2.7 (40-230 free roads) | 44-56 |
| crossings given up | 0 | 0 |
| near warnings | as the whole solve | |
| drawing positions | as the whole solve | |
| order wishes not kept | the whole solve's, or one more (2 of 6) | |

One edit (an order turned round) made more near warnings locally: the whole area was solved (about 53 s), and it had the same count.
In one other edit (a head) the whole solve stopped at its time limit (60 s for one stage) and failed; the local one took 2 s.
Limits: the local result is optimal for its free roads only, so a whole solve may keep a wish the local one gives up (one, above), and a
change that really costs a rule (an edit against a crossing) is always solved twice (about 2 s, then the whole). The ground (the number 0)
is chosen again after each solve, so the numbers of a held road may all move by one; its order with every other road stays.

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
