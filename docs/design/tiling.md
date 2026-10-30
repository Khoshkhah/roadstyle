# Tiling: one algorithm and one protocol

Status: 2026-10-29. This note replaces the per-path notes about the tile format, the last zoom and the compression. The reduction
rules and the size budget stay in [tile_contract.md](tile_contract.md). The MapLibre time stays in [tile_speed.md](tile_speed.md).

## The rule

The tiling does not depend on the project or on the data. One algorithm cuts the tiles. One set of defaults gives the format,
the last zoom, the keys and the compression. A **transport** only moves the tiles to MapLibre: an embedded file, a map worker, a
file server. A transport never changes a tile.

## The paths and the one rule for each choice

| Choice | The one rule | Where it is set |
|---|---|---|
| Cut | `Tiles::build` in `roadstyle-tiles`: clip to the tile and its buffer, simplify below the last zoom, drop what a pixel cannot show, leave out what the style hides at the zoom (`ZoomRules`) | `roadstyle-tiles` |
| Format | **MLT** for every path (decided 2026-10-29). MVT when a caller asks for it (`tile_format="mvt"`). The cut is MVT inside and MLT is made from it; each format has its own cache | `TileFormat::default()` |
| Last zoom | **16**. MapLibre scales the last zoom up. A caller with another need (a planet build) sets `tiles.maxzoom` in the look | `defaults.json`, `config.py` (`tiles`) |
| First zoom | 6 | the same |
| Keys | The keys that the style reads, and the road id. A page that needs more keys names them (`tile_keep`); this is the only difference between the callers | `TileOptions` |
| Compression | The library makes tiles with **no compression**. The transport compresses (next table) | the transports |
| Tile address | `<source>/<z>/<x>/<y>` with the generation of the road set. A transport only changes the prefix | the style's vector source |
| Road layers | One road layer and its dash layer, with **no `minzoom` and no `maxzoom`**. The worker builds the buckets of a tile only for the layers of the tile's zoom, and MapLibre keeps the tiles of the old zoom on the screen until the new ones come: a layer with a zoom range leaves the map empty for 0.1 to 0.3 s at each zoom it starts or ends (Nacka, z14 and z15; road ink 0.000 in 10 frames of 734). A value that changes with the zoom is a zoom curve inside the one layer | `layers/build.rs`, `layers/dash.rs` |
| Default | Tiles on for every page. The GeoJSON path is an opt-out: `tiles=False` | `page_options.rs` |

| Transport | Prefix | Compression | Used by |
|---|---|---|---|
| Embedded archive | `pmtiles://roads` | The tiles are not compressed one by one. The whole archive is one gzip stream (level 9), inflated by the page with `DecompressionStream` | A page (`render_dashboard`, `render_edges`) |
| Map worker | `rs://<generation>/...` | None: the bytes go to MapLibre in the same browser. The worker keeps each tile in each format | The duckosm-rust page, the level editor (`lv://`) |
| File server, PMTiles | `pmtiles://<URL>` | Gzip for each tile (the PMTiles format reads a range of one tile) | `export_style`, `roadstyle tiles` |
| File server, XYZ | `https://.../{z}/{x}/{y}.mlt` | None in the file; the web server compresses | `export_style`, `roadstyle tiles` |

## Why these values (Nacka, 22,191 roads, measured 2026-10-29)

The embedded archive, the tiles of one page:

| Tiles | Archive in the file | Test page |
|---|---|---|
| MVT, z6-z18, a gzip for each tile | 19.8 MB | 30.8 MB |
| MLT, z6-z18, a gzip for each tile | not measured | 21.9 MB |
| MLT, z6-z17, a gzip for each tile | 7.7 MB | 14.6 MB |
| MLT, z6-z17, one gzip stream | 6.2 MB | not built |
| MLT, z6-z16, a gzip for each tile | not measured | 10.9 MB |
| MLT, z6-z15, a gzip for each tile | not measured | 8.7 MB |

The pages above are the test page of the roads alone (the GeoJSON page of the same roads is 9.2 MB). The real daily page is 20.0 MB with these
rules with MLT (z16, one gzip stream), and 18.8 MB with GeoJSON roads. The size with MVT is in the report of the page build (not in this note).

