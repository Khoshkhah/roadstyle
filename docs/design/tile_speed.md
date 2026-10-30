# The speed of the first tiles

This document describes how the Rust engine makes the tiles of the level editor's map (`LiveTiles`, the wasm `LiveMap`), where
the time goes, and the rules that keep the tiles fast and the same. Burnaby (151,770 roads) is the test area.

## The tile path

The map asks for a tile with `LiveMap.tile(source, z, x, y)`. `LiveTiles::tile` (`rust/roadstyle/src/relevel.rs`) then does these
steps:

1. **Waiting.** `Tiles::waiting` finds the pieces in the tile that have no properties yet. A piece waits from `new LiveMap` until
   the first tile that shows it.
2. **Cells.** `SimpleSource::piece_cells` gives each waiting piece its properties: its road's cells and its own marks.
3. **Make.** `Tiles::make` interns the properties (each key and each value gets a number in its layer) and keeps the piece's line.
4. **Build.** `Tiles::build` finds the features of the tile in the R-trees, clips and simplifies their lines, and encodes them as a
   Mapbox Vector Tile. The tile cache keeps the result (64 MB).

Steps 1 to 3 occur one time for each piece. Step 4 occurs one time for each tile.

## Where the time goes

Burnaby, the tilted view (pitch 60, zoom 14, 21 tiles of zooms 12 to 14, 120,208 pieces), native, before this change:

| Step | Time | For each piece |
|---|---|---|
| Waiting | 22 ms | 0.2 µs |
| Cells | 170 ms | 1.4 µs |
| Make | 102 ms | 0.85 µs |
| Build | 86 ms | 0.7 µs |

The cells and the make were most of the time. The cause was allocations and name lookups, not arithmetic:

- Each piece made about 15 owned JSON values (each text was copied), and `Tiles::make` then made each value again as a `Val`.
- For each piece, the engine read all of the road's columns (about 30). For each column it did a lookup of the name in the marks'
  map, a check of the piece's keys, and a lookup in the set of read keys. For each mark it did a search of the column names.
- Each lookup in a layer's keys or values used SipHash, and each value made a new buffer for its bytes.

## The rules

1. **The pieces borrow the road's cells.** `Props<'a, V = Value>` (`roadstyle-model/src/props.rs`) keeps JSON values or cells. A
   piece's properties are `Cells<'a>` (`Props<'a, Cell<'a>>`): a text borrows the road's Arrow column or the shared `Values`, with
   no copy. The JSON form (`Props::to_values`) comes from the same cells, so there is one logic for the tiles, the GeoJSON text and
   the layers' checks.
2. **Read each road one time for all of its pieces.** `Piece::base` gives the road's cells that a piece of one kind (casing, fill,
   half) starts from. `Piece::over` adds the piece's own marks. In one call (a `Run`), the pieces of a road come one after
   another (the casing pieces of a road, then later its fill pieces), so the run keeps only the last road's base. A run also
   keeps a plan of each kind (`Roads::own_plan`): which columns to read and which marks to keep, found one time, not for each
   road. The run knows which marks are read, so an insert does no lookup of a name.
3. **Intern with no copy.** `Val<'a>` borrows its text. A layer keeps `Val<'static>` and copies a value only when the value is new.
   The value's bytes go in one buffer that the builder keeps. The layer's maps of keys and values use foldhash (a fast hash that
   the lock file already had). A property that is the same as the last feature's property in the same place takes its number with
   no lookup.
4. **The buffer of each zoom comes from the widest stroke** (`roadstyle_tiles::buffer`): half the line width, the gap and the
   offset of the widest layer at the map zooms that draw the tile, 3 times where a width reads the live width. `buffer_px` (80) is
   only for a zoom where a stroke has no limit. A thin road at a low zoom then gets a small buffer, and fewer features go in a tile.
5. **The same bytes.** A change of speed must not change a tile. The tile goldens, the Python and Rust parity tests and the
   Burnaby tile hashes (`bench_live_views.mjs`) must stay the same.

## Burnaby, before and after

