# Colour by your data

<p class="lead">Colour the roads by any column: categories, numbers, colours you computed, or several colourings behind a menu.</p>

<iframe src="../../maps/recolor.html" loading="lazy" title="A map with a Colour by menu: AADT, speed and road class" class="rs-demo"></iframe>

=== "Python"

    ```python
    rs.render_edges(edges, color_by="maxspeed_kmh", cmap="viridis", vmin=20, vmax=90)
    ```

=== "Command line"

    ```bash
    roadstyle edges.gpkg --color-by maxspeed_kmh --cmap viridis --vmin 20 --vmax 90
    ```

Roads keep their width, casing and lanes; only the fill colour changes. The map draws a legend
(`legend=True` is the default).

## One colouring

**Categories:** give `colors` a `{value: colour}` map.

```python
rs.render_edges(edges, color_by="highway",
                colors={"primary": "#ef4444", "secondary": "#f59e0b", "residential": "#64748b"})
```

**Numbers:** give a colour map. `cmap` is any matplotlib or branca name; `vmin` and `vmax` clamp
the range; `width_by=(1, 6)` also makes higher values wider, from 1 to 6 px.

```python
rs.render_edges(edges, color_by="maxspeed_kmh", cmap="magma", width_by=(1, 6))
```

Numeric colouring needs the `numeric` extra: `pip install "roadstyle[numeric]"`.

## Your own colours

`color_table` gives each edge a colour by `edge_id` (a dict, a Series, or a DataFrame with
`edge_id` and `color` columns). Edges not in the table are grey. `colors="self"` reads a column
that already holds colours.

```python
rs.render_edges(edges, color_table={edges.edge_id[0]: "#e6194B", edges.edge_id[1]: "#3cb44b"})
rs.render_edges(edges, color_by="color", colors="self")     # `color` holds "#rrggbb"
```

Neither draws a legend.

## Several colourings with a menu

`color_options` puts several colourings in one map, with a **Colour by** menu to switch between
them in the browser. The first entry shows when the map opens. An empty entry is the plain road
style, so pair it with `palette="mono"` to get grey roads under the data.

```python
rs.render_edges(edges, palette="mono", color_options={
    "Traffic": {"color_by": "aadt", "cmap": "viridis"},       # aadt: your own column
    "Speed":   {"color_by": "maxspeed_kmh", "cmap": "magma"},
    "Class":   {},
})
```

Each entry takes the same keywords as a single colouring: `color_by`, `colors`, `cmap`, `vmin`,
`vmax`, `width_by`. The legend follows the menu.

!!! tip "Blank values keep the base colour"
    In a `color_options` map, an edge with no value for an entry (NaN, or a category not in
    `colors`) keeps its road-class colour. On a `mono` base, "no data" roads stay grey instead of looking like a category.

From your own page, `rsSetColorField("Speed")` switches the colouring and `rsColor(ids, "#hex")`
paints a set of roads over it: see the [JavaScript API](../reference/javascript.md).

**See also:** [Every parameter](../reference/parameters.md) · [Style the roads](style.md) · [Dashboards & JavaScript](dashboards.md)
