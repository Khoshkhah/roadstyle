# Dashboard manual

<p class="lead">Each part of a dashboard, with its Python option and its JavaScript call. Push Run on a block to see the call work on the map below.</p>

<iframe id="rs-testbed" src="../../maps/dashboard_testbed.html" loading="lazy" title="A dashboard to try the JavaScript blocks on" class="rs-demo tall"></iframe>

Every block marked `javascript` has a **Run** button. It runs the block in the map above, and the output shows under the block. Reload the page to reset the map.
Blocks marked `js` need a key or a page option that the map above does not have, so they have no button.

## The parts

| Part | What it is | Python | JavaScript |
|---|---|---|---|
| Panel | The side panel with the query box, the results table and the selected road | `dashboard={"panel": ...}` | `rs.sections` |
| Toolbox | The bar of tools at the edge of the window | `dashboard={"toolbar": ...}` | `rs.tools` |
| Legend | The legend box of the toolbox | `dashboard={"legend": ...}` | `rs.legend`, `rs.colorModes` |
| Credits | The credits box of the toolbox | `dashboard={"credits": ...}` | none |
| Windows | Street View and Google 3D | `street_view=`, `google_3d=`, `dashboard={"windows": ..., "google_3d": ...}` | `rsSetStreetView`, `rsSetGoogle3D` |
| Boundary | The dashed outline of the area, with its shade and its camera limit | `boundary=`, `dashboard={"boundary": ...}` | none |
| Phone form | The bar at the top and the panel as a bottom sheet | `dashboard={"phone": ...}` | `rs.sheet`, `rs.freeArea` |
| Live data | Colors and widths from your own numbers | `live_data=True` | `rs.setData` |
| Events | Messages that the page sends when something changes | none | `rs.on`, `document.addEventListener` |

## Build a dashboard from Python

`render_dashboard` makes the page from a GeoDataFrame of road edges.

```python
import roadstyle as rs

rs.render_dashboard(
    edges,
    name="Södermalm",
    color_options={"Road class": {}, "Speed limit": {"color_by": "maxspeed_kmh", "cmap": "plasma", "vmin": 20, "vmax": 60}},
    live_data=True,
).save("dashboard.html")
```

The page keywords that matter most for a dashboard:

| Keyword | Use |
|---|---|
| `name` | The title of the page |
| `color_options` | The entries of the *Colour by* list |
| `basemap`, `basemaps`, `basemap_switcher` | The start base map, the list in the switcher, and the switcher itself |
| `live_data` | `True` adds the support for `rs.setData` |
| `views` | Named groups of settings, for `rs.setView` |
| `street_view`, `street_view_key` | The Street View window, and its Google key |
| `google_3d`, `google_3d_layers` | The Google 3D window, and the layers that it draws |
| `boundary`, `boundary_dim`, `boundary_limit` | The outline of the area, the shade outside it, and the camera limit |
| `minzoom` | The first zoom of each road class |
| `page_script` | JavaScript text that the page runs after `rs:ready` |
| `dashboard` | The options below |

Every keyword is in [Every parameter](../reference/parameters.md).

### The `dashboard` option

Give only the parts that you change. The call merges them over the defaults. A wrong key or value is an error.

```python
rs.render_dashboard(edges, dashboard={"toolbar": {"position": "left"}, "panel": {"width_px": 460}})
```

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

## Control a dashboard from JavaScript

The page has one object, `window.rs`. The global `rs*` functions of the [reference](../reference/javascript.md) do the same jobs, and a few of them (`rsSetTheme`, `rsSetStreetView`) have no `rs.` form.

### Wait for the page

Call your code after `rs.ready`. It runs now if the page is ready, and on the event `rs:ready` if not. In Python, `page_script=` runs your text after that event.

```javascript
rs.ready(() => console.log("ready, contract", rs.contract));
```

### Find and read roads

`rs.query` and `rs.find` give the ids of roads. `rs.props` gives the row of one road. These ids are roadstyle's ids, not your `edge_id`. See [Ids past 2**53](../reference/javascript.md#ids-past-253).

```javascript
const ids = rs.query({highway: "primary"});      // columns that equal a value
console.log(ids.length, "primary roads");
console.log(rs.find("gatan").length, "roads with gatan in a field");
console.log(rs.props(ids[0]));
```

### Select, highlight and focus