- **MLT** gives the same pixels as MVT (0 differing pixels at zoom 11.5 to 22). It is 60 % of the bytes after gzip. In the worker, an MLT tile costs
  0.8 to 3 ms more to make than an MVT tile (Nacka, native; 1.5 to 6.5 ms for a tile of z11 to z16 against 0.6 to 3.6 ms). The worker keeps each tile
  in each format, so the cost is once for a tile. MapLibre needs about the same time to read both formats (docs/rust/tiles.md).
- **The last zoom 16**: z17 and z18 are 55 % of the MVT archive (z18: 9,337 tiles of 0.7 KB). Against tiles to z18, the pictures at zoom 17 to
  20.5 differ in 0.1 to 0.3 % of the pixels, none by more than 64 levels except 81 at z20.5; at z22 in 8 pixels. Tiles to z15 differ more (213 pixels by more than 64
  levels at z19.5), so 16 is the lowest zoom that holds.
- **One gzip stream** is a fifth smaller than one gzip for each tile (7.7 to 6.2 MB for MLT to z17): a tile of the last zoom has about 1 KB, and a stream sees
  what the tiles have in common. gzip level 9 for each tile gives 0.3 %. Brotli would give another 18 %, but `DecompressionStream` does not read it.
- **The GeoJSON path** draws 2.4 to 2.6 times the triangles of the tiles at zoom 11 to 13, and its pan and zoom stall for twice as long. It is only for a page that
  needs it (a palette in a view is not possible with tiles).

## The keys of a tile (2026-10-29)

A road feature in a tile has the geometry, the feature id (the road's row, a number) and the keys that MapLibre must read: the style's
expressions (paint, layout, filter) and the dashboard's layer filters. A road's other fields (name, edge, level, width, access, the popup fields)
are in the road table, and the popup, the panel, the filters by row and the live colours read the table by the row id.

**The list:** `TILE_ROAD_KEYS` and `TILE_TEXT_KEYS` in `rust/roadstyle-model/src/mark.rs`. A key of a road feature is a mark (`Mark::ALL`) or one of
`TILE_ROAD_KEYS`; a text value only in a pair of `TILE_TEXT_KEYS`. **Every path** makes its tiles with `TileOptions::rule` (the page's archive, the map
worker, `export_style`, `roadstyle tiles`): there is one rule, not one for each path.

**What the tiles of Monaco have** (the table that the test prints for every path; the CI job summary has it too). `simple` is the road pieces and
`slots` the name and arrow anchors. No road feature has a text value except the street name of a name slot.

| layer | key | value | read by the style | read by the page |
|---|---|---|---|---|
| simple | `__rs_k`, `__rs_ci`, `r`, `__rs_twoway`, `__rs_pair`, `__rs_bridge`, `__rs_tunnel`, `__rs_seam`, `__rs_lap` | number or flag | road layer and its dash layer | `__rs_k` |
| simple | `__rs_ci` | the class: the place in `roadstyle:classes` (the model's classes) | road layer (widths, offsets, the class minzoom) | |
| simple | `__rs_cc` | the class for the Roads filter: the place in `roadstyle:controls.filter.classes` | nobody | the Roads filter (`filter.js`) |
| simple | `__rs_dash`, `__rs_cap` | the index (from 1) of the dash pattern; 1 flat end, 2 square end | road layer | |
| simple | `lvl` | number | (the Roads filter: Bridges and Tunnels) | yes |
| slots | `__rs_ci` | the class of the chain, as in `simple` | names and arrows (the size by class, the minor-road rule, the class minzoom) | `arrows.js` |
| slots | `__rs_cc`, `lvl`, `__rs_tunnel` | number or flag | names and arrows; the Roads filter | |
| slots | `chain`, `slot`, `rank`, `oneway` | number | names, arrows | arrows.js, labels |
| slots | `name` | **text**: the only one | names (`text-field`) | labels |

A feature has at most `TILE_KEY_COUNT` keys (`simple` 13, `slots` 9, without `__rs_arw`; the export look has one less because it has no `__rs_cc`): the test `tile_keys` fails when a path has more. The number only goes down.

**Why two class keys.** `__rs_ci` is the place of the class in the model's classes (`roadstyle:classes`); every class that the model does not have gets the same number, the length of the list (the style's lookups have one fallback for them). `__rs_cc` is the place
in the filter panel's classes, which are the classes of the data. They differ when the data has a class that the model does not have: Monaco has `ferry`. With one key, the Roads filter could not hide `ferry` alone (it would hide every class
that is not in the model), and a lookup array cannot grow without a change in every `at` of the style. Tested on 2026-10-30: a tile cut with one key returns an error for Monaco ("the Roads filter has the class 'ferry', which is not one of the model's classes").
One key would need the class list of the page to be the model's classes and the data's classes, and the arrays of the style to have a fallback for each added class; the gain is about 5 % of the tag bytes (MVT), less in MLT.

