# The dashboard module

Date: 2026-10-23. Status: on branch `claude/dashboard-js-5ddf3e`, not merged.

## Why

The map controls of roadstyle's page (colour by, legend, road filter, find, Street View, Google 3D and more) were only in the
page template `rust/roadstyle-assets/files/static/web_template.html`, as one script of about 1,500 lines. The pages that use the Rust engine
(duckosm-rust's browser page, the GeoLibre plugin) could not use them. duckosm-rust copied parts of the template with a script
(`roadstyle_windows.py`), and these copies can become different from the template.

Now the controls are ES modules in `rust/roadstyle-assets/files/static/dashboard/`. There is one copy. The Python page and the Rust-engine pages
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
- Give the road table (`road_table`, or `window.RS_SIDE`): the popup, the search, `rsFocus` and Street View read it.
- `examples/dashboard_rust/` is a working page on a style from `rust/roadstyle-wasm` (Monaco).

The Python page (`render_web.render`) does not load modules. When `render_web.py` is imported, it reads the files in a fixed order
(`static/dashboard/files.txt`; the Rust page writer's `build.rs` reads the same list), removes each `import` line and each `export ` word, and puts the result in the page as one plain script. Thus a
saved page still works offline, as one file. Because the files become one script, two files must not declare the same top-level
name. A top-level name of a file is also a global of the Python page. Scripts that the page adds later use these globals: the
simple-mode script replaces `pick`, and the level editor calls `_sfeats` and `_rsArrows`.

## Roads that come later, as vector tiles

duckosm-rust's page adds the roads only after a build, as vector tiles of the engine's `Tiler`, on top of a base map that is not
roadstyle's (OpenFreeMap). Each network change gives a new roads style. `examples/dashboard_rust/tiles.html` does the same on Monaco.

```js
const rs = rsDashboard(map, {style: null, prefix: "rs-", tiles: true});
// after each build: remove the old rs- layers and sources, add the new ones with the prefix, then
rs.setStyle(style, {road_table});
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
- **The glow on tiles.** The engine's tiled style has one vector source `roads`; each layer names its source layer (`simple`,
  `slots`), as in Python's tiles. Every style of the engine gives the pieces `promoteId` `"__rs_edge"` (on the vector source
  `{simple: "__rs_edge"}`) and has the select and hover glow in its road layer (2026-10-24), so all the pieces of a road have the
  road's row as their id, and one feature state (`{source: "rs-roads", sourceLayer: "simple", id: row}`) lights the whole road,
  also in tiles that load later. Without `promoteId`, `setStyle` writes an error in the console. A road is picked on its fill
  pieces (`__rs_k` 1).
- **The road table.** The page gives each style's road table (`setStyle(style, {road_table})`, from `makeSources(...).roadTable()`).
  A road's fields, its line (Street View, Google 3D), its midpoint and its bbox come from it, so `rsQuery`, `rsFind` and `rsFocus`
  work with tiles too. (Until 2026-10-24 a page could give one road's fields at a time with `engine.props`; the road table replaced
  it. duckosm-rust's frozen page still pins a roadstyle with `engine.props`: at the end of its freeze it gives the road table.)
- **Street View on tiles.** The spot, the marker, the heading and the step buttons use the road's line from the road table. The
  marker is a MapLibre marker, not a layer: a new roads style (`setStyle`) does not remove it.

## One way for GeoJSON and tiles (design step g)

Date: 2026-10-24. The dashboard reads the roads in one way, whether the roads style has GeoJSON sources or vector tiles. Three parts
of `core.js` do it; the other files call them.

- **The sources by role (`_src`, `_role`).** A role is the name of a source of the roads style: `roads`, `simple`, `slots`,
  `arrows`, `decks`, `shadows`, `ov<i>`. With tiles, a role is a source layer of a vector source. The metadata
  `roadstyle:sources` (role to `{source, layer}`) gives the map. A style without it gives the same map from its layers: a layer's
  `source-layer`, else its source, is its role. `_src(role)` gives the map's source id (with the prefix) and the source layer
  only for a vector source. Filters, picking, the glow, the decks, the slots and Street View use it, with no branch on tiles.
  The road filters act on the layers of the road roles alone (`RS_ROLES`: the keys of `sources`, else of `roadstyle:sources`), and
  a road is picked on the layers of the option `pick`. No layer id is tested for a prefix (R7).
- **The road table (`RoadTable`).** One port for every read of a road: `has(i)`, `props(i)`, `line(i)`, `mid(i)`, `bbox(i)`,
  `rows()`, by the road's row. The data is the road table of stage 1 (`{props, mids, bboxes, lines}`), from the option
  `road_table` or from `window.RS_SIDE`. `_road(i)` makes a
  feature with the road's whole line for Street View and Google 3D. `rsQuery`, `rsFind`, `rsGetProps` and `rsFocus` read the
  table, so they work with tiles when the page has the table.
- **The glow (`_fs`).** The feature state of a road by its row. In simple mode the state goes on the pieces of the role
  `simple`, which all have the row as their id (the source has `promoteId` `"__rs_edge"`, GeoJSON and vector alike). In
  Python's full look it goes on the road in the role `roads`. Simple mode and its one road layer come from the style (a line
  layer of the role `simple`), so a later style can change them. A road's 3D decks come from one
  index road to decks, made again when the decks' data changes.
- **The arrows.** The metadata `roadstyle:arrows` says which arrows the style has: `"points"` (the dashboard places one arrow for
  each one-way chain, on the `arrows` source), `"line"` or `"line-center"` (the style's own symbol layers). A style without the
  key: points when it has an `arrows` source.

Every page of roadstyle embeds the road table (`static/page/side.html`) and sends `rs:tableready` when it has loaded it; the
dashboard reads it when it needs it, and `api.js` makes its edge id index again then. A page has no `roads` source in simple
mode. `_sdata` (MapLibre's private `_data`) stays only for the inline sources that have no table: the decks (the road-to-decks
index), the slots (the arrows) and the overlays.

The names that other page scripts call stay: `_rprops`, `_svTiled`, `_roadOf`, `_roadOfPiece`, `pick`, `ITEM_PICK`, `_sfeats`,
`_src`, `_rsArrows`, `_rsArrowAt` (the simple-mode script, the no-roads message, the level editor).

## Live data (R22)

Date: 2026-10-24. `rs.setData(table, options)` (`live.js`) colours and sizes the roads from a table, with no new style and no tile reload.

- **The style.** Made with `live_data=True`: the road layer reads the feature states that the metadata `roadstyle:live` names
  (`rs_c`, the colour; `rs_w`, a factor of the drawn width) on the road's row, with the baked value when there is no state. The
  metadata also gives the ramp (9 colours of the call's `cmap`, else viridis) and the no-data colour. The option `live` gives the
  same; without it `rsDashboard` reads the metadata.
- **The table.** An array of rows, an Arrow table (`toArray()`) or the URL of a JSON array. `key` names the column that is joined to
  the roads' `edge_id_col` (default), or `"row"` (the table's column `row` is the road's row).
- **The values.** `colorBy`: a number goes on the ramp from `vmin` to `vmax` (default: the data's range); a text gets a ramp colour
  for each value. A road without a value gets the no-data colour (`nodata: null` keeps its own colour). `widthBy`: a factor from
  `widthRange[0]` to `widthRange[1]` (default 1 to 3). `ramp` replaces the style's ramp. `stepped: true` gives each road the ramp's
  nearest stop, not a colour between two stops, and the legend shows the same steps.
- **The states.** `setFeatureState` on the role `simple` by row (`sourceLayer` only for a vector source). A vector source keeps the
  states for the tiles that load later. A second call replaces the values: a road with no new value loses the old one.
  `rs.clearData()` takes all of them away.
- **The legend and the popup.** The legend box shows the data's legend (`legend: false`: none; `legend: {title}`: another title),
  and the colour option's legend again after `clearData`. A road's properties include the joined fields (`RoadTable.props`), so the
  popup, the panel and the tooltip show them; a popup with a field list shows them after its fields.
- **The event.** `rs:datachange` (`rs.on("data", ...)`): `{rows, matched, colorBy, widthBy, ms}`.
- **Time** (`examples/dashboard_rust/live.html`, headless Chromium with software GL): Monaco, 13,298 roads: 14 ms for a colour,
  23 ms for a colour and a width, the map idle again 30 to 250 ms later. Tartu, 64,828 roads: 78 ms and 108 ms, idle about 100 ms
  later.

## The options

`rsDashboard(map, options)` takes one object. Each key has the name of a `render` keyword where one exists. The values are the
values that the page reads, which `render` makes from its keywords. The page has them in one JSON object, `RS_OPTIONS` (the
placeholder `__RS_OPTIONS__`, with the camera as `camera`).

| Option | From `render` | Default in `index.js` | Read by |
|---|---|---|---|
| `style` | the style object | `null`: the roads come later (`setStyle`) | `core.js` (the roles), `basemap.js` (the base map layer) |
| `prefix` | (none: the Python page adds the style as it is) | `""` | `core.js`, and each file that names a source or a layer |
| `road_table` | (none: the tiled page sets `window.RS_SIDE`) | `null` | `core.js` (`RoadTable`) |
| `live` | `live_data=True` (the Rust engine): `{color, width, types, ramp, nodata}` | the metadata `roadstyle:live`, else `null` | `live.js` |
| `basemaps` | `basemaps` | `[]` | `basemap.js` |
| `basemap_switcher` | `basemap_switcher` | `true` | `basemap.js` |
| `tiles` | `tiles` | `false` | `core.js` (the sidecar table `window.RS_SIDE`) |
| `sources` | the page's roles (`roadstyle:sources`) | `null`: the metadata, else the style's layers | `core.js` (`_src`, `RS_ROLES`), `filter.js` |
| `arrows` | the page's arrows (`roadstyle:arrows`) | the metadata, else `"points"` with an `arrows` source | `arrows.js` |
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
| `overlays` | `overlays`: `[{label, source, layers, popup, tooltip, interactive, under, base, select, color, visible, popup_window, kinds}]` (`kinds`: a base-map layer's `[[kind, count], ...]`, most first) | `[]` | `core.js`, `overlays.js`, `filter.js`, `select.js`, `features.js` |
| `modes` | a duckOSM map's modes: `[[mode, count], ...]` (`roadstyle:controls.modes`) | `[]` | `filter.js` |
| `box_layout` | `"stack"`: a base map's page (the Roads and Layers boxes folded, Layers under Roads); `"corner"`: the Layers box alone in its corner. On a screen 700 px wide or less (`panel._narrow`), every box (Roads, Layers, Legend) starts folded in both layouts, as the side panel starts closed | `"corner"` | `filter.js`, `overlays.js`, `panel.js` |
| `overlay_control` | `overlay_control` | `true` | `overlays.js` |
| `overlay_popup` | `overlay_popup` | `true` | `overlays.js` |
| `tunnel` | `tunnel_control` and the theme's tunnels: `{layers, control, strength, palette, palettes, ratio, ratios, toward, towards, to, steps}` | `{layers: {}, steps: [], control: false}` | `tunnel.js`, `arrows.js` |
| `fill_layers` | the road fill layer ids | `[]` | `svspot.js` |
| `pick` | the layers that a road is picked on (`roadstyle:controls`) | `[]`: the road layer of simple mode (a style with no interaction contract: a host's `makeStyle`, the level editor's style) | `select.js` |
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
| `color.js` | the Colour by menu, the recolouring, the road fill switch | `color_options`, `color_active`, `road_fill`; the states `rs_co`, `rs_top` (the full look: `rs_colors`, `rs_base`), `rs_ov_<n>`, `rs_fill_on`; the feature state `rs_c` | `rsSetColorField`, `rsColor`, `rsColorBase`, `rsSetRoadFill`, `RS_COLOR_OPTIONS` |
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

A limit of the Rust engine's style: the engine bakes each global state (`rs_co`, `rs_top`, `rs_fill_on`, `rs_tun_*`)
into the expressions, as `export_style` does. Thus on that style the legend shows the active option, but the Colour by menu,
`rsSetColorField`, `rsColor`, `rsColorBase`, `rsSetRoadFill` and the Tunnels box do not change the map. The hover and select glow
work, because they use feature-state. For a page that switches colours, the engine must keep these states as `global-state`.
The legend is correct only for option 0, because the metadata does not give the active option.

## Trusted inputs (audit N23)

The page puts the data into HTML only as text. `_esc` in `static/popup.js` escapes `&`, `<`, `>`, `"` and `'`, and every module uses it
for a data value that goes into HTML: a road's fields in the popup, the hover tooltip and the side panel, the search results, the
overlays' labels and fields, the legend's title, labels, colours and ends, the page's title in the side panel, and an error text. A road
name such as `<img src=x onerror=...>` shows as that text. The bundled sidebars (`templates/dashboard.html`, `report.html`) have their
own `esc` for the same values.

These inputs are HTML on purpose, from the page's author, and are not escaped:

- `side_panel_html`, the HTML of a host panel;
- the bundled sidebars' templates (`sidebar=`), and a host's own sidebar;
- the HTML that a host page gives to `rsInfoShow(html)` (the side panel's API).

Put data into these through `_esc`, or through `textContent`.

## Checks

- `pytest`: the tests read the options from the page's `RS_OPTIONS` object (`_opt(html, key)`).
- Screenshots of four Monaco pages (default; colour by with legend; panel with tunnels, overlays and a selected road; find and views),
  made with the old and the new code: the pixels are the same, and there are no page errors.
- `examples/dashboard_rust/` in a browser: the modules load as ES modules (strict mode) on a Rust-engine style, with no page errors.
  The popup, the hover tooltip, the glow, the search, Street View and 2D/3D work.
- `examples/dashboard_rust/tiles.html` in a browser: a mouse click on a road shows the properties from the road table (both
  directions of a pair) and lights the road on the tiles; after `setStyle` with another colouring the legend shows, there is one
  set of buttons, and the hover tooltip shows the fetched properties. No page errors.
