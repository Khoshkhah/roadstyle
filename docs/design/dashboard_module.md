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
- A style from the Rust engine is simple mode. Give `simple: "roads-simple"`, or the hover and select glow do not show.
- `examples/dashboard_rust/` is a working page on a style from `rust/roadstyle-wasm` (Monaco).

The Python page (`render_web.render`) does not load modules. When `render_web.py` is imported, it reads the files in a fixed order
(`_DASH_FILES`), removes each `import` line and each `export ` word, and puts the result in the page as one plain script. Thus a
saved page still works offline, as one file. Because the files become one script, two files must not declare the same top-level
name. A top-level name of a file is also a global of the Python page. Scripts that the page adds later use these globals: the
simple-mode script replaces `pick`, and the level editor calls `_sfeats` and `_rsArrows`.

## Roads that come later, as vector tiles

duckosm-rust's page adds the roads only after a build, as vector tiles of the engine's `Tiler`, on top of a base map that is not
roadstyle's (OpenFreeMap). Each network change gives a new roads style. `examples/dashboard_rust/tiles.html` does the same on Monaco.

```js
const rs = rsDashboard(map, {style: null, prefix: "rs-", tiles: true, simple: "roads-simple",
                             engine: {props: (id) => worker.roadProps(id)}});
// after each build: remove the old rs- layers and sources, add the new ones with the prefix, then
rs.setStyle(style);
```

- **`rsDashboard` returns an object.** Today it has one method, `setStyle(style)`. The plan for the runtime API
  (`rust_library.md`, "The runtime API") adds the other methods to the same object.
- **`setStyle(style)`.** The page adds the new style's sources and layers to the map first. The dashboard then reads the new style:
  its layers (to pick a road and to filter), its metadata (the popup and tooltip fields, the hover delay, the colour options and
  the legend), and its feature ids. The controls are made once, in `rsDashboard`; `setStyle` does not add a second set. The
  Colour by menu and the legend are made again in their place. The selection, the hover and the fetched properties go, because
  they are the old roads'. A switch that is off (a class, Bridges, Tunnels) applies to the new roads too.
- **`style: null`.** The dashboard starts with no roads: nothing to pick until `setStyle`.
- **`prefix`.** The page adds the roads style's sources and layers with this prefix (`"rs-"`). The dashboard adds it to each
  source and layer id that it uses. The names in the style itself stay as they are: a layer's `source-layer`, the metadata.
- **The base map.** With no `basemaps` option the dashboard has no base map button and does not touch the map's own base map.
- **The glow on tiles.** In the engine's tiles the `roads` source has no lines: the map draws the roads from the pieces of the
  `simple` source. The page adds the `simple` source with `promoteId: "__rs_edge"`. Then all the pieces of a road have the road's
  id, and one feature state (`{source: "rs-simple", sourceLayer: "simple", id: road}`) lights the whole road, also in tiles that
  load later. Without `promoteId`, `setStyle` writes an error in the console. A road is picked on its fill pieces (`__rs_k` 1).
- **`engine.props(id)`.** A function that returns a Promise of one road's properties (`id`: the road's row, the `__rs_edge` of its
  pieces). The dashboard calls it for a click, `rsSelect` and the hover tooltip, also for the road's second edge
  (`__rs_edge2`), and keeps the answers until the next style. If the Promise fails, the dashboard writes an error in the console
  and shows nothing. Without `engine.props` (the Python page) all of this runs at once, as before. `engine` is the same port as
  the plan's `engine.restyle`.
- **Limits.** `rsQuery`, `rsFind`, `rsGetProps` and `rsFocus` need all roads' properties and lines in the page (inline data, or
  Python's sidecar table `window.RS_SIDE`). With `engine.props` only, they find nothing. Street View takes the road's line from
  its longest fill piece in the loaded tiles.

## The options

