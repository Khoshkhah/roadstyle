# Big networks

<p class="lead">Keep a map fast as the network grows: inline data, embedded vector tiles, or the GPU.</p>

=== "Python"

    ```python
    import roadstyle as rs

    rs.render_edges(edges).save("map.html")               # up to ~10⁴ edges
    rs.render_edges(edges, tiles=True).save("map.html")   # ~10⁵ edges, still one file
    rs.render_edges(edges, backend="lonboard",            # millions, in a notebook
                    color_by="maxspeed_kmh", cmap="magma", width_by=(1, 5))
    ```

=== "Command line"

    ```bash
    roadstyle edges.gpkg -o map.html            # inline
    roadstyle edges.gpkg --tiles -o map.html    # embedded vector tiles
    ```

## Up to ~10⁴ edges: the default

The saved page inlines every edge (gzipped) and opens from disk with no server. Nothing to set.
Below ~10⁴ edges this is the simplest and just as fast as the options below.

## Towards ~10⁵ edges: `tiles=True`

`tiles=True` embeds the roads as a PMTiles vector tileset in the same HTML file.

- The browser parses only the tiles in view, so a ~100k-edge map opens in seconds, not ~10 s.
- Low zooms carry simplified geometry.
- The JavaScript API, popups and selection work exactly as with inline data.
- The file is somewhat larger and the Python build is slower (about a minute at ~100k edges).
- Needs the `tiles` extra: `pip install "roadstyle[tiles]"`.

## Millions of edges: lonboard

`backend="lonboard"` draws on the GPU (deck.gl) in a Jupyter notebook. Same call and colours,
but fewer cartographic touches: one colour and width per edge, no casing, labels, arrows,
legend or JavaScript API. Needs the `lonboard` extra. Explore at scale there, then ship a styled
subset with the default backend.

## Choose a backend

| | web (default) | folium | lonboard |
|---|---|---|---|
| Comfortable size | ~10⁴ edges, ~10⁵ with `tiles=True` | ~10³-10⁴ | 10⁵-10⁶+ |
| Road widths | scale with zoom | fixed pixels | fixed pixels |
| Two-way lanes, arrows, street names | yes | no | no |
| Bridges and tunnels | grade separation, 3D | draw order only | no |
| Legends | yes | yes | no |
| Colour menu (`color_options`), overlays, JS API | yes | no | no |
| `selected=` pre-highlighted edges | no (use `rsSelect`) | yes | no |
| Output | one offline HTML file | HTML (Leaflet) | notebook widget |

`folium` is for maps that must live inside a folium workflow. `selected=` is folium-only and
takes a GeoDataFrame of the edges to highlight:

```python
rs.render_edges(edges, backend="folium", selected=edges[edges.name == "Götgatan"])
```

**See also:** [Every parameter](../reference/parameters.md) · [Put it on a website](website.md)
