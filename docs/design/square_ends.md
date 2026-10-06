# Square ends per edge (`cap_col`)

**Status:** approved by Kaveh 2026-10-02 as part of mapstyle's `docs/design/levels_plan.md` ("go ahead and fix all issues in one
package"); a roadstyle addition asked for by Kaveh, an exception to "roadstyle is not changed for mapstyle".

## Problem

Every casing and fill is drawn with **round** caps, deliberately: consecutive edges are separate LineStrings, and a round
cap seals the seam where two connect. But a road drawn in **pieces** (mapstyle cuts a raised or sunk edge into a ground
piece at its joint and a raised piece over the crossing, `levels_plan.md`) meets its own other piece at the cut. There a round
end of the upper piece's casing shows as a ring on the lower piece's fill (checked on a synthetic scene: the ring only moved
from the joint to the cut). The pieces must end **square**.

## Rule

`cap_col` names a column. A true value (`True`, `1`, `"yes"`, as for `tunnel_col`) bakes `__rs_cap` on the feature, and the
edge is drawn by a **butt-capped twin** of its band's casing and fill layers; the round layers exclude it. MapLibre sets
`line-cap` per layer, not per feature, hence layers. Twins: `roads-low-casing-sq`, `roads-low-fill-sq`, `roads-casing-sq`,
`roads-fill-sq`, `roads-high-casing-sq`, `roads-high-fill-sq`, each right after its round layer, so a band's casings stay under
its fills. Dashed classes and bridges draw butt-capped already and are unchanged. `rsColor` / colour-by reach the twin fills
(`RS_FILL_LAYERS`).

## Also in this change: the tunnel look in any band

A tunnel moved to another band by `band_col` (a stretch at ground level at its mouth) keeps its look: the casing dashes,
the light fill dashes and the faded fill now also exist for the ground and the high band, only when such a tunnel is present.
Before, `band_col` moved the tunnel's casing and fill but dropped its look sublayers.

## Checks

Tests: twin layers and filters, order inside a band, nothing without the keyword, the tunnel look in the ground band and
nothing extra without such a tunnel.

## Square, and one end at a time (Kaveh 2026-10-06)

Found in the level editor: a wide road ending on a narrower one at a narrow angle, its round end reaching across the other road
(Tunnel Aureglia into Rue Grimaldi, Monaco). A flat end there fixes it, but a flat end on both ends makes the road look shorter by
half its width at each end, which confused. So:

- `cap_col` value `"square"`: MapLibre's square cap, flat but as far past the end point as a round end; twin layers `-sx`.
- `cap_start_col` / `cap_end_col`: one end each (`"round"`, `"square"`, flat = any other true value; null = `cap_col`'s). An edge
  whose two ends differ (`__rs_split`) is left out of the whole-edge fill layers and drawn from a `halves` source: the fill cut at
  the middle, each half with its end's cap (`roads-fill-h` / `-hsq` / `-hsx`, per position). Its casing is always cut into heads
  (the divided casing), each head with its end's cap. At the middle cut the halves overlap or meet in the same colour.