`rsDashboard(map, options)` takes one object. Each key has the name of a `render` keyword where one exists. The values are the
values that the page reads, which `render` makes from its keywords. The template fills in each value from a placeholder.

| Option | From `render` | Default in `index.js` | Read by |
|---|---|---|---|
| `style` | the style object | `null`: the roads come later (`setStyle`) | `core.js` (deck layers), `select.js` (pick layers), `basemap.js` (the base map layer) |
| `prefix` | (none: the Python page adds the style as it is) | `""` | `core.js`, and each file that names a source or a layer |
| `engine` | (none) | `null`; `{props: id => Promise}` | `core.js` (`_withProps`), `select.js` |
| `basemaps` | `basemaps` | `[]` | `basemap.js` |
| `basemap_switcher` | `basemap_switcher` | `true` | `basemap.js` |
| `tiles` | `tiles` | `false` | `core.js` (the sidecar table `window.RS_SIDE`) |
| `simple` | `simple` with inline data: the id of the one road layer (the Rust engine: also with tiles) | `false` | `core.js`, `select.js`, `svspot.js` |
| `popup_mode` | `popup_mode` (or `road_popup="panel"`) | `"popup"` | `panel.js`, and each control that docks in the panel |
| `find_control` | `find_control` | `false` | `find.js` |
| `zoom_readout` | `zoom_readout` | `true` | `zoom.js` |
| `pitch_3d` | the camera's `pitch_3d` | `55` | `view3d.js` |
| `street_view` | `street_view`: `"window"`, `true` or `false` | `"window"` | `streetview.js`, `svspot.js` |
| `street_view_key` | `street_view_key` | `""` | `streetview.js`, `google3d.js` |
| `google_3d` | `google_3d` | `false` | `google3d.js` |
| `select_color` | `select_color` (the theme's `selection.select`) | (none) | `google3d.js` (the clicked road's line) |
| `filter` | `filter_control`, `access_col`: `{on, col, classes, swatches, palettes, bridges, tunnels, access}` | `{on: false, classes: []}` | `filter.js`, `views.js` |
| `color_options` | `color_options` or a data styler's legend: `[{name, prop, legend}]` | the style's metadata, else `[]` | `color.js`, `legend.js`, `views.js` |
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
`roadstyle:interaction`. `export_style` and the Rust engine write this metadata. When a page does not give `color_options`,
`index.js` reads them from the style's metadata `roadstyle:color_options`. The Rust engine writes it when the map has data colours.

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

The Rust engine (`rust-engine` from `b3222cd`) writes the same list as the style's metadata `roadstyle:color_options`, and
`rsDashboard` reads it from there.

A limit of the Rust engine's style: the engine bakes each global state (`rs_co`, `rs_colors`, `rs_base`, `rs_fill_on`, `rs_tun_*`)
into the expressions, as `export_style` does. Thus on that style the legend shows the active option, but the Colour by menu,
`rsSetColorField`, `rsColor`, `rsColorBase`, `rsSetRoadFill` and the Tunnels box do not change the map. The hover and select glow
work, because they use feature-state. For a page that switches colours, the engine must keep these states as `global-state`.
The legend is correct only for option 0, because the metadata does not give the active option.

## Checks

- `pytest`: the tests read the options from the `rsDashboard(map, {...})` call of the page.
- Screenshots of four Monaco pages (default; colour by with legend; panel with tunnels, overlays and a selected road; find and views),
  made with the old and the new code: the pixels are the same, and there are no page errors.
- `examples/dashboard_rust/` in a browser: the modules load as ES modules (strict mode) on a Rust-engine style, with no page errors.
  The popup, the hover tooltip, the glow, the search, Street View and 2D/3D work.
- `examples/dashboard_rust/tiles.html` in a browser: a mouse click on a road shows the properties from `engine.props` (both
  directions of a pair) and lights the road on the tiles; after `setStyle` with another colouring the legend shows, there is one
  set of buttons, and the hover tooltip shows the fetched properties. No page errors.
