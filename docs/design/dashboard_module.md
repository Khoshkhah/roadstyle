# The dashboard module

Date: 2026-10-23. Status: on branch `claude/dashboard-js-5ddf3e`, not merged.

## Why

The map controls of roadstyle's page (colour by, legend, road filter, find, Street View, Google 3D and more) were only in the
page template `src/roadstyle/static/web_template.html`, as one script of about 1,500 lines. The pages that use the Rust engine
(duckosm-rust's browser page, the GeoLibre plugin) could not use them. duckosm-rust copied parts of the template with a script
(`roadstyle_windows.py`), and these copies can become different from the template.

Now the controls are ES modules in `src/roadstyle/static/dashboard/`. There is one copy. The Python page and the Rust-engine pages
use the same files.

## How a page uses it

A page with ES modules:

```html
<link rel="stylesheet" href=".../static/dashboard/dashboard.css">
<link rel="stylesheet" href=".../static/popup.css">
<script type="module">
import {rsDashboard} from ".../static/dashboard/index.js";
const map = new maplibregl.Map({container: "map", style});
rsDashboard(map, {style, select_color: "#7c4dff"});
</script>
```

- Call `rsDashboard` immediately after `new maplibregl.Map(...)`, before the map's `load` event. Some controls do their first
  step on `load`.
- The page must have the global `maplibregl` (MapLibre's UMD script).
- The page adds MapLibre's navigation and scale controls before `rsDashboard`, if it wants them. The dashboard's buttons
  (2D/3D, Street View, Google 3D, base map) go below them in the top-right column.
- A style from the Rust engine is simple mode with inline data. Give `simple: "roads-simple"`, or the hover and select glow do not
  show.
- `examples/dashboard_rust/` is a working page on a style from `rust/roadstyle-wasm` (Monaco).

The Python page (`render_web.render`) does not load modules. When `render_web.py` is imported, it reads the files in a fixed order
(`_DASH_FILES`), removes each `import` line and each `export ` word, and puts the result in the page as one plain script. Thus a
saved page still works offline, as one file. Because the files become one script, two files must not declare the same top-level
name. A top-level name of a file is also a global of the Python page. Scripts that the page adds later use these globals: the
simple-mode script replaces `pick`, and the level editor calls `_sfeats` and `_rsArrows`.

## The options

`rsDashboard(map, options)` takes one object. Each key has the name of a `render` keyword where one exists. The values are the
values that the page reads, which `render` makes from its keywords. The template fills in each value from a placeholder.

| Option | From `render` | Default in `index.js` | Read by |
|---|---|---|---|
| `style` | the style object | (required) | `core.js` (deck layers), `select.js` (pick layers), `basemap.js` (the base map layer) |
| `basemaps` | `basemaps` | `[]` | `basemap.js` |
| `basemap_switcher` | `basemap_switcher` | `true` | `basemap.js` |
| `tiles` | `tiles` | `false` | `core.js` (the sidecar table `window.RS_SIDE`) |
| `simple` | `simple` with inline data: the id of the one road layer | `false` | `core.js`, `select.js`, `svspot.js` |
| `popup_mode` | `popup_mode` (or `road_popup="panel"`) | `"popup"` | `panel.js`, and each control that docks in the panel |
| `find_control` | `find_control` | `false` | `find.js` |
| `zoom_readout` | `zoom_readout` | `true` | `zoom.js` |
| `pitch_3d` | the camera's `pitch_3d` | `55` | `view3d.js` |
| `street_view` | `street_view`: `"window"`, `true` or `false` | `"window"` | `streetview.js`, `svspot.js` |
| `street_view_key` | `street_view_key` | `""` | `streetview.js`, `google3d.js` |
| `google_3d` | `google_3d` | `false` | `google3d.js` |
| `select_color` | `select_color` (the theme's `selection.select`) | (none) | `google3d.js` (the clicked road's line) |
| `filter` | `filter_control`, `access_col`: `{on, col, classes, swatches, palettes, bridges, tunnels, access}` | `{on: false, classes: []}` | `filter.js`, `views.js` |
| `color_options` | `color_options` or a data styler's legend: `[{name, prop, legend}]` | `[]` | `color.js`, `legend.js`, `views.js` |
| `color_active` | `color_active`, as an index | `0` | `color.js` |
| `overlays` | `overlays`: `[{label, source, layers, popup, tooltip, interactive, under, base, select, color, visible, popup_window}]` | `[]` | `core.js`, `overlays.js`, `filter.js`, `select.js` |
| `overlay_control` | `overlay_control` | `true` | `overlays.js` |
| `overlay_popup` | `overlay_popup` | `true` | `overlays.js` |
| `tunnel` | `tunnel_control` and the theme's tunnels: `{layers, control, strength, palette, palettes, ratio, ratios, toward, towards, to, steps}` | `{layers: {}, steps: [], control: false}` | `tunnel.js`, `arrows.js` |
| `fill_layers` | the road fill layer ids | `[]` | `svspot.js` |
| `road_fill` | `road_fill`: `{on, paint}` | `{on: true, paint: {}}` | `color.js` |
| `views` | `views` | `[]` | `views.js` |
| `items` | `items`, `items_popup`: `{label, popup, layer}` or `null` | `null` | `select.js` |
| `road_popup` | `road_popup`: `false` (no popup), `null` (all fields) or a field list | the style's metadata | `select.js`, `find.js` |
| `road_tooltip` | `road_tooltip` or `tooltip`: `false`, `true` or a field list | the style's metadata | `select.js` |
| `hover_delay_ms` | `hover_delay_ms` | the style's metadata, else `300` | `select.js`, `overlays.js` |
| `edge_id_col` | `edge_id_col` | `"edge_id"` | `find.js` (the search always reads the id) |
| `arrow_icon`, `arrow_color`, `arrow_rules` | the theme's `arrows` and `labels.base_size` | `null`: no arrow image, no arrow placement | `arrows.js` |

When a page does not give `road_popup`, `road_tooltip` or `hover_delay_ms`, `index.js` reads them from the style's metadata
`roadstyle:interaction`. `export_style` and the Rust engine write this metadata.

## The files and the controls

| File | Control or part | Data that it reads | Its window API |
|---|---|---|---|
| `core.js` | the shared state, the road data (inline, tiles, simple pieces), the id-set queries | `style`, `tiles`, `simple`, `overlays`; the sources `roads`, `simple`, `decks` | `rsQuery`, `rsGetProps`, `rsHighlight`, `rsFocus` |
| `panel.js` | the side panel (`popup_mode="panel"`), the host panel (`side_panel_html`), the button that shows the panel again, the top-left stack | `popup_mode`; the element `.rs-host` | `rsPanelShow` |
| `find.js` | the search box (in the panel, or `find_control`) | `find_control`, `road_popup`, `edge_id_col` | `rsFind` |
| `zoom.js` | the zoom read-out | `zoom_readout` | |
| `view3d.js` | the 2D/3D button | `pitch_3d` | `rsSetView3D` |
| `float.js` | Google's script loader, the floating window (drag, size, place, remembered) | | |
| `streetview.js` | the Street View window, Linked and Classic | `street_view`, `street_view_key` | `rsSetStreetView` |
| `google3d.js` | the Google 3D window and its camera link | `google_3d`, `street_view_key`, `select_color` | `rsSetGoogle3D` |
| `svspot.js` | the Street View spot on a road, its marker, the step buttons, the Street View link | `street_view`, `fill_layers` | `rsSetStreetViewMarkerAt`, `rsSetStreetViewMarker`, `rsStreetViewStep`, `rsGetStreetViewSpot` |
| `basemap.js` | the base map button and menu | `basemaps`, `basemap_switcher`; the layers `basemap`, `bg` | `rsSetBasemap`, `RS_BASEMAPS` |
| `filter.js` | the Roads box: classes, Bridges, Tunnels, access kinds; the id filter | `filter`, `overlays` | `rsSetClasses`, `rsSetBridges`, `rsSetTunnels`, `rsSetAccess`, `rsGetAccess`, `rsFilter`, `RS_CLASSES`, `RS_CLASS_COL`, `RS_CLASS_COLORS`, `RS_ACCESS` |
| `color.js` | the Colour by menu, the recolouring, the road fill switch | `color_options`, `color_active`, `road_fill`; the states `rs_co`, `rs_colors`, `rs_base`, `rs_ov_<n>`, `rs_fill_on` | `rsSetColorField`, `rsColor`, `rsColorBase`, `rsSetRoadFill`, `RS_COLOR_OPTIONS` |
| `legend.js` | the legend of the active colour option | `color_options[i].legend` | |
| `overlays.js` | the overlay popups, the overlay tooltip, the Layers box | `overlays`, `overlay_control`, `overlay_popup` | `rsSetOverlay`, `RS_OVERLAYS` |
| `tunnel.js` | the Tunnels box (strength, colour, palette, dash ratio) | `tunnel`; the states `rs_tun_*` | `rsSetTunnelStyle`, `RS_TUNNEL_PALETTES`, `RS_TUNNEL_TOWARDS` |
| `views.js` | the View menu | `views`, `filter.palettes`; the state `rs_palette` | `rsSetView`, `RS_VIEWS` |
| `arrows.js` | the one-way arrow image, one arrow for each one-way road in the window | `arrow_icon`, `arrow_color`, `arrow_rules`; the sources `slots`, `arrows` | |
| `select.js` | hover, click, select, the road popup, the hover tooltip | `road_popup`, `road_tooltip`, `hover_delay_ms`, `items`, `overlays` | `rsSelect`, `rsDeselect` |
| `index.js` | the entry: the defaults, then each control in the order of the old template | all options | `rsDashboard` (a global of the Python page) |
| `dashboard.css` | the look of all of the above | | |

The page template keeps only what belongs to the Python page: the map with its camera, the one-tile-zoom rule (`_flatTiles`),
MapLibre's navigation and scale controls, the message for a page with no roads, and the first `fitBounds`.

## The legend data

The legend form is the form that `stylers.bake_color_options` makes and that the page reads. It does not change. Each entry of
`color_options` is `{name, prop, legend}`:

- `legend` is `null`, or `{title, kind: "categorical", entries: [[label, colour], ...]}`, or
  `{title, kind: "continuous", ramp: [colour, ...], vmin, vmax}`.
- The road layers pick the active option from the global state `rs_co` (the option's index). `rsSetColorField` sets it.

When the Rust engine makes `color_by` and the legend, a page gives its list as `color_options`. The dashboard does not read
it from the style's metadata yet, because the Rust engine has no key for it yet.

## Checks

- `pytest`: the tests read the options from the `rsDashboard(map, {...})` call of the page.
- Screenshots of four Monaco pages (default; colour by with legend; panel with tunnels, overlays and a selected road; find and views),
  made with the old and the new code: the pixels are the same, and there are no page errors.
- `examples/dashboard_rust/` in a browser: the modules load as ES modules (strict mode) on a Rust-engine style, with no page errors.
  The popup, the hover tooltip, the glow, the search, Street View and 2D/3D work.