**Why not one number for the flags (measured 2026-10-30; branch `claude/nacka-tile-keys-packed`, not for merge).** One number `__rs_f` for the six flags, the end shape, the piece kind, the dash index and the level
gives 3 keys on a piece, and it is **worse for the default format**. The tile budget (Monaco and Tartu, the view bytes of the same tiles):

| Packed into one number | MVT view bytes | MLT view bytes | Style expressions (Monaco) |
|---|---|---|---|
| nothing (the keys as they are) | 0 % | 0 % | 46,423 (limit 47,352) |
| the six flags and the slots' one-way flag | −1 % | −1 % to +0.1 % | 48,255 (over) |
| the same and the end shape | −1 % | −1 % to +0.4 % | 48,419 (over) |
| the same and the piece kind | −3 % to −5 % | +0.5 % to +6 % | 49,924 (over) |
| all of them, the dash index and the level too | −11 % to −14 % | +2 % to +9 % | 50,213 (over) |

Two reasons. MLT keeps a sparse flag as a presence bit, so a flag key costs less than one number for each feature; a combined number has many distinct values (46 values in a Monaco z9 tile against 28), and the
value table and the integers grow. And MapLibre has no bit operation: each read of a flag is `["%", ["floor", ["/", F, 2^i]], 2]`, longer than `["get", key]`. The budget fails on both, and a limit
does not go up without Kaveh. Do not pack the flags for MLT. If a page uses MVT only, a layout with one number is 11 % to 14 % smaller: that is a decision for a format-specific rule, not for the one rule.

**Why the paths do not have the same key set.** A key is in a tile when the style's expressions or the page's contract read it, and the three paths have
different styles. The test `the_paths_differ_only_in_the_documented_keys` fails for any other difference:
- `__rs_cc` (`simple` and `slots`) is in the **page look** only: its style has the filter panel (`roadstyle:controls.filter`), and the Roads filter hides a class by this number. The export
  look and the files of stage 1 have no filter panel, so no class key for the filter.
- `__rs_arw` (`slots`) is in the **export look and the stage 1 files** only: the export style's arrow layer draws only the slots that have it, and the page's `arrows.js`
  places its own arrows, so its style does not read it.

**Checklist and tests**

| # | Rule | Test | State |
|---|---|---|---|
| 1 | The feature id of a piece and of a slot is the road's row | `tile_keys.rs`, each path | done |
| 2 | A key of a road feature is a mark or one of `TILE_ROAD_KEYS`: no data column | `the_page_look_tiles_have_only_the_listed_keys`, `the_export_look_tiles_have_only_the_listed_keys`, `the_tiles_of_the_stage_1_files_have_only_the_listed_keys` | done |
| 3 | No text value on a road feature, outside `TILE_TEXT_KEYS` (only `slots.name`); an entry with no text value fails the test; every feature has `__rs_ci` | the same three | done (2026-10-29: `__rs_cls`, `highway`, `__rs_dash`, `__rs_cap` are numbers) |
| 3c | A feature has at most `TILE_KEY_COUNT` keys | the same three | done (2026-10-30) |
| 3b | The paths differ only in the documented keys | `the_paths_differ_only_in_the_documented_keys` | done |
| 4 | No whole-road layer `roads` in the tiles of `export_style` (a click reads the road table by row) | `tests/test_export_style.py::test_style_points_at_its_own_files` | done |
| 5 | A base-map layer keeps only what its layers read (`height`, `base`, `kind`; no `osm_id`, no `name`) | `stage.rs`: `a_base_map_layer_keeps_what_its_layers_read` | done |
| 6 | The tile bytes only go down | `tile_budget.rs`, `tests/test_tile_budget.py` | done (bytes); a number for the property bytes is not in the budget yet |