```javascript
const ids = rs.query({highway: "primary"});
rs.select(ids[0]);          // like a click: glow, popup or panel
rs.focus(ids);              // fit the camera to the set
rs.highlight(ids.slice(0, 5));
```

`rs.select(null)` clears the selection. `rs.highlight([])` clears the glow.

### Filter and color

```javascript
rs.setFilter({classes: ["primary", "secondary", "tertiary"], tunnels: false});   // also: bridges, access, ids
rs.setColorBy("Speed limit");                   // a name from color_options
rs.color([{color: "#ef4444", ids: rs.query({highway: "primary"})}]);
```

`rs.color(null)` removes your colors. `rs.setFilter({})` shows all roads again. `rs.can(part)` is false for a part that the page cannot apply, for example a color option that the style does not have.

### Theme, base map, overlays, views

```javascript
rsSetTheme("dark");
rs.setBasemap("blank");
rs.setView("Casing only");          // a name from views=
rs.setTunnelStyle({strength: 80});
```

`rs.setOverlay(label, visible)` shows or hides one overlay of the page. `rsSetBridges`, `rsSetTunnels` and `rsSetClasses` are the single-control forms of `rs.setFilter`.

### Save and share the state

`rs.getState()` gives a copy of the state. `rs.setState(part)` applies a part of it through the controls. `rs.link()` gives the part that differs from the start, as a `#rs=` link. A page opened with that link applies it.

```javascript
rs.setFilter({classes: ["primary"]});
const link = rs.link();
console.log(link);
rs.setState({classes: null});       // back to all classes
```

### Sections of the panel

```javascript
rs.sections.add({id: "notes", label: "Notes", before: "query", fold: true,
                 html: "<p>Text of the page</p><button class='sb-primary' id='go'>Go</button>"});
document.getElementById("go").onclick = () => rs.focus(rs.query({highway: "primary"}));
console.log(rs.sections.list());
```

Other calls: `get(id)`, `hide(id)`, `show(id)`, `remove(id)`, `fold(id, on)`, `foldAll(on)` and `folded(id)`. A section with `fold: true` needs a `label`.

### Legend rows and color modes

```javascript
rs.legend.add({id: "sensors", color: "#16a34a", label: "Sensors", shape: "circle"});
rs.colorModes.set(["Traffic", "Counted"], {active: "Traffic", onChange: name => console.log("mode", name)});
console.log(rs.legend.list(), rs.colorModes.active);
```

`rs.legend.remove(id)` removes a row. `rs.colorModes.select(name)` picks a mode, and `rs.colorModes.clear()` takes the list away.

### Toolbox

```javascript
rs.tools.add({id: "export", title: "Export", icon: "&#8681;", onClick: () => console.log("pressed")});
console.log(rs.tools.list().map(t => t.id));
```

`rs.tools.bind(id, {onClick})` gives a tool its behavior. `open(id)` and `close(id)` open and close the box of a tool. `remove(id)` removes a tool of your page. `ready()` shows a bar that `toolbar.hold` keeps hidden.
The built-in tools are `theme`, `navigate`, `street_view`, `google_3d`, `basemap`, `roads`, `buildings`, `legend`, `settings` and `attribution`.

### Help window

```javascript
rs.help.set({title: "How to read this page", intro: "The map shows roads.",
             terms: [["Primary", "A main road."]], note: "Data: OpenStreetMap."});
console.log(rs.help.get().title);
```

`rs.help.button(el, words)` puts a `?` button with its own words in `el`. `rs.help.open(words)` and `rs.help.close()` open and close the window. `rs.help.clear()` removes the window and the button.

### Number tiles, charts, tabs and a hover box

```javascript
rs.sections.add({id: "stats", label: "Statistics", html: "<div class='rs-kpis' id='kp'></div><div id='ch'></div>"});
document.getElementById("kp").innerHTML = rs.kpi("Roads", "2 800", "primary and secondary", "#0e7c8e");
const s = rs.svg(document.getElementById("ch"), "svg", {viewBox: "0 0 100 20", width: "100%"});
const bar = rs.svg(s, "rect", {x: 0, y: 4, width: 60, height: 12, fill: "var(--accent)"});
rs.hover.on(bar, "<b>60 %</b> of the roads");
```

`rs.tabs.use(nav, onChange)` makes the tabs of a `nav` element work and gives `{select(id), current()}`. [Add to the panel](dashboard-panel.md) shows the HTML.

