# Tiles v2: the review and the plan

Status: plan, 2026-10-27, for Kaveh's OK. No code. Branch `design-tile-v2`, from `rust-engine` at `7dbf59d` (phase 0, the tile size
standard, is in). It includes phase 1 (`design-tile-wk`, `ad2d1ea`, not landed). An independent review (`.claude/tile-lag/plan-review.md`)
and a web research (`.claude/tile-lag/research.md`) are applied (sections 9 and 10). The same plan with diagrams: `tile_v2_plan.html`.

The aim: the data apart from the tiles, and a fast map. **A step is in this plan only if a measurement shows a real gain** (time on the
Burnaby tilted view, or a clear size), or if the data contract needs it. The other ideas are in section 8, one line each.

Measurements: Burnaby, the tilted view (pitch 60, z14), the `ctl.py` harness: the page's tiles as static files, MapLibre 5.24.0 (the
page's version), headless Chromium with software GL, the median of 5, each run on a new page, with a 200 ms start wait in each time.
The numbers of one table come from one batch; two batches differ by up to 0.15 s. Files: `.claude/tile-lag/` of the workspace (`expr/`
has the probes of this plan), [tile_speed.md](tile_speed.md), [tile_contract.md](tile_contract.md).

## 1. The problem and the measured root

The page's tilted view of Burnaby takes 2.15 s from the jump to an idle map: 0.10 s to the first tile request, 0.35 s for `tile()` in the
page's worker, 0.05 s to move the bytes, 1.41 s for MapLibre's parse and layout of the 30 tiles (5.9 MB, 115k features), and 0.24 s to
draw. The MapLibre part is the root. Two causes, both measured:

| Probe | ms to idle |
|---|---|
| now (1 MapLibre worker, the default) | 1,343 to 1,534 |
| 4 MapLibre workers | 889 |
| width and offset as one table lookup for each zoom stop (phase 1) | 1,105 to 1,196 |
| phase 1 and 4 workers | 815 |
| all paint and layout values of the road layer constant (the floor of the expressions) | 870 |
| no road layer | 568 |

1. **MapLibre parses all the tiles on one worker.** In 5.24.0 the default worker count is 1 (`workerCount = isSafari ? min(cores, 3) :
   1`, in its source). 4 workers: −0.45 to −0.51 s. 6: 827 ms; 8: 894 ms.
2. **The road layer's expressions.** MapLibre calculates them for each feature. Phase 1 takes 0.3 s of it.

## 2. What the review of the code found

1. **The engine** (`simple.rs`) cuts each road into pieces and gives each piece a property map: the road's columns and up to 20 marks.
2. **The style builder** (`layers.rs`) writes the look as expressions that read these marks. Phase 1 compiles the width and the offset
   into tables after the builder wrote them (`width_key::compact`), with a fallback when the shape is not known, and keeps three flags in
   the tiles for the editor's compare.
3. **The tiles** (`roadstyle-tiles`) keep every `__rs_*` mark and the page's keys, not only the keys that the style reads. The pieces have
   no MVT id: `promoteId` reads `__rs_edge`. The encoder itself (interning, trees, cache, clip) is good.
4. **The page** reads tile properties in `filter.js`, `select.js`, `core.js` and `arrows.js`. The popup, the panel and the live colours
   already use the road table (`RoadTable`, on the main thread) and the feature-state by row.
5. **Python** has its own engine (still the default, `engine="python"`). Phase 1 had to be written two times.

## 3. The design

- **MapLibre gets 4 workers** (`maplibregl.setWorkerCount(Math.min(4, navigator.hardwareConcurrency || 1))` before the first map), in the duckosm-rust page and in roadstyle's pages.
- **The width and the offset** are phase 1's tables (`__rs_wk`), written by the builder with no fallback: a look that the tables cannot
  hold is an error in a test, not a second path.
