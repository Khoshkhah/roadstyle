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

- [ ] **`max_positions` in the Rust level solver.** The user can choose a hard
  limit on the number of drawing positions (`solve_levels(max_positions=K)`,
  `--max-positions`; `docs/design/level_input.md`). Only the Python solver has
  it. The Rust solver (a minimum-cost flow) has no such option, so a call with
  `max_positions` runs the Python solver (with a warning), and the browser
  editor cannot use it. It is a small change: one more rule in the model, that
  the span of all positions is at most (K - 1) steps. Do when: a user needs the
  limit in the browser editor or in the Rust program.