The first tiles of each view on a new map, 1280 × 800 at the roads' center. Native: `examples/bench_live.rs`. Node:
`rust/roadstyle-wasm/bench_live_views.mjs`. The tile bytes are the same before and after (the same hash in each view). One run
each, on a machine that other work also used: the numbers can change by about 10 %.

| View | Tiles | Size | Native before | Native after | Node before | Node after |
|---|---|---|---|---|---|---|
| z11 | 9 | 2.49 MB | 267 ms | 157 ms | 325 ms | 187 ms |
| z12 | 12 | 2.87 MB | 305 ms | 163 ms | 296 ms | 181 ms |
| z13 | 8 | 4.56 MB | 388 ms | 244 ms | 428 ms | 306 ms |
| z14 | 8 | 1.45 MB | 142 ms | 90 ms | 180 ms | 110 ms |
| z15 | 9 | 0.94 MB | 124 ms | 91 ms | 147 ms | 123 ms |
| Pitch 60, z14 (z12 to z14) | 21 | 6.47 MB | 482 ms | 295 ms | 521 ms | 359 ms |

The memory that the first tiles add stays the same (native: 35 to 67 MB).

After the change, the tilted view in native: waiting 22 ms, cells 70 to 88 ms, make 106 to 122 ms, build 88 to 100 ms.

## Features that no layer draws (option A)

MapLibre must parse every feature of a tile, also a feature that the style does not draw at that zoom. The style hides a casing end
(`__rs_seam`) without lap (`__rs_lap`) below z17, and a casing end with lap from z17. A tile of z12 to z16 had both kinds, so 17 % of
the features were parse work with no picture (Burnaby, the tilted view: 15,040 of 87,360 pieces in the z14 tiles).

A layer's filter now gives a feature a span of zooms [from, until) (`ZoomRules::span`; tiles.py `zoom_span`). The clauses that the rule
reads are `[">=", ["zoom"], E]`, `["<", ["zoom"], E]`, and "all" and "any" of them and of clauses on the feature. A clause with an
operator that the rule does not know keeps the feature at every zoom. A tile of zoom z has a feature when z + 1 is after `from` and z is
before `until` (the tiles of the last zoom have every feature that is drawn at or after the last zoom). One rule from the style: no
second copy of the zoom numbers.

Checked on the Burnaby tiles of z11 to z14: the features that the style draws (tested at z, z + 0.5 and z + 0.999) are the same before
and after, and the tiles after have no feature that is not drawn. Tile bytes (Burnaby, the same views):

| View | Features before | After | MB before | After | tile() Node before | After |
|---|---|---|---|---|---|---|
| z11 | 51,338 | 51,338 | 2.49 | 2.49 | 178 ms | 176 ms |
| z12 | 61,178 | 53,162 | 2.87 | 2.55 | 173 ms | 176–190 ms |
| z13 | 137,392 | 113,567 | 4.56 | 3.87 | 270 ms | 251–255 ms |
| z14 | 83,179 | 68,991 | 1.45 | 1.24 | 105 ms | 99–100 ms |
| Pitch 60, z14 (21 tiles) | | | 6.47 | 5.54 | 327 ms | 319–332 ms |

The time of `tile()` does not change: it makes and encodes the pieces that are drawn, and those are the same. Less data goes to the main
thread, but MapLibre's parse did not get much faster either. In the page session's control (the same style, tiles as static files, jump to
z14 at pitch 60, median of 5 runs, headless Chromium with software GL): now 1.47 s, with this rule 1.43 to 1.53 s (the runs overlap).
MapLibre does not build a bucket for a feature that its layer's filter hides, so a feature that is not drawn costs it little. The cost
follows the features that are drawn.

With no road layer at all, the same view takes 0.66 s (the base map and the overlays). With one feature for each road (only the fills below
z15, the casing as a second style layer on the same feature; a measurement, not code in the library) it takes 1.24 to 1.32 s: 26,064
road features in 3.15 MB. So the roads cost about 0.8 s now and about 0.6 s with one feature. Files and pictures:
`.claude/tile-lag/one-feature/` of the workspace.

## Tiny pieces at low zoom (rule B)