- **A piece in a tile** has the road's row as its MVT id, and only the keys that the style reads at that zoom. After phase 1 the style
  no longer reads `__rs_pair` and `__rs_twoway`, so they leave; `__rs_s` becomes the small rank `r`.
- **The sort key** is `["+", ["get", "r"], ["case", ["in", ["id"], ["global-state", "rs_top"]], R, 0]]` (R: the number of ranks; the
  raise of the top roads of `rsColor`). The encoder writes a tile's features in the order (rank, row), so two pieces with the same key
  keep one order, also after a relevel.
- **The data stays on the main thread** in `RoadTable`, by row (as now). The dashboard filters compute the rows that show from it and set
  one `match` on `["id"]`; after a relevel they compute it again. The popup and the panel read `RoadTable`. Live colour, width and the
  glow stay feature-state by row (152k states: 0.68 s one time, and no stall after it; section 10).

| Remove | Rewrite | Keep |
|---|---|---|
| `width_key`'s fallback | the keep rule: the keys that the style reads at each zoom (`TileOptions::rule`) | phase 1's tables and their unit test |
| `promoteId`; `__rs_edge`, `__rs_edge2`, `__rs_s`, `__rs_pair`, `__rs_twoway`, `__rs_cls`, `lvl`, `__rs_access` in `simple` tiles | the sort key (`r`, the tile order); the dashboard's reads (`f.id`, the rows from `RoadTable`) | the encoder, the tile cache, `ZoomRules`, clip, buffers, PMTiles |
| `osm_id`, `kind`, `name` in `ov4` tiles (the style reads only `height`, `base`) | `export_style`: a props file by row (D5) | `RoadTable` on the main thread, the feature-state |
| `roads`, `roads-fill`, `roads-highlight` of the full look (D5) | the map's start: 4 workers | the budget test and the ratchet |

## 4. The order of work

Each step is one commit that passes CI and needs no raise. The picture stays the same: the Monaco and Tartu goldens, and the Burnaby
tilted view in the harness (0 pixels differ). Phase 1 adds one key to each piece (+4 % bytes), so it comes after the steps that remove
keys, and the ratchet (`scripts/tile_budget.py`) runs after step 6: the end is below today's limits on every number (the width text with D2).

| Step | Commit | Measured basis | Tests |
|---|---|---|---|
| 1 | 4 MapLibre workers: one line in duckosm-rust's page (a small PR of its own) and in roadstyle's page template. No tile change. | −0.45 to −0.51 s | the harness; the page's e2e and phone check |
| 2 | D0: the Python engine's road style and tiles stop; the binding gives the Rust output. | phase 1 was two ports | the suite with `ROADSTYLE_ENGINE=rust` |
| 3 | The keep rule is the style's reads, plus the page's declared keys until step 5. `ov4`'s popup keys leave. | `ov4` −0.3 MB | budget rule 2, contract test |
| 4 | The row as the MVT id on `simple` and `slots`; the dashboard and the editor read `f.id`; `promoteId` goes; `__rs_edge` and `__rs_s` leave; `r` and the new sort key. | −0.53 MB and −74k distinct values (tile_contract.md, section 2) | budget rule 3, glow and live-colour e2e, editor e2e |
| 5 | The dashboard filters from `RoadTable` (`match` on `["id"]`, again after a relevel); `__rs_edge2`, `__rs_cls`, `lvl`, `__rs_access` leave; `reads.json` `pieces` keeps only `__rs_pick` (items). | −0.2 MB for `__rs_edge2` and more for the other three; a `match` of 152k ids adds 0.1 s to a filter change (1,592 against 1,496 ms) | filter e2e, budget rule 2 at 0 |
| 6 | Phase 1 lands (`design-tile-wk`); its fallback goes; `__rs_pair` and `__rs_twoway` leave (the style no longer reads them). Then the ratchet runs. | −0.08 s with 4 workers (889 to 815 ms); −0.3 s with 1 | `width_key` unit test, goldens, harness |
| 7 | `export_style` without `roads` (D5). | the full look's largest tile: 1.5 MB to 0.15 MB (Monaco z12) | budget of `monaco-full`, `tartu-full` |
| 8 | The page PR in duckosm-rust (section 6). | | duckosm-rust e2e |

