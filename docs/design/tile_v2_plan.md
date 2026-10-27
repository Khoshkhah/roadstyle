# Tiles v2: the review and the plan

Status: plan, 2026-10-27, for Kaveh's OK. No code. Branch `design-tile-v2`, from `rust-engine` at `7dbf59d` (phase 0, the tile size
standard, is in). It includes phase 1 (`design-tile-wk`, `ad2d1ea`, not landed).

The aim: tiles that apply every reduction rule of the standard ([tile_contract.md](tile_contract.md), "The tile size standard"), and a
data layer that is fully apart from the tiles. At the end, each number of the budget is smaller than now, and no raise is needed.

## 1. What the review found

The tile path, from the engine to the page:

1. **The engine** (`roadstyle-engine`, `simple.rs`) cuts each road into pieces (casing parts, halves, seams, laps, fill, items) and gives
   each piece a property map: the road's columns and up to 20 marks (`__rs_*`).
2. **The style builder** (`layers.rs`, `road_layers`) writes the look as MapLibre expressions that read these marks: a `case` tree on the
   kind and the flags, with class tables, at each zoom stop. MapLibre calculates the tree for each feature.
3. **The tiles** (`roadstyle-tiles`) keep every `__rs_*` mark and the keep list (`props::drawn`: the style's reads, the page's reads,
   the popup's fields and the caller's `keep`), intern the values, and encode. The pieces have no MVT id: `promoteId` reads `__rs_edge`.
4. **The wasm API** (`Tiler`, `LiveMap`, `tileSources`) gives the tiles and the road table as JSON. The page and the editor call
   `tileSources` (eager). `LiveMap` (lazy, with `relevel`) is used only by the benches.
5. **The page** (the dashboard JS) reads tile properties: `filter.js` (`__rs_cls`, `lvl`, `__rs_access`, `__rs_edge2`), `select.js`,
   `core.js` and `arrows.js` (`__rs_edge`, `__rs_k`, `__rs_pick`). The popup, the panel and the live colours already use the road
   table and the feature-state by row.

What this costs, against the 10 rules:

| # | Rule | Now | The cause in the code |
|---|---|---|---|
| 1 | Only drawn features | Done for `simple`. Not for `roads` (full look): 86 % not drawn at z12. | `roads-highlight` has no zoom rule. |
| 2 | Only the keys that the style reads | `simple` 3 of 18 unread, `slots` 6 of 12, `roads` 14 of 21, `ov4` 3. | The keep rule keeps every `__rs_*` mark and the page's keys. |
| 3 | The row as the MVT id | Not done. | `promoteId` on `__rs_edge`. |
| 4 | Numbers, not text | `highway` (filter), `__rs_casing` and `__rs_fill` (colours) are text. | The look writes colours and classes as text. |
| 5 | Each value once | Done. | |
| 6 | Pixel tolerance | 1/16 px. | `douglas_peucker_kept(.., 0.5)` at every zoom. |
| 7 | Nothing under a pixel | 50 % of the z12 `simple` features of Monaco are under 1 px. | Heads, seams and laps are cut at every zoom. |
| 8 | The zoom's grid | 4096 units at every zoom. | `EXTENT`. |
| 9 | Base-map layers | Rule 1 by `minzoom` only; all their keys stay. | `TileOptions::rule`: a GeoJSON source keeps all keys. |
| 10 | One copy of a road | Done in the page's look; the full look has `roads` too. | `crate::export(look)` keeps `roads`. |

The main design problem is item 2 above. The look becomes a large expression that reads many small keys, and MapLibre calculates it
for each feature. On Burnaby this is 0.65 s of the 1.42 s of the tilted view (`expr/`). Phase 1 compiles two of these expressions into
tables *after* the builder wrote them (`width_key::compact`), with a fallback when the shape is not known, and it keeps three flags in the
tiles for the editor's compare. That is a second path beside the first, and the tiles get 4 % larger.

## 2. The design of v2

**A piece in a tile has four items:**