Below the last zoom, the encoder leaves out a road whose pieces are together under 1 px (8 of 4096 units), unless the road leaves the
tile, and a casing end piece (`__rs_seam`) under 1 px. It keeps every fill piece and every casing body piece. A rule that dropped all
pieces under 1 px made visible breaks in streets. Burnaby, 4 MapLibre workers, flat views, median of 5 (`.claude/tile-lag/ruleB/`):

| View | Before | After | `simple` features | MB | Pixels that differ |
|---|---|---|---|---|---|
| z12 | 480 ms | 362 ms | 53,160 → 32,394 | 2.55 → 1.57 | 0.65 % |
| z13 | 494 ms | 418 ms | 71,289 → 52,988 | 3.49 → 2.64 | 0.74 % |
| z14, pitch 60 | 968 ms | 992 ms (noise) | 72,320 → 69,845 | 3.56 → 3.44 | 0.05 % |

The gain is in the low zooms that MapLibre parses and draws. The tilted view at z14 has few tiny pieces, so it does not change.

## What gave no gain

- **One projection for each road.** To project each road's line one time for all of its pieces saved about 5 % of the make.
- **The properties of each road made one time, with owned values.** To make a road's shared properties one time and to skip the
  check of a key that is there gave no gain that we could measure. The cost was in the owned values (a copy of each text), not in
  the work that the engine did again.
- **Pieces sorted by road before the make.** The pieces of a road are already one after another. A sort gave no gain.

## Tiles v2, steps 3 to 7 (2026-10-27)

The steps of `tile_v2_plan.md` (the row as the MVT id, one key set for each tile layer, no `__rs_edge2`, no class colour text, no `roads`
tile layer) make the tiles smaller and the style simpler. They do not change a pixel. MapLibre 5.24.0 with 4 workers, headless Chromium
with software GL, the median of 5 runs, a new page for each run, the tiles of the Python binding. Burnaby here is the duckOSM file
`burnaby.duckdb` (40,872 directed roads; no overlay layers), before = `6317dd7`, after = the end of `design-tile-steps`.

| View | Tiles | Bytes before | Bytes after | ms to idle before | ms to idle after | Pixels that differ |
|---|---|---|---|---|---|---|
| Tilted, pitch 60, z14 | 28 | 1,146,626 | 850,147 (−26 %) | 324 | 335 | 0 |
| Flat z12 | 9 | 626,385 | 458,406 (−27 %) | 210 | 221 | 0 |
| Flat z13 | 8 | 1,171,479 | 856,388 (−27 %) | 270 | 293 | 0 |

The time did not change (the difference is inside the batch noise of 0.15 s; on this small area the parse of the roads is a small part of
0.3 s). The gain is the size, the simpler contract and the full look: its Tartu z12 view goes from 8.1 MB to 0.29 MB because the
`roads` tile layer is gone. In the budget (`tile_budget.json`), the largest `simple` tile of Monaco z15 has 68 distinct values (was 8,713),
15 keys (was 19) and an MVT id on every piece.

## The tiles of the low zooms (2026-10-28)

On the duckosm-rust page, Burnaby (64,221 roads, with the base map) had low-zoom tiles of 0.5 to 1.2 MB, and MapLibre needed 0.4 to 0.7 s for one
tile. The tile cut in Rust is 2 to 80 ms. The page's zoom lag is therefore MapLibre's parse and layout, so the tiles must carry only what is drawn.
`.claude/tile-lag/speed/` of the workspace has the measurements and the drivers (`COMPOSITION.md`, `composition.mjs`, `ml.py`, `cmp.py`).

**The composition came first.** `composition.mjs` decodes the tiles of Burnaby at z9 to z15 and checks each feature against the style layers (zoom span,
filter, visibility). `ml.py tile` gives MapLibre's time for the largest tile of each zoom, with and without the style layers of a source layer
(headless Chromium, software GL, 1 worker, median of 3 to 5 runs, the noise is about 10 %):