## 5. The targets

| Number | Now | After step 7 |
|---|---|---|
| Burnaby tilted view, ms to idle (harness) | 1,343 to 1,534 | ≤ 850 (steps 1 and 6: 815 measured) |
| Burnaby tilted view, bytes | 5.29 MB | ≤ 4.4 MB (steps 3 to 5, then +0.2 MB for phase 1's key) |
| `keys_unread`, `no_id` of `simple` | 3, all | 0, 0 |
| `simple`, largest tile, values (Monaco z15) | 8,806 | ≤ 2,000 (`__rs_s` out) |
| Full look, largest tile (Monaco z12 / Tartu z12) | 1.5 MB / 4.0 MB | 0.15 MB / 0.24 MB |

A step that does not give its gain is not merged.

## 6. What the page must change

Step 1 is a small PR of its own (4 workers). Then, after step 7, one PR: the new wasm package, the new copy of the dashboard and
`level_editor.js` (its `addSource` without `promoteId`) together. If `promoteId` stays while `__rs_edge` is gone, no road has an id. The
dashboard checks the style's `contract: 2` and gives an error for another one, so that a cached old page does not draw new tiles. The e2e
tests (`e2e.py`, `editor_e2e.py`, `phone_e2e.py`) must pass, with a check of the phone layout.

## 7. Future needs, checked

**A planet service: an ID and a live colour for each road.** The tile schema of a piece is the same in the page's live tiles, an xyz
folder and a PMTiles archive. A planet archive is built one time; the live part is only feature-state. `Tiles` holds an area in memory;
a planet build is a second driver over the same per-piece function (regions in parallel, written by tile). The row is valid in one
generation (one build of the road set): the generation is in the tile URL and the metadata, and the archive and the live feed change
together. duckOSM's `edge_id` is the stable public ID; the server keeps the map from `edge_id` to the row (a planet's map is too large for
a client). The live service gives (generation, row, value) for the rows in a view, and the page sets `rs_c` and `rs_w`: no tile is made
again. A view has tens of thousands of roads; 152k states took 0.68 s. Before the first planet build, count the planet's directed edges
against 2^32 (D9).

**Live changes with no new tiles.** Colour, width, hover and selection are feature-state by row. A filter is one `match` on `["id"]`. A
relevel changes only the pieces of the changed roads and their ring (`replace_lines`); the rows stay, and the filters are computed again.
A new road set is a new generation: a new tile prefix, and the page clears its state.

**All consumers on one contract.** The page and the editor (the wasm tiles), Python (the binding, D0), the static export (PMTiles or xyz,
with a props file, D5) and roadstyle's HTML pages (inline GeoJSON: the same feature schema; the GeoJSON `id` is the row).

**Fixed and versioned.** The fixed part is the contract; a change to it is contract 3, with a migration: a piece has its row as the MVT
id and only the keys that its style reads; the layout of the style keys (`__rs_wk` = a fixed mode of the kind and the flags × the
versioned class list, `__rs_k`, `r`); the feature-state names (`rs_c`, `rs_w`, `hover`, `select`); the source name `roads`; 512 px
tiles. The versioned part comes from the look: the value tables, the zoom spans, the palettes and the base-map layers. So a second theme
with the same class list uses the same archive. The style's `roadstyle:tiles` and the PMTiles metadata get `contract: 2`, a hash of the
key layout and the generation.

## 8. Not done, and why

- **One draw key `d` for all style inputs, and colour, opacity, dash, cap and filter as tables**: no gain over phase 1 (parts of `d`:
  1,221 ms; a dense index of 600 rows: 1,204 ms; phase 1: 1,196 ms).
