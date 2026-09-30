# Which road goes on top at a junction: the plan

**Status:** proposal after research, for sign-off before implementation (Kaveh asked for research
first, 2026-09-30). A roadstyle change asked for by Kaveh. It builds on `draw_order_per_edge.md`
(`band_col` / `order_col`, implemented, not yet committed).

## Problem

Reported by Kaveh on duckOSM's Monaco build:

- **Avenue de la Costa and Bretelle Ostende**, edges 4628183342609875807, 6471016024852816111 and
  284593073383310203. A `primary_link` meets two `residential` edges and a car-park entrance.
  Within 40 m there is also a tunnel mouth (Boulevard du Larvotto, layer -1) and a bridge end
  (Avenue de la Costa, layer 1).
- **Avenue Princesse Grace:** sidewalks and crossings.

Within a level, roadstyle orders roads by one number per class (`roads.z_order`). A link gets its
parent's number minus 0.5, so `primary_link` (6.5) draws over `residential` (4). This is the
Avenue de la Costa case. A single number per class also can't say which of two streets *goes
through* a junction.

## What the research found

Established styles were read in their source.

1. **Links sit below every non-link class, residential included.** This is the one rule every
   established style shares:
   - openstreetmap-carto (`openstreetmap-carto-flex.lua`): residential 330, links 240 (motorway)
     down to 200 (tertiary), service 150, paths 100, steps 90;
   - OpenMapTiles / OSM Bright, Mapbox Streets v12, OSM Americana and Protomaps: link fills are
     drawn before minor streets.

   roadstyle is the exception.
2. **Paths, sidewalks and pedestrian ways sit below streets.** In openstreetmap-carto they are
   100 / 90 against 330. Its open issue #4944 describes the gaps sidewalks cut into streets.
3. **All casings, then all fills, per level band.** Grade separation happens only between bands.
   Every style does this, and roadstyle does too (tunnel / low / ground / high / bridge bands).
4. **Butt caps on bridge and tunnel casings, round caps on ground roads.** Round bridge caps glow
   round the deck end (openstreetmap-carto `roads.mss`). roadstyle already does this; to be
   checked, not changed.
5. **No style chooses the through road per junction.** Every style sorts only by class inside a
   band, so two streets of the same class are ordered by chance. "Strokes" are the established
   continuity method:
   - Thomson & Richardson 1999; Jiang et al. 2008 (arXiv:0804.1630); Zhou & Li 2012 (IJGIS
     26(4));
   - used in production for road *selection* (swisstopo, Benz & Weibel 2014; IGN, Touya 2010;
     Ordnance Survey patent US10030982B2).

   They have not been used for draw order, so this part is new ground: a tie-breaker within a
   class, not the main rule.
6. **MapLibre limits.**
   - `line-sort-key` sorts only within one style layer (and tile). A road's casing and fill can't
     be interleaved with another road's; the request for that, maplibre#2108, is open.
   - So the order within a band is fill-over-fill only. That is enough: at a same-level junction
     every casing is under every fill anyway.

## Plan, in four steps (each its own commit, checked before the next)

### 1. Class order like every established style (`roads.z_order`)

Links move below every non-link road, in their parents' order, between `pedestrian` (2) and
`service` (1.5): motorway_link 1.9, trunk_link 1.85, primary_link 1.8, secondary_link 1.75,
tertiary_link 1.7. This replaces the "parent minus 0.5" rule. The rest of the table is already
in carto's order.

- A **"Changed"** entry in the CHANGELOG: every map is affected, and the Avenue de la Costa case
  is fixed.
- Settings can still override any value.

### 2. Sidewalks under, crossings over (`band_col`, done)

- `band_col` is implemented in roadstyle; mapstyle passes duckOSM's `walk_type` (crossing +1,
  sidewalk -1).
- It stays as built. This commit also brings the `draw_order_per_edge.md` work in.

### 3. The through road on top: strokes, as a tie-breaker within a class

`render_edges(..., order="strokes")` (opt-in first). roadstyle builds the strokes from the line
geometry alone: roads sharing an end point meet at a junction, as `_mark_twoway` already finds
twins. So every caller gets it, without duckOSM node ids.

1. **Twins become one segment:** a two-way road's two directed edges. One-way carriageways stay
   separate.
2. **Bearing:** the bearing at each end is measured 15–20 m into the edge, not from the first
   vertex, so dense or noisy nodes don't dominate (Heinzle et al. 2007, "trend").
3. **Candidate pairs** at each junction:
   - a pair qualifies at a deflection of **45° or less** (Jiang 2008);
   - its cost is the deflection, plus 20° for each class step of difference, plus 10° when both
     are named and the names differ;
   - never link with non-link, roundabout with non-roundabout, or path with road;
   - a point where only two edges meet always joins.
4. **Every-best-fit:** pairs sorted by (cost, edge index), each taken if both ends are still free
   (Zhou & Li 2012: the best with geometry alone). The result is deterministic, which a map needs.
5. **Union-find** over the taken pairs gives stroke ids.
6. **Order:**
   - each edge's order is its class's `z_order` plus the stroke's rank within that class, scaled
     into 0 … 0.4;
   - rank goes by stroke length, then by stroke id;
   - so class always wins, and inside a class the long through street wins;
   - baked as `__rs_order` (the `order_col` channel), with `rsColor`'s +500 kept on top.

Cost is O(edges + Σ degree²), seconds for 100k edges, with no new dependency. momepy's COINS was
checked and not used:

- it needs undirected input without twins;
- it measures angles on the last vertex pair only;
- it ignores attributes;
- part of it is quadratic.

### 4. Default on, if the checks agree

After comparing on Monaco, Tartu and Stockholm, `order="strokes"` becomes the default, with
`order="class"` as the way back.

## Named checks (before / after, in a browser, at z16–18)

| Case | Where | Expected |
|---|---|---|
| Link over a street | Avenue de la Costa / Bretelle Ostende (the three edges above) | the residential street's fill runs on; the link tucks under (step 1) |
| Sidewalks and crossings | Avenue Princesse Grace (48 crossings, 84 sidewalks) | crossings over the street with their halo, sidewalks under it (step 2) |
| A "V" | a fork of two same-class streets, and a main road with a link leaving it at a sharp angle | the fork merges cleanly; the main road runs straight through and the link peels off under it (steps 1, 3) |
| A T-junction of two residential streets | Monaco, picked in the test data | the continuing street on top, the ending one under (step 3) |
| Tunnel mouth and bridge end | the same Avenue de la Costa junction | no glow round the bridge end, and the tunnel entrance unchanged (step 4 of the research: check only) |

Tests: the new link values; strokes on small synthetic junctions (a straight road + a T, a V fork,
a roundabout, a two-way street's twins as one segment, a link never joining its road); the result
is the same whatever the input order; without `order=` the style is unchanged (until step 4).

## Known limits (not in this plan)

- The two-lanes-side-by-side drawing (`offset_frac`) shifts the tips of a sharp V apart, leaving a
  notch. That is a separate geometry problem.
- A curved main road meeting a straight side street of the same class can lose to the side
  street: a known pitfall of strokes (Heinzle 2007). Class and names limit it, but don't remove
  it.
- Broken OSM topology (unsplit ways, dangling connectors) breaks strokes locally.
