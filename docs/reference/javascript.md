# JavaScript API

<p class="lead">Every <code>window.rs*</code> function, every <code>rs:*</code> event and every registry in a saved web map.</p>

Each built-in control is a thin UI over one of these functions, so a host page can drive the map
with the controls hidden. How to use them together: [Dashboards](../guides/dashboards.md).

## The `rs` object

`window.rs` (and the value that `rsDashboard(map, options)` returns) is one object for the whole page, with the edge ids of the roads
(`edge_id_col`, as text) in place of rows. The `window.rs*` functions below stay. Its state:

```js
{v: 1, selection, highlight, colorBy, colors, filter: {classes, bridges, tunnels, access, ids}, fade, overlays: {label: {visible}},
 roadFill, tunnel, palette, view, basemap, view3d, camera: {center, zoom, pitch, bearing}, streetView: {mode}, google3d, panel}
```

| method | does |
|---|---|
| `rs.getState()` | the state now (a copy) |
| `rs.setState(part)` | applies a part of the state through the controls' functions (a saved view, a URL) |
| `rs.can(part)` | false for a part that this page cannot apply (an unknown key, a colour option the style does not have) |
| `rs.link()` | the part that differs from the start, as `#rs=` and base64url JSON; a page opened with it applies it |
| `rs.on(event, fn)` | `event`: `state` (each change, as the part of the state that changed), or `select`, `deselect`, `filter`, `color`, `overlay`, `tunnel`, `view`, `view3d`, `basemap`, `highlight`, `roadfill`, `fade`, `streetview`, `google3d`, `data`, `tool` (the `rs:*` event's `detail`); returns the function that removes it |
| `rs.select(id)`, `rs.highlight(ids, set?)`, `rs.focus(ids)` | as `rsSelect`, `rsHighlight`, `rsFocus`, with edge ids (`null`: deselect). `rs.highlight(ids, {set, color, opacity})` lights a named set in its own colour, as `rsHighlight` does. `rs.focus` fits the roads above the bottom dock where the dock covers the map |
| `rs.request.tile(source, z, x, y)`, `.rows(source, ids)`, `.row(source, id)`, `.query(sql, {signal})`, `.schema()`, `.frames(from, to)`, `.lines(ids)` | the four requests of the dashboard (`dashboard/adapter.js`): each one calls the page's **adapter** and throws an `Error` that says so when the page has none, or its adapter lacks that function ([the design](../design/memory_budget.md)) | |
| `rs.setAdapter(adapter)` | set the adapter of the page, an object with the optional functions `tile(source, z, x, y)`, `rows(source, ids)`, `lines(ids)`, `query(sql, {signal})`, `schema()`, `frames(from, to)` and `style()`; null removes it. The option `adapter` of `rsDashboard` does the same at the start. A road that the road table has not got (a page with no table: way D) is asked from `rows`: a selection and a hover tooltip wait for it, and all the rows that ask in one turn go in one request. `dataDock` takes its `query` and `schema` from the adapter when the host gives none | |
| `rsHttpAdapter(base)` | the adapter of way D (a local program at `base`, for example `http://127.0.0.1:8830`): it answers the four requests at `/style.json`, `/tiles/<source>/<z>/<x>/<y>`, `/rows/<source>`, `/lines`, `/query`, `/schema` and `/frames` ([the addresses](../design/memory_budget.md#step-2-one-interface-for-the-four-requests-2026-11-11)). In a module: `import {httpAdapter} from "./dashboard/ways.js"` | |
| `rsFilesAdapter(base, {pmtiles, query, schema})` | the adapter of way B (the files of `export_style(..., format="pmtiles")` at the URL `base`): the style from `style.json`, a tile from `roads.pmtiles` (with the PMTiles library), and the rows of the roads from `props.json`, read one time. `query` and `schema` are the host's, for example DuckDB-wasm on Parquet files. In a module: `import {filesAdapter} from "./dashboard/ways.js"` | |
| `rsEngineAdapter({tiler, sources, format, query, schema})` | the adapter of way C (the WebAssembly engine in the page): the style and the tiles of roadstyle-wasm's `Tiler`, and the fields and the line of a road from `sources` (a `Sources` of the same roads: `roadTable`, read one time, and `roadLines`). In a module: `import {engineAdapter} from "./dashboard/ways.js"` | |
| `rs.fade(ids, {opacity})` | every road that is not in `ids` is drawn at `opacity` (default 0.18) of its own opacity, with its arrows and names; `rs.fade(null)` ends it. `fade` in `rs.getState()`, event `rs:fadechange`. The data dock's Focus uses it ([guide](../guides/data-dock.md)) |
| `rs.holdPopup(key, on)` | a part that shows the facts itself holds the popups while it is in view: a selection (a click on the map, `rs.select`) then has no popup, for a road, a road's item or an overlay item, and the tooltip stays. Each `key` holds once; the popups come back when no key holds it. A page with `road_popup=False` keeps no road popup. The data dock's card and the Street View window use it ([guide](../guides/data-dock.md)) |
| `rs.holdHover(key, on)` | a host tool that works on other objects holds the road hover while it is on: no road lights up, no road tooltip, no pointer over a road, and a lit road goes off at once. A click still selects the road and sends `rs:select`. An overlay keeps its own hover (`rsSetInteraction`). Each `key` holds once; the hover comes back when no key holds it |
| `rs.holdSelectLook(key, on)` | while a key holds it, a selection of a road or an overlay item sets no `select` state, so the host draws its own selection. `rs:select` and `rs:deselect` still come. The look of the selection now goes off at once |
| `rs.query({column: value})`, `rs.find(text)`, `rs.props(id)` | edge ids of the roads that match; one road's properties |
| `rs.setColorBy(name)`, `rs.color([{color, ids}])`, `rs.setFilter({classes, bridges, tunnels, access, ids})` | as the controls |
| `rsSetOverlays(on)`, `rsGetOverlays()` | all the style's base-map layers together (`window.rsSetOverlays`): on is each layer as the style starts it, off hides all; the one switch of the base-map box (its label is `overlays_label`, default "Map layers"). Event `rs:overlayschange`. A page with a bar has no Layers box: the legend box lists the layers with their colours |
| `rs.setOverlay(label, visible)`, `rs.setTunnelStyle(look)`, `rs.setView(name)`, `rs.setBasemap(key)` | as the controls |
| `rs.basemaps()` | the page's base maps as `[{key, label}]`, for `rs.setBasemap` (Ask's `get_map` uses it) |
| `rs.tools` | the toolbox: `add({id, title, icon, onClick})`, `bind`, `remove`, `open(id)`, `close(id)`, `list()` (each tool with its `kind`, `open` and `disabled` state; a tool that the page cannot use is greyed out, and its title says why), and `ready()` (with `toolbar.hold`). `rs.on("tool", fn)` tells of each open, close and press. The built-in tools are `theme`, `navigate` (with `navigation: "buttons"`: `zoom_in`, `zoom_out`, `compass`), `street_view`, `google_3d`, `basemap`, `roads`, `buildings`, `legend`, `settings`, `attribution` and `panel_show`. The element of each tool has `data-rs-tool="<id>"`: this attribute stays, and the `title` goes to the tooltip at the first hover |
| `rs.ready` | `ready(fn)`: runs `fn` now if the page is ready, else on `rs:ready` |
| `rs.svg` | `svg(parent, tag, attrs, text?)`: one SVG element of a chart; a value that starts with `var(` goes to the style ([guide](../guides/dashboard-parts.md)) |
| `rs.kpi` | the HTML of one number tile: `kpi(title, value, sub, color?)`, for a `<div class="rs-kpis">` ([guide](../guides/dashboard-parts.md)) |
| `rs.tabs` | tabs, the two-way switch, a tool row (`rs-toolrow`) and rows that a click selects (`rs-rows`, ↓ ↑ too; no row selected at the start): `use(nav, onChange)` returns `{select(id), current()}` ([guide](../guides/dashboard-parts.md)) |
| `rs.toggle` | `toggle(button, onChange)`: a button that stays pressed (`aria-pressed`) until the next click; returns `{set(on, quiet), value()}` ([guide](../guides/dashboard-parts.md#a-toggle-button)) |
| `rs.days` | the day picker of a page: `use(el, {days, value, label, onChange})` returns `{set(day, quiet), value()}`. `days` are "YYYY-MM-DD"; `onChange` can give a promise ([guide](../guides/dashboard-parts.md#a-day-picker)). `range(el, {unit, min, max, days, value, label, onChange})`: a period, `unit` `"day"` (from a day to a day), `"week"` (Monday to Sunday) or `"month"`; returns `{set([from, to], quiet), value(), unit(u)}` ([guide](../guides/dashboard-parts.md#a-date-range-a-week-or-a-month)) |
| `rs.hours` | the hour picker: `use(el, {value, range, hours, label, onChange})`, a field that opens a list of the hours. One hour: `value` 8 is 08:00–09:00. `range: true`: `value` `[7, 9]` is the hours 7 to 9 (From 07:00, To 10:00). Returns `{set(v, quiet), value()}` ([guide](../guides/dashboard-parts.md#an-hour-picker)) |
| `rs.slider`, `rs.number`, `rs.colorPick` | `slider(el, {label, min, max, step, value, unit, format, onInput, onChange})` (`value: [a, b]`: two handles), `number(el, {label, min, max, step, value, unit, snap, disabled, onChange})` (a typed value goes to the nearest `step`; `snap: false` keeps it, and the "−" and "+" buttons still change it by one `step`; `disabled: true` or `disabled(on)` on the handle switches the box and both buttons off), `colorPick(el, {label, value, palette, onChange})`; each returns `{value(), set(v, quiet)}`, and `number` also `disabled(on)` ([guide](../guides/dashboard-parts.md#a-slider)) |
| `rs.search` | `search(el, {placeholder, label, button, end, suggest, onPick, onSubmit, onClear, max, wait, none})`: a search field; `suggest(text)` gives `{label, sub, value}` rows or a promise of them. `end` is an element (an icon button) that goes inside the field at its right end. Returns `{value(), set(text), focus(), clear()}` ([guide](../guides/dashboard-parts.md#a-search-field)) |
| `rs.drop` | `drop(el, {accept, multiple, text, hint, onFiles, onClear})`: a file drop zone; returns `{files(), clear()}` ([guide](../guides/dashboard-parts.md#a-file-drop-zone)) |
| `rs.progress`, `rs.busy` | `progress(el, {label, value, text})` returns `{set(fraction \| null, text)}` (`null`: no known value); `busy(button, promise \| boolean)` puts a turning ring on the button and disables it until the promise ends ([guide](../guides/dashboard-parts.md#a-progress-bar-and-a-busy-button)) |
| `rs.mapBusy` | `mapBusy(text)`: a light veil over the free part of the map (`rs.freeArea()`) with a ring and `text` in a pill; a second call changes the text; `mapBusy(null)` takes it away. The pointer goes through it ([guide](../guides/dashboard-parts.md#a-busy-map)) |
| `rs.toast`, `rs.confirm` | `toast(html, {kind, ms, action: {label, onClick}})`: `kind` `info`, `ok`, `warn` or `error`, it goes after 4, 4, 6 or 8 s (`ms: 0`: it stays); returns `{close()}`. `confirm({title, text, ok, cancel, danger})`: a promise of `true` or `false`, in place of `confirm()` ([guide](../guides/dashboard-parts.md#a-toast-and-a-status-line)) |
| `rs.menu` | `menu(button, items)`: the action menu of a button, `items` `{label, icon, danger, disabled, onClick}` or `"-"`; returns `{open(), close(), set(items)}`. `menu.button(items, title)` makes a "⋯" button with its menu ([guide](../guides/dashboard-parts.md#an-action-menu)) |
| `rs.more` | `more(el, {items, page, noun, render})`: the first `page` rows of a list and "Show more"; returns `{set(items), shown()}` ([guide](../guides/dashboard-parts.md#show-more)) |
| `rs.panel` | `panel.bar()`: the fixed bar at the bottom edge of the panel, under the cards (empty: not shown; hidden while an editor frame is open) ([guide](../guides/dashboard-parts.md#the-panels-fixed-bar)) |
| `rs.frame` | the frame of an editor that uses the whole panel: `frame({panel, title, back, tabs, head, id, label})` returns an `EventTarget` with `root`, `top` (the title line), `head` (the head row that does not scroll), `body`, `bar`, `open(tab)`, `close()`, `isOpen()` and `tab(name)`. `tabs` is a list of `[id, name]` and goes into the head row; `head` is an element of the editor for the head row (for example its own tools, in place of tabs). The events are `back` and `tab` (`detail.tab`). Edit design uses it ([guide](../guides/dashboard-parts.md#an-editor-in-the-panel)) |
| `rs.dock` | the bottom dock under the map: `add({id, label, el, note, actions, closable})`, `remove(id)`, `open(id?)`, `close()`, `isOpen()`, `show(id)`, `note(id, text)`, `height(px?)`, `list()`. `table({columns, rows, idColumn, more, onSort})` gives `{el, set({columns, rows, more}), rows(), sort()}`: the dock's table (a 64-bit id exactly, a header click sorts, a row click with `idColumn` selects the road). Event `rs:dockchange` ([guide](../guides/dashboard-layout.md#the-bottom-dock)) |
| `rs.chart(el, spec)` | a chart of rows in `el`: `{kind, columns, rows, x, y, title, count, values, onPick, small}`, `kind` one of `bar`, `line`, `histogram`, `scatter`, `pie`. It gives `{set(change), spec(), svg(), destroy()}`. `rs.chart.ranges(numbers, parts)` gives about `parts` ranges of many numbers: `{n, of(v), label(k)}` ([guide](../guides/dashboard-parts.md#a-chart)) |
| `rs.hover` | the page's hover box: `show(html, event)`, `hide()`, `on(node, html \| fn)` ([guide](../guides/dashboard-parts.md)) |
| `rs.help` | the page's help window: `set({title, intro, terms: [[term, text], ...], note, anchor})` adds the "?" button to the panel's title (or to the element `anchor`) and keeps the window, `button(el, {title, ...})` adds a "?" button with words of its own to `el`, `get()` (the words now), `clear()`, `open({title, ...})`, `close`; event `rs:helpchange` ([guide](../guides/dashboard-parts.md)) |
| `rs.sections` | the sections of the dashboard panel (the panel starts empty): `add({id, html, el, part, text, fields, label, step, after, before, fold, open, note, background})` adds a section and returns its box. It holds your HTML (`html`), your element (`el`) or a part of roadstyle (`part`: `"query"`, `"road_card"` or `"chart"`; the chart's options are in `chart`, [Charts](../guides/dashboard-parts.md#a-chart)). A section with a `label` is a card with that title; `background: false` takes the card's colour away. With `fold: true` (and a `label`) its title is a button, the row has a chevron, a click hides its body, and the browser keeps the state. With `open` (a function, and a `label`) the card is one button that runs `open(card)` on a click anywhere on it (not in its body) or Enter on its title; its row has a pencil (`icon`: `"edit"`, `"ask"` or an `<svg>`), it has a thin edge and no background (`background: true`: a light tint of the accent colour), it never folds, and a disabled title button keeps it from opening. `note` is one line of state under the title of a card; `note(id, text)` changes it. `list()` gives the ids in order. `get(id)` gives the box of a section, so that you can move it into your own tab. `hide(id)`, `show(id)` and `remove(id)` hide, show and remove a section. `fold(id, on)` and `foldAll(on)` fold or unfold one section that folds, or all of those that are shown (a hidden one keeps its state). `folded(id)` tells whether one is folded. `step: 3` puts the number 3 in a round badge before the title of a card, and `done(id, on)` changes the number to a check mark (a card with no `step` gets the mark alone). `button(id, {icon, title, onClick})` puts an icon button after the title of a card; its click does not fold or open the card. The title row of the panel has one button, "Collapse all" / "Expand all", that does `foldAll`; it shows when a section folds. Event `rs:sectionchange` ([guide](../guides/dashboard-manual/javascript.md#the-same-from-javascript)) |
| `rs.colorModes` | the page's own "Colour by" list in the legend box (a live-data page has no colour options of the style): `set(["Traffic", "Counted?"], {active, onChange(name, index)})`, `select(name)`, `clear()`, `active`. Event `rs:colormode` (`detail.name`, `detail.index`) |
| `rs.naturalBreaks(values, k)` | the `k - 1` cut points (ascending) that split the numbers into `k` sets by Fisher-Jenks natural breaks: the `breaks` of `rs.setData` for a page that colours many calls the same way (an hour slider: the breaks of the whole day) |
| `rs.legend` | rows that the page adds to the legend: `add({id, color, label, shape})` or `add({id, html})`, `remove(id)`, `list()`. `shape` is the mark of what the page draws in this colour: `square` (default), `circle` or `line` |
| `rs.setData(rows, options)` | live data (`live_data=True`): colour and size the roads from rows, an Arrow table or the URL of a JSON file; a second call replaces the values. `rs.clearData()` takes them away. `edge_id` must be text. Event `rs:datachange`; Promise `{rows, matched, ms}`; a number goes in `classes` sets by natural breaks, or in your `breaks` ([guide](../guides/dashboard-manual/javascript.md#live-data-a-new-day)) |
| `rs.vehicles` | a traffic microsimulation run on the map ([the design](../design/vehicles_spec.md)): `load({wasm, fcd, net, routes, options?, colours?})` (a Promise of the run's report; `options` and `colours` default to the look's `vehicles` section), `play()`, `pause()`, `seek(t)`, `speed(x)`, `time()`, `playing()`, `count()` (the vehicles drawn now), `ids()`, `report()` (`samples`, `vehicles`, `t0`, `t1`, `lanes_unknown`, `path_gaps`, `teleports`). The page option `vehicles` loads a run at start |
| event `rs:ready` | `window.rs` and the panel's sections are there; `window.rsReady` is true from then on. It fires once: a listener added later never runs, so wait with `rs.ready(fn)` |
| `rs.setStyle(style)` | a new roads style (a page whose roads come later). Every control that a style gives follows each new style: the `roads` tool and its classes, the Tunnels box, the arrows' icon and rules, the boundary's shade and limits, the base-map layers (`ov<i>`) with their switch, hover and 3D switch, the pick layers, the id fields and the parts of `rs.getState()`. They go with a style that has none. A switch that the person turned off stays off. The selection, the hover, the glow of `rsHighlight` and every highlight set go: they were on the rows of the old roads. A part that wants its set on the new roads sets it again. A host's look must be live (`state="live"`) for the style to have the controls |
| `rs.roadLayers({prefix, before, also})` | `roadLayers` of `dashboard/roadlayers.js` on this map and this dashboard, for a page that has the dashboard in one file and cannot import the module. The dashboard then reads the roads with `prefix` (default `"rs-"`), also in a page that was made with no prefix: `show(style)` puts a new roads style on the map (the old roads go first), `reloadTiles()`, `remove()` ([Use roadstyle in the browser](../rust/browser.md#put-the-roads-on-your-map-roadlayers)) |
| `rs.restyle(style, {also, imagePrefix})` | a new look on the same tiles (the style of `LiveMap.setLook`): each road layer on the map takes the new style's paint, layout and filter, the style's images come again, and the controls read the new style (`rs.setStyle`). The sources, the tiles and the live colours stay. `also`: more id prefixes, for copies of the road layers; `imagePrefix`: the host's prefix of the image names. A Promise of `false` when the new style has other layers: then draw a new map ([the design panel](../guides/design-panel.md)) |
| `rs.prefix` | the prefix of the roads style's ids on the map (the option `prefix`) |
| `rs.sheet(n)` | the phone's bottom sheet: `rs.sheet()` is its height (0 closed, 1 40 %, 2 full; `null` when the page has no sheet), `rs.sheet(n)` sets it. The grip of the sheet has a button that goes one height down, and up from closed. Event `rs:sheetchange` |
| `rs.freeArea()` | the part of the map that the bar, the panel and the phone's sheet leave free, in window coordinates: `{lo, hi, top, bottom}`. A host page pads its map with it |
| `rsFreePad()` | the free part of the window as the `padding` of a camera: `{top, right, bottom, left}`, 30 px at least, more where the panel, the sheet or the bar covers the map. The page's first `fitBounds` uses it; a host page that fits the map itself can call it |
| `rsFirstPaint(first)` | for a host page that writes its own HTML: sets the classes of `<html>`, the panel's width and the phone class from `first_paint` of `data/host_options.json`, before the first paint. It is exported by `dashboard/template.js` |
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
| `rsQuery(p => bool, layer?)` | the ids of the features whose properties match. An overlay in tiles (a one-file page) reads its rows, which hold all its properties; a page of the map worker has no rows for it and gets an empty list | |
| `rsGetProps(ids, layer?)` | the rows behind the ids, internal fields removed | |
| `rsFilter(ids, layer?)` | show only these features; `null` resets. On roads it combines with the class, bridge and tunnel filters and hides every piece and every attached item (`Overlay(edge_col=...)`) of the other roads; on an overlay attached to edges it combines with its roads' filters and keeps each layer's position and order | `rs:filterchange` |
| `rsColor(ids, "#hex", layer?)` | paint the set one colour over the base colours, and draw it on top of the other roads on its level | `rs:colorchange` |
| `rsColor([[idsA, "#f80"], [idsB, "#08f"]])` | several sets at once, earlier pairs win overlaps (roads only) | `rs:colorchange` |
| `rsColor(null)` / `rsColor(null, null, layer)` | reset | `rs:colorchange` |
| `rsColorBase([[idsA, "#f80"], ...])` / `rsColorBase(null)` | recolour groups UNDER those of `rsColor`, for a host that paints its own roads: `rsColor` and `rsColor(null)` leave them | `rs:colorchange` (`base: true`) |
| `rsFade(ids, {opacity}?)` | as `rs.fade`, with roadstyle's feature ids; `rsFade(null)` ends it | `rs:fadechange` |
| `rsFind(text)` | the ids of the roads that match the text (a part of a popup field value or of an id; the docked panel's search); always defined, `find_control=True` adds the box | |
| `rsSetAccess(kind, on)` / `rsGetAccess()` / `RS_ACCESS` | with `access_col`: show / hide the roads of one access kind; `{kind: shown}`; `{kind: count}` | `rs:filterchange` (`access`) |
| `rsSetModes(list)` / `rsGetModes()` / `RS_MODES` | a duckOSM map: show only the roads that one of these modes (`driving`, `walking`, `cycling`) can use, from the road table's flags; `null` shows all. It combines with the other road filters. `RS_MODES`: `{mode: count}` from `roadstyle:controls.modes` | `rs:filterchange` (`modes`) |
| `rsSetKinds(label, list)` / `rsGetKinds(label)` / `RS_KINDS` | a base-map layer: show only these `kind` values (`null`: all), with the layer's own filter and `rsFilter`; `RS_KINDS`: `{label: {kind: count}}` from each overlay entry's `kinds` | `rs:filterchange` (`overlay`, `kinds`) |
| `rsSetInteraction(label, {clickable, tooltip, popup})` / `rsGetInteraction(label)` | a base-map layer: its clicks (and its hover colour), its hover tooltip (its field list, else its popup's, else every field) and its click popup. The start values are the overlay entry's `interactive`, `tooltip` and `popup_window` | `rs:interactionchange` (`overlay`, `clickable`, `tooltip`, `popup`) |
| `rsSetArrows(on)` / `rsArrowsOn()` / `rsHasArrows()` (also exports of `dashboard/arrows.js`) | the one-way arrows of the roads: the row "One-way arrows" of the base-map box shows the same state, and this browser keeps it (`rs-top:arrows`). `rsHasArrows()` tells whether the map has arrow layers; the row hides when it has none | `rs:arrowschange` (`on`) |
| `rsSetBuildings3D(on)` / `rsGetBuildings3D()` | the 3D buildings (the layer that a base-map overlay names in `extrude`): they show while this is on and their buildings layer is shown. A row under the buildings in the Layers box of a map page is the switch. While these buildings are on, the buildings of a vector base map are not drawn, and the base-map box's row for them is off | `rs:buildings3dchange` (`on`) |
| `rsSetWalls(w)` / `rsSetWallStyle(s)` / `rsHasWalls()` (`dashboard/walls.js`) | the 3D walls by type, over the 3D buildings of `rsSetBuildings3D`. `w` is a GeoJSON FeatureCollection from the page (`null` removes it): a LineString is one wall with `type` (`front`, `back`, `side`, `party`, `court`), `height`, `base` (metres) and `azimuth` (the compass direction of its outward normal); a Polygon or a MultiPolygon is the roof of a building with `height`. Or `w` is a function that gives the walls (or a Promise of them): it runs once, when the walls first show (`on` and the 3D buildings shown), and gives a FeatureCollection, `null`, or the vector source of wall tiles that roadstyle-wasm's `LiveMap.setWalls(bytes)` returns (the map worker cuts the walls into the tile layer `walls`; [Edit the design](../guides/design-panel.md#the-3d-walls)). A large area gives a function: then the page has no wall data until the walls show. The page gets the heights from roadstyle-wasm's `buildingHeights(look, rows)`, so they are the heights of the tiles. Each wall is a strip of 0.4 m on the outer side of its line, from the base to 0.25 m over the height; a roof is a slab of 0.25 m. `s` = `{on, front, back, side, party, court, roof, roof_dark}` (colours as `#rrggbb`; `roof_dark` is the roof in the dark theme); no argument gives the style now. The walls show while `on` is true and the 3D buildings show. A FeatureCollection is a GeoJSON source; a vector source is tiles. `rsHasWalls()` is true when the page gave walls (a function: until it gave none) | |
| `rsBuildings(on)` | the 3D buildings of a vector base map (OpenFreeMap): the switch of the *3D buildings* row in the base-map box. It moves nothing. A person's click on the switch also tilts a flat map to 55° and zooms in to 15 when the zoom is under 14.5 (where the buildings start); off, it flattens the map again if that switch tilted it | |
| `rsBuildingsOpacity(value)` | the opacity of the 3D buildings of a vector base map, from 0 to 1: the *Opacity* slider under the *3D buildings* row of the base-map box (the slider shows only while that row is on). No argument: the opacity now. Another value throws. The start is `buildings_opacity=`, else `ontop.buildings.opacity` of `data/basemaps.json` (1, solid). At 1 a road behind a building does not show through the roof | `rs:buildingsopacitychange` (`opacity`) |
| `rsHillshade(on)` / `rsTerrain(on)` | the *Hillshade* and *3D terrain* switches of the base-map box, from the area's ground (the page option `ground`, `rsGround`), else from the DEM of `ontop.dem` (the AWS Terrain Tiles). No argument: whether it is on. They move no camera (a person's click on the terrain row tilts a flat map to `ontop.terrain.pitch`). With the terrain on, every layer lies on the ground of the DEM: a tunnel is drawn on the hill above it and a bridge on the valley under it, because MapLibre has no height of its own for a line. The roads are flat with the terrain off. | `rs:terrainchange` (`on`) |
| `rsGround(ground)` | the area's ground (the page option `ground`): from now on, the hillshade and the 3D terrain come from its terrain file. `ground`: `{id, source, product, vertical_datum, resolution_m, license, terrain}`, and `terrain` is a URL, a `File` or `Blob` (a file in the browser disk, OPFS: the page reads one tile at a time), an `ArrayBuffer` or a `Uint8Array`. `null`: the AWS Terrain Tiles. A hillshade or a terrain that is on stays on. No argument: the ground now. The terrain comes when the file's header is read | `rs:groundchange` (`ground`), `rs:terrainchange` |
| `rsTunnelsOpacity(value)` | the opacity of the tunnels while the 3D terrain is on, `0` (hidden) to `1` (shown): the slider Tunnels under 3D terrain (base-map box). No argument: the opacity now (the person's, else the mode's of `rsTerrainTunnels`) | `rs:tunnelsopacitychange` (`opacity`) |
| `rsTerrainTunnels(mode)` | what a tunnel does while the 3D terrain is on: `"show"`, `"fade"` (the default) or `"hide"`; no argument: the mode now; another value throws. MapLibre has no height for a line, so a per-edge height (a `z` column) cannot be drawn | |
| `rsHighlight(ids, layer?)` | selection glow on the set; `[]` clears | `rs:highlightchange` |
| `rsHighlight(ids, {set, color, opacity?})` | a highlight set: the roads of the named set in `color` (a CSS colour), at the road's own width at every zoom. `opacity` (0 to 1) mixes the colour with the road's fill; the default is the look's `selection.opacity`. More than one set can be on. When a road is in two sets, the set that you set last has the road. When that set clears, the road gets the colour of the other set again. `rsHighlight([], {set})` clears only that set. A bridge road lights its 3D deck too. The colour is over the select and hover glow. The road layer reads the feature states `rs_hl` (the colour) and `rs_hlo` (the opacity) on the road's row | `rs:highlightchange` (`set`, `ids`) |
| `rsFocus(ids, opt?, layer?)` | fit the camera to one id or a set; `opt` goes to MapLibre `fitBounds` (default `padding` 80, `maxZoom` 17) | |
| **Selection** | | |
| `rsSelect(id)` | select one road exactly like a click: glow, popup, and the road card when the page has one | `rs:select` |
| `rsDeselect()` | clear the selection | `rs:deselect` |
| **Built-in controls** | | |
| `rsSetBasemap(keyOrIndex)` | switch the base map (key, label or index into `RS_BASEMAPS`) | `rs:basemapchange` |
| `rsSetClasses(list)` | show exactly these road classes | `rs:filterchange` |
| `rsSetBridges(on)` | show / hide every bridge and its 3D deck | `rs:filterchange` |
| `rsSetBridges3D(on)` | draw the bridges as 3D decks (on) or as flat lines (off); no argument: whether they are 3D. A page with no decks (`view_3d=False`) stays flat | `rs:bridges3dchange` |
| `rsBridgeGroups()` | the groups of bridge roads that touch each other: `[{group, roads, height, set}]`, the largest first | |
| `rsSetBridgeHeight(target, metres)` | give the whole group of `target` (a group number, a road row, or a list of them) the full height `metres`; `null` gives the height of the look back. The ramps keep the length that the engine made | `rs:bridgeheightchange` |
| `rsBridgeHeight(target)` | the full height of the group of `target`, in metres | |
| `rsSetTunnels(on)` | show / hide every tunnel, with its street names and arrows | `rs:filterchange` |
| `rsSetColorField(nameOrIndex)` | switch the active `color_options` entry | `rs:colorchange` |
| `rsSetTunnelStyle({strength, palette, ratio, toward})` | move the tunnel look: `strength` 0-100, `palette` a name of `RS_TUNNEL_PALETTES`, `ratio` `[dash, gap]`, `toward` a name of `RS_TUNNEL_TOWARDS` or a `#rrggbb` (any may be left out; another `toward` throws) | `rs:tunnelchange` |
| `rsSetView(nameOrIndex)` | apply a `views` entry: each setting it names, through the functions of this table | `rs:viewselect` (and each function's own event) |
| `rsSetRoadFill(on)` | show / hide the roads' own fill (`road_fill`); the casing stays. Every road piece is in the road layer `roads-simple` (source `simple`) and its dash layer `roads-simple-dash`; this function, `rsColor` and `rsSetColorField` set it too | `rs:roadfillchange` |
| `rsSetOverlay(labelOrIndex, on)` | show / hide one overlay | `rs:overlaychange` |
| `rsSetTheme("light" \| "dark")` | switch the page theme (a base map with a dark twin follows it) | `rs:themechange` |
| `rsOpenSettings()` | open the settings box | |
| `rsAddTopRow({id, label, get, set, available?})` | add a check box for a layer of the page under "On top" in the base-map box; `get()` tells whether it shows, `set(on)` shows or hides it, `available()` false greys the row | `rs:toprowschange` |
| `rsLabelsOn()` | whether the map labels are on (one state for the map and the Google 3D window) | `rs:labelschange` |
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
| `rs:highlightchange` | `rsHighlight` | `ids` (plus `overlay` on an overlay, or `set` for a highlight set) |
| `rs:themechange` | `rsSetTheme`, the theme button | `theme` (`light` or `dark`) |
| `rs:basemapchange` | `rsSetBasemap` | `basemap` (key), `index` |
| `rs:overlaychange` | `rsSetOverlay` | `overlay` (label), `visible` |
| `rs:interactionchange` | `rsSetInteraction` | `overlay` (label), `clickable`, `tooltip`, `popup` |
| `rs:buildings3dchange` | `rsSetBuildings3D` | `on` |
| `rs:arrowschange` | `rsSetArrows`, the row "One-way arrows" of the base-map box | `on` |
| `rs:toprowschange` | your page, when it changes the state of a row of `rsAddTopRow` (the base-map box reads the row again) | none |
| `rs:viewchange` | `rsSetView3D` | `view3d` |
| `rs:tunnelchange` | `rsSetTunnelStyle` | `strength`, `palette`, `ratio`, `toward` |
| `rs:viewselect` | `rsSetView` | `view` (name), `index` |
| `rs:roadfillchange` | `rsSetRoadFill` | `road_fill` |
| `rs:streetviewchange` | `rsSetStreetView` | `open` |
| `rs:google3dchange` | `rsSetGoogle3D` | `open` |
| `rs:streetviewmove` | `rsStreetViewStep` | `id`, `streetView`, `atStart`, `atEnd` |
| `rs:streetviewspot` | a pick, a step, a walk or turn in the panorama | the `rsGetStreetViewSpot()` object (or `null`) |
| `rs:ready` | the page is ready; it fires once | an empty object |
| `rs:sectionchange` | `rs.sections` adds, removes, hides, shows or folds a section | `id`, `state` (`add`, `remove`, `hide`, `show`, `fold` or `unfold`) |
| `rs:chartpick` | a click on a mark of a chart card that has `data` ([Charts](../guides/dashboard-parts.md#a-chart)) | `id` (the section), `row` (the values of the mark), `rows` (the indices of the rows of `data` in it) |
| `rs:dockchange` | the bottom dock opens, closes, changes its content or its height | `open`, `id`, `height` (0 on a phone) |
| `rs:dockreset` | the person clicks Reset in the data dock (or the host calls `data.reset()`): the colour layers, the focus, the lit roads, the selected road and the table are gone | `id` (the dock's id) |
| `rs:fadechange` | `rs.fade` fades the other roads, or ends it | `ids` (rows; `null`: no fade) |
| `rs:helpchange` | the help window opens or closes | `open`, and `title` when it opens |
| `rs:colormode` | `rs.colorModes` picks a mode | `name`, `index` |
| `rs:datachange` | `rs.setData`, `rs.clearData` | `rows`, `matched`, `colorBy`, `widthBy`, and `ms` from `rs.setData` |
| `rs:vehicleload` | `rs.vehicles.load` | the run's report |
| `rs:vehicletime` | the vehicles' clock, at most 4 times a second | `t` (seconds of the run) |
| `rs:toolchange` | a tool opens, closes or is pressed | `id`, `state` (`open`, `close` or `press`) |
| `rs:toolsready` | the page has added its tools (`rs.tools.ready()`) | none |
| `rs:sheetchange` | the phone's bottom sheet changes its height | `height` (0, 1 or 2) |
| `rs:layoutchange` | the side or the look of the panel changes | `panel` (the side) or `look` |
| `rs:basemapready` | a vector base map has loaded its layers | `key`, `vector` |
| `rs:buildingschange` | the 3D buildings of the base map switch | `on`, `vector` |
| `rs:buildingsopacitychange` | the opacity of the 3D buildings of the base map changes (the slider or `rsBuildingsOpacity`) | `opacity` |
| `rs:labelschange` | the map labels switch | `on` |
| `rs:overlayschange` | the list of overlays changes (the one switch of the base-map layers) | `visible` |
| `rs:g3dmodechange` | the mode of the Google 3D window changes | none |
| `rs:stylechange` | `rs.setStyle` (and `rs.restyle`) gave the dashboard a new style: a part that paints on the road layers paints again | none |
| `rs:tableready` | the table of the level editor is ready | none |

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
| `RS_DOCK` | the look's `dock` section: `{result, selected, roles, role_series}`, the colours of the data dock's objects on the map (`{light, dark}` each); the kinds of the dock need it |
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

## Drive the map from your own page

`m.html` is the saved page as a string. Put your own panel before `</body>`, and talk to the map through the `window.rs*` functions and the `rs:*` events of this page:

```python
m = rs.render_edges(edges, palette="mono")
panel = """
<div id="side" style="position:fixed;top:0;right:0;bottom:0;width:320px;background:#fff"></div>
<style>#map{right:320px!important} body{--rs-side:320px}</style>
<script>
map.once("load", () => {                  // the roads are queryable once the map loads
  const ids = rsQuery(p => p.name === "Götgatan");
  rsColor(ids, "#e63946"); rsFocus(ids);
});
document.addEventListener("rs:select", e => {
  document.getElementById("side").textContent = JSON.stringify(e.detail.properties);
});
</script>"""
open("host.html", "w").write(m.html.replace("</body>", panel + "</body>"))
```

!!! warning "Traps of a host page"
    - **Ids past 2**53.** See [Ids past 2**53](#ids-past-253).
    - **A fixed side panel covers the map.** Inset it: `#map{right:320px!important} body{--rs-side:320px}`. The map's controls, the base-map button among them, move with it. `--rs-side` shifts the rest (the overlay toggle and the Street View window).
    - **Show a set of edges by recoloring them.** Use `rsColor`, or a `color_options` entry. Extra lines drawn over the roads double them and hide the styling of the road.
    - **A selection in the base color shows nothing.** Pick a highlight color that no `color_options` entry uses.

## The dashboard on another map

The controls and the road interaction of a saved page are ES modules in `rust/roadstyle-assets/files/static/dashboard/` (the wheel has them in `roadstyle/static/dashboard/`). A page that makes its own
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

**See also:** [Dashboards](../guides/dashboards.md) · [Every parameter](parameters.md) · [On a website or in a map app](../guides/website.md)
