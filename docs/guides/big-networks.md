# Big networks

<p class="lead">Keep a map fast as the network grows: inline data, embedded vector tiles, or the GPU.</p>

=== "Python"

    ```python
    import roadstyle as rs

    rs.render_edges(edges).save("map.html")               # up to ~10⁴ edges
    rs.render_edges(edges, tiles=True).save("map.html")   # ~10⁵ edges, still one file
    levels = rs.compute_levels(edges)      # the drawing order, once
    rs.render_edges(levels, tiles=True, casing_level_col="casing_level", fill_level_col="fill_level",
                    casing_start_col="casing_start", casing_end_col="casing_end").save("map.html")
    ```

=== "Command line"

    ```bash
    roadstyle edges.gpkg -o map.html            # inline
    roadstyle edges.gpkg --tiles -o map.html    # embedded vector tiles
    ```

## Up to ~10⁴ edges: the default

The saved page embeds the roads as a PMTiles vector tileset (`tiles=True`, the default) and opens from disk with no server. Nothing to set.

## Why tiles are the default: `tiles=True`

`tiles=True` embeds the roads as a PMTiles vector tileset in the same HTML file. The road pieces are in the tileset as one tile layer. The tiles are MLT (about 60 % of the bytes of MVT, the same picture), up to zoom 16 (the map scales them up), and the whole archive is one gzip stream. On Nacka (22,000 roads) the page is 20 MB, against 18.8 MB with GeoJSON roads (`tiles=False`), which draws 2.5 times the triangles at zoom 11 to 13.

- The browser parses only the tiles in view, so a ~100k-edge map opens in seconds, not ~10 s.
- Low zooms carry simplified geometry.
- The JavaScript API, popups and selection work exactly as with inline data.
- A page with a palette in a view needs `tiles=False`.

## The drawing order of a big network

The web map draws every edge by two positions that `render_edges` computes first, with a minimum-cost flow
([how](../design/levels_split_casing.md)). It takes seconds for a district and longer for a large network, so compute it once.

Compute it once with
`rs.compute_levels`, keep the result with `rs.save_levels` (duckOSM file, schema `visualization`), and draw with the columns.
With `tiles=True` the archive also carries the casing pieces and the end caps, so it is larger than before.

**See also:** [Every parameter](../reference/parameters.md) · [Put it on a website](website.md)
