# Make tiles and PMTiles

<p class="lead">Make the roads as vector tiles with the Rust engine, and get them to the browser in one of three ways: in one
HTML file, on a server, or made in the browser.</p>

The Rust engine makes the tiles with the rules of the Python engine (`tiles.py`): one vector source `roads`, zooms 6 to 18, a
buffer of 80 units, and simplified lines below the last zoom. The tiles have the same features as the tiles of the Python
engine. The bytes can differ: a number can be an integer in one engine and a float in the other.

To select a way, see [Three choices for the road data](drawing.md#three-choices-for-the-road-data). In short:

| Way | Use it for | Call |
|---|---|---|
| [A. In one HTML file](#a-put-the-tiles-in-one-html-file) | a file to send or to open from disk | `render_edges(edges, tiles=True)` |
| [B. On a server](#b-put-the-tiles-on-a-server) | a large area, or another map app | `export_style(...)` |
| [C. Made in the browser](#c-make-the-tiles-in-the-browser) | a page that makes its maps itself | `new Tiler(...)` |

## A. Put the tiles in one HTML file

```python
rs.render_edges(edges, tiles=True).save("map.html")
```

The page has a PMTiles archive inside it, and it opens from disk with no server. The browser loads the whole file with the page;
MapLibre then decodes only the tiles in view. The Rust engine writes the archive itself.

## B. Put the tiles on a server

`export_style` writes a folder: `style.json`, the tiles, the sprite (the one-way arrow) and `popup.js` and `popup.css` (the road
popup for an app's plugin). Put the folder on a web server at `base_url`. A map app opens `style.json` by its URL, and the style
leads it to the tiles and the sprite, so every URL in it starts with `base_url`. The style has the roads only: the base map
comes from the app.

The tiles can be in one of two forms. In both forms the map downloads only the tiles of its view.

### As a folder of XYZ tiles

```python
rs.export_style(edges, "monaco_xyz", base_url="https://example.org/monaco")
```

The tiles are one file each: `tiles/<z>/<x>/<y>.pbf`. The map gets each tile with one request for its file. Every web server and
every map app can use this form.

### As one PMTiles file

```python
rs.export_style(edges, "monaco_pm", base_url="https://example.org/monaco", format="pmtiles")
```

All tiles are in one file, `roads.pmtiles`, with an index at its start. The map reads the index, then gets each tile with a
request for a part of the file (an HTTP range request). The server must answer range requests (most static servers and cloud
storage do), and the map page must load the [pmtiles](https://github.com/protomaps/PMTiles) library for the `pmtiles://`
protocol. The same map gives the same archive each time: the archive has no time in its gzip streams.

On Monaco (849 edges), the XYZ form has 31 tile files (3.1 MB), and the PMTiles form is one file of 1.1 MB, because its tiles
are gzipped.

### The tile format: MVT or MLT

A tile can be in one of two formats. `mlt` (MapLibre Tile) is the default (2026-10-29, [tiling.md](../design/tiling.md)). `mvt` (Mapbox Vector Tile) is for an app that cannot read MLT. Both
formats have the same features: the same layers, ids, order, properties and geometry. The tile contract is the same too.

```python
rs.export_style(edges, "monaco_mlt", base_url="https://example.org/monaco", tile_format="mlt")
```

With `tile_format="mlt"`:

- the tile files end in `.mlt`, not `.pbf`;
- the vector source in `style.json` has `"encoding": "mlt"`;
- a PMTiles file has tile type 6 (MapLibre Vector Tile) in its header.

The map app must use MapLibre GL JS 5.12 or later. An app that does not know MLT shows no road.

#### Which format to choose

- **MLT** is the better choice for tiles that go over a network: a tile server, a folder of XYZ tiles or a PMTiles file. An MLT
  tile has about 40 % of the bytes of an MVT tile, and about 60 % after gzip.
- **MVT** is the better choice for tiles that the browser makes itself (`Tiler`, see [section C](#c-make-the-tiles-in-the-browser)).
  No network sends these tiles, so the smaller size gives no gain, and the worker needs more time to make an MLT tile.
- **MVT stays the default.** MapLibre needs about the same time to read both formats, but the speed can depend on the browser and
  on the device. All measurements below use one browser (Chromium with software rendering). A comparison in several browsers and
  on a phone is still to do.

#### Measured results

All numbers come from MapLibre GL JS 5.24.

| Test | MVT | MLT |
|---|---|---|
| Monaco test data, 468 tiles, bytes | 5.9 MB | 2.4 MB |
| The same tiles, after gzip | 2.3 MB | 1.4 MB |
| Burnaby, the largest tile of each zoom 9 to 15, after gzip | 70 to 495 KB | 43 to 288 KB (57 to 61 % of MVT) |
| Burnaby, MapLibre time to read and lay out the largest tile | base | +1 to +10 % (z9 to z13), -1 % (z14), +6 % (z15) |
| Pixels that differ from the MVT picture | - | 0 (Monaco, four views; Burnaby, 17 views) |

The page of duckosm-rust measured the tile of a Burnaby view (driving) in the browser, with the blank base map. Each row is the mean
over the tiles of the view, in 2 runs for each format. "Cut" is the time that the map worker needs to make the tile. "Read" is the
time that MapLibre needs to parse the tile and make its layout.

| Zoom | Tiles | KB for each tile, MVT / MLT | Cut (ms), MVT / MLT | Read (ms), MVT / MLT |
|---|---|---|---|---|
| 11 | 14 | 113 / 45 | 0.4 / 5.3 | 128 / 122 |
| 13 | 10 | 248 / 90 | 1.1 / 12.8 | 173 / 211 |
| 15 | 9 | 113 / 49 | 0.6 / 7.2 | 133 / 103 |

- The read time is about the same. The difference is within the noise of the runs.
- The worker needs 5 to 13 ms to cut an MLT tile, and about 1 ms for an MVT tile. The MVT time is low because the engine keeps the
  MVT tiles that it cut before; MLT is made from the MVT tile each time it is asked for.
- The tests are `tests/test_mlt.py` (the pixels), `rust/roadstyle-rs/tests/tile_mlt.rs` (the features) and
  `rust/roadstyle-rs/tests/tile_budget.rs` (the size limits of the MLT tiles). The Burnaby numbers of the first table are from a
  speed study of 2026-10-28 (headless Chromium, software rendering, 1 worker, the best of 7 to 15 runs). The second table is from the
  duckosm-rust page (2026-10-29).

#### What is different in MLT

- A property has one type in a tile layer. When a key has two types in one layer, MLT writes its values as text. For example,
  `__rs_cap` is `true` on some pieces and `"square"` on others, so MLT gives `"true"` and `"square"`. A style expression that
  reads such a key must work with text. The expressions of the roadstyle style do.
- The encoder does not use a shared dictionary (MapLibre GL JS 5.24 refuses it), FSST or FastPFOR (they give larger tiles after gzip).

### The input of `export_style`

`export_style` takes the keywords of `render_edges` that change the style. In place of a GeoDataFrame, it also takes the path of
a duckOSM GeoParquet export (`duckosm export-gis --format geoparquet`). That file must have the drawing levels, else the call
stops with an error that tells you how to save them.

## C. Make the tiles in the browser

`Tiler` in the WebAssembly package makes each tile when MapLibre asks for it. No tile is written at the start, and there is no
file and no folder:

1. `new Tiler(roads, look, ...)` makes the style and the pieces of the roads (the casings, the fills, the names and the arrows),
   and keeps them in memory with a spatial index. It makes no tile.
2. When MapLibre needs a tile, it asks for an address `rs://<generation>/roads/<z>/<x>/<y>`. The page answers with
   `tiler.tile(z, x, y)`: the engine cuts the pieces in that square and encodes the tile.
3. The engine does not keep the tile. MapLibre keeps the tiles that it has in its own cache.

A new look gives a new `Tiler` and a new generation in the address, so MapLibre does not mix old tiles with the new style.
`tiler.tile("roads", z, x, y, "mlt")` gives the tile in MLT, and `tiler.style("mlt")` gives the style of the same format (the
vector source has `"encoding": "mlt"`). Without the format, they use the format of the `Tiler` (MVT, or the look's `tile_format`).
`tiler.archive(bounds, layers)` is the exception: it makes all tiles in the bounds at once, as one PMTiles archive in memory, for
a page that saves its map as a file. See [Use roadstyle in the browser](browser.md#add-roads-that-come-later-as-vector-tiles).

**See also:** [How a map is drawn](drawing.md) · [Big networks](../guides/big-networks.md) ·
[Put it on a website](../guides/website.md)- **MVT stays the default for every path** until MLT is compared in several browsers (the one default of [tiling.md](../design/tiling.md)). MapLibre needs about the same time to read both
  formats, but the speed can depend on the browser and on the device. All measurements below use one browser (Chromium with software rendering). A comparison in several browsers and on
  a phone is still to do. The worker keeps each tile in each format: an MLT tile costs 1 to 6 ms to make from the MVT one (Nacka, native), once for a tile.

#### Measured results

All numbers come from MapLibre GL JS 5.24.

| Test | MVT | MLT |
|---|---|---|
| Monaco test data, 468 tiles, bytes | 5.9 MB | 2.4 MB |
| The same tiles, after gzip | 2.3 MB | 1.4 MB |
| Burnaby, the largest tile of each zoom 9 to 15, after gzip | 70 to 495 KB | 43 to 288 KB (57 to 61 % of MVT) |
| Burnaby, MapLibre time to read and lay out the largest tile | base | +1 to +10 % (z9 to z13), -1 % (z14), +6 % (z15) |
| Pixels that differ from the MVT picture | - | 0 (Monaco, four views; Burnaby, 17 views) |

The page of duckosm-rust measured the tile of a Burnaby view (driving) in the browser, with the blank base map. Each row is the mean
over the tiles of the view, in 2 runs for each format. "Cut" is the time that the map worker needs to make the tile. "Read" is the
time that MapLibre needs to parse the tile and make its layout.

| Zoom | Tiles | KB for each tile, MVT / MLT | Cut (ms), MVT / MLT | Read (ms), MVT / MLT |
|---|---|---|---|---|
| 11 | 14 | 113 / 45 | 0.4 / 5.3 | 128 / 122 |
| 13 | 10 | 248 / 90 | 1.1 / 12.8 | 173 / 211 |
| 15 | 9 | 113 / 49 | 0.6 / 7.2 | 133 / 103 |

- The read time is about the same. The difference is within the noise of the runs.
- The worker needs 5 to 13 ms to cut an MLT tile, and about 1 ms for an MVT tile. The MVT time is low because the engine keeps the
  MVT tiles that it cut before; MLT is made from the MVT tile each time it is asked for.
- The tests are `tests/test_mlt.py` (the pixels), `rust/roadstyle-rs/tests/tile_mlt.rs` (the features) and
  `rust/roadstyle-rs/tests/tile_budget.rs` (the size limits of the MLT tiles). The Burnaby numbers of the first table are from a
  speed study of 2026-10-28 (headless Chromium, software rendering, 1 worker, the best of 7 to 15 runs). The second table is from the
  duckosm-rust page (2026-10-29).

#### What is different in MLT

- A property has one type in a tile layer. When a key has two types in one layer, MLT writes its values as text. For example,
  `__rs_cap` is `true` on some pieces and `"square"` on others, so MLT gives `"true"` and `"square"`. A style expression that
  reads such a key must work with text. The expressions of the roadstyle style do.
- The encoder does not use a shared dictionary (MapLibre GL JS 5.24 refuses it), FSST or FastPFOR (they give larger tiles after gzip).

### The input of `export_style`

`export_style` takes the keywords of `render_edges` that change the style. In place of a GeoDataFrame, it also takes the path of
a duckOSM GeoParquet export (`duckosm export-gis --format geoparquet`). That file must have the drawing levels, else the call
stops with an error that tells you how to save them.

## C. Make the tiles in the browser

`Tiler` in the WebAssembly package makes each tile when MapLibre asks for it. No tile is written at the start, and there is no
file and no folder:

1. `new Tiler(roads, look, ...)` makes the style and the pieces of the roads (the casings, the fills, the names and the arrows),
   and keeps them in memory with a spatial index. It makes no tile.
2. When MapLibre needs a tile, it asks for an address `rs://<generation>/roads/<z>/<x>/<y>`. The page answers with
   `tiler.tile(z, x, y)`: the engine cuts the pieces in that square and encodes the tile.
3. The engine does not keep the tile. MapLibre keeps the tiles that it has in its own cache.

A new look gives a new `Tiler` and a new generation in the address, so MapLibre does not mix old tiles with the new style.
`tiler.tile("roads", z, x, y, "mlt")` gives the tile in MLT, and `tiler.style("mlt")` gives the style of the same format (the
vector source has `"encoding": "mlt"`). Without the format, they use the format of the `Tiler` (MVT, or the look's `tile_format`).
`tiler.archive(bounds, layers)` is the exception: it makes all tiles in the bounds at once, as one PMTiles archive in memory, for
a page that saves its map as a file. See [Use roadstyle in the browser](browser.md#add-roads-that-come-later-as-vector-tiles).

**See also:** [How a map is drawn](drawing.md) · [Big networks](../guides/big-networks.md) ·
[Put it on a website](../guides/website.md)- **MLT is the one default for every path**, also for tiles that the browser makes itself (`Tiler`, see [section C](#c-make-the-tiles-in-the-browser)). The worker makes an MLT tile
  from the MVT cut in 1 to 6 ms and keeps it, so the cost is once for a tile. MapLibre needs about the same time to read both formats, but the speed can depend on
  the browser and on the device. All measurements below use one browser (Chromium with software rendering). A comparison in several browsers and on a phone is still to do.
- **MVT** only when a caller asks for it (`tile_format="mvt"`), for an app with MapLibre older than 5.12.

#### Measured results

All numbers come from MapLibre GL JS 5.24.

| Test | MVT | MLT |
|---|---|---|
| Monaco test data, 468 tiles, bytes | 5.9 MB | 2.4 MB |
| The same tiles, after gzip | 2.3 MB | 1.4 MB |
| Burnaby, the largest tile of each zoom 9 to 15, after gzip | 70 to 495 KB | 43 to 288 KB (57 to 61 % of MVT) |
| Burnaby, MapLibre time to read and lay out the largest tile | base | +1 to +10 % (z9 to z13), -1 % (z14), +6 % (z15) |
| Pixels that differ from the MVT picture | - | 0 (Monaco, four views; Burnaby, 17 views) |

The page of duckosm-rust measured the tile of a Burnaby view (driving) in the browser, with the blank base map. Each row is the mean
over the tiles of the view, in 2 runs for each format. "Cut" is the time that the map worker needs to make the tile. "Read" is the
time that MapLibre needs to parse the tile and make its layout.

| Zoom | Tiles | KB for each tile, MVT / MLT | Cut (ms), MVT / MLT | Read (ms), MVT / MLT |
|---|---|---|---|---|
| 11 | 14 | 113 / 45 | 0.4 / 5.3 | 128 / 122 |
| 13 | 10 | 248 / 90 | 1.1 / 12.8 | 173 / 211 |
| 15 | 9 | 113 / 49 | 0.6 / 7.2 | 133 / 103 |

- The read time is about the same. The difference is within the noise of the runs.
- The worker needs 5 to 13 ms to cut an MLT tile, and about 1 ms for an MVT tile. The MVT time is low because the engine keeps the
  MVT tiles that it cut before; MLT is made from the MVT tile each time it is asked for.
- The tests are `tests/test_mlt.py` (the pixels), `rust/roadstyle-rs/tests/tile_mlt.rs` (the features) and
  `rust/roadstyle-rs/tests/tile_budget.rs` (the size limits of the MLT tiles). The Burnaby numbers of the first table are from a
  speed study of 2026-10-28 (headless Chromium, software rendering, 1 worker, the best of 7 to 15 runs). The second table is from the
  duckosm-rust page (2026-10-29).

#### What is different in MLT

- A property has one type in a tile layer. When a key has two types in one layer, MLT writes its values as text. For example,
  `__rs_cap` is `true` on some pieces and `"square"` on others, so MLT gives `"true"` and `"square"`. A style expression that
  reads such a key must work with text. The expressions of the roadstyle style do.
- The encoder does not use a shared dictionary (MapLibre GL JS 5.24 refuses it), FSST or FastPFOR (they give larger tiles after gzip).

### The input of `export_style`

`export_style` takes the keywords of `render_edges` that change the style. In place of a GeoDataFrame, it also takes the path of
a duckOSM GeoParquet export (`duckosm export-gis --format geoparquet`). That file must have the drawing levels, else the call
stops with an error that tells you how to save them.

## C. Make the tiles in the browser

`Tiler` in the WebAssembly package makes each tile when MapLibre asks for it. No tile is written at the start, and there is no
file and no folder:

1. `new Tiler(roads, look, ...)` makes the style and the pieces of the roads (the casings, the fills, the names and the arrows),
   and keeps them in memory with a spatial index. It makes no tile.
2. When MapLibre needs a tile, it asks for an address `rs://<generation>/roads/<z>/<x>/<y>`. The page answers with
   `tiler.tile(z, x, y)`: the engine cuts the pieces in that square and encodes the tile.
3. The engine does not keep the tile. MapLibre keeps the tiles that it has in its own cache.

A new look gives a new `Tiler` and a new generation in the address, so MapLibre does not mix old tiles with the new style.
`tiler.tile("roads", z, x, y, "mlt")` gives the tile in MLT, and `tiler.style("mlt")` gives the style of the same format (the
vector source has `"encoding": "mlt"`). Without the format, they use the format of the `Tiler` (MVT, or the look's `tile_format`).
`tiler.archive(bounds, layers)` is the exception: it makes all tiles in the bounds at once, as one PMTiles archive in memory, for
a page that saves its map as a file. See [Use roadstyle in the browser](browser.md#add-roads-that-come-later-as-vector-tiles).

**See also:** [How a map is drawn](drawing.md) · [Big networks](../guides/big-networks.md) ·
[Put it on a website](../guides/website.md)