**What cannot leave the tile**
- `name` on the `slots` features: `text-field` reads the street name from the tile; MapLibre has no side table for a layout property. It stays on the label anchors, never on a road piece.
- The numbers and flags in the first rows: the style's expressions and the dashboard's layer filters read them while MapLibre draws.

**How the text leaves** (`rust/roadstyle-tiles/src/codes.rs` and `layer.rs`; one rule for every path). The tile cut writes the numbers, and `encode_style` rewrites the expressions of the tile layers to read them (a
GeoJSON layer keeps its text): `__rs_cls` becomes `__rs_cc`, the index in `roadstyle:controls.filter.classes` (the Roads filter hides a class by its number in a vector source); the class text of a slot
(`highway`) becomes `__rs_ci` and the class text of a piece is dropped (the engine has put `__rs_ci` on it; a `match` on the class text reads `__rs_ci` and the numbers of the classes in `roadstyle:classes`); `__rs_dash` is the
index from 1 in the road layer's dash patterns; `__rs_cap` is 1 or 2. A page with no filter panel has no `__rs_cc`.

**What it gave, measured on Nacka** (the same base, with and without the numbers; z6-z16; MVT and MLT): **almost nothing in bytes**. MVT: 0.0 % (21.33 and 21.34 MB of tiles); MLT: 1.8 % of the tile
bytes and 0.6 % more in the archive (6.96 and 6.83 MB; the archive 5.30 and 5.33 MB). A text value is in a tile once (the value table), and a feature has only its index, as it has for a number; the gzip
makes the text keys small. The gain of the work is the rule (no text on a road feature, one list, a test on every path), not the size. **The size is in the number of keys of a piece**
(8 to 14 tags, 34 to 40 % of the raw bytes): a key that leaves every piece takes about 2 bytes of 37 (5 %), so one class key in place of two (`__rs_ci` for the style, `__rs_cc` for the Roads filter: they differ when the filter column is not the class column) saves about 5 % of the tag bytes, and
`lvl` (a number that the Bridges and Tunnels switches filter on) and the flags `__rs_twoway`, `__rs_pair` could be one `__rs_k`-like code.

**Where the bytes are** (Nacka, MVT, 13,687 tiles; a count of the raw bytes of a tile: geometry, the tags of each feature (a key and a value index), the key and value tables)

| Zoom | Features | Geometry | Tags | Key table | Value table | The rest (feature header, id) |
|---|---|---|---|---|---|---|
| z12 | 60,502 | 28 % | 40 % | 0 % | 0 % | 32 % |
| z14 | 104,896 | 29 % | 40 % | 0 % | 2 % | 29 % |
| z16 | 160,650 | 30 % | 37 % | 2 % | 4 % | 27 % |
| z17 | 217,616 | 29 % | 34 % | 4 % | 6 % | 27 % |

The tags are the largest part (34 to 40 %): a piece has 8 to 14 of them. A key that leaves a piece takes about 2 bytes of each piece before the gzip.
The `__rs_cls`, `highway` text and the dash text are the same string for most pieces, so the gzip makes them small (the key and value tables are under 10 %);
the gain of moving them is mostly the tags of two keys (about 2 of 10 on a piece), and the simpler style.

## What is not one yet

1. The embedded archive has 3 tile layers (`roads`, `simple`, `slots`). The other sources of the page (the base map, the boundary, the overlays) stay GeoJSON in the page.
   The worker and the server tiles carry all the sources. Rule: all sources are tile layers. Not done.
2. The full look (`export_style`) has a layer `roads` (one feature for each road with 21 columns) that the page's look does not have
   (tile_contract.md, rule 10).
3. The keys of the embedded page include the class, the filter column, `__rs_twoway`, the edge, `lvl` and the width, because the page filters read them from the feature. The road
   table has all of them. Rule: the page reads them by the id. Not done.
4. A host can ask the worker for z17 or more tiles; the look sets the last zoom, and the worker follows it.

## Tests

`tests/test_tile_budget.py` and `rust/roadstyle-rs/tests/tile_budget.rs` keep the size rules. `rust/roadstyle-rs/tests/tile_mlt.rs` and `tests/test_mlt.py` keep
the MLT pictures equal to the MVT pictures.
