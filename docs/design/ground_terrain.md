# The map terrain from the area's own ground

Date: 2026-11-10. Status: accepted by Kaveh on 2026-11-10 and built in roadstyle (`roadstyle-tiles/src/terrain.rs`, `elevation.js`).
The Studio part waits for Studio PR 136 (the DEM step).

## Summary

Today the hillshade and the 3D terrain of every roadstyle page come from the AWS Terrain Tiles
(`basemaps.json` `ontop.dem`: Terrarium PNG, 256 px, maxzoom 13). Each tilt of the map downloads tiles from AWS. The heights
are not the area's ground, so a road, a deck or a vehicle with its own height floats above the terrain or goes into it.

The standard "The ground reference" (duckOSM `docs/concepts/ground-reference.md`) gives the rule: every renderer draws the
area's ground, and roadstyle's terrain comes from Terrarium PNG tiles made from that ground.

This design makes **one terrain file for each area**: the Terrarium PNG tiles in one PMTiles archive, made one time from the
area's ground grid by roadstyle's Rust engine. The page reads the file in place of AWS, by the same transports as the road
tiles. The AWS tiles stay only for an area with no ground.

## The file

| Item | Rule |
|---|---|
| Input | A ground grid with the columns `col`, `row`, `lon`, `lat`, `z` (NULL on nodata): duckOSM `main.elevation_grid` (the DTM's own pixels). It must be a full rectangle, regular in longitude and latitude: duckOSM reads a DEM in EPSG:4326 only. When SimReady's conformed ground exists as a grid with the same columns, it is the input |
| Content | Terrarium PNG tiles, 256 px, RGB, height = R·256 + G + B/256 − 32768 (step 1/256 m) |
| Archive | One PMTiles v3 file, `tile_type` PNG, no tile compression (a PNG is already compressed). The writer is `roadstyle-tiles/src/pmtiles.rs`, which the road tiles use |
| Metadata | The ground id (`sha256`), `source`, `product`, `vertical_datum`, `resolution_m`, `license`, from `main.elevation_metadata` |
| Bounds | The grid's box. Only tiles that touch the grid are in the file |
| Size | Monaco (FABDEM, 104 x 126 cells): 105 KB, zooms 8 to 13 (measured). A county is larger: not measured (only Monaco and Tartu are tested) |

### The last zoom follows the ground's resolution

The last zoom is the first zoom whose pixel (east–west, at the area's centre latitude) is not larger than the grid's
resolution. A higher zoom adds no information: MapLibre scales the last zoom up. The maximum is 16, the roads' last zoom.

| Ground | Monaco (43.7° N) | Stockholm (59.3° N) |
|---|---|---|
| 30 m DEM (1 arc-second: 22 m east–west at Monaco) | z13 (pixel 13.8 m) | z13 (pixel 9.8 m) |
| 1 m LiDAR DTM | z16 (cap) | z16 (cap) |

The first zoom is 5 zooms below the last zoom (z8 for a 30 m DEM). Each zoom is made from the grid in the same way (next
section), so the check below applies to every zoom. Below the first zoom, MapLibre requests no tile, and the map has no
terrain from this file. A zoom 0 tile covers the world, and the grid's edge values would make a smear over it.

### How a tile pixel gets its height

A tile pixel has a point in longitude and latitude: its north-west corner. MapLibre reads pixel (i, j) of a DEM tile as the
height at the point (i, j) of the tile, not at the pixel's centre. A first build used the centre: on a plane, every height on
the map was 0.84 m too high (half a z13 pixel of slope). The pixel's height is the bilinear value of the grid at that point.

A grid in a projected CRS (a national DTM) is not done: duckOSM does not write one now. When it does, the engine must find
the grid cell from the `lon` and `lat` of the cells, with no projection library.

A pixel outside the grid, or next to nodata only, gets the nearest valid height of the grid. MapLibre needs a value in every
pixel, and a step down to 0 m at the edge of the area is worse.

## Which code makes the file

roadstyle's Rust engine, a new module `roadstyle-tiles/src/terrain.rs`: `terrain_pmtiles(grid, meta) -> Vec<u8>`. The PNG
encoder uses `flate2`, which the engine already has (no new dependency). The three paths call the same function, so they make
the same bytes:

| Path | Call |
|---|---|
| Python binding | `roadstyle._rust.terrain_pmtiles(col, row, lon, lat, z, ground)`; `roadstyle.duckosm.ground(db)` reads a duckOSM file and gives the page option, and `duckosm.page` uses it |
| CLI | `roadstyle terrain <elevation_grid.parquet> <out.pmtiles> [--ground FILE.json]` |
| Browser (`roadstyle-wasm`) | `terrainPmtiles(col, row, lon, lat, z, ground)` with the columns as typed arrays |

## How the file reaches the map

The file is the same for each transport. A transport only moves it (`tiling.md`, "The rule"). The page reads the tiles of the
view only, so the memory grows with the view and not with the area (`memory_budget.md`, "The rule").

| Transport | Source of the `raster-dem` | Used by |
|---|---|---|
| A file in the browser disk (OPFS) | `pmtiles.FileSource` on the OPFS `File`: the page reads the bytes of one tile at a time | duckOSM Studio |
| Embedded in the page | A `data:` URL in the option (`roadstyle.duckosm.ground` makes it) | `render_dashboard`, `render_edges`, `duckosm.page` |
| A URL or a server | The URL of the file (HTTP range requests) | a server |

In each case `elevation.js` reads the archive with pmtiles.js and gives the tiles to MapLibre through its own protocol
`rsground://`. The page's `pmtiles://` protocol stays for the roads only.

One function in `elevation.js`, `_elDemTile(z, x, y)`, reads one DEM tile from the page's ground, and `_elDemMaxZoom()` gives
its last zoom. `google3d.js` uses them for its ground heights and names the ground in its credit. `bridgemesh.js` uses them for
the ground under the bridge decks. A host gives a ground after the page starts with `rsGround(ground)`, where `terrain` can be
a `File` (OPFS), a `Blob`, an `ArrayBuffer` or a URL.

## The page option `ground`

`ground` is a new page option, in the Python binding, the CLI and the page's options:

```json
{"id": "<sha256>", "source": "FABDEM V1-2", "product": "DTM", "vertical_datum": "EGM2008",
 "resolution_m": 30, "license": "CC BY-NC-SA 4.0", "terrain": "<a URL or a data: URL>"}
```

- With `ground`, the DEM source is the terrain file, and the attribution shows
  "Ground: FABDEM V1-2 (DTM, EGM2008), id 3f2a…" with its license. duckOSM has no `sha256` column yet, so the id is
  empty until it does.
- Without `ground`, the page uses `ontop.dem` (the AWS tiles), and the attribution shows "Ground: AWS Terrain Tiles".
  This is for an area with no ground grid only.
- A ground with `product: DSM` shows "Ground: surface model" (the standard, section 1).

## The checks

The standard's check of the map terrain says: "the terrain tiles of a page minus the conformed ground grid, at the grid's
points: at most 0.10 m (the PNG step)". A measurement on Monaco shows that this check cannot pass as written, for any zoom.

The measurement (FABDEM V1-2, Monaco, 30 m; the grid's points are compared with MapLibre's bilinear value of the tile
pixels; a script in this session, not in the repository):

| Last zoom | Pixel | Largest difference | 99 % of the points under | Points over 0.10 m |
|---|---|---|---|---|
| z12 | 27.6 m | 22.8 m | 6.3 m | 62 % |
| z13 | 13.8 m | 12.1 m | 3.4 m | 57 % |
| z15 | 3.5 m | 3.3 m | 0.8 m | 33 % |
| z17 | 0.9 m | 0.8 m | 0.2 m | 6 % |

The cause is not the PNG step (1/256 m). The tile pixels are not at the grid's points (the tiles are in Web Mercator and the
grid is in the DEM's CRS), so MapLibre interpolates a value that was already interpolated. On Monaco's steep ground (up to
56 m between two cells) that difference is metres.

So this design has two checks:

1. **The file (a test, at most 0.10 m).** For each pixel of each tile: the decoded height minus the grid's bilinear value at
   the pixel's point. This checks the engine. The expected difference is at most 1/512 m (half the Terrarium step).
   Tests: `terrain.rs` (Rust), `tests/test_ground_terrain.py` (the tiles decoded by the pmtiles package and PIL, not by the
   engine). On the Monaco FABDEM grid: 62,465 pixels, the largest difference 0.0020 m. In the browser, on a plane, MapLibre's
   own height (`queryTerrainElevation`) equals the grid to 0.10 m.
2. **The display (a number in the report, not a test).** The table above, made again on the file: at the grid's points,
   through MapLibre's interpolation.

The standard's wording must change to the check 1 ("at the tile pixels' points"). The standard belongs to duckOSM.

## The measurement of the speed

Monaco, Chromium (Playwright, software WebGL), a blank base map, a new browser context for each run (an empty cache). The time
is from "hillshade and terrain on, pitch 60, zoom 15" to the map with all tiles loaded. Seven runs for each:

| DEM | Median | Runs (ms) | Requests to AWS |
|---|---|---|---|
| AWS Terrain Tiles | 3,474 ms | 3,496 3,569 3,437 3,474 3,392 3,689 3,293 | 44 to 50 |
| Terrain file, embedded in the page | 1,757 ms | 1,623 1,873 1,732 1,814 1,714 1,757 1,806 | 0 |

The terrain file is about two times faster. The Studio path (OPFS) is measured in step 3.

## The steps

1. Done: roadstyle `terrain.rs` and its tests; the Python binding, `roadstyle.duckosm.ground` and the CLI.
2. Done: the page option `ground`, `rsGround`, `elevation.js`, `google3d.js` and the attribution; the browser test with no
   request to AWS; the speed measurement.
3. duckOSM Studio, after Studio PR 136 ("a DEM file gives `main.elevation_grid`") merges: read `main.elevation_grid` from
   DuckDB in the browser, make the file with `roadstyle-wasm` in the map worker, write it to OPFS, and give roadstyle the
   ground with `rsGround`. Then the phone-viewport check.

## Open item

The standard's check (duckOSM `docs/concepts/ground-reference.md`, section 5) says "at the grid's points". It must say "at
the tile pixels' points", as check 1 above. The standard belongs to duckOSM.
