# Levels and looks: one drawing rule for every road

**Status:** approved by Kaveh 2026-10-01 ("A, do the refactor"). Supersedes `tunnel_portals.md` and the stretch rule of
mapstyle's `junctions.md` (`_stretches`).

## Problem

A road's **level** (where it is drawn: under the ground roads, with them, over them) and its **look** (a faded, dashed
tunnel; a bridge deck) were one thing in the code. A tunnel had its own band, its own layers
(`roads-tunnel-*`, `roads-tunnelgr-*`, `roads-tunnel-under-*`) and its own algorithm: `_stretches` cut every tunnel
into *ground* stretches (drawn with the ground roads) and *under* stretches, and drew the edge itself invisibly. A road
with a negative `layer` and no tunnel tag was cut the same way. So anything built on the map had to know the tunnel
rules: the one-way arrows of a tunnel were stacked under its ground stretches and hidden; lanestyle had to mirror the
cutting in Python to place its lane lines. Kaveh: "a tunnel should act like an ordinary road; only the colour style
differs", and, again, "it shouldn't make a difference".

## Rule

1. **Level = the draw band.** Three bands by `lvl` (the OSM `layer`, else 1 for a bridge, -1 for a tunnel) or a caller's
   `band_col`: **low** (< 0), **ground**, **high** (> 0). Each band is a casing layer then a fill layer, and every road of
   a band has its casing under every fill of it. Inside a band the order is the `line-sort-key` (level, then class or
   `order_col`). Nothing else decides the band: no tag, no geometry.
2. **Look = data and sublayers on top of the band.** A tunnel or bridge changes how a road is *painted*, never where:
   - **tunnel** (in the low band): its casing is the two-tone one (`__rs_casing` is baked as the solid tone), a dashed
     overlay layer on the casing (`roads-low-casing-dash`), light dashes on the fill (`roads-low-fill-pat`) and a data-driven
     `line-opacity` on the fill (since [the tunnel look](tunnel_look.md): an opaque fill faded toward the background);
   - **bridge** (in the high band): the black, heavier, butt-capped deck casing and a fill layer of its own, drawn after
     the plain high roads (`roads-bridge-casing` / `-fill`), and the 3D deck ribbons;
   - **dashed classes** (footway, path, steps ...): a sublayer per dash pattern in whichever band the road is.
   `line-dasharray` and a heavier width cannot be data-driven, which is why these are layers; a layer is not a different
   algorithm, it is the same road painted with its look.
3. **Colour-by reaches every layer of a road**, dashed sublayers included (`RS_FILL_LAYERS`), so a pattern and a colour
   scheme work together.

## Removed

`_stretches` and everything it fed: the `tpieces` source, `__rs_piece`, `__rs_pieced`, `__rs_gstart` / `__rs_gend`,
`__rs_tfill`, the layers `roads-tunnel-*`, `roads-tunnelgr-*`, `roads-tunnel-under-*`, `roads-lowp-*`, `roads-plaingr-*`,
`roads-highp-*`, the settings `tunnel_stretches` (a stepping stone, never released) and the page code that followed a
stretch to its edge (`RS_PIECE_LAYERS`, `l.source === "tpieces"`). `band_col` now also applies to a tunnel.

## Consequences

- A tunnel is drawn whole, under every ground road. At a **mouth** a ground road's round end is drawn over the start of the
  tunnel's casing (the problem `tunnel_portals.md` solved with stretches). With an opaque fill and exact lane widths
  (lanestyle: no casing) it does not show; with casings it is a small notch at the mouth. Accepted: one rule for every
  road is worth more than a perfect mouth.
- A plain-layer road (a `layer` tag only) that passes over or under nothing is drawn in its own band instead of with the
  ground roads: it is below / above the ground roads, as its level says.
- Overlays (arrows, lane lines, labels) follow the band of the road: tunnel arrows sit above the low fill, with the low
  band, and nothing covers them but a ground road that really crosses over.
- mapstyle, lanestyle and duckOSM maps: tunnel mouths look different (above); everything else is unchanged.

## Checks

Tests: a tunnel is in the low band with the tunnel look, whole, and no stretch layers exist; the bridge keeps its look; a
caller's `band_col` moves a tunnel; colour-by recolours the dashed sublayers; arrows of a tunnel are above its fill;
the three-band toggles still hide by level. Before / after pictures of Monaco (tunnels, a bridge, a roundabout in a tunnel
mouth) in `assets/` for Kaveh to look at.
