---
hide:
  - navigation          # the left menu is hidden: the page is wide enough (over 700 px) for the desktop form of the dashboards on it
---

# Python SDK

<p class="rs-manual-nav"><a href="../">Dashboard manual</a> &middot; <a href="../python/">Python SDK</a> &middot; <a href="../javascript/">JavaScript</a></p>

<p class="lead">Make a dashboard page from a GeoDataFrame of roads, and set each part of it with one call. Each example shows the page that it makes.</p>

The Python SDK has one call for a dashboard, `rs.render_dashboard`. You give it road edges. It gives you a page: one HTML file with the map, the panel and the toolbox. The file works offline. Each example below makes the page that you see under it.
For the JavaScript side of the same page, see [JavaScript](javascript.md).

## Make a dashboard

`edges` is a GeoDataFrame in EPSG:4326 with a `LineString` for each road and a `highway` column. `color_options` fills the *Colour by* list. `name` sets the page title.

```python
import roadstyle as rs

rs.render_dashboard(
    edges,
    name="Södermalm",
    color_options={
        "Road class": {},
        "Speed limit": {"color_by": "maxspeed_kmh", "cmap": "plasma", "vmin": 20, "vmax": 60},
    },
).save("dashboard.html")
```

<iframe src="../../../maps/dashboard.html" loading="lazy" title="The dashboard that the block above makes" class="rs-demo"></iframe>

`render_dashboard` gives a map object. `.save(path)` writes the file, and `.html` is the same page as text. The command line does the same: `roadstyle edges.gpkg --page dashboard -o dashboard.html`.

## Move the toolbox and the panel

`dashboard=` changes any part of the page. The toolbox goes to the left edge, and the panel goes to the right as a floating card.

```python
rs.render_dashboard(
    edges,
    color_options={"Road class": {}},
    dashboard={"toolbar": {"position": "left"}, "panel": {"side": "right", "look": "card", "width_px": 360}},
).save("dashboard_left.html")
```

<iframe src="../../../maps/dashboard_left.html" loading="lazy" title="The dashboard with the toolbox at the left and the panel at the right" class="rs-demo"></iframe>

## Dock the panel

`layout="dock"` gives the panel its own space at the left. The map takes the rest, and there is no toolbox.

```python
rs.render_dashboard(edges, color_options={"Road class": {}}, layout="dock").save("dashboard_dock.html")
```

<iframe src="../../../maps/dashboard_dock.html" loading="lazy" title="The dashboard with the panel docked at the left" class="rs-demo"></iframe>

## Page keywords

The page keywords that matter most for a dashboard:

| Keyword | Use |
|---|---|
| `name` | The title of the page |
| `color_options` | The entries of the *Colour by* list |
| `basemap`, `basemaps`, `basemap_switcher` | The start base map, the list in the switcher, and the switcher itself |
| `live_data` | `True` adds the support for `rs.setData` |
| `views` | Named groups of settings, for `rs.setView` |
| `street_view`, `street_view_key` | The Street View window, and its Google key |
| `mapillary_token` | A Mapillary client token for the Street View window (or the variable `MAPILLARY_TOKEN`). Limit it to your site: it is written into the page. |
| `google_3d`, `google_3d_layers` | The Google 3D window, and the layers that it draws |
| `boundary`, `boundary_dim`, `boundary_limit` | The outline of the area, the shade outside it, and the camera limit |
| `minzoom` | The first zoom of each road class |
| `page_script` | JavaScript text that the page runs after `rs:ready` |
| `dashboard` | The options below |

Every keyword is in [Every parameter](../../reference/parameters.md).

## The `dashboard` option

Give only the parts that you change. The call merges them over the defaults. A wrong key or value is an error. Two examples are above. These tables list every key.

**Frame**

| Key | Default | Meaning |
|---|---|---|
| `template` | `"dashboard"` | `"dashboard"` has a panel. `"map"` has the map and its controls only. |
| `layout` | `"overlay"` | `"overlay"`: the map fills the window and the panel floats. `"dock"`: the panel takes its own space and there is no toolbox. |
| `scale_box` | `False` | `True` shows the scale and the zoom number at the start. |

**`panel`** (`None` removes the panel)

