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