| Tile | KB | all layers | roads only | base map only | `ov0` (land) only | `ov5` (other ways) only |
|---|---|---|---|---|---|---|
| z9 | 638 | 154 ms | 34 | 191 | 113 | 78 |
| z10 | 841 | 202 | 42 | 205 | 115 | 50 |
| z11 | 1,157 | 246 | 110 | 197 | 116 | 36 |
| z12 | 790 | 178 | 104 | 86 | 57 | 30 |
| z13 | 590 | 148 | 109 | 40 | 37 | 17 |

At z9 to z11 the base map is the cost. At z12 and z13 the road pieces are the cost. Three facts from the composition decide the rules:

- A base-map polygon goes into each tile whole and is not simplified. The z10 tile has 92,611 vertices of land, and 80 % of its segments are shorter than 1 px.
- The layer of other ways (`ov5`: the streets that are not in the network) has 17,000 to 23,000 lines with no property in a low-zoom tile, and 74 % of them at z9
  are shorter than 1 px. They are drawn with a stroke of 1.4 px.
- No feature of a visible layer is outside its zoom span. Rule 1 has no gain here. The layers that the page hides at the start have 0.1 to 1.1 % of the bytes (3.1 % at z15).

**The rules.** A layer is flat when only `fill` and `line` style layers draw it (`Tiles::flat`): a point, symbol or extrusion layer needs its shape as it is.
Below the last zoom, for a flat layer (`roadstyle-tiles/src/small.rs`):

| # | Rule | Gain on Burnaby | Test |
|---|---|---|---|
| 1 | Only the features that a style layer draws at the zoom | None. Not changed. | `undrawn` = 0 (the budget) |
| 6 | A polygon is cut to the tile and its buffer and simplified to 1 tile unit (1/8 px) | `ov0` 262 KB to 147 KB at z10, MapLibre z9 155 to 100 ms, z10 187 to 138 ms | `a_flat_layers_polygon_is_cut_to_the_tile_and_simplified` |
| 7 | A line that is together under half a pixel long and stays in the tile is left out | `ov5` 384 KB to 208 KB at z10, MapLibre z9 100 to 73 ms, z10 138 to 114 ms | `a_flat_layers_line_under_half_a_pixel_is_left_out` |
| 7 | A polygon whose box is under 1 px on both sides is left out | 2 to 4 % of the bytes, no change in MapLibre time. **Not done.** | |

Why these numbers (each was measured on Burnaby, MapLibre time and the pixels that differ by more than 64 of 765 in 17 views, z9 to z16 and pitch 60):

- The tolerance of 2 units gave 15 % less MapLibre time than 1 unit, and 0.009 to 0.2 % of pixels that differ (against 0.002 to 0.06 %). The edge of a polygon moves
  by 1/8 px at most, which is the step of the tile grid. A tile of zoom z is drawn at the map zooms z to z + 1, so at the end of that span the edge moves by 1/4 px.
- A limit of 1 px for the lines gave the same MapLibre time as half a pixel, 0.005 to 0.41 % of pixels that differ (half a pixel: 0.003 to 0.17 %), and 20 to 55 KB less for each tile at z9 to z10.
  A fragment of a footway is one feature, so a limit of 1 px makes more breaks in a path that has many short fragments.
- The polygons under 1 px (rule 7, the third row) were built, measured and removed from the code: a gain of 2 to 4 % of the bytes and no gain in time is not worth a rule.

The last zoom is as before. A layer that a circle, symbol or extrusion layer draws is as before (the walls of an extrusion at a cut edge would show).

| View (1400 x 850) | KB before | KB after | Features before | After | Vertices before | After |
|---|---|---|---|---|---|---|
| z9 | 638 | 322 | 24,778 | 13,300 | 130,115 | 56,815 |
| z10 | 841 | 518 | 30,463 | 19,602 | 170,199 | 88,206 |
| z11 | 1,508 | 1,260 | 48,992 | 42,874 | 246,363 | 167,235 |
| z12 | 1,838 | 1,630 | 56,541 | 53,620 | 307,917 | 225,353 |
| z13 | 2,270 | 2,158 | 66,407 | 65,618 | 270,140 | 220,558 |
| z14 | 1,018 | 969 | 28,484 | 28,351 | 116,317 | 94,684 |
| z15 | 840 | 840 | 22,595 | 22,595 | 98,744 | 98,744 |
| Pitch 60, z13 (22 tiles) | 4,549 | 4,189 | 136,744 | 131,933 | 638,343 | 494,069 |