- **A merge of the pieces of one road into one feature** (research rank 3): pieces with the same keys give 13 % fewer features (72,322 to
  62,745): −0.10 s with 1 worker, −0.02 s with 4 (noise). Pieces with another sort rank (31 %) cannot merge: the draw order changes.
- **`setSourceTileLodParams`** (research rank 4): (4, 3) and (2, 2) against the defaults (9.314, 3): the same 28 tiles, the same time.
- **Shared buckets** (research rank 5): the road layer is one bucket; the 12 visible layers on the source are 12 families (a fill and its
  outline have two types), so nothing joins.
- **No data-driven sort key**: −0.01 s; `r` stays for the raise of the top roads.
- **More than 4 workers**: 6 gave 827 ms and 8 gave 894 ms, against 889 ms for 4: no clear gain, and a phone has fewer cores.
- **The rest of the expressions' cost** (815 against the floor): no table form reduces it.
- **The data in a worker** (`fields`, `select`, `rowsOf` by message): no measurement shows a need.
- **A coarser simplification**: 1 px gave 6.47 to 6.42 MB on Burnaby (about 1 %) and no time.
- **One casing per road at low zooms; one casing for two equal halves**: not measured.
- **Class minzooms for steps, corridor, platform, bridleway and construction**: −3 % features at z12, −1.6 % at z14; it changes the map.
- **A coarser grid at low zooms**: geometry is 11 to 18 % of the bytes.
- **Colours as palette indexes**: the text values of `simple` are 200 to 300 bytes in a tile.

## 9. The review

The independent review (`.claude/tile-lag/plan-review.md`), finding by finding:

1. Step 1 not measured: **accepted**. The probes are in sections 1 and 8; the phase 1 step is phase 1 with no fallback.
2. An archive tied to one look: **accepted**. The key layout is fixed (section 7); only the value tables come from the look.
3. An id list wrong after a relevel: **accepted**. The filters are computed again after each relevel.
4. A large `match` not measured: **measured**. 152k ids add 0.1 s to a filter change; the layout again of the loaded tiles is the cost, as
   now.
5. The road table to a worker not measured: **accepted**. `RoadTable` stays on the main thread.
6. `r` and the sort key can go: **in part**. `__rs_s` goes; `r` stays, because the raise of the top roads needs a sort key.
7. The id step too large: **accepted**. It is steps 4 and 5.
8. Parts not defined: **accepted**. No palette index (the colour keys stay as now); items keep `__rs_pick`; decks and shadows are inline
   GeoJSON, not tiles, and do not change; the contract test checks every zoom up to 24 for the tiles of the last zoom.
9. Planet ids: **accepted** (section 7, D9).
10. The order and the page's safety: **accepted** (section 6, D0).

## 10. Against established practice (the research)

The research (`.claude/tile-lag/research.md`) ranks five changes. Each was measured here; the sources are at the end.

