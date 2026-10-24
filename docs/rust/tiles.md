# Make tiles and PMTiles

<p class="lead">Make the roads as vector tiles with the Rust engine, and get them to the browser in one of three ways: in one
HTML file, on a server, or made in the browser.</p>

The Rust engine makes the tiles with the rules of the Python engine (`tiles.py`): one vector source `roads`, zooms 6 to 15, a
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
rs.render_edges(edges, engine="rust", tiles=True).save("map.html")
```

The page has a PMTiles archive inside it, and it opens from disk with no server. The browser loads the whole file with the page;
MapLibre then decodes only the tiles in view. The Rust engine writes the archive itself, so the `tiles` extra
(`roadstyle[tiles]`) is not necessary.

## B. Put the tiles on a server

`export_style` writes a folder: `style.json`, the tiles, the sprite (the one-way arrow) and `popup.js` and `popup.css` (the road
popup for an app's plugin). Put the folder on a web server at `base_url`. A map app opens `style.json` by its URL, and the style
leads it to the tiles and the sprite, so every URL in it starts with `base_url`. The style has the roads only: the base map
comes from the app.

The tiles can be in one of two forms. In both forms the map downloads only the tiles of its view.

### As a folder of XYZ tiles

```python
rs.export_style(edges, "monaco_xyz", base_url="https://example.org/monaco", engine="rust")
```

The tiles are one file each: `tiles/<z>/<x>/<y>.pbf`. The map gets each tile with one request for its file. Every web server and
every map app can use this form.

### As one PMTiles file

```python
rs.export_style(edges, "monaco_pm", base_url="https://example.org/monaco", format="pmtiles", engine="rust")
```

All tiles are in one file, `roads.pmtiles`, with an index at its start. The map reads the index, then gets each tile with a
request for a part of the file (an HTTP range request). The server must answer range requests (most static servers and cloud
storage do), and the map page must load the [pmtiles](https://github.com/protomaps/PMTiles) library for the `pmtiles://`
protocol. The same map gives the same archive each time: the archive has no time in its gzip streams.

On Monaco (849 edges), the XYZ form has 31 tile files (3.1 MB), and the PMTiles form is one file of 1.1 MB, because its tiles
are gzipped.

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
`tiler.archive(bounds, layers)` is the exception: it makes all tiles in the bounds at once, as one PMTiles archive in memory, for
a page that saves its map as a file. See [Use roadstyle in the browser](browser.md#add-roads-that-come-later-as-vector-tiles).

**See also:** [How a map is drawn](drawing.md) · [Big networks](../guides/big-networks.md) ·
[Put it on a website](../guides/website.md)
