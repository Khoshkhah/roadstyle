# Overlay styles

**Status:** design, then code. Builds on [Overlays attached to edges](edge_overlays.md).

A library that draws things on roads (mapstyle: the base map and the road looks; lanestyle: lane lines, dash lines, zebra crossings, lane arrows, street names) knows how those things must **look**: a divider is a white line 12 cm wide
from zoom 16, a dashed line has a pattern, a street name is text along the road. roadstyle must be able to draw such looks, but it must not know them. So:

- **roadstyle provides the mechanism**: an overlay can **name a style**, and roadstyle applies the style it is given. roadstyle ships **no** overlay style of its own.
- **The library defines the styles in its own theme** (a YAML file, as mapstyle's themes: its `roadstyle:` block is merged into the settings) and **passes them in `settings=`**, which is how mapstyle already gives roadstyle its looks.
  lanestyle creates its own theme in the same way: the looks of its dividers, dashed lines, zebra crossings, lane arrows and street names.

## In the settings

The styles are a block of the settings, `config.overlays.styles`: a name and its fields.

```yaml
config:
  overlays:
    styles:
      divider:     {kind: line, color: "#ffffff", width_m: 0.12, min_zoom: 16}
      dashed:      {kind: line, color: "#ffffff", width_m: 0.12, dash: [3, 3], min_zoom: 16}
      zebra:       {kind: fill, color: "#ffffff", opacity: 0.9, min_zoom: 17}
      street_name: {kind: text, text_col: name, text_size: 12, text_color: "#444444", text_halo: "#ffffff", min_zoom: 14}
```

```python
rs.render_edges(roads, settings=my_settings, road_fill=False,
                overlays=[rs.Overlay(markings, edge_col="edge_id", order_col="order", style="dashed")])
```

An argument given to `Overlay` itself wins over the field of its style. A style that is not in the settings is an error that lists the known names. The word for the whole file is a **theme**; the word for one entry of it, which an overlay names, is a **style**.

## The fields of a style

| Field | Meaning |
|---|---|
| `kind` | `fill`, `line`, `circle` (as for an overlay) or **`text`** |
| `color`, `opacity`, `outline`, `radius`, `width` | as the arguments of `Overlay`; `width` is in px |
| **`width_m`** | a width in **metres** for a line (and a polygon's outline): from the zoom `min_zoom` (default 0) on, the line is drawn exactly that wide, as the lanes are with `width_m_col`. At a low zoom it is thinner than a pixel: set `min_zoom`. It replaces `width` |
| **`dash`** | the dash pattern of a line, in line widths (MapLibre's `line-dasharray`): `[3, 3]` |
| **`min_zoom`**, **`max_zoom`** | the zooms in which the overlay is drawn (the layers' `minzoom` and `maxzoom`) |
| **`text_col`** | for `kind: text`: the property that holds the text |
| `text_size`, `text_color`, `text_halo` | the size in px, the colour and the halo colour of the text (no halo if absent) |

`width_m` is the real width on the ground: the width in px is `width_m / cos(latitude) × 512 · 2^zoom / 40,075,016.686`, found at the feature's own latitude, as for the roads. It is exact between two zooms, because the width doubles with each zoom.
The text of `kind: text` is drawn along a line (`line-center`, once for a feature) or at a point, in the font roadstyle uses for its street names.

## What does not change

- An overlay without a `style` is as before. The settings of a library are applied and restored for one call, as every `settings=` is.
- An overlay attached to edges takes its place from its edge and its order, whatever its style: a text, a dashed line and a polygon are all drawn at the fill number of their edge.

## Tests

- A style from `settings=` is applied; an argument of the `Overlay` wins; an unknown style is an error with the names.
- `width_m`: the line width is the metre expression, exact between zooms; `dash` and `min_zoom` / `max_zoom` are on the layer.
- `kind: text`: a symbol layer reading `text_col`, along a line; the glyphs are available.
- Attached to edges with the style of each kind: the layers are at the edge's position.

## Open points

1. A different width for each feature (a column), and icons on a point: not yet.
2. A text that avoids other symbols (lanestyle cuts its names clear of arrows and zebras): the cut is done by the library, in the geometry it gives.