MapLibre time for the largest tile of each zoom (`ml.py tile`, median of 5), before and after: z9 154 to 73 ms, z10 202 to 114 ms, z11 246 to 193 ms, z12 178 to 152 ms,
z13 148 to 146 ms, z14 and z15 are the same tiles. The roads are the rest of the time at z11 to z13. Pixels that differ by more than 64 of 765: 0.003 to 0.17 % (0 at z15 and z16.5).
The tile cut time (`LiveMap.tile`) does not change by more than 5 ms for each tile.

**Burnaby on the page, before and after.** A scratch copy of the contract-2 page (duckosm-rust `claude/tile-contract-2`: roadstyle `2fc8477`, 4 MapLibre workers, no tile
queue or overview of the other page PRs) with only `map/pkg` replaced: the build of `origin/rust-engine` (`71af6fe4`) and the build of this branch. `black.py` of
`.claude/tile-lag/zoom/` builds Burnaby in the page (driving, blank dark, pitch 60) and then zooms with the mouse wheel. Path A: start at zoom 9, 10 wheel events of 400 px, the
view goes to zoom 13.6, three pans, and the same wheel events out. Headless Chromium with software GL. Before and after ran at the same time on one machine, 5 runs each: the
run-to-run noise is 30 %, so read the median and the runs.

| | before | after |
|---|---|---|
| Largest tile of z6, z7, z8, z9 (KB) | 220, 317, 454, 638 | 37, 111, 205, 322 |
| Largest tile of z10, z12, z13 (KB) | 841, 791, 591 | 518, 705, 557 |
| MapLibre parse and layout, median of the tiles over 20 KB: z12, z13 (ms) | 637, 694 | 402, 469 |
| Zoom in (path A), ms to idle: median (runs) | 5,785 (4,854; 5,785; 5,076; 5,844; 6,603) | 3,552 (3,902; 2,618; 3,050; 4,479; 3,552) |
| Zoom out, ms with more than 5 % of the area empty: median (runs) | 1,117 (588; 1,763; 1,117; 1,820; 792) | 785 (345; 1,108; 785; 0; 1,728) |
| Zoom out, empty share of the area times the time (area-ms): median | 483 | 280 |
| Tile calls, MB of path A: median | 155 calls, 8.2 MB | 149 calls, 8.4 MB |

Path A mostly asks for tiles of z12 to z13, where the road pieces are the cost, so the total bytes of the path do not change. Path B (the fit view, zoom 11.45, 14 wheel events
of 250 px, 2 runs each): zoom in 7,984 ms (6,972; 8,996) before and 6,366 ms (5,450; 7,282) after; zoom out empty for more than 5 % of the area 1,588 ms before and 1,211 ms after.
The static test (`ml.py view`: the saved tiles of Burnaby, a flat view jumps in by 2 zooms, 4 MapLibre workers, median of 5 runs, with the first frame of a new map): z10 451 ms before
and 476 after (the same tiles within the noise), z11 806 to 357, z12 813 to 451, z13 697 to 557, pitch 60 at z14 527 to 420. The tile cut in Node (`LiveMap.tile`, 12 tiles of one view)
costs more: z10 38 to 65 ms before and 71 to 105 ms after, z12 87 to 118 ms before and 128 to 192 ms after, that is 3 to 6 ms for each tile for the polygon clip and the simplification.
That time is in the map worker, in parallel with MapLibre's, and it is below the gain of 30 to 100 ms that MapLibre has for each tile.

**What the page can do (not changed here).**

- **Keep the overview at z9** (`rs-low`, land and water). Its tile is now 322 KB and MapLibre needs 73 ms (before 638 KB and 154 ms). An overview at z8 would be 205 KB, and the
  start below z9 (the black zoom out from z6 to z8 of the report) would load tiles of 37 to 205 KB, not 220 to 454 KB.
