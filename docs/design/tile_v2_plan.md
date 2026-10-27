# Tiles v2: the review and the plan

Status: plan, 2026-10-27, for Kaveh's OK. No code. Branch `design-tile-v2`, from `rust-engine` at `7dbf59d` (phase 0, the tile size
standard, is in). It includes phase 1 (`design-tile-wk`, `ad2d1ea`, not landed).

The aim: the data layer fully apart from the tiles, and tiles that are as small as the measurements show is worth it. **A step is in this
plan only if a measurement shows a real gain** (time on the Burnaby tilted view, or a clear size), or if the data-layer contract needs
it. The other ideas are in section 8, one line each.

Measurements: Burnaby, the tilted view (pitch 60, z14), `ctl.py` harness (headless Chromium, median of 5). Before phase 1: 1.36 to
1.45 s, 5.29 MB, 115k features. With phase 1: 1.15 s, 5.49 MB. With no road layer: 0.57 to 0.66 s. Files: `.claude/tile-lag/` of the
workspace, [tile_speed.md](tile_speed.md), [tile_contract.md](tile_contract.md).

## 1. What the review found

1. **The engine** (`simple.rs`) cuts each road into pieces and gives each piece a property map: the road's columns and up to 20 marks
   (`__rs_*`).
2. **The style builder** (`layers.rs`, `road_layers`) writes the look as expressions that read these marks: a `case` tree on the kind
   and the flags, with class tables, at each zoom stop. MapLibre calculates it for each feature: 0.65 s of 1.42 s (`expr/`).
3. **Phase 1** compiles the width and the offset into tables *after* the builder wrote them (`width_key::compact`), with a fallback when
   the shape is not known. It keeps three flags in the tiles for the editor's compare, so the tiles are 4 % larger. That is a second
   path beside the first.
4. **The tiles** (`roadstyle-tiles`) keep every `__rs_*` mark and the page's keys. The pieces have no MVT id: `promoteId` reads
   `__rs_edge`. The encoder itself (interning, trees, cache, clip) is good.
5. **The API.** The page and the editor call `tileSources` (eager). `LiveMap` (lazy, with `relevel`) is used only by the benches.
6. **The page** reads tile properties in `filter.js`, `select.js`, `core.js` and `arrows.js`. The popup, the panel and the live colours
   already use the road table and the feature-state by row.
7. **Python** has its own engine (still the default, `engine="python"`) with its own style and tiles. Phase 1 had to be written two times.

## 2. The design

**A piece in a tile has four items:**

