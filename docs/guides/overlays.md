# Add your own layers

<p class="lead">Draw your own zones, points or lines with the roads. Each one is a layer that you can click and switch on or off.</p>

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

`zones` and `pois` are GeoDataFrames of your own, in any CRS. An overlay keeps the style that you give it. It does not use the road
palette.

## The Overlay

| Argument | What it does |
|---|---|
| `kind` | `"fill"`, `"line"`, `"circle"` or `"text"`. With no value, it follows the geometry: a polygon is a fill, a line is a line, a point is a circle. |
| `placement` | `"under"` the roads (for zones) or `"over"` them (for points). The default is `"over"`. |
| `color`, `opacity`, `outline`, `radius`, `width` | one style for the whole layer. A colour is a text: `"#d32f2f"`, `"red"`, `"rgba(0,0,0,.5)"`. |
| `color_col` | the property with a CSS colour for each feature. A feature with no value gets `color`. |
| `label` | the name of the layer in the **Layers** box |
| `popup` | the fields that show when you click a feature. `None` shows all fields. `[]` makes the layer not clickable. |
| `tooltip` | the fields that show under the pointer |
| `visible` | `False` starts the layer switched off |

A MapLibre expression in place of a colour (`["get", "colour"]`) is an error: use `color_col`.

## The Layers box and the clicks

On a map page, each overlay has a check box in the **Layers** box at the bottom right. A dashboard has no Layers box: its overlays
are in the base map box and the legend box of the toolbox ([Layout and toolbox](dashboard-layout.md)). From your page,
`rsSetOverlay("Zones", false)` hides a layer, by its label or its index ([JavaScript API](../reference/javascript.md)).

A click goes to the layer on top: first an `"over"` overlay, then the roads, then an `"under"` overlay only where the click misses all
roads. So you can still select a road in a clickable zone. Its popup also lists the zones under the click.

Overlays work only on the web backend (the default).

## Overlays attached to edges

An item that belongs to one road (a lane, a lane marking, a zebra crossing, a sign) must be drawn **at the place of its road**: over
the fill of its road and under each road above it. Give the overlay the column with the id of its edge, and the column with its order:

```python
lanes = rs.Overlay(lane_polygons, edge_col="edge_id", order_col="order", color_col="color", kind="fill")
rs.render_edges(edges, overlays=[lanes, markings, signs])
```

An item gets the **fill number of its edge** ([Which road is on top](levels.md)). At each number the map draws the casings, the fills,
the edge items by their order, the one-way arrows and the street names. So a sign is over its own road and under each road that goes
over it. An item whose edge id is not in the roads is an error that lists the ids.

??? info "The columns, the selection, styles and the road with no fill"

    **Columns**

    - `edge_col`: the property with the id of the item's edge, from the id column of the roads (`edge_id_col`, default `edge_id`).
    - `order_col`: a whole number, the order of the item: the lower one is drawn first (null is 0). The order is the same for all
      edges.
    - `width_m_col`, `offset_m_col`, `dash_col` (lines, simple mode): the width and the offset of each item in metres (correct at each
      zoom; a positive offset is to the right of the edge's direction) and its dash pattern (in line widths; empty is solid). These
      items are drawn in the road layer at the fill number of their edge, so a bridge over them covers them. An edge can have at most
      38 such items: put the marks of one kind into one MultiLineString.

    **What a click selects** (`select`)

    - `select="road"` (the default): **the road** of the item. The road shows as selected, and the item's fields come with it in
      `overlays`. Use it for a sign or a crossing.
    - `select="item"`: **the item**. It gets the hover and select colours of the page and its own popup. `rs:select` gives it as
      `item` (`{overlay, id, properties}`) with its road. Use it for a lane.

    An item hides with its road (`rsFilter`, and the class, bridge and tunnel switches).

    **Overlay styles.** An overlay can name a style that the settings give. roadstyle has no styles of its own: a library puts them
    in its theme and gives them in `settings=` (a dict, or the path of a JSON or YAML file).

    ```python
    settings = {"config": {"overlays": {"styles": {
        "dashed":      {"kind": "line", "color": "#ffffff", "width_m": 0.12, "dash": [3, 3], "min_zoom": 16},
        "street_name": {"kind": "text", "text_col": "name", "text_size": 12, "text_halo": "#ffffff", "min_zoom": 14}}}}}
    rs.render_edges(roads, settings=settings, overlays=[rs.Overlay(markings, style="dashed"), rs.Overlay(names, style="street_name")])
    ```

    The fields of a style are `kind`, `color`, `opacity`, `outline`, `radius`, `width` (px), `width_m` (metres, correct from
    `min_zoom`), `dash`, `min_zoom`, `max_zoom`, and for text `text_col`, `text_size`, `text_color`, `text_halo`. An argument of
    `Overlay` wins over its style.

    **The road with no fill.** A library that draws the fill of the roads itself (lanes, dashes) can keep only the road's outline:
    `render_edges(edges, road_fill=False, overlays=[...])`. The road's fill stays in the page with no colour, so a click or a hover still
    finds the road.

    Design: [Overlays attached to edges](https://github.com/Khoshkhah/roadstyle/blob/main/docs/design/edge_overlays.md) ·
    [Overlay styles](https://github.com/Khoshkhah/roadstyle/blob/main/docs/design/overlay_styles.md)

**See also:** [Every parameter](../reference/parameters.md) · [Colour by your data](colour.md) · [Dashboards](dashboards.md)
