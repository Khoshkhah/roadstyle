# Tiles v2: the review and the plan

Status: draft, 2026-10-27 (the web research is not in it yet). No code. Branch `design-tile-v2`, from `rust-engine` at `7dbf59d` (phase 0, the tile size
standard, is in). It includes phase 1 (`design-tile-wk`, `ad2d1ea`, not landed). An independent review (`.claude/tile-lag/plan-review.md`)
is applied in section 9.

The aim: the data apart from the tiles, and tiles that are as small as the measurements show is worth it. **A step is in this plan only if
a measurement shows a real gain** (time on the Burnaby tilted view, or a clear size), or if the data contract needs it. The other ideas
are in section 8, one line each.

Measurements: Burnaby, the tilted view (pitch 60, z14), the `ctl.py` harness (headless Chromium, software GL, median of 5, with a 200 ms
start wait). Files: `.claude/tile-lag/` of the workspace (`expr/` has the probes of this plan), [tile_speed.md](tile_speed.md),
[tile_contract.md](tile_contract.md).

## 1. The problem and the measured root

The page's tilted view of Burnaby takes 2.15 s from the jump to an idle map. `tile()` in the worker is 0.35 s of it; MapLibre's parse
and layout of the 30 tiles (5.9 MB, 115k features) is 1.41 s. In the control harness (the same tiles as static files) the view takes
1.42 to 1.53 s, and 0.57 to 0.66 s with no road layer. The root is the one road layer:

| Probe (the road layer only changes) | ms to idle |
|---|---|
| now | 1,534 |
| width and offset as one table lookup for each zoom stop (phase 1) | 1,196 |
| all paint and layout values constant (the floor) | 870 |
| no road layer | 568 |

Phase 1 takes 0.34 s of the 0.66 s that the road layer's expressions cost. No other form of the expressions took more (section 8).

## 2. What the review of the code found

1. **The engine** (`simple.rs`) cuts each road into pieces and gives each piece a property map: the road's columns and up to 20 marks.
2. **The style builder** (`layers.rs`) writes the look as expressions that read these marks. Phase 1 compiles the width and the offset
   into tables after the builder wrote them (`width_key::compact`), with a fallback when the shape is not known, and keeps three flags in
   the tiles for the editor's compare (the tiles are 4 % larger).
3. **The tiles** (`roadstyle-tiles`) keep every `__rs_*` mark and the page's keys, not only the keys that the style reads. The pieces have
   no MVT id: `promoteId` reads `__rs_edge`. The encoder itself (interning, trees, cache, clip) is good.
4. **The page** reads tile properties in `filter.js`, `select.js`, `core.js` and `arrows.js`. The popup, the panel and the live colours
   already use the road table (`RoadTable`, on the main thread) and the feature-state by row.
5. **Python** has its own engine (still the default, `engine="python"`). Phase 1 had to be written two times.

## 3. The design

- **The width and the offset** are phase 1's tables (`__rs_wk`), written by the builder with no fallback: a look that the tables cannot
  hold is an error in a test, not a second path.
- **A piece in a tile** has the road's row as its MVT id, and only the keys that the style reads at that zoom. After phase 1 the style
  no longer reads `__rs_pair` and `__rs_twoway`, so they leave; `__rs_s` becomes the small rank `r`.
- **The sort key** is `["+", ["get", "r"], ["case", ["in", ["id"], ["global-state", "rs_top"]], R, 0]]` (R: the number of ranks; the
  raise of the top roads of `rsColor`). The encoder writes a tile's features in the order (rank, row), so two pieces with the same key
  keep one order, also after a relevel.
- **The data stays on the main thread** in `RoadTable`, by row (as now). The dashboard filters compute the rows that show from it and
  set one `match` on `["id"]`; after a relevel they compute it again. The popup and the panel read `RoadTable`. Live colour, width and
  the glow stay feature-state by row.

| Remove | Rewrite | Keep |
|---|---|---|
| `width_key`'s fallback | the keep rule: the keys that the style reads at each zoom (`TileOptions::rule`) | phase 1's tables and their unit test |
| `promoteId`; `__rs_edge`, `__rs_edge2`, `__rs_s`, `__rs_pair`, `__rs_twoway`, `__rs_cls`, `lvl`, `__rs_access` in `simple` tiles | the sort key (`r`, the tile order); the dashboard's reads (`f.id`, the rows from `RoadTable`) | the encoder, the tile cache, `ZoomRules`, clip, buffers, PMTiles |
| `osm_id`, `kind`, `name` in `ov4` tiles (the style reads only `height`, `base`) | `export_style`: a props file by row (D5) | `RoadTable` on the main thread, the feature-state |
| `roads`, `roads-fill`, `roads-highlight` of the full look (D5) | | the budget test and the ratchet |

