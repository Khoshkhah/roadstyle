# Big networks

<p class="lead">Keep a map fast when the network is large. The page has the roads as vector tiles by default, and all tools make the
same tiles.</p>

=== "Python"

    ```python
    import roadstyle as rs

    rs.render_edges(edges).save("map.html")                       # vector tiles in the file (the default)
    rs.render_edges(edges, tiles=False).save("map.html")          # the roads as GeoJSON
    rs.render_edges(edges, tile_format="mvt").save("map.html")    # MVT tiles in place of MLT
    ```

=== "Command line"

    ```bash
    roadstyle edges.gpkg -o map.html             # vector tiles in the file (the default)
    roadstyle edges.gpkg --no-tiles -o map.html  # the roads as GeoJSON
    ```

## Tiles are the default

The saved page has the roads as a PMTiles vector tileset (`tiles=True`). It opens from disk with no server, and you do not set
anything:

- The browser reads only the tiles that you see, so a map of 100,000 edges opens in seconds.
- At low zooms the lines are simpler.
- The JavaScript API, the popups and the selection work as with GeoJSON roads.

The page, the browser worker, `export_style` and `roadstyle tiles` make the same tiles with one rule.

??? info "How the tiles are made"

    - **MLT** is the tile format. `tile_format="mvt"` gives MVT, for a map app with MapLibre GL JS older than 5.12. After gzip an
      MLT tile has about 60 % of the bytes of an MVT tile, and the map looks the same.
    - The last tile zoom is **16**. MapLibre makes the tiles of zoom 16 larger for the higher zooms.
    - The whole archive is **one gzip stream**. The page opens it with `DecompressionStream`.
    - There is **one road layer for all zooms**, with no `minzoom` and no `maxzoom`, so the map is never empty while the tiles of a
      new zoom load.
    - A road feature in a tile has only its marks and some keys. The other fields of the road are in the road table of the page.

    Design: [Tiling: one algorithm and one protocol](https://github.com/Khoshkhah/roadstyle/blob/main/docs/design/tiling.md).

## Turn the tiles off

Use `tiles=False` for a small network, or for a page with a palette in a view: such a page gives an error that says so. The page then
has the roads as GeoJSON, and MapLibre makes the tiles in the browser. To keep a GeoJSON page fast, use `data_maxzoom` and
`data_tolerance` ([Every parameter](../reference/parameters.md)).

## The drawing order of a big network

`render_edges` calculates which road is on top before it draws ([Which road is on top](levels.md)). This takes seconds for a district
and more for a large network. So calculate it once with `rs.compute_levels`, keep it with `rs.save_levels` (in a duckOSM file, schema
`visualization`), and draw with the columns:

```python
levels = rs.compute_levels(edges)
rs.render_edges(levels, casing_level_col="casing_level", fill_level_col="fill_level",
                casing_start_col="casing_start", casing_end_col="casing_end").save("map.html")
```

**See also:** [Every parameter](../reference/parameters.md) · [On a website or in a map app](website.md)