| Practice | Source | Here | Measured |
|---|---|---|---|
| More MapLibre workers (the default is 1) | [1], [2] | **follow**, step 1 | −0.45 to −0.51 s |
| A small width expression (a composite expression is calculated twice for each feature) | [3], [4] | **follow**, phase 1 | −0.24 to −0.34 s |
| One feature for each road and level (Planetiler's line merge, Tippecanoe's `--coalesce`) | [5], [6] | **differ** | −0.02 s with 4 workers |
| Fewer tiles at the horizon (`setSourceTileLodParams`), class minzooms | [7], [8] | **differ** | no change; −1.6 to −3 % features |
| Shared buckets, a constant sort key, features in draw order | [9], [10] | **follow in part**: features in (rank, row) order; the key stays | −0.01 s |
| Feature-state for live colour (the research warned of a stall at 20k keys, #6633, fixed in 2026) | [11], [12] | **follow** | 152k states: 0.68 s one time; no stall after |
| `match`, not `in`, for long lists (a hash, not a linear search) | [13] | **follow** | 152k ids: +0.1 s |
| The MVT spec: an id SHOULD be unique in a layer | [14] | **differ**: the pieces of a road share its row, so that one feature-state paints the road (MapLibre accepts it, as with `promoteId` now) | |
| Tippecanoe and Planetiler drop or coalesce features to a size limit (500 KB, 200,000 features) | [6], [15] | **differ**: the style decides what is drawn; no drop that changes the map | |
| Few attributes, each with a minzoom; booleans only when true | [8], [16] | **follow**: only the style's keys; a false flag is not written | |

Sources:

1. MapLibre `getWorkerCount`: https://maplibre.org/maplibre-gl-js/docs/API/functions/getWorkerCount/
2. MapLibre `worker_pool.ts` (and the 5.24.0 build): https://raw.githubusercontent.com/maplibre/maplibre-gl-js/main/src/util/worker_pool.ts
3. MapLibre `program_configuration.ts` (source and composite binders): https://raw.githubusercontent.com/maplibre/maplibre-gl-js/main/src/data/program_configuration.ts
4. MapLibre expressions: https://maplibre.org/maplibre-style-spec/expressions/
5. Planetiler `FeatureMerge.java`: https://raw.githubusercontent.com/onthegomap/planetiler/main/planetiler-core/src/main/java/com/onthegomap/planetiler/FeatureMerge.java
6. Tippecanoe README: https://raw.githubusercontent.com/felt/tippecanoe/main/README.md
7. MapLibre `setSourceTileLodParams`: https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/#setsourcetilelodparams
8. OpenMapTiles transportation in Planetiler: https://raw.githubusercontent.com/openmaptiles/planetiler-openmaptiles/main/src/main/java/org/openmaptiles/layers/Transportation.java
9. MapLibre `group_by_layout.ts`: https://raw.githubusercontent.com/maplibre/maplibre-style-spec/main/src/group_by_layout.ts
10. MapLibre `line_bucket.ts`: https://raw.githubusercontent.com/maplibre/maplibre-gl-js/main/src/data/bucket/line_bucket.ts
11. MapLibre issue 6633 (feature-state keys and zoom lag): https://github.com/maplibre/maplibre-gl-js/issues/6633
12. MapLibre PR 7550 (feature-state as an array): https://github.com/maplibre/maplibre-gl-js/pull/7550
13. The style spec's `match` and `in`: https://raw.githubusercontent.com/maplibre/maplibre-style-spec/main/src/expression/definitions/match.ts
14. The vector tile spec 2.1: https://raw.githubusercontent.com/mapbox/vector-tile-spec/master/2.1/README.md
15. Planetiler config (the tile size warning): https://raw.githubusercontent.com/onthegomap/planetiler/main/planetiler-core/src/main/java/com/onthegomap/planetiler/config/PlanetilerConfig.java
16. Shortbread schema: https://shortbread-tiles.org/schema/1.0/

## Decisions for Kaveh

| | Decision | Changes the map? | Recommendation |
|---|---|---|---|
| D1 | 4 MapLibre workers in duckosm-rust's page and roadstyle's pages, as a small PR now (before the rest) | no | yes |
| D0 | The Python engine's road style and tiles stop; the binding gives the Rust output (the P7 switch: the default engine becomes `rust`). SonoFlow's `viz/daily.py` uses `simple=False`: its `rs.setData` path must ship first. | no | yes, before step 3 |
| D2 | Phase 1's width and offset text: 44 KB and 19 KB, over today's limit of 25,796 characters. Write the tables as a class curve plus a mode term (about 4 KB; the same time in the probe: 1,221 against 1,196 ms) if the unit test shows the numbers exact, else raise the one limit with this reason. | no | the compact form if exact; else the raise |
| D5 | `export_style` for a server: no `roads` layer; the popup reads a props file by row. The same SonoFlow condition. | no picture change; a server app needs the props file | yes |
| D9 | For more than one road table (a planet): the id as a dense global row (an offset for each table) under 2^32, not `table << 32 \| row` (5 to 8 bytes for each id) | no | yes, before the first planet build; one table gives the same ids |
