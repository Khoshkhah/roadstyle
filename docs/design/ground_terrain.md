# The map terrain from the area's own ground

Date: 2026-11-10. Status: proposal, not built. It waits for Kaveh's yes.

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
| Input | A ground grid with the columns `col`, `row`, `lon`, `lat`, `z` (NULL on nodata): duckOSM `main.elevation_grid` (the DTM's own pixels). When SimReady's conformed ground exists as a grid with the same columns, it is the input |
| Content | Terrarium PNG tiles, 256 px, RGB, height = R·256 + G + B/256 − 32768 (step 1/256 m) |
| Archive | One PMTiles v3 file, `tile_type` PNG, no tile compression (a PNG is already compressed). The writer is `roadstyle-tiles/src/pmtiles.rs`, which the road tiles use |
| Metadata | The ground id (`sha256`), `source`, `product`, `vertical_datum`, `resolution_m`, `license`, from `main.elevation_metadata` |
| Bounds | The grid's box. Only tiles that touch the grid are in the file |
| Size | Monaco: some tens of tiles. Stockholm county at z13: about 1,100 tiles, about 70 MB (an estimate, not measured) |

### The last zoom follows the ground's resolution

The last zoom is the first zoom whose pixel (east–west, at the area's centre latitude) is not larger than the grid's
resolution. A higher zoom adds no information: MapLibre scales the last zoom up. The maximum is 16, the roads' last zoom.

| Ground | Monaco (43.7° N) | Stockholm (59.3° N) |
|---|---|---|
| 30 m DEM (1 arc-second: 22 m east–west at Monaco) | z13 (pixel 13.8 m) | z13 (pixel 9.8 m) |
| 1 m LiDAR DTM | z16 (cap) | z16 (cap) |

The first zoom is 0. Each zoom is made from the grid in the same way (next section), so the check below applies to every
zoom. The lower zooms are few tiles and small.

### How a tile pixel gets its height

A tile pixel has a point (its centre) in longitude and latitude. Its height is the bilinear value of the grid at that point.
The grid is regular in the DEM's own CRS, not always in longitude and latitude (a national DTM is often in a projected CRS).
So the engine does not use a projection library. It finds the grid cell from the pixel centres that the grid gives (`lon`,
`lat` of each `col`, `row`): a global affine first guess, then a local correction in the 2 × 2 cells. This works for any
CRS of the DEM.

A pixel outside the grid, or next to nodata only, gets the nearest valid height of the grid. MapLibre needs a value in every
pixel, and a step down to 0 m at the edge of the area is worse.

## Which code makes the file

roadstyle's Rust engine, a new module `roadstyle-tiles/src/terrain.rs`: `terrain_pmtiles(grid, meta) -> Vec<u8>`. The PNG
encoder uses `flate2`, which the engine already has (no new dependency). The three paths call the same function, so they make
the same bytes:

| Path | Call |
|---|---|
| Python binding | `roadstyle.terrain_tiles(db_or_grid, out)` |
| CLI | `roadstyle terrain <area.duckdb> -o ground.pmtiles` |
| Browser (`roadstyle-wasm`) | `terrain_pmtiles(col, row, lon, lat, z, meta)` with the columns as typed arrays |

## How the file reaches the map

The file is the same for each transport. A transport only moves it (`tiling.md`, "The rule"). The page reads the tiles of the
view only, so the memory grows with the view and not with the area (`memory_budget.md`, "The rule").

| Transport | Source of the `raster-dem` | Used by |
|---|---|---|
| A file in the browser disk (OPFS) | `pmtiles.FileSource` on the OPFS `File`: the page reads the bytes of one tile at a time | duckOSM Studio |
| Embedded in the page | The archive in the page, as the embedded road archive (`pmtiles://ground`) | `render_dashboard`, `render_edges` |
| A URL or a server | `pmtiles://<URL>` (HTTP range requests) | `export_style`, a server |

One function in the dashboard, `rsDemTile(z, x, y)`, reads one DEM tile from the page's ground. `elevation.js` (the hillshade
and the terrain), `bridgemesh.js` and `google3d.js` use it. Today the last two make the AWS URL from `O.ontop.dem.tiles[0]`
by themselves. With this change all three read the same ground.

## The page option `ground`

`ground` is a new page option, in the Python binding, the CLI and the page's options:

```json
{"id": "<sha256>", "source": "FABDEM V1-2", "product": "DTM", "vertical_datum": "EGM2008",
 "resolution_m": 30, "license": "CC BY-NC-SA 4.0", "terrain": "<URL or pmtiles:// name or OPFS file>"}
```

- With `ground`, the DEM source is the terrain file, and the attribution shows
  "Ground: FABDEM V1-2 (DTM, EGM2008), id 3f2a…" with its license.
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
   the pixel's point. This checks the engine. The expected difference is at most 0.004 m (the PNG step).
2. **The display (a number in the report, not a test).** The table above, made again on the file: at the grid's points,
   through MapLibre's interpolation.

The standard's wording must change to the check 1 ("at the tile pixels' points"). The standard belongs to duckOSM.

## The measurement of the speed

On Monaco, in Chromium (Playwright), with an empty cache, five runs for each:

- the time from `rsTerrain(true)` with a tilted camera (pitch 55) to the map's `idle` event, with all DEM tiles loaded;
- the AWS tiles against the terrain file, from OPFS and from the embedded archive;
- the count of requests to `elevation-tiles-prod` (must be 0 with `ground`).

## The steps after the yes

1. roadstyle: `terrain.rs` with the check 1 as a Rust test on the Monaco FABDEM grid; the Python binding and the CLI.
2. roadstyle: the page option `ground`, `rsDemTile`, `elevation.js`, `bridgemesh.js`, `google3d.js`, the attribution; the
   browser test with no request to AWS; the speed measurement.
3. duckOSM Studio, after Studio PR 136 ("a DEM file gives `main.elevation_grid`") merges: read `main.elevation_grid` from
   DuckDB in the browser, make the file with `roadstyle-wasm` in the map worker, write it to OPFS, and give roadstyle the
   option `ground`. Then the phone-viewport check.

## Questions for Kaveh

1. Is this design correct?
2. The check: is it correct to test the file at the tile pixels (check 1) and to change the standard's wording to that?
3. The last zoom: the rule above gives z13 for a 30 m DEM. A higher last zoom makes the display difference smaller (the table)
   but the file larger, with no new information. Is z13 correct?