| Key | Default | Meaning |
|---|---|---|
| `side` | `"left"` | `"left"` or `"right"`. |
| `width_px` | `400` | The width of the panel. |
| `look` | `"frame"` | `"frame"`: full height, with a translucent frame. `"card"`: a floating card. |
| `sections` | `[]` | Sections that your page adds: `{id, html, label, after, before, fold}`. |
| `hide` | `["base_map", "colour_by", "legend"]` | Sections to hide. The ids of the panel's own sections are `base_map`, `colour_by`, `legend`, `query` and `selected_road`. |

**`toolbar`**

| Key | Default | Meaning |
|---|---|---|
| `position` | `"right"` | `"right"`, `"left"`, `"top"` or `"bottom"`. |
| `navigation` | `"box"` | `"box"`: a compass needle with sliders. `"buttons"`: zoom and tilt buttons. |
| `settings` | `True` | Shows the settings tool. |
| `hold` | `False` | `True` keeps the bar hidden until your page calls `rs.tools.ready()`, or for 6 s. |

**`legend`**, **`credits`**

| Key | Default | Meaning |
|---|---|---|
| `legend.rows` | `[]` | Rows that your page adds to the legend: `{color, label, shape}`. `shape` is `"square"`, `"circle"` or `"line"`. |
| `credits` | OpenStreetMap | The credits of your own data: `[{"text": ..., "href": ...}]`. They show before the credits of the base map. `[]` shows none. |

**`windows`**: the rules of the Street View and Google 3D windows

| Key | Default | Meaning |
|---|---|---|
| `clamp` | `True` | Keeps a window inside the screen. |
| `recenter_map` | `False` | `True` moves the map when you drag a window. |
| `restore_open` | `True` | Opens again the windows that were open at the last visit. |
| `remember` | `True` | Keeps the size and the place of each window in the browser. |

**`phone`**

| Key | Default | Meaning |
|---|---|---|
| `max_width_px` | `700` | At this window width or less, the page uses the phone form. |
| `toolbar` | `"top"` | The edge of the bar on a phone. |

**`boundary`**: what the page does with `boundary=`

| Key | Default | Meaning |
|---|---|---|
| `dim` | `False` | Shades the outside of the boundary (the keyword `boundary_dim`). |
| `limit` | `False` | Keeps the camera near the boundary (the keyword `boundary_limit`). |
| `dim_light`, `dim_dark` | `0.16`, `0.4` | The opacity of the shade in the light and in the dark theme. |
| `limit_pad` | `2.0` | The center of the map stays inside the bounds of the boundary, grown by this share of their size. |
| `zoom_out` | `3.0` | The lowest zoom is this many levels under the zoom at which the whole boundary fits the window. |

**`google_3d`**: the Google 3D window

| Key | Default | Meaning |
|---|---|---|
| `fov_deg` | `None` | Google's vertical field of view. `None`: the range comes from the camera distance of the map. |
| `follow` | `True` | The window starts with **Follow** on. |
| `min_alt_m` | `80.0` | Under this camera height, in meters, the window shows a note. |
| `min_zoom_drawn` | `17.0` | Over this map zoom, the drawn map shows the note. |
| `mesh_altitude_m` | `1.5` | The height in meters over Google's mesh at which a line or a pin lies. At 0.5 m the bumps of the mesh cut a line into pieces. |
| `selection_style` | see below | The line, the outline and the arrows of the selected road. |
| `layers` | `[]` | Layers from GeoJSON sources of the page. Use the keyword `google_3d_layers`. |

`selection_style` keys: `color` (`#22d3ee`), `width` (8), `outline` (`#0b1020`), `outline_width` (2), `arrow_color` (`#ffffff`), `arrow_width` (5), `arrow_every` (25 m between two arrows) and `fill` (`rgba(34,211,238,0.35)`).

A layer has `id`, `label`, `kind` (`line`, `ribbon`, `polygon` or `points`), `source`, `scope` (`selection` or `view`), `match` (the property that ties a `selection` layer to the road), `max` (500), `on` (`True`), `arrows` and `style`. The `style` keys are `color`, `width`, `outline`, `outline_width`, `dash`, `fill`, `width_m`, `width_prop` and `radius`. A key that does not fit the kind has no effect.

**See also:** [Overview](index.md) · [JavaScript](javascript.md) · [Dashboard layout](../dashboard-layout.md) · [Every parameter](../../reference/parameters.md)
