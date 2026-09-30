# Tunnel mouths that look connected

**Status:** implemented 2026-09-30 (approved by Kaveh the same day).

## Problem

A road that goes into a tunnel is drawn as if it hit a wall. The web renderer draws in three bands:
tunnels (lvl < 0) first, then the surface roads' casing and fill, then bridges. At a **tunnel mouth**
(a tunnel edge and a surface edge sharing an end point), the surface road's casing and round end cap
are painted **over** the start of the tunnel. The reader sees a grey line across the road: two
roads on different levels that don't touch, although they are one road.

Seen in duckOSM's Monaco maps, e.g. "Tunnel Aureglia" → "Rue Grimaldi" (edges
2835193137460404044 → 5645487982128392741) and "Tunnel Albert II". Monaco's driving network has
96 junctions where a tunnel or a bridge meets a surface road.

**Bridge ends are fine:** the bridge band is on top, so the bridge's fill covers the surface road's
cap and the road reads as continuous. Only tunnel mouths need a fix.

## Proposal: a portal piece at street level

For each tunnel end that meets a surface road, draw a short piece of the tunnel, its first or last
few metres, **at street level**, as fill only:

- **Found in Python** while the page is built: tunnel-edge end points (lvl < 0) that equal an end
  point of a surface edge (lvl 0), matched on rounded coordinates. The piece is cut from the
  tunnel's own geometry (`portal_m`, default 8 m, a setting under `config`).
- **Its own source, `portals`**, not in `roads`: one feature per edge stays the rule, so feature
  ids, `rsQuery`, `rsSelect` and the other JS calls don't change. A piece carries its tunnel's
  properties that styling needs (`highway`, `__rs_fill`, the two-way offset fields) and its road's
  feature id (`__rs_road`).
- **One new layer, `roads-portal-fill`**, between `roads-casing` and `roads-fill`: same fill width
  and offset expressions as the roads, full opacity. It covers the surface road's casing where the
  tunnel starts, so the road runs into the tunnel; the tunnel look (dashed casing, faded fill)
  starts a few metres in, as at a real tunnel mouth.
- **Recolouring follows:** `rsColor`, `color_options` and `rsFilter` apply to the pieces through
  `__rs_road` (the same expressions, keyed on `["get", "__rs_road"]` instead of `["id"]`), so a
  highlighted or hidden tunnel is highlighted or hidden at its mouth too. The class filter and
  `minzoom` apply as to the roads.
- Not clickable: a click there hits the surface road or the tunnel next to it.

## Not chosen

- **Splitting the tunnel feature** at the mouth: two features for one edge would break the id
  contract (one feature per edge, `rsSelect(id)`).
- **Dropping the surface casing at the mouth:** a line's casing can't be switched off for part of
  it.

## Checks

- Tests: pieces found for a tunnel-surface end, none for tunnel-tunnel or surface-surface ends; the
  layer sits between `roads-casing` and `roads-fill`; `rsColor` on a tunnel's id repaints its piece.
- In a browser (snapshots, before and after): duckOSM Monaco at Tunnel Aureglia and Tunnel Albert
  II, zoom 16 to 19, light and dark themes; a tunnel recoloured with `rsColor`.
- Release note in `CHANGELOG.md`; `docs/` guide on bridges and tunnels if it shows the old look.

## After this (duckOSM)

`duckosm route-map` draws the route in its own layers per band; its tunnel band has the same wall
at a mouth. With this in roadstyle, route-map adds its route line on the `portals` source too
(filtered on `__rs_road`), in the surface band. Then the maps are rebuilt with the new roadstyle.
