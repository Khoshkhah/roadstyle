# Add your own layers

<p class="lead">Draw your own zones, points or lines with the roads, each as a layer you can click and switch on or off.</p>

<iframe src="../../maps/overlays.html" loading="lazy" title="A map with zones under the roads and points over them" class="rs-demo"></iframe>

=== "Python"

    ```python
    rs.render_edges(edges, palette="mono", overlays=[
        rs.Overlay(zones, placement="under", color="#6aa9ff", opacity=0.14,
                   label="Zones", popup=["zone_id", "name"]),
        rs.Overlay(pois, placement="over", color="#ff5d5d", radius=7,
                   label="Places", popup=["name", "type"]),
    ]).save("overlays.html")
    ```

`zones` and `pois` are your own GeoDataFrames, in any CRS. An overlay keeps the style you give it;
it does not use the road palette.

## The Overlay

```python
rs.Overlay(data, kind=None, placement="over", color=None, opacity=None, outline=None,
           radius=None, width=None, label=None, popup=None, tooltip=None, visible=True,
           edge_col=None, order_col=None, color_col=None)
```

- `kind`: `"fill"`, `"line"` or `"circle"`. Left out, it follows the geometry: polygons fill,
  lines are lines, points are circles.
- `placement`: `"under"` the roads (zone fills) or `"over"` them (points). The default is `"over"`.
- `color`, `opacity`, `outline` (fills), `radius` (circles), `width` (lines and outlines): one
  style for the whole layer. To colour features by a value, split them into one overlay per value.
- `label`: the layer's name in the Layers control.
- `popup`: the fields shown when a feature is clicked. `None` shows every field; `[]` makes the
  layer not clickable.
- `tooltip`: the fields shown on hover. `visible=False` starts the layer switched off.

## Overlays attached to edges

A thing that belongs to one road (a lane, a lane marking, a zebra crossing, a sign) must be drawn **at the place of its road**: over the road's fill and under every road above it, not over all roads.
Give the overlay two columns:

```python
lanes = rs.Overlay(lane_polygons, edge_col="edge_id", order_col="order", color_col="color", kind="fill")
rs.render_edges(edges, overlays=[lanes, markings, signs])
```

- `edge_col`: the property with the **id of the feature's edge**. The ids are the values of the roads' own id column (`edge_id_col` of `render_edges`, default `edge_id`).
- `order_col`: the property with a whole number, the **order** of the feature: the lower is drawn first (null is 0). The order is global: it orders the features of different edges at the same position too.
- `color_col`: a property with a colour per feature.

Each road is drawn by a casing number and a fill number ([which road is on top](levels.md)). A feature takes the **fill number of its edge**. In each position the layers are: the casings, the fills,
the edge overlays by order, the one-way arrows, the street names. So a sign is over its own road and under every road that passes above it. `placement` is not used for such an overlay.

A feature whose edge id is not among the roads is an error that lists the ids; nothing is drawn at a default place. A click on an edge overlay wins over the roads, like an `"over"` overlay.
Design: [Overlays attached to edges](../design/edge_overlays.md).

## The Layers control

Each overlay gets a checkbox in the **Layers** control, at the bottom-right above the base-map
button. From your own page, `rsSetOverlay("Zones", false)` hides a layer (by label or index): see
the [JavaScript API](../reference/javascript.md).

## What wins a click

The layer drawn on top wins:

1. an `"over"` overlay,
2. the roads,
3. an `"under"` overlay, only where the click misses every road.

So a road inside a clickable zone can still be selected. Its popup also lists the zones under the
click.

!!! note
    Overlays work on the web backend only (the default).

**See also:** [Every parameter](../reference/parameters.md) · [Colour by your data](colour.md) · [Dashboards & JavaScript](dashboards.md)
