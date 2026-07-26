# TODO

Ideas noted from comparing against Overture's demo road style (2026-07-25).
Neither shows as a problem on current maps — pick up only if the symptom appears.

- [ ] **Per-class zoom culling in the web style.** Overture's demo gives each
  class layer its own `minzoom` (motorway 6 → footway 15). Our single
  data-driven layer pair can't use layer `minzoom` per class, but a
  `["step", ["zoom"], ...]`-based filter gating minor classes below ~z12 would
  skip their paint work on large extents. Do when: low-zoom rendering of a
  county-sized network feels slow.

- [ ] **`line-cap`/`line-join` step at low zoom.** Overture uses
  `["step", ["zoom"], "butt", 13, "round"]` (and `miter` → `round`) so dense
  low-zoom networks don't "bead" from overlapping round caps. One layout
  expression on `roads-casing`/`roads-fill`. Do when: cap blobbing is visible
  at z10–12.
