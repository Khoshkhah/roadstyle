---
hide:
  - navigation          # the left menu is hidden: the page is wide enough (over 700 px) for the desktop form of the dashboards on it
---

# Python SDK

<p class="rs-manual-nav"><a href="../">Dashboard manual</a> &middot; <a href="../python/">Python SDK</a> &middot; <a href="../javascript/">JavaScript</a></p>

<p class="lead">Make a dashboard page from a GeoDataFrame of roads, and change its options with one call. Each example shows the page that it makes.</p>

The Python SDK has one call for a dashboard, `rs.render_dashboard`. You give it road edges. It gives you a page: one HTML file with the map, the toolbox and the panel. The file works offline. Each example below makes the page that you see under it.
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

`dashboard=` changes any option of the page. The toolbox goes to the left edge, and the panel goes to the right as a floating card.

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
| `template`, `layout` | `"dashboard"` (the default of `render_dashboard`) has a panel, `"map"` has the map only; `layout`: `"overlay"` or `"dock"`. `template` is a keyword, not a key of `dashboard=` |
| `color_options` | The entries of the *Colour by* list |
| `basemap`, `basemaps`, `basemap_switcher` | The start base map, the list in the switcher, and the switcher itself |
| `live_data` | `True` adds the support for `rs.setData` |
| `views` | Named groups of settings, for `rs.setView` |
| `street_view`, `street_view_key` | The Street View window, and its Google key |
| `mapillary_token` | A Mapillary client token for the Street View window (or the variable `MAPILLARY_TOKEN`). Limit it to your site: it is written into the page. |
| `google_3d`, `google_3d_layers` | The Google 3D window, and the layers that it draws |
| `boundary`, `boundary_dim`, `boundary_limit` | The outline of the area, the shade outside it, and the camera limit |
| `minzoom` | The first zoom of each road class |
| `page_script` | JavaScript text that the page runs before it is ready: put the code in `rs.ready(() => ...)` |
| `dashboard` | The options of the next section |

Every keyword, with its default, is in [Every parameter](../../reference/parameters.md).

## The `dashboard` option

Give only the keys that you change. The call merges them over the defaults. A wrong key or value is an error. Two examples are above. Every key, with its default and its meaning, is in [Dashboard options](../../reference/parameters.md#dashboard-options). This list shows the keys by group:

- Frame: `layout`, `scale_box`. `template` is a keyword, not a key of `dashboard=`.
- `panel` (`None` removes the panel): `side`, `width_px`, `look`, `sections`. A section has `id`, `part`, `html`, `text`, `fields`, `chart`, `label`, `after`, `before`, `fold` and `background` ([Add to the panel](../dashboard-panel.md)). A chart card (`part: "chart"`) has `chart` with `kind`, `x`, `y`, `agg`, `scale`, `data`, `title`, `height` and `follow` ([Charts](../charts.md)).
- `toolbar`: `position`, `navigation`, `settings`, `hold`.
- `legend`: `rows`. A row has `color`, `label` and `shape`.
- `credits`: a list of `{text, href}`.
- `windows`: `clamp`, `recenter_map`, `restore_open`, `remember`.
- `boundary`: `dim`, `limit`, `dim_light`, `dim_dark`, `limit_pad`, `zoom_out`.
- `google_3d`: `fov_deg`, `follow`, `min_alt_m`, `min_zoom_drawn`, `mesh_altitude_m`, `selection_style`, `layers`. `selection_style` has `color`, `width`, `outline`, `outline_width`, `arrow_color`, `arrow_width`, `arrow_every` and `fill`. A layer has `id`, `label`, `kind`, `source`, `scope`, `match`, `max`, `on`, `arrows` and `style`. A `style` has `color`, `width`, `outline`, `outline_width`, `dash`, `fill`, `width_m`, `width_prop` and `radius`.

There is no `phone` option. The page turns to its phone form by itself when the window is 700 px wide or less.

**See also:** [Overview](index.md) · [JavaScript](javascript.md) · [Dashboard layout](../dashboard-layout.md) · [Every parameter](../../reference/parameters.md)