## 4. The order of work

Each step is one commit that passes CI, lowers the budget (`scripts/tile_budget.py`) and needs no raise. The picture stays the same: the
Monaco and Tartu goldens, and the Burnaby tilted view in the harness (0 pixels differ).

| Step | roadstyle commit | Measured basis | Tests |
|---|---|---|---|
| 0 | D0: the Python engine's road style and tiles stop; the binding gives the Rust output. | phase 1 was two ports | the suite with `ROADSTYLE_ENGINE=rust` |
| 1 | Phase 1 lands (`design-tile-wk`); its fallback goes. | −0.34 s (1,534 to 1,196 ms) | `width_key` unit test, goldens, harness |
| 2 | The keep rule is the style's reads, plus the page's declared keys until step 4. `__rs_pair`, `__rs_twoway` and `ov4`'s popup keys leave. | `ov4` −0.3 MB (measured); `__rs_pair` (on 18k casing halves) and `__rs_twoway` not measured alone. Phase 1's +4 % is its own key, `__rs_wk`, and stays. | budget rule 2, contract test |
| 3 | The row as the MVT id on `simple` and `slots`; the dashboard and the editor read `f.id`; `promoteId` goes; `__rs_edge` and `__rs_s` leave; `r` and the new sort key. | −0.53 MB and −74k distinct values (tile_contract.md, section 2) | budget rule 3, glow and live-colour e2e, editor e2e |
| 4 | The dashboard filters from `RoadTable` (`match` on `["id"]`, again after a relevel); `__rs_edge2`, `__rs_cls`, `lvl`, `__rs_access` leave; `reads.json` `pieces` keeps only `__rs_pick` (items). | −0.2 MB for `__rs_edge2` and more for the other three; a `match` of 152k ids adds 0.1 s to a filter change (1,592 against 1,496 ms) | filter e2e, budget rule 2 at 0 |
| 5 | `export_style` without `roads` (D5). | the full look's largest tile: 1.5 MB to 0.15 MB (Monaco z12) | budget of `monaco-full`, `tartu-full` |
| 6 | The page PR in duckosm-rust (section 6). | | duckosm-rust e2e |

## 5. The targets

| Number | Now | After step 5 |
|---|---|---|
| Burnaby tilted view, ms to idle (harness) | 1,534 | ≤ 1,200 (step 1; the bytes give little time) |
| Burnaby tilted view, bytes | 5.29 MB | ≤ 4.2 MB (steps 2 to 4) |
| `keys_unread`, `no_id` of `simple` | 3, all | 0, 0 |
| `simple`, largest tile, values (Monaco z15) | 8,806 | ≤ 2,000 (`__rs_s` out) |
| Full look, largest tile (Monaco z12 / Tartu z12) | 1.5 MB / 4.0 MB | 0.15 MB / 0.24 MB |

A step that does not give its gain is not merged.

## 6. What the page must change (one PR at the end)

In duckosm-rust, in one PR: the new wasm package, the new copy of the dashboard and `level_editor.js` (its `addSource` without
`promoteId`) together. If `promoteId` stays while `__rs_edge` is gone, no road has an id. The dashboard checks the style's `contract: 2`
and gives an error for another one, so that a cached old page does not draw new tiles. The e2e tests (`e2e.py`, `editor_e2e.py`,
`phone_e2e.py`) must pass, with a check of the phone layout.

## 7. Future needs, checked

**A planet service: an ID and a live colour for each road.** The tile schema of a piece is the same in the page's live tiles, an xyz
folder and a PMTiles archive. A planet archive is built one time; the live part is only feature-state. `Tiles` holds an area in memory;
a planet build is a second driver over the same per-piece function (regions in parallel, written by tile). The row is valid in one
generation (one build of the road set): the generation is in the tile URL and the metadata, and the archive and the live feed change
together. duckOSM's `edge_id` is the stable public ID; the server keeps the map from `edge_id` to the row (a planet's map is too large for
a client). The live service gives (generation, row, value) for the rows in a view, and the page sets `rs_c` and `rs_w`: no tile is made
again. Before the first planet build, count the planet's directed edges against 2^32 (D9).

**Live changes with no new tiles.** Colour, width, hover and selection are feature-state by row. A filter is one `match` on `["id"]`. A
relevel changes only the pieces of the changed roads and their ring (`replace_lines`); the rows stay, and the filters are computed again.
A new road set is a new generation: a new tile prefix, and the page clears its state.

**All consumers on one contract.** The page and the editor (the wasm tiles), Python (the binding, D0), the static export (PMTiles or xyz,
with a props file, D5) and roadstyle's HTML pages (inline GeoJSON: the same feature schema; the GeoJSON `id` is the row).