- **Make the tiles of the zooms below the view before the map asks for them.** The zoom out is empty because the map has no tile 3 or more levels up. Each such tile costs 50 to 190 ms in
  MapLibre now, so the worker can make and the map can parse 2 levels up while the user zooms in.
- **The source `maxzoom` of `rs-roads`** (15 in the page's look) is correct: the tiles of z13 to z15 are 550 to 170 KB and take 135 to 50 ms. A lower `maxzoom` saves little (z15 at pitch 60: 3,068 KB
  of 20 tiles against 3,018 KB of 19 tiles at z14) and makes the casing pieces less exact (`tile_precision.rs`).
- **The roads are the cost from z11.** The smaller road width expression (below: built, 8 to 12 ms for each tile at z11 to z13) is a roadstyle change, not a page change.

**The road width expression.** The expression is 29,032 characters (24,720 in the style of the page: `line-width` of `roads-simple`). We measured the MapLibre time of the largest tile,
with the road layer only (the base-map layers removed, tiles of this change, median of 5):

| Tile | the expression now | a smaller form with the same widths | one lookup by class (the widths are wrong) | constant width |
|---|---|---|---|---|
| z11 | 125 ms | 97 | 90 | 84 |
| z12 | 99 | 81 | 74 | 62 |
| z13 | 113 | 89 | 74 | 65 |

The smaller form has the same widths: one `let` that computes the row of the piece (kind, pair, bridge, two-way) once and one lookup in a table of 20 rows for each of the 9 stops.
A check of 187,920 combinations of features, zooms and live widths found no difference (`width_let.mjs`).

**Built (2026-10-29, branch `design-width-table`).** The engine now writes this form (`layers/width_table.rs`). `width_curve` still builds the `case` form; `table_form` evaluates it
for each row (kind, pair, bridge, two-way), class and stop, and writes the `let`. Two more steps make it smaller than the prototype: the classes that have the same width in all rows
and stops are one group (13 groups for 29 classes: a second `at` gives the group), and the numbers are rounded to 6 decimals. A width that a feature sets (metres, items) is not in a
table: `table_form` gives None and the `case` form stays. The new form is 14,580 characters in the budget's styles (before 26,312) and 14,270 in the Burnaby style (before 24,720).
`tests` in `layers/width_tests.rs` compare the two forms for all 48 rows, all classes, zooms 11 to 21 in halves and two live widths, in three modes (no pairs; pairs; pairs and tunnels).
The same check in MapLibre's own style-spec evaluator (`width_table_check.mjs`) found 0 differences in 187,920 combinations; the largest difference is 8e-7 px.

MapLibre parse and layout of the largest tile (Burnaby, `ml.py tile`, tiles of this branch, ms, median of 28 runs, the runs in brackets). The road layer alone (base-map layers removed),
the three forms in turn, 4 rounds of 7 runs, on a machine that other sessions also used:

| Tile | `case` form | prototype | table form (built) |
|---|---|---|---|
| z11 (903 KB) | 129 (116-161) | 120 (102-169) | 117 (97-143) |
| z12 (687 KB) | 100 (90-152) | 95 (80-119) | 92 (81-122) |
| z13 (564 KB) | 112 (102-215) | 100 (89-141) | 104 (90-154) |

The gain is 7 to 9 % of the road time, 8 to 12 ms for each tile, not the 18 to 22 % of the first measurement (125 to 97 ms at z11). The machine had more load now, and the run-to-run noise
is 20 to 30 %: read the direction (the table form is faster at all three zooms, as the prototype is), not the last digit. The full style (all layers), 2 rounds of 7 runs:
z11 203 to 185 ms, z12 185 to 150 ms, z13 142 to 134 ms. The pixels of 17 views are the same (see the CHANGELOG).

**The budget.** `tile_budget.json` has views of zoom 9 to 15 (it had 12 to 15) and the areas `monaco-base` and `tartu-base`: the page's look with the base map. The rules above have a
limit in it now (`short_segments`, `tiny`, `bytes` and `features` of each base-map layer). The check of rule 1 knows the last zoom of the look.

## The next levers

