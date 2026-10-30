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
