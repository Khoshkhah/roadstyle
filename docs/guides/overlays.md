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
           edge_col=None, order_col=None, color_col=None, select="road")
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
- `width_m_col`, `offset_m_col`, `dash_col` (line items, simple mode): each item's own width and side offset in metres (exact at every
  zoom; offset + = right of the edge's direction) and its dash pattern (in line widths; empty = solid). In simple mode, LINE items attached
  with `edge_col` and a width in metres are drawn **in the one road layer at their edge's fill position** (in `order_col` order), so a bridge above covers them;
  an edge that has such items keeps its fill under them, so its ends are those of the road without items. At most 38 items per edge: put many
  marks of one kind into one MultiLineString. `select="item"` selects one item.

Each road is drawn by a casing number and a fill number ([which road is on top](levels.md)). A feature takes the **fill number of its edge**. In each position the layers are: the casings, the fills,
the edge overlays by order, the one-way arrows, the street names. So a sign is over its own road and under every road that passes above it. `placement` is not used for such an overlay.

A feature whose edge id is not among the roads is an error that lists the ids; nothing is drawn at a default place.

What a hover or click on such a feature picks is `select`:

- `select="road"` (the default): **its road**. The road highlights and is selected (its popup, `rs:select` with the road), and the feature's
  own fields come along in `overlays`. A sign or a crossing.
- `select="item"`: **the feature itself**. It takes the hover and select highlight (`hover_color` / `select_color` of the page), shows its own
  popup (its `popup` fields, with the road's Street View link), and `rs:select` carries it as `item` (`{overlay, id, properties}`) next to its
  road (`id`, `properties`), so a panel or Street View can still follow the road. A lane.

Either way the feature hides with its road (`rsFilter`, the class, bridge and tunnel switches).
Design: [Overlays attached to edges](../design/edge_overlays.md).

### The look: overlay styles

An overlay can name a **style**, and roadstyle applies the style it finds in the settings. roadstyle ships none: a library defines them in its own **theme** and passes them in `settings=`.

```python
settings = {"config": {"overlays": {"styles": {
    "dashed":      {"kind": "line", "color": "#ffffff", "width_m": 0.12, "dash": [3, 3], "min_zoom": 16},
    "street_name": {"kind": "text", "text_col": "name", "text_size": 12, "text_halo": "#ffffff", "min_zoom": 14}}}}}
rs.render_edges(roads, settings=settings, overlays=[rs.Overlay(markings, style="dashed"), rs.Overlay(names, style="street_name")])
```

`settings=` is a dict or the **address of a JSON or YAML file** (`.yaml`, `.yml`) of the same shape (`render_edges(roads, settings="lanestyle_theme.yaml", ...)`); a file that is missing or cannot be read is an error that names it.

Fields of a style (an argument given to `Overlay` wins): `kind` (`fill`, `line`, `circle`, `text`), `color`, `opacity`, `outline`, `radius`, `width` (px), **`width_m`** (a width in metres, exact from `min_zoom` on),
**`dash`**, **`min_zoom`** / **`max_zoom`**, and for text `text_col`, `text_size`, `text_color`, `text_halo`. Design: [Overlay styles](../design/overlay_styles.md).

### The road without its fill

Three uses: roadstyle alone draws the casing and the fill of each road; a library that adds items (markings, signs) keeps both and attaches the items; a library that draws the fill itself (lanes, dash lines, connectors)
draws **the casing of the road and not its fill**: `render_edges(edges, road_fill=False, overlays=[...])`. The road's own fill stays in the page, invisible, so a click or a hover still finds the road.

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
