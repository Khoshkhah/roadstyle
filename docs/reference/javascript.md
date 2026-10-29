# JavaScript API

<p class="lead">Every <code>window.rs*</code> function, every <code>rs:*</code> event and every registry in a saved web map.</p>

Each built-in control is a thin UI over one of these functions, so a host page can drive the map
with the controls hidden. How to use them together: [Dashboards & JavaScript](../guides/dashboards.md).

## The `rs` object

`window.rs` (and the value that `rsDashboard(map, options)` returns) is one object for the whole page, with the edge ids of the roads
(`edge_id_col`, as text) in place of rows. The `window.rs*` functions below stay. Its state:

```js
{v: 1, selection, highlight, colorBy, colors, filter: {classes, bridges, tunnels, access, ids}, overlays: {label: {visible}},
 roadFill, tunnel, palette, view, basemap, view3d, camera: {center, zoom, pitch, bearing}, streetView: {mode}, google3d, panel}
```

| method | does |
|---|---|
| `rs.getState()` | the state now (a copy) |
| `rs.setState(part)` | applies a part of the state through the controls' functions (a saved view, a URL) |
| `rs.can(part)` | false for a part that this page cannot apply (an unknown key, a colour option the style does not have) |
| `rs.link()` | the part that differs from the start, as `#rs=` and base64url JSON; a page opened with it applies it |
| `rs.on(event, fn)` | `event`: `state` (each change, as the part of the state that changed), or `select`, `deselect`, `filter`, `color`, `overlay`, `tunnel`, `view`, `view3d`, `basemap`, `highlight`, `roadfill`, `streetview`, `google3d` (the `rs:*` event's `detail`); returns the function that removes it |
| `rs.select(id)`, `rs.highlight(ids)`, `rs.focus(ids)` | as `rsSelect`, `rsHighlight`, `rsFocus`, with edge ids (`null`: deselect) |
| `rs.query({column: value})`, `rs.find(text)`, `rs.props(id)` | edge ids of the roads that match; one road's properties |
| `rs.setColorBy(name)`, `rs.color([{color, ids}])`, `rs.setFilter({classes, bridges, tunnels, access, ids})` | as the controls |
| `rs.setOverlay(label, visible)`, `rs.setTunnelStyle(look)`, `rs.setView(name)`, `rs.setBasemap(key)` | as the controls |
| `rs.tools` | the toolbox: `add({id, title, icon, onClick})`, `bind`, `remove`, `open(id)`, `close(id)`, `list()`, and `ready()` (with `toolbar.hold`). The element of each tool has `data-rs-tool="<id>"`: this attribute stays, and the `title` goes to the tooltip at the first hover |
| `rs.sections` | the dashboard panel's sections: `add({id, html, el, label, after, before})`, `get`, `list`, `hide`, `show`, `remove`; event `rs:sectionchange` ([guide](../guides/dashboard-panel.md)) |
| `rs.colorModes` | the page's own "Colour by" list in the legend box (a live-data page has no colour options of the style): `set(["Traffic", "Counted?"], {active, onChange(name, index)})`, `select(name)`, `clear()`, `active`. Event `rs:colormode` (`detail.name`, `detail.index`) |
| `rs.naturalBreaks(values, k)` | the `k - 1` cut points (ascending) that split the numbers into `k` sets by Fisher-Jenks natural breaks: the `breaks` of `rs.setData` for a page that colours many calls the same way (an hour slider: the breaks of the whole day) |
| `rs.legend` | rows that the page adds to the legend: `add({id, color, label, shape})` (`shape`: `square`, `circle` or `line`) or `add({id, html})`, `remove(id)`, `list()` |
| `rs.setData(rows, options)` | live data (`live_data=True`): colour and size the roads from rows, an Arrow table or the URL of a JSON file; a second call replaces the values. `rs.clearData()` takes them away. `edge_id` must be text. Event `rs:datachange`; Promise `{rows, matched, ms}`; a number goes in `classes` sets by natural breaks, or in your `breaks` ([guide](../guides/live-data.md)) |
| event `rs:ready` | `window.rs` and the panel's sections are there; `window.rsReady` is true from then on. A `page_script` waits for it |
| `rs.setStyle(style)` | a new roads style (a page whose roads come later). The controls read the new style: its base-map layers (`ov<i>`) get their Layers box rows, hover and 3D switch, and the rows of the old style go. A switch that the person turned off stays off |
| `rs.sheet(n)` | the phone's bottom sheet: `rs.sheet()` is its height (0 closed, 1 40 %, 2 full; `null` when the page has no sheet), `rs.sheet(n)` sets it. Event `rs:sheetchange` |
| `rs.freeArea()` | the part of the map that the bar, the panel and the phone's sheet leave free, in window coordinates: `{lo, hi, top, bottom}`. A host page pads its map with it |
| `rsFirstPaint(first)` | for a host page that writes its own HTML: sets the classes of `<html>`, the panel's width and the phone class from `first_paint` of roadstyle-wasm's `hostOptions`, before the first paint. It is exported by `dashboard/template.js` |
| `rs.error` | `null`, or the error of a style whose interaction contract (`roadstyle:contract`) is newer than the dashboard reads, or whose generation (`roadstyle:generation`) is not the generation of its tiles: then the dashboard adds no road interaction for it (and, for the generation, shows a message and hides the vector layers). `setStyle` sets it again |
| `rs.contract` | the newest `roadstyle:contract` that the dashboard reads |
| `rs.destroy()` | removes the object's listeners |

```js
rs.on("state", part => history.replaceState(null, "", rs.link()));    // the URL follows the map
rs.setState({colorBy: "speed", filter: {bridges: false}});
```

## Functions

`layer?` is optional; see [the `layer` argument](#the-layer-argument).

| function | does | fires |
|---|---|---|
| **Query and act on id sets** | | |
| `rsQuery(p => bool, layer?)` | the ids of the features whose properties match | |
| `rsGetProps(ids, layer?)` | the rows behind the ids, internal fields removed | |
| `rsFilter(ids, layer?)` | show only these features; `null` resets. On roads it combines with the class, bridge and tunnel filters and hides every piece and every attached item (`Overlay(edge_col=...)`) of the other roads; on an overlay attached to edges it combines with its roads' filters and keeps each layer's position and order | `rs:filterchange` |
| `rsColor(ids, "#hex", layer?)` | paint the set one colour over the base colours, and draw it on top of the other roads on its level | `rs:colorchange` |
| `rsColor([[idsA, "#f80"], [idsB, "#08f"]])` | several sets at once, earlier pairs win overlaps (roads only) | `rs:colorchange` |
| `rsColor(null)` / `rsColor(null, null, layer)` | reset | `rs:colorchange` |
| `rsColorBase([[idsA, "#f80"], ...])` / `rsColorBase(null)` | recolour groups UNDER those of `rsColor`, for a host that paints its own roads: `rsColor` and `rsColor(null)` leave them | `rs:colorchange` (`base: true`) |
| `rsFind(text)` | the ids of the roads that match the text (a part of a popup field value or of an id; the docked panel's search); always defined, `find_control=True` adds the box | |
| `rsSetAccess(kind, on)` / `rsGetAccess()` / `RS_ACCESS` | with `access_col`: show / hide the roads of one access kind; `{kind: shown}`; `{kind: count}` | `rs:filterchange` (`access`) |
| `rsSetModes(list)` / `rsGetModes()` / `RS_MODES` | a duckOSM map: show only the roads that one of these modes (`driving`, `walking`, `cycling`) can use, from the road table's flags; `null` shows all. It combines with the other road filters. `RS_MODES`: `{mode: count}` from `roadstyle:controls.modes` | `rs:filterchange` (`modes`) |
| `rsSetKinds(label, list)` / `rsGetKinds(label)` / `RS_KINDS` | a base-map layer: show only these `kind` values (`null`: all), with the layer's own filter and `rsFilter`; `RS_KINDS`: `{label: {kind: count}}` from each overlay entry's `kinds` | `rs:filterchange` (`overlay`, `kinds`) |
| `rsSetInteraction(label, {clickable, tooltip, popup})` / `rsGetInteraction(label)` | a base-map layer: its clicks (and its hover colour), its hover tooltip (its field list, else its popup's, else every field) and its click popup. The start values are the overlay entry's `interactive`, `tooltip` and `popup_window` | `rs:interactionchange` (`overlay`, `clickable`, `tooltip`, `popup`) |
| `rsSetBuildings3D(on)` / `rsGetBuildings3D()` | the 3D buildings (the layer that a base-map overlay names in `extrude`): they show while this is on and their buildings layer is shown. A button under the 2D/3D button and a row under the buildings in the Layers box | `rs:buildings3dchange` (`on`) |
| `rsHighlight(ids, layer?)` | selection glow on the set; `[]` clears | `rs:highlightchange` |
| `rsFocus(ids, opt?, layer?)` | fit the camera to one id or a set; `opt` goes to MapLibre `fitBounds` (default `padding` 80, `maxZoom` 17) | |
| **Selection** | | |
| `rsSelect(id)` | select one road exactly like a click: glow, popup or panel | `rs:select` |
| `rsDeselect()` | clear the selection | `rs:deselect` |
| **Built-in controls** | | |
| `rsSetBasemap(keyOrIndex)` | switch the base map (key, label or index into `RS_BASEMAPS`) | `rs:basemapchange` |
| `rsSetClasses(list)` | show exactly these road classes | `rs:filterchange` |
| `rsSetBridges(on)` | show / hide every bridge and its 3D deck (the filter panel's *Bridges* row) | `rs:filterchange` |
| `rsSetTunnels(on)` | show / hide every tunnel, with its street names and arrows (the filter panel's *Tunnels* row) | `rs:filterchange` |
| `rsSetColorField(nameOrIndex)` | switch the active `color_options` entry | `rs:colorchange` |
| `rsSetTunnelStyle({strength, palette, ratio, toward})` | move the tunnel look: `strength` 0-100, `palette` a name of `RS_TUNNEL_PALETTES`, `ratio` `[dash, gap]`, `toward` a name of `RS_TUNNEL_TOWARDS` or a `#rrggbb` (any may be left out; another `toward` throws) | `rs:tunnelchange` |
| `rsSetView(nameOrIndex)` | apply a `views` entry: each setting it names, through the functions of this table | `rs:viewselect` (and each function's own event) |
| `rsSetRoadFill(on)` | show / hide the roads' own fill (`road_fill`); the casing stays. With `simple=True` every road piece is the one layer `roads-simple` (source `simple`), and this function, `rsColor` and `rsSetColorField` set it too | `rs:roadfillchange` |
| `rsSetOverlay(labelOrIndex, on)` | show / hide one overlay | `rs:overlaychange` |
| `rsSetView3D(on)` | tilt to `camera.pitch_3d`, or back to flat and north-up | `rs:viewchange` |
| `rsPanelShow(on)` | panel mode and `side_panel_html`: hide / show the side panel (a host panel's state is kept per page) | |
| **Street View** | | |
| `rsSetStreetView(on)` | open / close the Street View window (`street_view="window"` only; otherwise does nothing) | `rs:streetviewchange` |
| `rsSetGoogle3D(on)` | open / close the Google 3D window (`google_3d=True` only; otherwise does nothing) | `rs:google3dchange` |
| `rsG3dLayers.register(layer)` | add a layer to the Google 3D window: `{id, label, kind, features(selection, {bounds}) -> GeoJSON, style, arrows, scope, max, on, available()}`. The same `id` replaces a layer. `google_3d_layers` (Python) makes the same layers from a GeoJSON source | |
| `rsG3dLayers.list()` / `isOn(id)` / `setOn(id, on)` / `refresh()` | read the layers; show or hide one (kept per page); draw again | |
| `rsStreetViewStep(m)` | move the Street View spot `m` metres along the edge (negative = back), stopping at its ends; returns the new URL | `rs:streetviewmove` |
| `rsSetStreetViewMarker(on)` | show / hide the map marker at the Street View spot | |
| `rsSetStreetViewMarkerAt(lng, lat, heading)` | put the marker where a panorama stands, looking `heading` degrees (for a Street View that reports its own moves). The spot is snapped onto the road as drawn, in its lane: the clicked edge while the viewer is on it, else the nearest road on screen in the direction they walked; free only with no road within 20 m. `null` goes back to the edge spot; the next selection or step clears it | |
| `rsGetStreetViewSpot()` | where the Street View spot is now: `{id, properties, m, len, lng, lat, heading, roadHeading, onRoad, source}`, or `null` before any pick. `m` is metres along the edge from its start, `len` its length, `heading` where the viewer looks, `roadHeading` the edge's direction there. `source` is `"panorama"` when a Street View that reports its moves (Linked) put it there - current - and `"map"` after a click or step: in the keyless embed (Classic) the viewer may have walked on since. Off every road (`onRoad: false`) only `lng`, `lat`, `heading` are set | `rs:streetviewspot` |

## Events

All fire on `document` as `CustomEvent`s; read the fields from `e.detail`.

| event | when | `e.detail` |
|---|---|---|
| `rs:select` | a road, or an item attached to it (`Overlay(edge_col=...)`), is clicked, or `rsSelect` runs | `id` (the road's), `layer` (`null` from `rsSelect`, the MapLibre layer id from a click), `properties` (the road's), `overlays` (`[{label, fields, properties}]` of clickable overlays under the point, a clicked item among them), `item` (only for a `pick` item of `items=` (`overlay` "items") or an item of `Overlay(select="item")`: `{overlay, id, properties}`, the item itself, selected and highlighted in place of the road), `streetView` (URL or `null`), `twin` (`{id, properties}` of the other direction when the road is half of a pair drawn as one line, `single_line_classes`; else absent) |
| `rs:select` | a feature of an overlay that belongs to no road is clicked | `id`, `layer` and `overlay` (both the overlay label), `fields`, `properties` |
| `rs:deselect` | a click on empty map, or `rsDeselect` | none |
| `rs:filterchange` | `rsSetClasses` | `visible`, `hidden` (class lists) |
| | `rsSetBridges` | `bridges` |
| | `rsSetTunnels` | `tunnels` |
| | `rsFilter` on roads / an overlay | `ids` / `overlay`, `ids` |
| | `rsSetAccess` / `rsSetModes` / `rsSetKinds` | `access`, `visible` / `modes` / `overlay`, `kinds` |
| `rs:colorchange` | `rsSetColorField` | `option` (the `RS_COLOR_OPTIONS` entry), `index` |
| | `rsColor` with one set / several | `ids`, `color` / `groups: [{ids, color}]` |
| | `rsColor` on an overlay | `overlay`, `ids`, `color` |
| `rs:highlightchange` | `rsHighlight` | `ids` (plus `overlay` on an overlay) |
| `rs:basemapchange` | `rsSetBasemap` | `basemap` (key), `index` |
| `rs:overlaychange` | `rsSetOverlay` | `overlay` (label), `visible` |
| `rs:interactionchange` | `rsSetInteraction` | `overlay` (label), `clickable`, `tooltip`, `popup` |
| `rs:buildings3dchange` | `rsSetBuildings3D` | `on` |
| `rs:viewchange` | `rsSetView3D` | `view3d` |
| `rs:tunnelchange` | `rsSetTunnelStyle` | `strength`, `palette`, `ratio`, `toward` |
| `rs:viewselect` | `rsSetView` | `view` (name), `index` |
| `rs:roadfillchange` | `rsSetRoadFill` | `road_fill` |
| `rs:streetviewchange` | `rsSetStreetView` | `open` |
| `rs:google3dchange` | `rsSetGoogle3D` | `open` |
| `rs:streetviewmove` | `rsStreetViewStep` | `id`, `streetView`, `atStart`, `atEnd` |
| `rs:streetviewspot` | a pick, a step, a walk or turn in the panorama | the `rsGetStreetViewSpot()` object (or `null`) |

```js
document.addEventListener("rs:select", e => {
  if (e.detail.overlay) return;                 // an overlay click, not a road
  console.log(e.detail.properties.name, e.detail.streetView);
});
```

## Registries

Read-only globals for building your own controls.

| global | holds |
|---|---|
| `window.map` | the MapLibre `Map` (camera: `map.easeTo({pitch, bearing})`) |
| `RS_BASEMAPS` | `[{key, label, tiles, bg}]`, the switcher's base maps |
| `RS_CLASSES` | the road classes in the filter, in order |
| `RS_CLASS_COL` | the column `RS_CLASSES` came from |
| `RS_CLASS_COLORS` | `{class: fill colour}` |
| `RS_COLOR_OPTIONS` | `[{name, prop, legend}]`, the `color_options` entries |
| `RS_TUNNEL_TOWARDS` | `{name: "#rrggbb"}`, the colours a tunnel can move toward |
| `RS_TUNNEL_PALETTES` | `{name: [dash, gap] or null}`, the tunnel casing palettes (`null`: one colour) |
| `RS_VIEWS` | `[{name, set}]`, the `views` entries |
| `RS_OVERLAYS` | `[{label, source, layers, visible, color, popup, tooltip, under, interactive, …}]` |

## The `layer` argument

- Omitted or `null`: the roads.
- An overlay's `label` (or its index in `RS_OVERLAYS`): that overlay.
- Each layer has its own ids. Never pass ids from one layer to another.
- Every piece of a road belongs to its edge (docs/design/edge_items.md): the casing, the fill, the end caps, the one-way arrows and the street names (the edge under the middle of
  each), the bridge shadows and 3D decks (shown while any of their edges is), and every item attached with `Overlay(edge_col=...)`. `rsFilter` on the roads, the class filter and the
  bridge and tunnel switches hide them with their edge. Hovering an attached item highlights its road and clicking it selects the road. An overlay that belongs to no road
  keeps only its own `rsFilter(ids, label)`.

## Ids past 2**53

!!! warning "Use roadstyle's ids, not your `edge_id`"
    `rsSelect`, `rsColor`, `rsFocus` and the other functions take roadstyle's **feature ids**
    (the same ids as in `rs:select`), never your `edge_id`. A 64-bit `edge_id` does not fit a
    JavaScript number, so roadstyle stores big ids as strings. Look ids up by string:

    ```js
    const ids = rsQuery(p => String(p.edge_id) === "8121729169906061189");
    rsSelect(ids[0]); rsFocus(ids);
    ```

    Or add a small integer column in Python (`pidx = 0..n-1`) and query on it. In pandas, a column
    that mixes big ints and `None` turns into float64 and rounds the ids: use `dtype="Int64"`.

## The dashboard on another map

The controls and the road interaction of a saved page are ES modules in `roadstyle/static/dashboard/`. A page that makes its own
MapLibre map, for example from a style of roadstyle's Rust engine, can add them:

```js
import {rsDashboard} from "./dashboard/index.js";   // and link dashboard/dashboard.css and popup.css
const map = new maplibregl.Map({container: "map", style});
rsDashboard(map, {style, find_control: true});
```

Call `rsDashboard` immediately after you make the map. The options have the names of the Python keywords. The functions and events
on this page then work on that map. Roads that come later (vector tiles, a new style after each build): give `style: null`, the
`prefix` of their source and layer ids, and call `setStyle(style, {road_table})` (the road table of stage 1) on the
object that `rsDashboard` returns. `roadTable()` gives the table without the roads' lines (most of its bytes); give the table
`linesOf: rows => JSON.parse(new TextDecoder().decode(sources.roadLines(rows)))` (or a function that returns a Promise of the
lines, for an engine in a worker), and Street View and Google 3D get a road's line when they need it. `roadTable(fields, true)`
gives the lines in the table. A `LiveMap` has `roadLines(rows)` too, and `roadEnds()` (4 numbers for each row: the line's start
lon, lat and end lon, lat); the level editor on a host map reads the table's `endsOf()` (a Promise of them) for its end marks. Live data (a style made with `live_data=True`): `rs.setData(rows, {colorBy, widthBy})` colours
and sizes the roads from a table with no new style, and `rs.clearData()` takes it away. The options and the files:
`docs/design/dashboard_module.md` in the repository.

**See also:** [Dashboards & JavaScript](../guides/dashboards.md) · [Every parameter](parameters.md) · [Put it on a website](../guides/website.md)
