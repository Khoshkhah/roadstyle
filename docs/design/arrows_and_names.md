# Arrows and street names on the roads

**Status:** the slots and the street names are as they were; the arrows are new (reviewed and merged, 2026-10-06).
Code: `_annotation_slots` and the arrow / label layers in `render_web.py`; `_rsArrows` in `web_template.html`.

## 1. Chains and slots: one plan for both

Arrows and names are placed on a plan made once, in Python, from the roads (`_annotation_slots`):

1. **Chains.** Roads with the same name, level (`lvl`), direction (one-way or not), class and drawing position (`fl`) are walked together
   through every node where exactly two of them meet. A two-way street is walked once (its reverse twin is skipped); a one-way chain only
   continues in its own direction, so its arrows never turn round half-way. The class is part of the key so that a cycleway named after the
   street beside it does not join the roadway's chain.
2. **Slots.** Each chain is cut into equal pieces of `slot_m` metres (setting `annotations.slot_m`, default 100), numbered 0, 1, 2 … along
   the chain. A leftover at the end shorter than 30 % of `slot_m` gets no piece of its own (no name or arrow there); a piece shorter than
   20 % of `slot_m` is dropped, so a chain shorter than 20 m has none.
   **Crossings (2026-10-08).** Before the cutting, every other road's line that meets or crosses the chain (a junction, the chain's own ends
   where others join, a bridge or tunnel over it, a zebra: any edge of the data, twins of the chain's own edges excepted) takes
   `half its drawn width + 2 m` out of the chain, on each side of the point: half the width with casing at zoom 20 in metres (a footway,
   path, cycleway or steps at least 2 m: a zebra's stripes are about 4 m wide along the street). The stretches left between are cut into
   slots on their own, each starting with a name slot (an even number), so a street through a node that is not a crossing stays one stretch,
   and no name or arrow sits across a crossing. A stretch shorter than 20 m (with `slot_m` 100) gets no name piece; on a one-way
   street a stretch of at least 8 m still gets one arrow piece (an odd slot, `_ARROW_MIN_M`, 2026-10-09: 254 of Monaco's 394 one-way chains
   have a piece, 177 with 20 m for both). A name is one `line-center`
   symbol in the middle of its slot, the same place at every zoom.
3. **Each piece knows its road.** It carries the edge under its middle (`__rs_road`, and the twin `__rs_road2` of a two-way street), so
   hiding a road (`rsFilter`, the class filter, the Bridges / Tunnels toggles) hides its names and arrows with it. It also carries `chain`
   (the chain's number), `rank` (the class order, higher = more important), `name`, `highway`, `oneway`, `lvl` and `fl`.

```
a one-way chain, 100 m slots:   | slot 0 | slot 1 | slot 2 | slot 3 | slot 4 |
                                  name     (arrow)   name     (arrow)   name
```

**Names take the even slots, arrows the odd ones**, so the two never sit on the same piece.

The pieces are the `slots` source of the page (inline GeoJSON; with `tiles=True`, a layer of the tile archive).

## 2. Street names

- One name **in the middle of every even slot** of a named chain (`symbol-placement: line-center`), so a long street repeats its name about
  every 200 m.
- From zoom 14; footway, cycleway, path, steps, service, track and pedestrian from zoom 16 (below that they still lie inside the stroke of
  the street beside them, and their name would sit on the wrong line).
- Grey `#5b5b5b` at the arrows' opacity (0.7), no halo, Noto Sans, 10 px at zoom 14 to 14 px at zoom 18 (settings `labels`).
- MapLibre drops a name that is longer than its piece or that collides with another; between two names, the more important class wins
  (`symbol-sort-key`).
- One name layer per drawing position, right after that position's arrows (or its fill layers), so a road drawn above covers the names
  of the road below it.

## 3. Arrows

The page places them (`_rsArrows`), after every move and once the slots are loaded. **A one-way road in the window has at most one arrow.**

- **Where.** Never on a name (arrows overlapped the names). The pieces of the chain are laid end to end, and a name is taken to
  cover the middle of its even piece, as wide as its letters at the current text size (about 0.6 em a letter). The places an arrow may go
  are the middle of every odd piece and just past either end of every name (14 px gap); an unnamed road may take the middle of its visible
  part. Of these, the one inside the window (10 px from its edge) and nearest the middle of the road's visible part is taken. If none is
  in the window, the road is too short there for its name and an arrow: **the name wins and the road has no arrow.** The arrow is rotated
  along the road.
- **It stays.** While an arrow is still in the window it keeps its place; only a road whose arrow has left the window, or a road that has
  just come into view, gets a new place (re-centring after each pan made it slide along the road).
- **Thinned** (after trying one per road: still too many):
  - none below zoom 15; below zoom 17 only motorway, trunk, primary, secondary and tertiary roads and their links; the minor classes from
    zoom 16 in any case;
  - no arrow on a road whose visible part is shorter than 100 px;
  - arrows at least 150 px apart: an arrow already shown keeps its place first (no jumps while panning), then the higher class (`rank`),
    then the longer road.
  The numbers are `_RS_ARROW` in the page (also the 14 px gap beside a name and the 10 px from the window's edge).
- **Drawn.** Each arrow is a point in the page's `arrows` source with the properties of the slot piece it lies on, so the arrow layers keep
  their filters (one-way, drawing position, class, minzoom) and everything that hides a road hides its arrow. One arrow layer per drawing
  position, right after that position's fill layers: a road drawn above covers the arrows below it. Where the arrow would still touch a
  name (the page's estimate of the name's width fell short), the arrow is left out: MapLibre places the names first and drops an arrow
  that collides with one (`icon-allow-overlap: false`), and an arrow never pushes a name away (`icon-ignore-placement`) (2026-10-06).

**Before (until 2026-10-06):** the icon was repeated along every one-way slot (`symbol-placement: line`, about every 200 px at zoom 15). At
zoom 15 a 100 m slot is about 20 px, so long roads carried many arrows; and an earlier version with one arrow per chain (`line-center`) often
had that arrow outside the window.

### Only driving roads, only one-way ones

Two questions, two inputs (2026-10-09):

1. **The drawing, two directions or one line: `directed_col` alone.** An edge and its reverse are two directions only when both are
   directed. `rs.is_directed(edges)` is the one definition (mapstyle and the level areas use it): an edge open to cars or bikes
   (`driving` or `cycling`) that is not a path class (config `single_line_classes`). A one-way street's walking-only reverse is
   undirected: one line. A reverse that is a bus or bike lane is directed: a half of its own (coloured by who uses it: mapstyle's access
   colours), next to the car half with its arrow.
2. **The arrow: one-way AND driving.** `__rs_oneway` is true only for an edge that is one-way (its `oneway`, or with no `oneway` column,
   no twin) and driving (`driving_col` true or null; no `driving_col`: every edge). The `oneway` the pages get is the driving network's,
   but a non-driving edge never gets an arrow even if a copied `oneway` says true. `driving_col` never decides the drawing.

Example: Monaco, OSM way 1449981121 (Boulevard Charles III, oneway=yes, oneway:bicycle=no). Driving has only #1f (oneway); walking and
cycling have #1f and #1r (#1r is a bus lane, driving.private_edges access=bus, that bikes use too). Both are directed: two halves; one
arrow, on #1f, pointing #1f's way, in #1f's half.

A pair drawn as two directions keeps one representative for the slots: its one-way edge when only one is (so its arrow points that
edge's way), else the edge with the lower ends. The page (`_rsArrowLane`) moves such an arrow off the pair's centre line into the middle
of its edge's half, right of travel by the half's drawn offset at that zoom (`_svLanePx`, as the Street View marker); with `tiles=True`
the arrows repeat along the slot lines, on the centre line. An edge lying on a chain's line the other way round (a
one-way street's undirected reverse) is no crossing: it does not cut the chain's slots. The same slot plan feeds `tiles=True`.

A first fix (unreleased, 2026-10-09) also let `driving_col` false split a pair; it decided the drawing from the cars through the arrow
input and is gone: the drawing is `directed_col`'s alone.

## 4. On a tunnel

With the tunnel look (`docs/design/tunnel_look.md`), the names and arrows of a tunnel fade with the slider like everything else on it: the
slot pieces carry `__rs_tunnel` from their road.

## Limits

- A map from a tile archive (`tiles=True`) has no slot geometry in the page: its arrows are still repeated along the slots.
- A street whose chain is split (a class, level, position or name change half-way) is two roads: two arrows, two sets of names.
- The name's width is an estimate (letters × 0.6 em): a name of unusually wide letters can still touch its arrow.
- A one-way road too short for its name and an arrow side by side shows the name and no arrow.
