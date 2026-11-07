# Colour by your data

<p class="lead">Colour the roads by a column of your data: categories, numbers, colours that you made, or more than one colouring with a menu.</p>

<iframe src="../../maps/recolor.html" loading="lazy" title="A map with a Colour by menu: AADT, speed and road class" class="rs-demo"></iframe>

=== "Python"

    ```python
    rs.render_edges(edges, color_by="maxspeed_kmh", cmap="viridis", vmin=20, vmax=90)
    ```

=== "Command line"

    ```bash
    roadstyle edges.gpkg --color-by maxspeed_kmh --cmap viridis --vmin 20 --vmax 90
    ```

The roads keep their width, outline and lanes. Only the fill colour changes. The map shows a legend (`legend=True` is the default).

| Your data | Use | Legend |
|---|---|---|
| categories | `color_by` and `colors={value: colour}` | yes |
| numbers | `color_by` and `cmap` | yes |
| a colour for each road | `color_table` or `colors="self"` | no |
| more than one colouring | `color_options`, with a **Colour by** menu | yes, it follows the menu |

## One colouring

**Categories:** give `colors` a `{value: colour}` map.

```python
rs.render_edges(edges, color_by="highway",
                colors={"primary": "#ef4444", "secondary": "#f59e0b", "residential": "#64748b"})
```

**Numbers:** give a colour map. `cmap` is a matplotlib or branca name. `vmin` and `vmax` set the ends of the range.
`width_by=(1, 6)` also makes a higher value wider, from 1 px to 6 px.

```python
rs.render_edges(edges, color_by="maxspeed_kmh", cmap="magma", width_by=(1, 6))
```

A colour map needs no other package: roadstyle has the colour ramps in its data (`data/cmaps.json`).

## Your own colours

`color_table` gives each edge a colour by its `edge_id`: a dict, a Series, or a DataFrame with the columns `edge_id` and
`color`. An edge that is not in the table is grey. `colors="self"` reads a column that has the colours in it.

```python
rs.render_edges(edges, color_table={edges.edge_id[0]: "#e6194B", edges.edge_id[1]: "#3cb44b"})
rs.render_edges(edges, color_by="color", colors="self")     # `color` holds "#rrggbb"
```

## Classes from your data

To put numbers in a few classes, `rs.classify` gives the breaks, a label for each road and the colours:

```python
cls = rs.classify(edges["coverage"], method="natural", k=5, pivot=0.8, palette="rdylgn", fmt="{:.0%}")
edges["cov_class"] = cls.labels
rs.render_dashboard(edges, color_options={"Coverage": cls.option("cov_class")})
```

`method` is `natural` (Fisher-Jenks: the breaks are in the gaps of the data), `quantile`, `equal` or `fixed`. More: [Dashboard parts](dashboard-parts.md#colour-classes).

## Several colourings with a menu

`color_options` puts more than one colouring in one map, with a **Colour by** menu in the page. The map opens with the first
entry. An empty entry is the normal road style: use it with `palette="mono"` to have grey roads under your data.

```python
rs.render_edges(edges, palette="mono", color_options={
    "Traffic": {"color_by": "aadt", "cmap": "viridis"},       # aadt: your own column
    "Speed":   {"color_by": "maxspeed_kmh", "cmap": "magma"},
    "Class":   {},
})
```

Each entry takes the keywords of one colouring: `color_by`, `colors`, `cmap`, `vmin`, `vmax` and `width_by`.

!!! tip "A road with no value keeps its class colour"
    In a `color_options` map, an edge with no value for an entry (NaN, or a category that is not in `colors`) keeps the colour
    of its road class. With `palette="mono"`, a road with no data stays grey, so it does not look like a category.

From the JavaScript of your page, `rsSetColorField("Speed")` changes the colouring, and `rsColor(ids, "#hex")` gives some roads
a colour over it: see the [JavaScript API](../reference/javascript.md).

**See also:** [Every parameter](../reference/parameters.md) · [Style the roads](style.md) · [Dashboards](dashboards.md)
