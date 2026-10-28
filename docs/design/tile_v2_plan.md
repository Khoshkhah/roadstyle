# Tiles v2: the review and the plan

Status: **steps 0 to 7 are done** on branch `design-tile-steps` (from `rust-engine` at `6317dd7`, 2026-10-27; section 12 has the results). Step 8, the
page PR, waits. Decided by Kaveh, 2026-10-27: D0, D1, D5 and D9 yes; phase 1 and D2 out. The plan came from branch `design-tile-v2` (`rust-engine` at `7dbf59d`). Two reviews (`.claude/tile-lag/plan-review.md` and
`final-review-fable.md`) and a web research (`research.md`) are applied (sections 10 and 11). The same plan with diagrams:
`tile_v2_plan.html`.

The aim: the data apart from the tiles, a fast map, simple code. **A step is in this plan only if a measurement shows a real gain** (time on
the Burnaby tilted view above the batch noise of 0.15 s, or a clear size), or if the contract needs it. The other ideas are in section 9.

Measurements: Burnaby, the tilted view (pitch 60, z14), the `ctl.py` harness: the page's tiles as static files, MapLibre 5.24.0 (the
page's version), headless Chromium with software GL, the median of 5, each run on a new page, with a 200 ms start wait in each time.
Two batches differ by up to 0.15 s. Files: `.claude/tile-lag/` of the workspace (`expr/` has the probes), [tile_speed.md](tile_speed.md),
[tile_contract.md](tile_contract.md).

## 1. The problem and the measured root

The page's tilted view of Burnaby takes 2.15 s from the jump to an idle map: 0.10 s to the first tile request, 0.35 s for `tile()` in the
page's worker, 0.05 s to move the bytes, 1.41 s for MapLibre's parse and layout of the 30 tiles (5.9 MB, 115k features), and 0.24 s to
draw. The MapLibre part is the root.

| Probe | ms to idle |
|---|---|
| now (1 MapLibre worker, the default) | 1,343 to 1,534 |
| 4 MapLibre workers | 889 |
| phase 1 (width and offset as tables), 1 worker / 4 workers | 1,105 / 815 |
| all paint and layout values of the road layer constant | 870 |
| no road layer | 568 |

**MapLibre parses all the tiles on one worker.** In 5.24.0 the default worker count is 1 (`workerCount = isSafari ? min(cores, 3) : 1`,
in its source). 4 workers: −0.45 to −0.51 s. That is the one large gain. With 4 workers, phase 1 gives −0.07 s, inside the batch noise,
so it is not in the plan (section 9).

## 2. What the review of the code found

1. **The engine** (`simple.rs`) cuts each road into pieces and gives each piece a property map: the road's columns and up to 20 marks.
2. **The tiles** (`roadstyle-tiles`) keep every `__rs_*` mark and the page's keys, not only the keys that are read. The pieces have no MVT
   id: `promoteId` reads `__rs_edge`. The encoder itself (interning, trees, cache, clip) is good.
3. **The colours are text in each piece** (`__rs_fill`, `__rs_casing`, and one key for each colour option), so a tile set is tied to one
   palette.
4. **The page** reads tile properties in `filter.js`, `select.js`, `core.js` and `arrows.js`. The popup, the panel and the live colours
   already use the road table (`RoadTable`) and the feature-state by row.
5. **Python** has its own engine (still the default, `engine="python"`).

## 3. The design

- **MapLibre gets 4 workers**: `maplibregl.setWorkerCount(Math.min(4, navigator.hardwareConcurrency || 1))` before the first map.
- **A piece in a tile** has the road's row as its MVT id, and only the keys of the contract: the keys that the style reads, and the
  three keys of the dashboard's filters (`__rs_cls`, `lvl`, `__rs_access`). The set is one for each tile layer (all zooms); the
  feature spans stay for each zoom (phase 0).