The Node profile of the tilted view after this change: interning about 90 ms, tile encoding (`Tiles::build`) about 60 ms of its
own time, allocations (`malloc`, `free`, `realloc`) about 47 ms, piece cells about 47 ms.

- **Interning.** About half of the values are new to the last feature, because the pieces of a road are about two for each run.
  Each new road then has a lookup for each of its values. A road's interned numbers, kept for its casing run and its fill run,
  could remove some of them.
- **Allocations.** Each piece makes three vectors: its cells (a copy of the road's base), its interned numbers and its line. A
  buffer that the run keeps for the cells could remove one.
- **Build.** Clipping, simplification and encoding are now about a third of the time. A coarser simplification at low zooms (1 px of a
  512 px tile) gave 1 to 2 % on Burnaby, because its lines have few points: not worth the change of bytes. Fewer pieces at low zooms (one
  line for each road) cut the tile() time of z11 to z13 to a third and the pitch-60 case from 327 ms to 208 ms, but the map loses the
  two casing halves, the bridge casing and the order of levels.
- **The page's tilted view.** The page asked for 36 tiles at pitch 60, zoom 14 (1.5 s before). The model of MapLibre's tilted view
  in `bench_live_views.mjs` gives 21 tiles. With the gain above, the page's case is about 1.0 s. The target of 0.6 s needs one of
  the levers that change the tile bytes, or tiles that the worker makes before the map asks for them.

## The road layer in MapLibre (2026-10-29)

**Problem.** MapLibre evaluates each data-driven paint property for each feature of a tile. For the road layer, this is 75 to 86 % of the
feature loop (z12 and z13, Burnaby). A property that is one value, or a layer without a property, costs less.

**Zoom bands (removed 2026-10-29).** `layers/bands.rs` split the road layer for each band of zooms (`roads-simple`, `-z14`, `-z15`), and each band
had its paint values as constants. They saved 13 to 19 % of the MapLibre time (Burnaby, z11 to z14). They were removed the same day: the worker
builds the buckets of a tile only for the layers whose `minzoom` and `maxzoom` hold the tile's zoom, and MapLibre keeps the tiles of the old zoom
on the screen until the tiles of the new zoom have come. A layer that the map draws at the new zoom has no buckets in those tiles, so the roads were
missing: at pitch 60 on Nacka, zooming out from z14 to z13.5 left roads only in the far field, and zooming in past z14 the same (a screenshot at z13.72;
0 empty frames in 60 without bands, 4 with). It happens with GeoJSON roads and with tiles. A layer with a zoom range is safe only when no tile of
another zoom can be on the screen, and that is never true. The road layer is now one layer for every zoom (and its dash layer).

**Dash layers.** Only the dashed pieces have `line-dasharray`: a tunnel's gap and dashes (`__rs_k` 3 and 4) and a piece with `__rs_dash`.
They are in the layer `<band>-dash`, under the layer of the other pieces. A tunnel is then under the roads that cross it and under its own
fill, as in rank. A dashed piece with `__rs_dash` is under all other pieces, not between them. The picture changes by 1 % of the pixels
(the dotted fringe of the casing goes).

**Layers.** Before: 1 road layer. After: 1, and 2 when the area has dashed pieces. The style text
of the road grows from 29 KB to 70 KB (Monaco); the tile budget has the new limits.

**JS.** The dashboard reads the road layers as a list (`RS_LEANS`; `leanAt()` gives the one that the map draws). Pick, hover, select and
Street View use the list.

**Cost in code.** 111 lines in `bands.rs`, 20 in the style builder and 20 in the JS (without tests).

**Result** (Burnaby, live style, minimum of 15 runs, change against the style before; noise 5 to 8 points):

| Change | z11 | z12 | z13 | z14 | Pixels that differ |
|---|---|---|---|---|---|
| Zoom bands alone (removed, see above) | -18 % | -13 % | -15 % | -19 % | 0 |
| Dash layers alone | -14 % | -9 % | -8 % | -9 % | 0.97 % |
| Both | -18 % | -11 % | -26 % | -26 % | 0.97 % |

The MLT and MVT tiles give the same pixels. The tiles do not change (the same bytes).
