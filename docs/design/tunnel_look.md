# The tunnel look: one slider

**Status:** built (branch `tunnel-look`), waiting for Kaveh's review. Asked for 2026-10-06, from the Monaco v2 test
(`docs/v2/tunnel-coloring.md` on `v2-dev`). Builds on [Levels and looks](levels_and_looks.md): a tunnel is drawn at its
position like any road; only its look differs.

## What a tunnel looks like

One number, the **fade** (0 to 1, setting `tunnel_fade`, default 0.3), moves three things together:

| part | at fade 0 | as the fade grows |
|---|---|---|
| the fill | the road's own colour | moves toward the base map's background colour. **Opaque**: no see-through fill and no underlay, so overlapping pieces never show darker joints |
| the casing | the two tones of the road's casing (`tunnel_gap_shade`, `tunnel_dash_shade`) | the solid tone moves toward the palette's gap colour, the dashes toward its dash colour |
| the items attached to the tunnel (`Overlay(edge_col=...)`: lanes, lines, arrows, names) | their own colours | move toward the background with the fill. They keep their own colour: no tunnel colour replaces it (Kaveh) |

The **palette** (setting `tunnel_palette`) names the casing's two colours, `[dash, gap]`, in `tunnel_palettes`: `Slate + ice`
(default), `Blue + cyan`, `Warm + sand`, the three of the v2 test. The light dashes on the fill (`tunnel_fill_dash`) stay as they were.

## In the page

A **Tunnels** box (on a map with tunnels; `tunnel_control=False` leaves it out) has the slider and the palette menu.
`rsSetTunnelStyle({fade, palette})` does the same from a host page and fires `rs:tunnelchange`. *Colour by* and `rsColor` keep the
fade: the road fill's colour is always passed through it. A new base map moves the fade toward its background.

## How

Each colour that takes the look is a MapLibre expression: for a feature with `__rs_tunnel`,
`["interpolate", ["linear"], fade, 0, <colour>, 1, <target>]`, else the colour (`_tun_mix` in Python, `_tunMix` in the page). The
page keeps each layer's colour without the look (`TUNNEL.layers`) and builds the expression again when the slider moves; no data is
baked per value. An item of a tunnel gets `__rs_tunnel` from its edge when the overlay is attached (`_edge_overlay`).

## Limits

- A slider move resets an `rsColor` recolouring of an overlay attached to edges (it rebuilds the layer's colour from the one without
  the look). `rsColor` on the roads is kept.
- The fade goes toward one colour, the background's. Over a satellite or tiled map a faded tunnel is that flat colour, not see-through.