**Against established practice.**

| Practice | We follow | We differ, and why |
|---|---|---|
| The MVT spec 2.1 | extent 4096, zigzag deltas, one key and value table for each layer | the spec says an id SHOULD be unique in a layer. All pieces of a road share its row, so that one feature-state paints the road; MapLibre accepts it (as with `promoteId` now). |
| MapLibre's performance guidance | one road layer, feature-state for frequent changes, no feature where no layer draws it | none |
| Tippecanoe | simplification at the tile's resolution; 500 KB as a warning sign | no drop of features by density or by a size limit: it changes what the map shows. The style decides what is drawn. |
| Planetiler and OpenMapTiles | a minzoom for each class, few attributes | no line merge at low zooms: no measured gain (section 8). |

**Fixed and versioned.** The fixed part is the contract; a change to it is contract 3, with a migration: a piece has its row as the MVT
id and only the keys that its style reads; the layout of the style keys (`__rs_wk` = a fixed mode of the kind and the flags × the
versioned class list, `__rs_k`, `r`); the feature-state names (`rs_c`, `rs_w`, `hover`, `select`); the source name `roads`; 512 px
tiles. The versioned part comes from the look: the value tables, the zoom spans, the palettes and the base-map layers. So a second theme
with the same class list uses the same archive. The style's `roadstyle:tiles` and the PMTiles metadata get `contract: 2`, a hash of the
key layout and the generation.

## 8. Not done, and why

- **One draw key `d` for all style inputs, and colour, opacity, dash, cap and filter as tables** (the plan of `af22436`): measured, no
  gain over phase 1 (as parts of `d`: 1,221 ms; as a dense index of 600 rows: 1,204 ms; phase 1: 1,196 ms).
- **The rest of the road layer's cost** (1,196 against the floor of 870 ms): no table form reduces it; it is the data-driven paint
  itself.
- **The data in a worker** (`fields`, `select`, `rowsOf` by message): no measurement shows a need; `RoadTable` on the main thread works.
- **A coarser simplification**: 1 px gave 6.47 to 6.42 MB on Burnaby (about 1 %) and no time.
- **One casing per road at low zooms; one casing for two equal halves**: not measured.
- **Class minzooms for steps, corridor, platform, bridleway and construction**: −3 % features at z12, −1.6 % at z14; it changes the map.
- **A coarser grid at low zooms**: geometry is 11 to 18 % of the bytes.
- **Colours as palette indexes**: the text values of `simple` are 200 to 300 bytes in a tile.
- **A line merge at low zooms**: the pieces of a road differ in their keys, so few pieces merge.

## 9. The review

The independent review (`.claude/tile-lag/plan-review.md`), finding by finding:

1. Step 1 not measured: **accepted**. The probes are in section 1 and 8; step 1 is now phase 1 with no fallback.
2. An archive tied to one look: **accepted**. The key layout is fixed (section 7); only the value tables come from the look.
3. An id list wrong after a relevel: **accepted**. The filters are computed again after each relevel; a filter on tile keys needs the keys
   that step 4 removes.
4. A large `match` not measured: **measured**. 152k ids add 0.1 s to a filter change; the layout again of the loaded tiles is the cost, as
   now.
5. The road table to a worker not measured: **accepted**. `RoadTable` stays on the main thread.
6. `r` and the sort key can go: **in part**. `__rs_s` goes; `r` stays, because the raise of the top roads needs a sort key.
7. Step 4 too large: **accepted**. It is steps 3 and 4.
8. Parts not defined: **accepted**. No palette index (the colour keys stay as now); items keep `__rs_pick`; decks and shadows are inline
   GeoJSON, not tiles, and do not change; the contract test checks every zoom up to 24 for the tiles of the last zoom.
9. Planet ids: **accepted** (section 7, D9).
10. The order and the page's safety: **accepted** (section 6, D0).

## Decisions for Kaveh

| | Decision | Changes the map? | Recommendation |
|---|---|---|---|
| D0 | The Python engine's road style and tiles stop; the binding gives the Rust output (the P7 switch: the default engine becomes `rust`). SonoFlow's `viz/daily.py` uses `simple=False`: its `rs.setData` path must ship first. | no | yes, before step 2 (step 1 already has its Python port) |
| D5 | `export_style` for a server: no `roads` layer; the popup reads a props file by row. The same SonoFlow condition. | no picture change; a server app needs the props file | yes |
| D9 | For more than one road table (a planet): the id as a dense global row (an offset for each table) under 2^32, not `table << 32 \| row` (5 to 8 bytes for each id) | no | yes, before the first planet build; one table gives the same ids |
