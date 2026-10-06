# The tunnel look: v2's slider

**Status:** built (branch `tunnel-look`), waiting for Kaveh's review. From the Monaco v2 test (`docs/v2/monaco_roads_v2.html` on
`v2-dev`, its *Tunnel style* slider), 2026-10-06. Builds on [Levels and looks](levels_and_looks.md): a tunnel is drawn at its position like
any road; only its look differs.

## The rule

One slider, the **strength** (0 to 100, setting `tunnel_strength`, default 35 as v2; presets Normal colors 0, Subtle 20, Balanced 35,
Strong 70), moves **everything on a tunnel the same way, toward one colour**, slate `#64748b`: the road's fill, its street names, its
one-way arrows, and every item attached to it with `Overlay(edge_col=...)` (lanes, lines, arrows, names). It makes no difference how an
item was added (Kaveh: "the fading part applies on every item on a tunnel"). Everything else is unchanged.

The fill is **opaque**: no see-through fill and no underlay, so overlapping pieces never show darker joints.

## The casing

As v2, a tunnel's casing is drawn by its dash layer alone (the other casing layers leave a tunnel out), 3 px wider than a casing
(1.5 px each side) so its colours show:

- **One colour** (`tunnel_palette`, the default; two colours are not decided yet): slate dashes `#94a3b8` with empty gaps, at any strength.
  Why a second colour exists (Kaveh): with empty gaps, where a tunnel passes under a road it looks connected to it; a solid second colour
  closes the gaps. So the default should become a pair once one is chosen.
- **A two-colour palette**: above 0 the dash layer draws a pattern image of the palette's two colours **as they are**, dash and gap. (v2
  blended them from slate and from the background by the strength; at 35 % the second colour was hard to see, Kaveh 2026-10-06.) v2's
  `Slate + ice`, `Blue + cyan`, `Warm + sand`, and three more to try with stronger second colours: `Graphite + silver`, `Indigo + lavender`,
  `Teal + mint` (`tunnel_palettes`, `name: [dash, gap]`).
- The dash ratio (`tunnel_casing_dash`, in line widths): 3:3 (default, as v2), 1:1 (Kaveh: maybe better than 2:2 or 4:3), 4:4, 2:2, 4:3.

## In the page

A **Tunnels** box (on a map with tunnels; `tunnel_control=False` leaves it out): the preset menu, the slider, the palette and the dash ratio.
`rsSetTunnelStyle({strength, palette, ratio})` does the same from a host page and fires `rs:tunnelchange`. *Colour by* and `rsColor` keep the
look. While the slider is dragged, only its newest value is applied (once per frame).

## How

Each colour that takes the look is a MapLibre expression: for a feature with `__rs_tunnel`,
`["interpolate", ["linear"], strength, 0, <colour>, 100, "#64748b"]`, else the colour (`_tun_mix` in Python, `_tunMix` in the page). The page
keeps each layer's colours without the look (`TUNNEL.layers`) and builds the expressions again when the slider moves; no data is baked per
value. The street-name and arrow slots carry `__rs_tunnel` from their road; on a map with tunnels the arrow icon is an SDF one, coloured by
`icon-color` (one symbol layer cannot mix SDF and plain icons). An item gets `__rs_tunnel` from its edge when the overlay is attached (`_edge_overlay`).

## Limits

- At a high strength a tunnel's name nears its fill colour (everything moves to the same slate); at 100 they are one colour.
- A slider move resets an `rsColor` recolouring of an overlay attached to edges. `rsColor` on the roads is kept.
