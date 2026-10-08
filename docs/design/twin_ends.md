# Two-way roads that end like one road

**Status:** implemented 2026-09-30 (approved: "just make sure fixing it in roadstyle
doesn't make another issue"). A roadstyle change, asked for after it was noticed on every
two-way road of duckOSM's Monaco maps.

**Found after the first version, fixed:** a cap at a point where another road draws in a
lower band (a tunnel mouth, a plain `layer=-1` road, a sidewalk moved by `band_col`) painted its
casing ring across that road (Monaco: Boulevard Louis II's tunnel mouths). Such an end now gets no
cap and keeps its old look (1,578 ends in Monaco meet a road in another band).

**Found while checking for new issues, and handled:** on a map coloured per direction (SonoFlow's
flows), a cap in one twin's colour would show that direction's colour at the street's end, so a
cap draws only where both lanes share a colour (each fill prop is carried twice, `<prop>__b`).
Checked in a browser on five page kinds (plain, dashboard, planner, `tiles=True`, 3D): no page
errors with filters, recolouring, colour options, mode / class / bridge / tunnel toggles. Size:
Monaco +0.25 MB (+8 %), Tartu +1.17 MB (+11 %).

**2026-10-08: one casing for the pair** (config `twin_casing`, `"one"`; `"each"` is the look below). Each direction drew its own casing,
so a bridge showed two dark bands with square ends (Avenue de France, Monaco). Now the pair's casing is drawn ONCE: the casing pieces of the
first edge of the pair (`_mark_twin_casing`: the two edges must be the same line, reversed, and of one class), unshifted (`__rs_pair`: no
line-offset), as wide as the two directions together (a direction's casing width + twice its offset, `_pair_width`: the outer edge of the two
lanes, the same as this cap's radius). The second edge has no casing piece; both fills stay as they were. The casing's ends are its own caps
(round, flat, square from the first edge's caps and heads; its start is the second edge's end), so the blob below is not drawn; a small notch
between two round fill ends at a dead end is accepted. The twins' casing numbers, heads and caps must agree reversed (the level area writes
them so); a pair that does not is named in a warning, and the first edge's are drawn.

## Problem

A two-way road is two directed edges, the *twins* (`_mark_twoway`, the same line in reverse).
roadstyle draws them as two lanes side by side:

- each lane is shifted sideways by `offset_frac` (0.28) of the road's width;
- each lane is narrowed to `width_frac` (0.6);
- both ramp in from `offset_zoom` (15) to 17.

Each lane is its own line, with its own **round end**. So where a two-way road ends, at a dead end
or a junction, the pair ends in **two half-width bumps with a dip between them** ("ω"), not one
round end.

At full split, with road width `w`:

- the lanes' centres are ±0.28 `w` from the road's centre, and each cap has radius 0.3 `w`;
- so at the centre line the pair reaches only 0.1 `w` past the end, while each lane reaches
  0.3 `w`: the dip is 0.2 `w` deep;
- the casings do the same, so the outline dips too.

A single road would end in one half-circle, of radius 0.58 `w` (the pair's outer half-width).

The two lanes must stay two features, so that each direction can still be clicked and coloured on
its own ("we must be able to select them separately").

## Options considered

| Option | Why not |
|---|---|
| Draw both twins on the centre line (`offset_frac=0`) | clean ends, but the two directions lie on top of each other and can't be told apart or clicked separately |
| Butt caps on two-way lanes | MapLibre's `line-cap` is per layer, not per feature, so this needs a copy of every road layer. A square step would still show where lanes meet other roads |
| Bake a taper into the lane geometry (lanes meet at the end) | the shift is in pixels and changes with zoom, so geometry in degrees can't match every zoom |

## Proposal: an end cap at each end of a twin pair

At each **end point shared by a twin pair**, add **one round cap the width of the whole road**,
drawn under the lanes' fills. It fills the dip, so the pair ends in one clean half-circle. The
lanes stay exactly as they are, both clickable.

1. **Found in Python while the page is built** (`_twin_ends`). For every twin pair, take its two
   end points. A dead end, a junction, or a point where the road goes on as one-way all count.
2. **Its own source, `ends`**, a point per end, like the tunnel `portals`:
   - one feature per edge stays the rule in `roads`, so feature ids and `rsQuery` don't change;
   - a point carries what styling needs from its pair: class, `lvl`, `__rs_band`, `__rs_fill`,
     `__rs_casing`;
   - it also carries both twins' feature ids, `__rs_road` / `__rs_road2`.
3. **Two circle layers per plain band** (ground, low, high):
   - `roads-ends-casing` sits just under the band's casing layer, with radius = the pair's outer
     casing half-width;
   - `roads-ends-fill` sits between the band's casing and fill layers, with radius = the pair's
     outer fill half-width;
   - both radii are the same zoom-interpolated class widths the lanes use (`_width_expr`,
     `_offset_expr`), so the cap grows with the road and with the lane split;
   - below `offset_zoom` the lanes lie on one another, and the cap equals their own caps.
4. **Order stays right at a junction:**
   - the cap fill is under every lane fill of its band, so a crossing primary road still covers a
     residential street's cap;
   - it is above every casing, like the lanes' own fills, so the junction still merges into one
     shape (edges and fills, `junction_order.md`).
5. **Follows the road:**
   - the class filter, the bridge and tunnel toggles, and `rsFilter` / `rsSetModes` apply: a cap is
     hidden when both its twins are hidden (a filter on `__rs_road` / `__rs_road2`, as the portals
     do);
   - `rsColor` and the colour-by options recolour a cap when both its twins get the same colour,
     so a route on both directions ends clean; otherwise it keeps its base colour;
   - caps aren't clickable (the lanes are); `rsColor`'s +500 lift is irrelevant under the fills.
6. **Bridges and tunnels are skipped.** Their casings already use butt caps (the bridge deck, the
   tunnel mouth pieces), so they have no round-cap dip.
7. **Size and `tiles=True`:**
   - Monaco (duckOSM, all modes) has 6,235 twin pairs (12,470 of its 12,969 edges have a reverse
     twin: nearly every path is stored both ways), so up to about 12,500 points;
   - they travel as their own GeoJSON source, gzipped like the roads, with only the fields above,
     and also with `tiles=True`, like the portals;
   - to be measured on Tartu before sign-off of the implementation.
8. **A setting to turn it off:** `config.twin_end_caps` (default `true`).

## Follow-up (2026-09-30): lanes only for real two-way roads, and tunnel mouths

Seen at Rue du Castelleretto (Monaco, edges 441704187184649227 / 5990211243552773545 and
4146834466225551101 / 7910395095814073287):

- **A one-way street drawn as two lanes.** Twins are found by geometry: same line, reverse
  direction. duckOSM's walking network has both directions of every street, so a street one-way for
  cars gets a walking-only reverse edge, and roadstyle draws it as a two-way road. That is 666 of
  Monaco's 1,578 road pairs, and every footpath too.
  - **Fix:** an optional `directed_col` (per edge: true / null = a direction of travel of its own,
    false = undirected) says whether an edge can be a lane. A pair is two lanes only when **neither**
    edge is false; otherwise both are drawn centred at full width, as one line, with no end caps;
    arrows still follow `oneway`. (First named `twoway_col`; renamed 2026-09-30:
    "two-way" means two directions, which a footway has too.)
  - mapstyle sets `is_directed` true for an edge open to cars or bikes that isn't a path. The
    walking-only reverse edge stays on the map, on top of the one-way edge, so data and routing
    don't change.
- **"Bump, dip, bump" at a tunnel mouth.** Where a lower band meets the end, the cap was skipped, so
  the two lanes' own round ends and casings showed across the mouth.
  - **Fix:** there the cap is **fill only**. It fills the dip and draws no casing ring across the
    lower road (`__rs_nocase`: the casing circles skip it).

## Checks

- Tests:
  - a dead-end two-way street gets two points (one per end) with both twins' ids;
  - a one-way street gets none;
  - a bridge or tunnel twin pair gets none;
  - the two circle layers exist in each plain band, in order (ends-casing < casing < ends-fill < fill);
  - the radius expression equals the lanes' outer half-width at z14, z16 and z18;
  - a filter on both twins' ids hides the cap;
  - `twin_end_caps: false` gives today's style.
- In a browser (Monaco, z16–18):
  - a dead-end two-way street;
  - a T-junction of two two-way streets;
  - a two-way street meeting a one-way street;
  - Avenue de la Costa;
  - before and after snapshots, and both directions still selectable one by one.

## Limit

A sharp V of two two-way roads still shows the lanes' sideways shift near the tip (the tips are
apart by the shift). The caps round each road's end, but they don't move the lanes. That stays the
known limit in `junction_order.md`.