| Item | What | Size |
|---|---|---|
| MVT id | the road's row (`RoadKey`) | 2 to 3 bytes; no value |
| `d` | the draw row: one small integer for all that the style needs of the piece and that has few values (the kind, the class index, the pair, twoway, bridge and tunnel flags, the cap, the dash, seam and lap) | a few hundred values in an area |
| `r` | the sort rank (2 × position + the kind's step) | about 100 values |
| `f` | the colour index into the active option's palette (fill and casing) | the palette's size |

A look in metres also has the piece's metre width (a number of the road). An item (kind 5) keeps its own colour, width and minzoom.
Nothing else goes into the tile.

**The style reads only these.** The builder writes each property as a table by `d`, made from the look directly, not from an old
expression:

- `line-width` = `["+", ["at", class part of d, base table], ["at", mode part of d, mode table]]` at each zoom stop, times the live
  width factor. The base table is the casing and fill curve of each class; the mode table is what a shadow, a bridge casing, a tunnel
  and a pair add. Two small tables for each stop (about 80 numbers), not 20 × 29 (phase 1) or a `case` tree (now).
- `line-offset`, `line-opacity`, `line-dasharray`, `line-cap` and the casing colour: one table by `d` each.
- The filter: `["at", d, minzoom table]` and `["at", d, maxzoom table]`. The tiles apply the same tables (rule 1, `ZoomRules`).
- `line-sort-key` = `["+", ["*", ["get", "r"], 1e8], ["id"]]`; the raise of the top roads reads `["id"]`.
- The fill colour = `["coalesce", ["feature-state", "rs_c"], ["at", ["get", "f"], palette]]`, with the glow as now.

The parts of `d` come out with `%` and `/` (cheap arithmetic, not a tree). The engine checks with a unit test that the tables give the
numbers of the old expressions for every kind, flag, class and stop (phase 1's check, kept as a test, not as a fallback at run time).

**The data layer.** All other data of a road is in the worker: the road table and the feature tables, by row
([tile_contract.md](tile_contract.md), section 4: `generation`, `edgeIds`, `rowsOf`, `fields`, `columns`, `select`, `features`). The
dashboard filters ask `select` and set one `match` on `["id"]`. The popup and the panel ask `fields`. The live colours and the glow stay
feature-state by row.

**One tile path.** The pieces always wait for their properties until a tile shows them (`add_waiting`, as `LiveTiles` does now), so the
eager and the lazy maps are one code. `tileSources`, `Tiler` and `LiveMap` become one object (`LiveMap`) with the data layer calls. The
editor's `relevel` compares pieces by their `d`, `r` and line, not by their property maps.

### Remove, rewrite, keep

| Remove | Rewrite | Keep |
|---|---|---|
| `width_key.rs` and its fallback (phase 1) | the pieces' properties: `d`, `r`, `f` (`simple.rs`) | the encoder: interning, value cache, trees by first zoom, tile cache |
| the `case` trees of the road layer (`by_feature`, `times_each_stop`, `pair_width` as expressions) | the road layer's paint, layout and filter as tables (`layers.rs`) | `ZoomRules::span` (rule 1), with `at`, `%` and `/` in `roadstyle_model::eval` |
| `promoteId`, `PROMOTED`, `__rs_edge`, `__rs_edge2`, `__rs_s` in tiles | the keep rule: the keys that the style reads at each zoom (`TileOptions::rule`) | clip, buffers per zoom, PMTiles |
| `__rs_k`, `__rs_ci`, `__rs_wk`, `__rs_pair`, `__rs_bridge`, `__rs_twoway`, `__rs_tunnel`, `__rs_cap`, `__rs_seam`, `__rs_lap`, `__rs_dash`, `highway`, `__rs_cls`, `lvl`, `__rs_access` in `simple` tiles | `LiveTiles::relevel`: compare typed pieces | the relevel ring and `style_changed` |
| the eager path for `simple` (`add_lines` of pieces) | the wasm API: one `LiveMap` with the data layer | the road table (now as Arrow, by row) |
| `reads.json` `pieces` (empty at the end) | the dashboard reads: `f.id`, `select`, `fields` | the feature-state of live colours and the glow |
| `roads`, `roads-fill`, `roads-highlight` in the full look (D5) | `export_style`: a props file by id (D5) | the budget test, the ratchet |

The `d` table must hold every value that a relevel can make (all caps, seams and laps of the classes in the area), so that a relevel does
not change the style. A new class or a new colour option is a new style, as now (`style_changed`).

## 3. The order of work

Each commit passes CI. Each commit lowers the budget (`scripts/tile_budget.py`) and needs no raise. The pixels stay the same until
step 7: the Monaco and Tartu goldens, and the Burnaby tilted view with the `ctl.py` harness (0 pixels differ).

| Step | roadstyle commit | Rules | Expected effect (Burnaby tilted view) |
|---|---|---|---|
| 0 | D0 decided: the Python engine's road style and tiles stop (the binding gives the Rust output; parity tests of the road layer retire). Without this, each step below is two ports. | | |
| 1 | `d` and the tables: the engine writes `d` and `f`; the builder writes the tables; `width_key.rs` goes; the style-only marks leave `simple`. Phase 1's gain comes with it, and its 4 % does not. | 2, 4 | about −0.3 s (phase 1 gave −0.2 to −0.3 s with the width and offset only); −1.0 to −1.5 MB (9 keys fewer on 87k pieces) |
| 2 | Keys from the style: the keep rule is the style's reads at each zoom, plus the page's declared keys (temporary). Base-map layers the same (`ov4` keeps `height`, `base`). | 2, 9 | about −0.3 MB |
| 3 | The row as the MVT id on `simple` and `slots`; `r` and `["id"]` for the sort key; `__rs_s` goes (`promoteId` stays until step 5). | 3, 4 | about −0.13 MB and −49k values (tile_contract.md, section 2: `__rs_s` out, the id and `r` in) |
| 4 | The data layer API in roadstyle-wasm and Python; one `LiveMap`; the eager path goes. | | none on the tiles |
| 5 | The dashboard on the data layer (`filter.js`, `select.js`, `core.js`, `arrows.js`, `live.js`); `promoteId` and the page's keys leave the tiles; `reads.json` `pieces` empty. Rules 2 and 3 reach 0 and the test asserts them. | 2, 3 | about −0.7 MB (`__rs_edge` 0.40, `__rs_edge2` 0.20, `__rs_cls`, `lvl`, `__rs_access`); the filters: one `match` |
| 6 | `export_style` without `roads` (D5). | 1, 2, 10 | full look: the largest tile from 1.5 MB (Monaco z12) to the page's 0.15 MB |
| 7 | The low-zoom casing (D1), the pixel tolerance (D2), one casing for two equal halves (D3), the class minzooms (D4), each with a picture test | 6, 7 | D1 + D3: about −30k features; −0.1 to −0.2 s |
| 8 | The page PR in duckosm-rust (below) | | |

## 4. The targets

Measured now (rust-engine `7dbf59d`; Burnaby with the `ctl.py` harness, headless Chromium, median of 5): 1.36 to 1.45 s, 5.29 MB,
115k features. With phase 1: 1.15 s, 5.49 MB. The floor, with no road layer: 0.57 to 0.66 s. The targets after step 7 are estimates from
these measurements; each step measures its own number.

| Number | Now | Target |
|---|---|---|
| Burnaby tilted view, ms to idle | 1.36 to 1.45 s | ≤ 0.9 s |
| Burnaby tilted view, bytes | 5.29 MB | ≤ 3.2 MB |
| Burnaby tilted view, features | 115k | ≤ 115k without D1/D3, ≤ 85k with them |
| Keys on a `simple` piece | 18 | 4 (id not counted) |
| `simple`, largest tile, bytes (Monaco z15 / Tartu z13) | 333,935 / 280,126 | −40 % or more |
| `simple`, largest tile, values (Monaco z15) | 8,806 | ≤ 1,000 |
| `roads-simple` `line-width` (characters) | 25,796 | ≤ 4,096 |
| Style expressions, total (the page's look) | 38,936 | ≤ 15,000 |
| Rule numbers `keys_unread`, `no_id`, `strings` of `simple` | 3, all, 19 to 33 | 0, 0, 0 |
| Full look, largest tile (Monaco z12 / Tartu z12) | 1.5 MB / 4.0 MB | the page's look (0.15 / 0.24 MB) |

## 5. What the page must change (one PR at the end)

In duckosm-rust, after step 7: the new wasm package and the new copy of the dashboard; `map_worker.js` makes one `LiveMap` and answers
`fields`, `select`, `rowsOf` and `features` by message, not one road table in JSON; `keep` goes; the editor's `addSource` has no
`promoteId`. The e2e tests (`e2e.py`, `editor_e2e.py`, `phone_e2e.py`) must pass, with a check of the phone layout. Until this PR,
the page uses the last package and does not change.

## 6. Risks

- **The `d` table and the editor.** If a relevel makes a value that the table has not, the style changes and the map lays out again.
  The table holds every cap, seam and lap value of the area's classes (a test makes all of them).
- **MapLibre.** The same MVT id on many features (now true with `promoteId`: low risk); `["id"]` in `line-sort-key` and the arithmetic
  on `d` (a test in the browser harness in step 1 and step 3).
- **A large `match`** of 150k ids at a filter change: the smaller of the shown and the hidden set; a change of a switch only.
- **Two engines.** Without D0, each step is also a Python port (phase 1 had to do `_width_keys` in Python).
- **Burnaby is not in CI.** The local gate and the `ctl.py` harness are the proof of the time; CI has Monaco and Tartu.
- **The pixels.** Steps 1 to 6 must give the same picture. A step that changes a pixel stops and goes to a decision.

## Decisions for Kaveh

| | Decision | Changes the map? | Recommendation |
|---|---|---|---|
| D0 | The Python engine's road style and tiles stop; the Python binding gives the Rust output (the default engine becomes `rust`) | no | yes, before step 1 |
| D1 | Below zoom 14, one casing piece for each road (no heads, seams or laps). A head is 5 m: 0.4 px at z12 and 0.8 px at z13 (Burnaby's latitude) | yes, under 1 px | yes, with the picture test at z12 and z13 |
| D2 | Simplify to 0.25 px (2 units), not 1/16 px | yes, under 1 px | no for now: 1 px gave only 1 to 2 % on Burnaby |
| D3 | One casing for the two halves of a two-way road when they are equal (option B, about −18k features) | antialias only | yes, with the picture test |
| D4 | Class minzooms for `steps`, `corridor`, `platform`, `bridleway` and `construction`, as a standard map (OSM Carto, OpenMapTiles: steps z15, platform z16, corridor z17; the other two from the same maps in step 7). Now they show from z0. | yes | yes |
| D5 | `export_style` for a server: no `roads` layer; the popup reads a props file by id | no picture change; a server app needs the props file | yes |
| D6 | Only the active colour option in the tiles; another option comes as feature-state from the worker when the person selects it | no; a switch sets the state of each road (an estimate: 0.1 to 0.3 s on Burnaby) | yes |
| D7 | Rule 8 (a coarser grid at low zooms) | yes, under 1 px | no: geometry is 11 to 18 % of the bytes |
