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

- [ ] **Move the logic of the Python layer into Rust.** Rust is the main
  library (`docs/design/target_architecture.md`). The browser editor and the
  Rust command line have no Python, so a rule that only Python has is missing
  there. Python must keep only the calls of the Python API, the GeoDataFrame
  conversion and `snapshot.py` (it needs a browser). Files to check first, in
  `src/roadstyle/`: `classify.py` (Rust has no color class cuts),
  `validate.py`, `filters.py`, `overlays.py`, `edges.py`, `duckosm.py` (input
  rules written twice), `_settings.py`, `config.py`, `basemaps.py` (the look
  files already belong to Rust), the export file writing in `_engine.py` and
  `export.py`, `cli.py` and `mcp_server.py` (Rust has both). The level solver
  stays in Python until `max_positions` is in Rust (the item above). Step 1,
  with no code change: an audit of each Python function, with one table that
  says "Rust has an equal" or "Rust does not have it". Do when: the next work
  on the library is a feature that the browser editor or the Rust program
  needs, and Python has it.