| Item | What |
|---|---|
| MVT id | the road's row |
| `d` | the draw key: one small integer for all that the style needs of the piece with few values (kind, class index, pair, twoway, bridge and tunnel flags, cap, dash, seam, lap). A mixed-radix number whose radixes come from the look, not from the data. |
| `r` | the sort rank (2 × position + the kind's step), about 100 values |
| `f` | the colour index into the active option's palette (fill and casing) |

A look in metres also keeps the piece's metre width; an item keeps its own colour, width and minzoom. Nothing else goes into the tile.

**The style reads only these, as tables by `d`, written from the look directly:**

- `line-width` = a class curve plus a mode term, two small tables for each zoom stop (about 80 numbers), times the live width factor.
  `line-offset`, `line-opacity`, `line-dasharray`, `line-cap` and the casing colour are one table by `d` each. The parts of `d` come out
  with `%` and `/`.
- The filter: `["at", d, minzoom table]` and `["at", d, maxzoom table]`. The tiles apply the same tables (rule 1, `ZoomRules`).
- `line-sort-key` = `["get", "r"]`. MapLibre keeps the tile's order for equal keys, so the encoder writes a tile's features in the order
  (r, row). A redrawn road keeps its place, and no id is in the key.
- The fill = `["coalesce", ["feature-state", "rs_c"], ["at", ["get", "f"], palette]]`, with the glow as now.

A unit test checks that the tables give the numbers of the old expressions for every kind, flag, class and stop (phase 1's check, as a
test, not a fallback). `d` is a fixed function of the look, so the same look gives the same `d` in every area and after every relevel: a
relevel never changes the style.

**The data layer.** All other data of a road is in the worker, by row ([tile_contract.md](tile_contract.md), section 4: `generation`,
`edgeIds`, `rowsOf`, `fields`, `columns`, `select`, `features`). The dashboard filters ask `select` and set one `match` on `["id"]`. The
popup and the panel ask `fields`. The live colours and the glow stay feature-state by row.

**One tile path.** One `LiveMap`: the pieces wait for their properties until a tile shows them, for the page and for the editor. The
editor's `relevel` compares pieces by `d`, `r` and the line, not by their property maps.

| Remove | Rewrite | Keep |
|---|---|---|
| `width_key.rs` and its fallback; the `case` trees of the road layer | the pieces' properties (`d`, `r`, `f`); the road layer as tables | the encoder, the tile cache, clip, buffers, PMTiles |
| `promoteId`; `__rs_edge`, `__rs_edge2`, `__rs_s` and 13 other marks in `simple` tiles | the keep rule: the keys that the style reads | `ZoomRules::span`, with `at`, `%` and `/` in `roadstyle_model::eval` |
| the eager `tileSources` path for `simple` | one `LiveMap` with the data layer | the relevel ring, `style_changed` |
| `reads.json` `pieces`; the dashboard's reads of tile properties | the dashboard on `f.id`, `select`, `fields` | the feature-state of colour, width and glow |
| `roads`, `roads-fill`, `roads-highlight` of the full look (D5) | `export_style`: a props file by row (D5) | the budget test and the ratchet |

## 3. The order of work

Each step is one commit that passes CI, lowers the budget (`scripts/tile_budget.py`) and needs no raise. The picture stays the same:
the Monaco and Tartu goldens, and the Burnaby tilted view in the harness (0 pixels differ).

| Step | roadstyle commit | The measured basis |
|---|---|---|
| 0 | D0: the Python engine's road style and tiles stop; the binding gives the Rust output. | phase 1 was two ports |
| 1 | `d`, `f` and the tables; `width_key.rs` goes; the style-only marks leave `simple` (phase 1 folds in here, without its 4 %). | width and offset as tables: −0.2 to −0.3 s (phase 1); colour and opacity constant: −0.08 and −0.06 s (`expr/`, an upper limit) |
| 2 | Keys from the style: the keep rule is the style's reads, plus the page's declared keys until step 4. Base-map layers the same (`ov4` keeps `height` and `base`). | `ov4`'s `osm_id`, `kind`, `name`: 0.3 MB |
| 3 | The data layer API (roadstyle-wasm and Python); one `LiveMap`. No tile change. | the contract needs it |
| 4 | The row as the MVT id; `r` for the sort; the dashboard on the data layer; `promoteId`, `__rs_edge`, `__rs_edge2`, `__rs_s`, `__rs_cls`, `lvl`, `__rs_access` out; `reads.json` `pieces` empty. Rules 2 and 3 reach 0 and the test asserts them. | −0.73 MB and −85k distinct values (tile_contract.md, section 2) |
| 5 | `export_style` without `roads` (D5). | the full look's largest tile: 1.5 MB to 0.15 MB (Monaco z12) |
| 6 | The page PR in duckosm-rust (section 5). | |

## 4. The targets

| Number | Now (before phase 1) | Target after step 5 |
|---|---|---|
| Burnaby tilted view, ms to idle | 1.36 to 1.45 s | ≤ 1.05 s (phase 1, then colour and opacity; the bytes give little time) |
| Burnaby tilted view, bytes | 5.29 MB | ≤ 3.3 MB (an estimate: 9 keys fewer on 87k pieces, and steps 2 and 4) |
| Keys on a `simple` piece | 18 | 3 or 4 (the id not counted) |
| `simple`, largest tile, values (Monaco z15) | 8,806 | ≤ 1,000 |
| `roads-simple` `line-width` (characters) | 25,796 | ≤ 4,096 |
| Style expressions, total (the page's look) | 38,936 | ≤ 15,000 |
| `keys_unread`, `no_id`, `strings` of `simple` | 3, all, 19 to 33 | 0, 0, 0 |

Each step measures its own numbers in the harness and in the budget. A step that does not give its gain is not merged.

## 5. What the page must change (one PR at the end)

In duckosm-rust: the new wasm package and the new copy of the dashboard; `map_worker.js` makes one `LiveMap` and answers `fields`,
`select`, `rowsOf` and `features` by message, not one road table in JSON; `keep` goes; the editor's `addSource` has no `promoteId`. The
e2e tests (`e2e.py`, `editor_e2e.py`, `phone_e2e.py`) must pass, with a check of the phone layout. Until this PR the page uses the last
package and does not change.

## 6. Risks

- **MapLibre.** The same MVT id on many features (true now with `promoteId`: low risk); the arithmetic on `d` and the tile order for
  equal sort keys (a browser test in steps 1 and 4).
- **A large `match`** of 150k ids at a filter change: the page sends the smaller of the shown and the hidden set; only a switch does it.
- **Two engines.** Without D0, each step is also a Python port.
- **Burnaby is not in CI.** The local gate and the harness prove the time; CI has Monaco and Tartu.
- **The pixels.** A step that changes a pixel stops and goes to Kaveh.

## 7. Future needs, checked

**A planet service: an ID and a live colour for each road.** The tile schema of a piece (id, `d`, `r`, `f`) is the same in the page's
live tiles, an xyz folder and a PMTiles archive. A planet archive is built one time; the live part is only feature-state. `Tiles` holds
an area in memory (a city or a county). A planet build is a second driver over the same per-piece function (regions in parallel,
written by tile, as Planetiler does); this works because `d`, `r` and `f` depend only on the look and the road. The row is valid in one
generation (one build of the road set); duckOSM's `edge_id` is the stable public ID, and an archive has the id map as a side file. For
the live colour, the client knows the rows in its view from the tiles, gets (row, value) for them, and sets `rs_c` and `rs_w`: no tile
is made again.

**Live changes with no new tiles.** Colour, width, hover and selection are feature-state by row. A filter is one `match` on `["id"]`.
A relevel changes only the pieces of the changed roads and their ring (`replace_lines`); the rows stay, so the state and the filters stay
correct. A new road set is a new generation: a new tile prefix, and the page clears its state and asks `rowsOf` again.

**All consumers on one contract.** The page and the editor (`LiveMap`), Python (the binding, D0), the static export (PMTiles or xyz,
with a props file, D5), and roadstyle's HTML pages (inline GeoJSON: the same feature schema, the GeoJSON `id` is the row).

**Against established practice.**

| Practice | We follow | We differ, and why |
|---|---|---|
| The MVT spec 2.1 | extent 4096, zigzag deltas, one key and value table for each layer | the spec says an id SHOULD be unique in a layer. All pieces of a road share its row, so that one feature-state paints the road; MapLibre accepts it (as with `promoteId` now). |
| MapLibre's performance guidance | one road layer, simple expressions (tables), feature-state for frequent changes, no feature where no layer draws it | none |
| Tippecanoe | simplification at the tile's resolution; 500 KB as a warning sign | no drop of features by density or by a size limit: it changes what the map shows. The style decides what is drawn. |
| Planetiler and OpenMapTiles | a minzoom for each class, few attributes | OpenMapTiles keeps text classes because its schema serves many styles. Our tiles serve the one style that comes with them, so a number is enough, and the text is in the data layer. No line merge at low zooms: no measured gain for us (section 8). |

**Fixed and versioned.** The fixed part is the contract; a change to it is contract 3, with a migration: a piece has its row as the MVT
id and only the keys that its style reads; the meaning of `r`, `f` and `d`; the data layer (rows by generation, `edge_id` as the public
ID, the calls); the feature-state names (`rs_c`, `rs_w`, `hover`, `select`); the source name `roads`; 512 px tiles. The versioned part
can change with no break, because the style and the tiles always come together: the radixes and tables of `d`, the zoom spans, the
palettes, the base-map layers, and the builder. The style's `roadstyle:tiles` and the PMTiles metadata get `contract: 2`, the look's
hash and the generation. A page that gets another contract gives an error.

## 8. Not done, and why

- **A coarser simplification** (rule 6): 1 px gave 6.47 to 6.42 MB on Burnaby (about 1 %) and no time; the engine keeps its tolerance.
- **One casing per road at low zooms** (rule 7): no measurement of this change; one feature per road gave −0.15 to −0.2 s but lost the
  look of the levels. Measure it before a plan.
- **One casing for two equal halves** (option B, about −18k features): no measurement of the time.
- **Class minzooms for steps, corridor, platform, bridleway and construction**: −3 % features at z12, −1.6 % at z14; it changes the map.
- **A coarser grid at low zooms** (rule 8): geometry is 11 to 18 % of the bytes.
- **Only the active colour option in the tiles**: no area with more than one option was measured.
- **A ramp colour as a palette index**: no measurement; it changes colours by up to 1/256 of the ramp.
- **A line merge at low zooms** (as OpenMapTiles): the pieces of a road differ in `d`, so few would merge.

## Decisions for Kaveh

| | Decision | Changes the map? | Recommendation |
|---|---|---|---|
| D0 | The Python engine's road style and tiles stop; the Python binding gives the Rust output (the default engine becomes `rust`) | no | yes, before step 1 |
| D5 | `export_style` for a server: no `roads` layer; the popup reads a props file by row | no picture change; a server app needs the props file | yes |
| D9 | For more than one road table (a planet): the id as a dense global row (an offset for each table) under 2^32, not `table << 32 \| row` (5 to 8 bytes for each id) | no | yes, before the first planet build; one table gives the same ids |
