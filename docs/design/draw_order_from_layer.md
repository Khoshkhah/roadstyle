# Draw order from the OSM `layer` tag

**Status:** implemented 2026-09-30 (approved by Kaveh the same day).

## Problem

roadstyle decides which road draws over which from its own `lvl`, not from OSM's `layer`
(`_mark_lvl` in `render_web.py`):

| Tags | `lvl` today |
|---|---|
| `bridge` | `max(1, layer)` |
| `tunnel` | `min(-1, layer)` |
| anything else | `min(layer, 0)`: a positive `layer` counts as ground |

In OSM, `layer` *is* the vertical order where ways cross; `bridge` and `tunnel` say what the
structure is. The rule above goes wrong where the two disagree. In duckOSM's Monaco build:

| Case | `layer` | `lvl` | Driving | Walking | Effect |
|---|---|---|---|---|---|
| `layer=1` or `2`, no `bridge` (a walkway on a raised deck, an upper-floor passage) | 1–2 | 0 | 2 | 164 | drawn **under** the street it passes over (footway 1154628869190511772 at Avenue Princesse Grace) |
| `tunnel` with `layer=1` | 1 | -1 | 2 | – | drawn under ground-level roads |
| `tunnel` / `bridge` with no `layer` | – | -1 / 1 | 22 | 126 | right |

## Proposal: order from `layer`, look from `bridge` / `tunnel`

1. **Order:** `lvl` = the OSM `layer` when tagged (and not 0); when it isn't, a bridge is 1, a tunnel
   -1, anything else 0. This matches OSM's meaning of `layer`, and the tags only fill in a missing one.
2. **Look:** unchanged, from the tags: the deck casing only for `bridge`, the dashed casing and
   faded fill only for `tunnel`.
3. **Bands:** as now, by the sign of `lvl`: below ground, ground, above ground. Each band gets a
   plain pair of layers next to its structure pair, because MapLibre can't switch a dash pattern
   per feature:
   - below: `roads-tunnel-*` (tunnels) and new `roads-low-*` (a road with a negative `layer`
     that isn't a tunnel: plain look, drawn below ground roads);
   - ground: `roads-casing` / `roads-fill`, unchanged;
   - above: `roads-bridge-*` (bridges) and new `roads-high-*` (a raised road that isn't a bridge:
     plain look, drawn over ground roads).

   A tunnel tagged with a positive `layer` goes in the above band with the plain look (rare: 2
   edges in Monaco).
4. **Kept as is:** the existing layer ids and their order (host pages anchor on `roads-casing`,
   `roads-bridge-casing`, `roads-highlight`); `lvl` still sorts within a band (a layer-3 viaduct over a
   layer-1 bridge); the bridge toggle hides `lvl > 0`; tunnel mouths (`tunnel_portals.md`) and 3D decks
   stay bridge / tunnel only.

## Behaviour change

Negative `layer` without `tunnel` today gets the tunnel look (dashed); with this it's drawn plain,
still under ground roads. Raised roads without `bridge` move above the ground roads. Both are
CHANGELOG entries under "Changed".

## Checks

- Tests: `lvl` for each row of the table above; the new layers exist, in band order, with the
  right filters; the bridge toggle still hides raised roads.
- In a browser (before and after): Monaco walking at Avenue Princesse Grace (the raised footway
  over the street) and Promenade Honoré II; Stockholm or Monaco bridges and tunnels unchanged.

## After this (duckOSM)

The maps' `level` (hover, popup, route list) is roadstyle's `lvl`, so it follows: it becomes the
layer, with 1 / -1 for an untagged bridge / tunnel. duckOSM's `add_level` changes to the same rule.
