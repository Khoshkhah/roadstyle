# The tunnel look: v2's slider

**Status:** built (branch `tunnel-look`), waiting for Kaveh's review. From the Monaco v2 test (`docs/v2/monaco_roads_v2.html` on
`v2-dev`, its *Tunnel style* slider), 2026-10-06. Builds on [Levels and looks](levels_and_looks.md): a tunnel is drawn at its position like
any road; only its look differs.

## The rule

One slider, the **strength** (0 to 100, setting `tunnel_strength`, default 35 as v2; in the Tunnels box five steps, Normal colors 0,
Subtle 20, Balanced 35, Strong 70, Full 100), moves **everything on a tunnel the same way, toward one colour**, slate `#64748b`: the road's fill, its street names, its
one-way arrows, and every item attached to it with `Overlay(edge_col=...)` (lanes, lines, arrows, names). It makes no difference how an
item was added (Kaveh: "the fading part applies on every item on a tunnel"). Everything else is unchanged.

The fill is **opaque**: no see-through fill and no underlay, so overlapping pieces never show darker joints.

## The casing

As v2, a tunnel's casing is drawn by its dash layer alone (the other casing layers leave a tunnel out), 3 px wider than a casing
(1.5 px each side) so its colours show:

The casing follows the slider like everything on a tunnel (Kaveh 2026-10-06): its colours move toward the same slate `#64748b`.

- **One colour** (`tunnel_palette`; the default is two colours, `Graphite + silver`, Kaveh 2026-10-06): dashes with empty gaps, `#94a3b8` at 0, moved toward slate.
  Why a second colour exists (Kaveh): with empty gaps, where a tunnel passes under a road it looks connected to it; a solid second colour
  closes the gaps. So the default should become a pair once one is chosen.
- **A two-colour palette**: the palette's two colours, dash and gap, at any strength: as they are at 0, each moved toward slate as the
  strength rises. (v2 blended the gap up from the background; at 35 % the second colour was hard to see.) v2's
  `Slate + ice`, `Blue + cyan`, `Warm + sand`, and three more to try with stronger second colours: `Graphite + silver`, `Indigo + lavender`,
  `Teal + mint` (`tunnel_palettes`, `name: [dash, gap]`).
- The dash ratio (`tunnel_casing_dash`, in line widths, so a 1 is as long as the casing line is wide): **1:1** (the default, Kaveh 2026-10-06:
  both colours equal, short pieces, so a crossing never lands in one long dash or gap), 2:2, 3:3 (v2's), 4:4, 2:1, 3:2, 4:3 (longer dashes:
  with One colour, shorter empty gaps), 1:2.

The light dashes on the fill (`tunnel_fill_dash`) are off by default, as in v2's look (Kaveh 2026-10-06); `[1.2, 1.2]` turns them on.

## In the page

A **Tunnels** box (on a map with tunnels; `tunnel_control=False` leaves it out): the preset menu, the slider, the palette and the dash ratio.
`rsSetTunnelStyle({strength, palette, ratio})` does the same from a host page and fires `rs:tunnelchange`. *Colour by* and `rsColor` keep the
look. While the slider is dragged, only its newest value is applied (once per frame).

## How

Each colour that takes the look is a MapLibre expression: for a feature with `__rs_tunnel`,
`["interpolate", ["linear"], strength, 0, <colour>, 100, "#64748b"]`, else the colour (`_tun_mix` in Python, `_tunMix` in the page). The page
keeps each layer's colours without the look (`TUNNEL.layers`) and builds the expressions again when the slider moves; no data is baked per
value. A two-colour casing is two layers with MapLibre's own dash, no image: the position's casing layer draws the tunnel's gap colour
(transparent for One colour) and the dash layer the dash colour on top, both 3 px wider than a casing. v2 drew a pattern image instead;
measured on Monaco both take the same time per slider step (about 325 ms headless, no tile reload) and look the same, and the two layers
need no image to keep in step (2026-10-06). The street-name and arrow slots carry `__rs_tunnel` from their road; on a map with tunnels the arrow icon is an SDF one, coloured by
`icon-color` (one symbol layer cannot mix SDF and plain icons). An item gets `__rs_tunnel` from its edge when the overlay is attached (`_edge_overlay`).

## Limits

- At a high strength a tunnel's name nears its fill colour (everything moves to the same slate); at 100 they are one colour.
- A slider move resets an `rsColor` recolouring of an overlay attached to edges. `rsColor` on the roads is kept.