### Live data

`live_data=True` must be on in Python. `rs.setData` takes an array of rows, an Arrow table, or the URL of a JSON file. Write `edge_id` as text.

```javascript
const ids = rs.query({highway: "primary"});
const rows = ids.map(id => ({edge_id: String(rs.props(id).edge_id), flow: Math.round(Math.random() * 1000)}));
const r = await rs.setData(rows, {colorBy: "flow", legend: {title: "Random flow"}});
console.log(r);                      // {rows, matched, ms}
console.log(rs.naturalBreaks(rows.map(x => x.flow), 4));
```

`rs.clearData()` takes the data away. See [Live data](live-data.md) for all options.

### Phone sheet and free area

```javascript
console.log("sheet height:", rs.sheet());        // 0 closed, 1 for 40 %, 2 full, null if the page has no sheet
console.log(rs.freeArea());                      // {lo, hi, top, bottom}: the part of the map that nothing covers
```

`rs.sheet(n)` sets the height of the sheet.

### Street View and Google 3D

These windows need a Google key, so the map above cannot run them.

```js
rsSetStreetView(true);        // street_view="window" only
rsStreetViewStep(20);         // 20 m along the edge
console.log(rsGetStreetViewSpot());
rsSetGoogle3D(true);          // google_3d=True only
```

[Google Street View](street-view.md) and [Google 3D](google-3d.md) explain the options.

### Replace the style, and clean up

`rs.setStyle(style)` gives the page a new roads style. Every control that a style gives follows it. `rs.error` is `null`, or the error of a style that the dashboard cannot read. `rs.destroy()` removes the listeners of the object.

## Events

All events fire on `document` as `CustomEvent`s. Read the data from `e.detail`. `rs.on(name, fn)` listens for the shorter names (`select`, `deselect`, `filter`, `color`, `basemap` and others), calls `fn` with the `detail` itself, and gives the function that stops the listener.

```javascript
const stop = rs.on("select", d => console.log("selected", d.properties.name));
document.addEventListener("rs:themechange", e => console.log("theme", e.detail.theme), {once: true});
rs.select(rs.query({highway: "primary"})[0]);
stop();
```

| Event | When |
|---|---|
| `rs:ready` | The page is ready. |
| `rs:select`, `rs:deselect` | A road is selected or cleared. |
| `rs:filterchange` | A road filter changes. |
| `rs:colorchange` | The color option or the colors of roads change. |
| `rs:highlightchange` | The glow changes. |
| `rs:themechange` | The theme changes. `detail.theme` is `light` or `dark`. |
| `rs:basemapchange`, `rs:basemapready` | The base map changes, and a vector base map has loaded its layers. |
| `rs:buildingschange`, `rs:buildings3dchange` | The 3D buildings of the base map, or of the style, switch. |
| `rs:labelschange` | The map labels switch. |
| `rs:overlaychange`, `rs:overlayschange` | One overlay, or the list of overlays, changes. |
| `rs:interactionchange` | The clicks or the popup of an overlay change. |
| `rs:tunnelchange`, `rs:roadfillchange` | The tunnel look, or the fill of the roads, changes. |
| `rs:viewchange`, `rs:viewselect` | The 2D or 3D view, or a named view, changes. |
| `rs:sectionchange` | A section of the panel is added, removed, hidden, shown or folded. |
| `rs:helpchange` | The words of the help window change. |
| `rs:colormode` | `rs.colorModes` picks a mode. |
| `rs:datachange` | `rs.setData` or `rs.clearData` runs. |
| `rs:toolchange`, `rs:toolsready` | A tool opens, closes or is pressed. The page has added its tools (`rs.tools.ready()`). |
| `rs:sheetchange`, `rs:layoutchange` | The phone sheet, or the side or look of the panel, changes. |
| `rs:streetviewchange`, `rs:streetviewmove`, `rs:streetviewspot` | The Street View window opens or closes, moves along the edge, or picks a spot. |
| `rs:google3dchange`, `rs:g3dmodechange` | The Google 3D window opens or closes, or its mode changes. |
| `rs:tableready` | The table of the level editor is ready. |

The `detail` of each event is in the [reference](../reference/javascript.md#events).

**See also:** [Dashboard layout](dashboard-layout.md) · [Add to the panel](dashboard-panel.md) · [Live data](live-data.md) · [JavaScript API](../reference/javascript.md)
