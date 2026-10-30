# Big networks

<p class="lead">Keep a map fast as the network grows. Vector tiles are on by default, and one tiling rule serves every path.</p>

=== "Python"

    ```python
    import roadstyle as rs

    rs.render_edges(edges).save("map.html")                       # vector tiles inside the file (the default)
    rs.render_edges(edges, tiles=False).save("map.html")          # the roads as GeoJSON
    rs.render_edges(edges, tile_format="mvt").save("map.html")    # MVT tiles in place of MLT
    levels = rs.compute_levels(edges)      # the drawing order, once
    rs.render_edges(levels, casing_level_col="casing_level", fill_level_col="fill_level",
                    casing_start_col="casing_start", casing_end_col="casing_end").save("map.html")
    ```

=== "Command line"

    ```bash
    roadstyle edges.gpkg --tiles -o map.html    # embedded vector tiles
    roadstyle edges.gpkg -o map.html            # the roads as GeoJSON (the command line does not turn tiles on by itself)
    ```

## Tiles are the default

The saved page embeds the roads as a PMTiles vector tileset (`tiles=True`, the default). It opens from disk with no server. You do not
need to set anything. The tiles are the same for every path that makes them: the page, the browser worker, `export_style` and
`roadstyle tiles`. One rule makes them ([Tiling: one algorithm and one protocol](../design/tiling.md)):

- **MLT** is the tile format. `tile_format="mvt"` gives MVT. An MLT tile has about 60 % of the bytes of an MVT tile after gzip, and the
  map looks the same.
- The last tile zoom is **16**. MapLibre scales the tiles of zoom 16 up. At zoom 17 to 20.5, 0.1 to 0.3 % of the pixels differ from
  tiles that go to zoom 18.
- The whole archive is **one gzip stream**. The page inflates it with `DecompressionStream`.
- There is **one road layer for every zoom**. It has no `minzoom` and no `maxzoom`, so the map is never empty while the tiles of a
  new zoom load. A value that changes with the zoom is a zoom curve inside the layer.
- A road feature in a tile has no text, except the street name of a name slot, and it has one class key. The other fields of the
  road are in the road table. A test fails when a key is added.

On Nacka (22,000 roads) the page is 20 MB with tiles and 18.8 MB with GeoJSON roads. The GeoJSON page draws 2.4 to 2.6 times the
triangles at zoom 11 to 13, so its pan and zoom stall about twice as long.

- The browser parses only the tiles in view, so a map of 100,000 edges opens in seconds.
- Low zooms carry simplified geometry.
- The JavaScript API, popups and selection work exactly as with GeoJSON roads.
- A page with a palette in a view needs `tiles=False`. An error tells you this.

## Turn the tiles off

Use `tiles=False` for a small network, or for a page with a palette in a view. The page then has the roads as GeoJSON, and MapLibre
cuts them into tiles in the browser. It keeps every vertex. To keep the GeoJSON page fast, use `data_maxzoom` and `data_tolerance`
([every parameter](../reference/parameters.md)).

To get MVT tiles, use `tile_format="mvt"`. Use it for a map app that has MapLibre GL JS older than 5.12.

## The drawing order of a big network

The web map draws every edge by two positions that `render_edges` computes first, with a minimum-cost flow
([how](../design/levels_split_casing.md)). It takes seconds for a district and longer for a large network, so compute it once.

Compute it once with
`rs.compute_levels`, keep the result with `rs.save_levels` (duckOSM file, schema `visualization`), and draw with the columns.
The tile archive also carries the casing pieces and the end caps, so it is larger than the road lines alone.

**See also:** [Every parameter](../reference/parameters.md) · [Put it on a website](website.md)