- **The sort key keeps the row**: `["+", ["*", ["get", "r"], 4294967296], ["id"], ["case", ["in", ["id"], ["global-state", "rs_top"]],
  R, 0]]`. `r` is the small rank (2 × position + the kind's step); R lifts the top roads of `rsColor`. After a relevel the order is the
  same as on a new map. The row is under 2^32 (D9), so the key is exact.
- **No colour in a tile** (the contract now; step 6 makes it): a class colour is `["at", ["get", "__rs_ci"], palette]` in the style; a
  colour for each road is a number key or the feature-state `rs_c`. Then a second theme with the same class list uses the same tiles.
- **The data by row** stays behind the `RoadTable` port (on the main thread, as now). The filters of class, level and access are filters on
  the tile keys; `match` on `["id"]` is only for `rsFilter` and selections. Live colour, width and the glow stay feature-state by row
  (152k states: 0.68 s one time, and no stall after it).

| Remove | Rewrite | Keep |
|---|---|---|
| `promoteId`; `__rs_edge`, `__rs_edge2`, `__rs_s` in `simple` tiles | the keep rule: the contract's keys for each tile layer | the encoder, the tile cache, `ZoomRules`, clip, buffers, PMTiles |
| `osm_id`, `kind`, `name` in `ov4` tiles (the style reads only `height`, `base`) | the sort key (`r` and the row) | the filters on `__rs_cls`, `lvl`, `__rs_access` |
| the colour text in the pieces (step 6) | the colours: by `__rs_ci` in the style, or `rs_c` | `RoadTable`, the feature-state |
| `roads`, `roads-fill`, `roads-highlight` of the full look (D5) | `export_style`: a props file by row (D5) | the budget test and the ratchet |

## 4. The order of work

Each step is one commit (or one page PR) that passes CI, lowers the budget (`scripts/tile_budget.py`) and needs no raise. The picture stays
the same: the Monaco and Tartu goldens, and the Burnaby tilted view in the harness (0 pixels differ).

| Step | Commit | Measured basis | Tests |
|---|---|---|---|
| 1 | 4 MapLibre workers in duckosm-rust's page (the page session does it now) and in roadstyle's page template. No tile change. | −0.45 to −0.51 s | the harness; the e2e tests; on a phone: the time with 4 workers against 1 (a 4-core phone runs 4 MapLibre workers, the wasm worker and the main thread) |
| 2 | D0: the Python engine's road style and tiles stop; the binding gives the Rust output. SonoFlow's `rs.setData` path ships first. | one port for each later step, not two | the suite with `ROADSTYLE_ENGINE=rust` |
| 3 | The keep rule: the contract's keys for each tile layer. `ov4`'s popup keys leave. | `ov4` −0.3 MB | budget rule 2, contract test |
| 3b | Tiny pieces at low zoom (rule B, `drop_tiny` in `roadstyle-tiles`, `_drop_tiny` in `tiles.py`): below the last zoom, a road whose pieces are together under 1 px (8 of 4096 units) is left out unless it leaves the tile, and a casing end piece (`__rs_seam`) under 1 px is left out. Every fill and every casing body piece stays. | Burnaby, 4 workers, median of 5: z12 flat 480 → 362 ms (53,160 → 32,394 `simple` features, 2.55 → 1.57 MB); z13 flat 494 → 418 ms (71,289 → 52,988, 3.49 → 2.64 MB); z14 tilted 968 → 992 ms (noise; 72,320 → 69,845, 3.56 → 3.44 MB). Pixels that differ: 0.65 %, 0.74 %, 0.05 %; no gap. Files: `.claude/tile-lag/ruleB/`. | budget rule 7 (`tiny`: Monaco z12 1,564 → 169), the unit tests, the goldens (the tile-byte parity tests of the Python engine are xfail) |
| 4 | The row as the MVT id on `simple` and `slots`; the dashboard and the editor read `f.id`; `promoteId` goes; `__rs_edge` and `__rs_s` leave; `r` and the new sort key. | −0.53 MB and −74k distinct values (tile_contract.md, section 2) | budget rule 3, glow and live-colour e2e, editor e2e, the order after a relevel |
| 5 | `__rs_edge2` leaves: `rsFilter` adds the twin of each row from `RoadTable`. | −0.20 MB | filter e2e |
| 6 | No colour in the tiles: a class colour by `__rs_ci` in the style; a colour option of a column as a number key or `rs_c`. Before the first archive. | −0.26 MB on Burnaby (`__rs_casing` 180 KB, `__rs_fill` 79 KB) with a class colour | goldens (the same colours), budget `strings` |
| 7 | `export_style` without `roads` (D5); the popup reads a props file by row. | the full look's largest tile: 1.5 MB to 0.15 MB (Monaco z12) | budget of `monaco-full`, `tartu-full` |
| 8 | The page PR in duckosm-rust (section 6). | | duckosm-rust e2e |

After step 5, measure phase 1 (`design-tile-wk`) again with 4 workers. It lands only if its gain is above the batch noise (0.15 s).

## 5. The targets

| Number | Now | After step 7 |
|---|---|---|
| Burnaby tilted view, ms to idle (harness) | 1,343 to 1,534 | ≤ 900 (step 1: 889 measured) |
| Burnaby tilted view, bytes | 5.29 MB | ≤ 4.1 MB (steps 3 to 6) |
| `keys_unread` of `simple` (the declared filter keys not counted) | 3 | 0 |
| `no_id` of `simple` | all | 0 |
| `strings` of `simple` | 19 to 33 | 0 (step 6, class colours) |
| `simple`, largest tile, values (Monaco z15) | 8,806 | ≤ 2,000 (`__rs_s` out) |
| Full look, largest tile (Monaco z12 / Tartu z12) | 1.5 MB / 4.0 MB | 0.15 MB / 0.24 MB |

## 6. What the page must change

Step 1 is a small PR of its own. Then, after step 7, one PR: the new wasm package, the new copy of the dashboard and `level_editor.js`
(its `addSource` without `promoteId`) together. If `promoteId` stays while `__rs_edge` is gone, no road has an id. The dashboard checks
the style's `contract: 2` and the generation, and gives an error for another contract, so that a cached old page does not draw new
tiles. The e2e tests (`e2e.py`, `editor_e2e.py`, `phone_e2e.py`) must pass, with a check of the phone layout.

## 7. The server side

- **The generation** of a road set is the first 16 hex characters of `roadstyle_levels::edge_hash` (the SHA-256 of the sorted edge
  ids): two processes that read the same roads give the same generation. The page, the tile URL, the PMTiles metadata and the live feed
  carry it. A row is valid in one generation only.
- **Tiles on a server**: the eager path (`add_lines`) and `Tiles` behind an `Arc`: `Tiles::tile(&self)` with its cache behind a `Mutex`
  answers many requests at one time. `LiveTiles` (`&mut self`, the pieces made when a tile first shows them) is the browser's path.
- **Edits**: `replace_lines` builds the layer's trees again and clears the whole tile cache for each edit. That is correct for the editor;
  its ceiling is frequent edits on a server, where an index of each road's features is the next step.
- **The data by row**: the props file is in row order, cut into chunks by the tile grid at one zoom (one chunk today), behind the
  `RoadTable` port, so that a client loads only the chunks of its view. This is the contract; it is built when a server needs it.
- **Live colour for a planet**: the server keeps the map from `edge_id` to the row; the live feed gives (generation, row, value) for the
  rows of a view, and the page sets `rs_c` and `rs_w`. No tile is made again. Before the first planet build, count the planet's directed
  edges against 2^32 (D9).

## 8. The contract: fixed and versioned

**Fixed** (a change is contract 3, with a migration): the row as the MVT id (a dense global row under 2^32, D9); only the contract's keys
in a piece (the style's keys, and `__rs_cls`, `lvl`, `__rs_access`); no colour in a piece; the sort key of `r` and the row; the
feature-state names (`rs_c`, `rs_w`, `hover`, `select`); the source name `roads`; 512 px tiles; the generation from `edge_hash`.
**Versioned** (from the look, no break): the palettes and value tables in the style, the zoom spans, the base-map layers. The style's
`roadstyle:tiles` and the PMTiles metadata get `contract: 2` and the generation.

**Shared ids.** All pieces of a road share its row, so one feature-state paints the road. The MVT spec says an id SHOULD be unique in a
layer; MapLibre accepts it (as with `promoteId` now). Other tools (QGIS, Martin's inspector, Tippecanoe) can merge or drop pieces with one
id: the tiles are for MapLibre clients.

## 9. Not done, and why

- **Phase 1** (width and offset as tables, `design-tile-wk`): with 4 workers −0.07 s (889 to 815 ms), inside the batch noise; it adds a
  key to each piece and a table builder. Measure again after step 5.
- **One draw key `d`; colour, opacity, dash, cap and filter as tables**: no gain over phase 1 (1,221 and 1,204 ms against 1,196 ms).
- **A merge of the pieces of one road**: 13 % fewer features; −0.02 s with 4 workers (noise).
- **`setSourceTileLodParams`**: (4, 3) and (2, 2): the same 28 tiles, the same time.
- **Shared buckets**: the 12 visible layers on the source are 12 families; nothing joins.
- **More than 4 workers**: 6 gave 827 ms, 8 gave 894 ms: no clear gain, and a phone has fewer cores.
- **Filters by id list for class, level and access** (`select`): +0.1 s for each switch with 152k ids, and they do not scale to a planet;
  filters on tile keys do.
- **A key set for each zoom**: one set for each tile layer is simpler; the feature spans already act for each zoom.
- **The data in a worker**: no measurement shows a need.
- **A coarser simplification**: 1 px gave about 1 % on Burnaby and no time.
- **One casing per road at low zooms; one casing for two equal halves**: not measured.
- **Class minzooms for steps, corridor, platform, bridleway and construction**: −3 % features at z12; it changes the map.
- **A coarser grid at low zooms**: geometry is 11 to 18 % of the bytes.

## 10. The reviews

The first review (`plan-review.md`) asked for the probes and the measurements that sections 1 and 9 now show; its findings are applied.
The final review (`final-review-fable.md`, approve with changes), finding by finding:

1. Phase 1 and D2: **cut**; measure again after step 5.
2. The sort key after a relevel: **accepted**; the key keeps the row (`replace_lines` adds new pieces at the end of the layer).
3. The generation: **accepted**; the first 16 hex of `edge_hash` (section 7).
4. The colour text in the tiles: **accepted**; no colour in a piece is in the contract now, and step 6 makes it.
5. Filters by id list: **accepted**; `__rs_cls`, `lvl`, `__rs_access` stay as contract keys; step 5 removes only `__rs_edge2`.
6. Keys for each zoom: **accepted**; one set for each tile layer.
7. Server concurrency: **accepted** (section 7).
8. The data as an API: **accepted**; the props file by row in chunks, behind the `RoadTable` port (section 7).
9. Step 1 on phones: **accepted**; the phone check measures the time.
10. Shared ids: **accepted** (section 8).

## 11. Against established practice (the research)

| Practice | Source | Here | Measured |
|---|---|---|---|
| More MapLibre workers (the default is 1) | [1], [2] | **follow**, step 1 | −0.45 to −0.51 s |
| A small width expression | [3], [4] | **not now** (section 9) | −0.07 s with 4 workers |
| One feature for each road and level | [5], [6] | **differ** | −0.02 s with 4 workers |
| Fewer tiles at the horizon; class minzooms | [7], [8] | **differ** | no change; −1.6 to −3 % features |
| Shared buckets; a constant sort key | [9], [10] | **differ** | −0.01 s; the row in the key keeps the order after a relevel |
| Feature-state for live colour | [11], [12] | **follow** | 152k states: 0.68 s one time; no stall after |
| `match`, not `in`, for long lists | [13] | **follow** (`rsFilter`, selections) | 152k ids: +0.1 s |
| An MVT id SHOULD be unique in a layer | [14] | **differ** (section 8) | |
| Drop or coalesce features to a size limit | [6], [15] | **differ**: the style decides what is drawn | |
| Few attributes, each with a minzoom; booleans only when true | [8], [16] | **follow** | |

Sources:

1. MapLibre `getWorkerCount`: https://maplibre.org/maplibre-gl-js/docs/API/functions/getWorkerCount/
2. MapLibre `worker_pool.ts`: https://raw.githubusercontent.com/maplibre/maplibre-gl-js/main/src/util/worker_pool.ts
3. MapLibre `program_configuration.ts`: https://raw.githubusercontent.com/maplibre/maplibre-gl-js/main/src/data/program_configuration.ts
4. MapLibre expressions: https://maplibre.org/maplibre-style-spec/expressions/
5. Planetiler `FeatureMerge.java`: https://raw.githubusercontent.com/onthegomap/planetiler/main/planetiler-core/src/main/java/com/onthegomap/planetiler/FeatureMerge.java
6. Tippecanoe README: https://raw.githubusercontent.com/felt/tippecanoe/main/README.md
7. MapLibre `setSourceTileLodParams`: https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/#setsourcetilelodparams
8. OpenMapTiles transportation in Planetiler: https://raw.githubusercontent.com/openmaptiles/planetiler-openmaptiles/main/src/main/java/org/openmaptiles/layers/Transportation.java
9. MapLibre `group_by_layout.ts`: https://raw.githubusercontent.com/maplibre/maplibre-style-spec/main/src/group_by_layout.ts
10. MapLibre `line_bucket.ts`: https://raw.githubusercontent.com/maplibre/maplibre-gl-js/main/src/data/bucket/line_bucket.ts
11. MapLibre issue 6633: https://github.com/maplibre/maplibre-gl-js/issues/6633
12. MapLibre PR 7550: https://github.com/maplibre/maplibre-gl-js/pull/7550
13. The style spec's `match`: https://raw.githubusercontent.com/maplibre/maplibre-style-spec/main/src/expression/definitions/match.ts
14. The vector tile spec 2.1: https://raw.githubusercontent.com/mapbox/vector-tile-spec/master/2.1/README.md
15. Planetiler config: https://raw.githubusercontent.com/onthegomap/planetiler/main/planetiler-core/src/main/java/com/onthegomap/planetiler/config/PlanetilerConfig.java
16. Shortbread schema: https://shortbread-tiles.org/schema/1.0/

## 12. Results of steps 0 to 7 (2026-10-27, branch `design-tile-steps`)

Each step is one commit. After each, `cargo test`, clippy, the Python suite, the guard and the tile budget pass; the budget only went down,
with one reason-listed raise (step 6). The wasm cross-language test needs a new editor package (`rust/roadstyle-wasm/build_editor.sh`) after
each step: the package in the shared target folder is the one of the last build.

| Step | Commit | What changed |
|---|---|---|
| 0 | `c7b2531` | Tests of removed modules (`roadstyle.tiles`, the full look, the `mapstyle` project) are gone. The guard reads the tests: a `"__rs_` name only in `mark.rs`. |
| 3 | `233b792` | One key set for each tile layer (`TileOptions::rule`). A base-map layer (`roadstyle:base`) keeps the keys that its style layers and the popup read: `ov4` has `height` and `base` only. The slot key `fl` is gone. |
| 4 | `546aaee` | The road's row is the MVT id of the pieces and the slots. `promoteId`, the tile keys `__rs_edge` and `__rs_s` are gone; `r` and the sort key `r * 2^32 + id`. The contract is version 2, the generation is in the style metadata (`roadstyle:generation`), in the tile URL (`?g=`) and in the PMTiles metadata. |
| 5 | `196b5d8` | `__rs_edge2` is a field of the road table only; `rsFilter` adds the twin from the table. |
| 6 | `fe5efa2` | The class colours are not in the pieces: the road layer reads them by `__rs_ci`. A piece has `__rs_fill` or `__rs_casing` only when its road has another colour (an access kind). Colour by a column, colour options and a colour table: see step 6b. |
| 6b | `design-tile-colour` | The other colour modes (a colour by a number or a category, a colour table, colour options) have no colour text in the pieces too. The distinct fill colours and the distinct casing colours are two tables in the style (the `let` variables of the road layer's `line-color`, place 0 is the theme's fallback colour). A piece holds the place of its colour in `__rs_fill`, `__rs_fill__<i>` and `__rs_casing`. A numeric ramp has no other form: its colours are in the table too, one entry for each distinct colour, so the picture is exact (a ramp over many values gives a long table; a quantized ramp is the next step if a style gets too large). The picture stays the same ( 0 pixels differ in 5 modes on Monaco). A view palette has its own tables, and the copies `<property>@<palette>` are places in them. Test: `tile_colour.rs`. |
| 7 | `185dfbc` | A tiled style has no `roads` source and no `roads-fill` or `roads-highlight` layer. `export_style` writes `props.json` (the fields of each road by row, `roadstyle:interaction.props`). The inline export keeps the `roads` source. |
| 7b | `design-tile-colour` | The dashboard checks the generation of the tiles (`generation.js`): a style and tiles of two generations give one message, no vector layer and no road interaction. Test: `test_contract_version.py`. |

The page's look, the tiles of the budget views (the 3 x 3 tiles of Monaco and of Tartu at zoom 12 to 15; the numbers are the budget limits,
the measured number plus 2 %):

| Number | Before (`6317dd7`) | After |
|---|---|---|
| Bytes of the tiles of a view | Monaco 84,569 / 280,951 / 412,244 / 1,184,014; Tartu 398,764 / 1,149,502 / 1,113,303 / 798,981 | −26 % to −30 % in every view |
| `simple`, largest tile, distinct values (Monaco z15) | 8,713 | 68 |
| `simple` features without an MVT id (Monaco z15) | 6,556 | 0 (the budget limit is 1) |
| `simple` keys (z14 / z15) | 19 | 15 |
| `simple` unread keys | 4 | 1 |
| Full look (`export_style`), bytes of a view (Tartu z12 / Monaco z15) | 8,126,709 / 2,888,569 | 294,245 / 826,955 (the `roads` layer is gone) |
| Style, `roads-simple` `line-color`, characters | 1,767 | 2,239 (the class tables, once; the budget has the raise and its reason) |

Burnaby (the duckOSM file `burnaby.duckdb`, 40,872 directed roads; the 151,770-road data of the earlier runs is not on this machine), the
tiles of the Python binding, MapLibre 5.24.0 with 4 workers, headless Chromium with software GL, the median of 5 runs, a new page for each run:

| View | Tiles | Bytes before | Bytes after | ms to idle before | ms to idle after | Pixels that differ |
|---|---|---|---|---|---|---|
| Tilted, pitch 60, z14 | 28 | 1,146,626 | 850,147 (−26 %) | 324 | 335 | 0 |
| Flat z12 | 9 | 626,385 | 458,406 (−27 %) | 210 | 221 | 0 |
| Flat z13 | 8 | 1,171,479 | 856,388 (−27 %) | 270 | 293 | 0 |

The times are inside the batch noise (0.15 s): these steps are a size and a contract gain, as the plan said. On this data the whole
tilted view takes about 0.3 s, so a time gain is not visible.

**What the page PR (step 8) must change:** see the list in the CHANGELOG, "Tiles, contract 2". **Not done:** the planet-scale count of directed edges against 2^32 (D9).

## Decisions (Kaveh, 2026-10-27)

| | Decision | Result |
|---|---|---|
| D1 | 4 MapLibre workers, as a small page PR now | yes (the page session does it) |
| D0 | The Python engine's road style and tiles stop; the binding gives the Rust output (the P7 switch) | yes; SonoFlow's `rs.setData` path ships first. Done on branch `design-rust-only` (CHANGELOG, Unreleased) |
| D5 | `export_style` without `roads`; the popup reads a props file by row | yes |
| D9 | The id as a dense global row under 2^32 for more than one road table | yes, before the first planet build |
| D2 | Phase 1's text form | out, with phase 1: "simple code and a good view are important; if it does not have much effect, leave it" |

No decision is open.
