# Make tiles and PMTiles

<p class="lead">Write the roads as vector tiles with the Rust engine: in the page, as a folder of tiles, or as one PMTiles file
for another map app.</p>

The Rust engine makes the tiles with the rules of the Python engine (`tiles.py`): one vector source `roads`, zooms 6 to 15, a
buffer of 80 units, and simplified lines below the last zoom. The tiles have the same features as the tiles of the Python
engine. The bytes can differ: a number can be an integer in one engine and a float in the other.

## Put the tiles in the page

```python
rs.render_edges(edges, engine="rust", tiles=True).save("map.html")
```

The page has an embedded PMTiles archive and still opens from disk. The Rust engine writes the archive itself, so the `tiles`
extra (`roadstyle[tiles]`) is not necessary.

## Write a folder of XYZ tiles

```python
rs.export_style(edges, "monaco_xyz", base_url="https://example.org/monaco", engine="rust")
```

The folder has `style.json`, the tiles in `tiles/<z>/<x>/<y>.pbf`, the sprite (`sprite.png`, `sprite.json`, and the `@2x` files),
`popup.js` and `popup.css`. Put the folder on a web server at `base_url`.

## Write one PMTiles file

```python
rs.export_style(edges, "monaco_pm", base_url="https://example.org/monaco", format="pmtiles", engine="rust")
```

The folder has `style.json`, `roads.pmtiles` (all tiles in one file), the sprite, `popup.js` and `popup.css`. The same map gives
the same archive each time: the archive has no time in its gzip streams. A map app reads the archive with the
[pmtiles](https://github.com/protomaps/PMTiles) protocol.

The two forms hold the same tiles, and in both forms a map reads only the tiles of its view:

| | XYZ folder | One PMTiles file |
|---|---|---|
| The files | one file for each tile | one file; an index at its start tells where each tile is |
| How a map gets one tile | one request for that tile's file | one request for a part of the file (an HTTP range request) |
| What the server must do | serve static files | serve static files and answer range requests (most servers and cloud storage do) |
| What the map page needs | nothing more | the `pmtiles` library for the `pmtiles://` protocol |

On Monaco (849 edges), the XYZ folder has 31 tile files (3.1 MB) and the PMTiles file is 1.1 MB, because its tiles are gzipped.

`export_style` takes the keywords of `render_edges` that change the style. The style has the roads only: the base map comes
from the app. In place of a GeoDataFrame, `export_style` also takes the path of a duckOSM GeoParquet export
(`duckosm export-gis --format geoparquet`). That file must have the drawing levels, else the call stops with an error that tells
you how to save them.

## Make tiles in the browser

`Tiler` in the WebAssembly package makes the same tiles on request, and `tiler.archive(bounds, layers)` makes the PMTiles
archive. See [Use roadstyle in the browser](browser.md#add-roads-that-come-later-as-vector-tiles).

**See also:** [Big networks](../guides/big-networks.md) · [Put it on a website](../guides/website.md)
