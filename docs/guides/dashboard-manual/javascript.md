---
hide:
  - navigation          # the left menu is hidden: the page is wide enough (over 700 px) for the desktop form of the dashboards on it
---

# JavaScript

<p class="rs-manual-nav"><a href="../">Dashboard manual</a> &middot; <a href="../python/">Python SDK</a> &middot; <a href="../javascript/">JavaScript</a></p>

<p class="lead">Call each piece of a dashboard from JavaScript, and see the result on the map at the same time.</p>

<iframe id="rs-testbed" src="../../../maps/dashboard_testbed.html" loading="lazy" title="A dashboard to try the JavaScript blocks on" class="rs-demo rs-sticky"></iframe>

The map above stays at the top of the screen while you scroll. Under each heading is one piece of the dashboard and a block of code. To try a block:

1. Scroll to the block.
2. Push **Run** under it.
3. Look at the map above, and at the output under the block.

Each **Run** reloads the map first, so each block starts from the same map. Blocks marked `js` need a Google key or a page option that this map does not have, so they have no button.
The page has one object, `window.rs`. The global `rs*` functions of the [reference](../../reference/javascript.md) do the same jobs, and a few of them (`rsSetTheme`, `rsSetStreetView`) have no `rs.` form.
For the Python side of the same page, see [Python SDK](python.md).

## Wait for the page

Call your code in `rs.ready(fn)`. It runs now if the page is ready, and on the event `rs:ready` if not. The event fires once, so a listener that you add later never runs. In Python, `page_script=` runs your text before the page is ready: put it in `rs.ready(() => ...)` too.

```javascript
rs.ready(() => console.log("ready, contract", rs.contract));
```

## Find and read roads

`rs.query` and `rs.find` give the ids of roads. `rs.props` gives the row of one road. These ids are roadstyle's ids, not your `edge_id`. See [Ids past 2**53](../../reference/javascript.md#ids-past-253).

```javascript
const ids = rs.query({highway: "primary"});      // columns that equal a value
console.log(ids.length, "primary roads");
console.log(rs.find("gatan").length, "roads with gatan in a field");
console.log(rs.props(ids[0]));
```

## Select, highlight and focus

```javascript
const ids = rs.query({highway: "primary"});
rs.select(ids[0]);          // like a click: glow, popup, road card
rs.focus(ids);              // fit the camera to the set
rs.highlight(ids.slice(0, 5));
```

`rs.select(null)` clears the selection. `rs.highlight([])` clears the glow.

To light more than one group of roads, each in its own colour, give each group a set name. The light is as wide as the road at every zoom.
When a road is in two sets, the set that you set last has the road. `rsHighlight` uses the road rows, as `rsQuery` gives them.

```javascript
const rows = rsQuery(p => p.highway === "primary");
rsHighlight(rows.slice(0, 3), {set: "edit", color: "#2563eb", opacity: 1});
rsHighlight(rows.slice(3, 6), {set: "turn", color: "#16a34a"});   // opacity: the look's selection opacity
rsHighlight([], {set: "turn"});                                     // clears only this set
```

Each change sends `rs:highlightchange` with `set` and `ids`.

## Filter and color

```javascript
rs.setFilter({classes: ["primary", "secondary", "tertiary"], tunnels: false});   // also: bridges, access, ids
rs.setColorBy("Speed limit");                   // a name from color_options
rs.color([{color: "#ef4444", ids: rs.query({highway: "primary"})}]);
```

`rs.color(null)` removes your colors. `rs.setFilter({})` shows all roads again. `rs.can(part)` is false for a part that the page cannot apply, for example a color option that the style does not have.

## Theme, base map, overlays, views

```javascript
rsSetTheme("dark");
rs.setBasemap("blank");
rs.setView("Casing only");          // a name from views=
rs.setTunnelStyle({strength: 80});
```

`rsHillshade(on)` and `rsTerrain(on)` switch the hillshade and the 3D terrain of the base-map box (`rsTerrainTunnels(mode)`: "fade", "hide" or "show" for the tunnels meanwhile) (the DEM is the Terrain Tiles on AWS; no argument: whether it is on). With the terrain on, every layer lies on the ground of the DEM, so a tunnel is drawn on the hill above it and a bridge on the valley under it; the roads are flat with it off. `rs.setOverlay(label, visible)` shows or hides one overlay of the page. `rsSetBridges`, `rsSetTunnels` and `rsSetClasses` are the single-control forms of `rs.setFilter`.

`rsBuildingsOpacity(value)` sets the opacity of the 3D buildings of a vector base map, from 0 to 1 (the *Opacity* slider under the *3D buildings* row of the base-map box). No argument gives the opacity now. The event is `rs:buildingsopacitychange` (`opacity`).

## Save and share the state

`rs.getState()` gives a copy of the state. `rs.setState(part)` applies a part of it through the controls. `rs.link()` gives the part that differs from the start, as a `#rs=` link. A page opened with that link applies it.

```javascript
rs.setFilter({classes: ["primary"]});
const link = rs.link();
console.log(link);
rs.setState({classes: null});       // back to all classes
```

## Sections of the panel

The panel starts empty. Add a part of roadstyle (`part`: `"query"` or `"road_card"`) or your own HTML (`html`).

```javascript
rs.sections.add({id: "q", label: "Query", part: "query", text: "p.highway == 'primary'"});
rs.sections.add({id: "road", label: "Selected road", part: "road_card", fields: ["name", "highway"]});
rs.sections.add({id: "notes", label: "Notes", before: "road", fold: true,
                 html: "<p>Text of the page</p><button class='sb-primary' id='go'>Go</button>"});
document.getElementById("go").onclick = () => rs.focus(rs.query({highway: "primary"}));
rs.sections.add({id: "edit", label: "Edit levels", note: "No edits", open: () => openMyEditor()});   // one click opens your editor
rs.sections.note("edit", "5 edits applied");
console.log(rs.sections.list());
```

Other calls: `get(id)`, `hide(id)`, `show(id)`, `remove(id)`, `fold(id, on)`, `foldAll(on)` and `folded(id)`. A section with a `label` is a card. A section with `fold: true` or `background: false` needs a `label`.

## Legend rows and color modes

```javascript
rs.legend.add({id: "sensors", color: "#16a34a", label: "Sensors", shape: "circle"});
rs.colorModes.set(["Traffic", "Counted"], {active: "Traffic", onChange: name => console.log("mode", name)});
console.log(rs.legend.list(), rs.colorModes.active);
```

`rs.legend.remove(id)` removes a row. `rs.colorModes.select(name)` picks a mode, and `rs.colorModes.clear()` takes the list away.

## Toolbox

```javascript
rs.tools.add({id: "export", title: "Export", icon: "&#8681;", onClick: () => console.log("pressed")});
console.log(rs.tools.list().map(t => t.id));
```

`rs.tools.bind(id, {onClick})` gives a tool its behavior. `open(id)` and `close(id)` open and close the box of a tool. `remove(id)` removes a tool of your page. `ready()` shows a bar that `toolbar.hold` keeps hidden.
The built-in tools are `theme`, `navigate`, `street_view`, `google_3d`, `basemap`, `roads`, `buildings`, `legend`, `settings` and `attribution`.

## Help window

```javascript
rs.help.set({title: "How to read this page", intro: "The map shows roads.",
             terms: [["Primary", "A main road."]], note: "Data: OpenStreetMap."});
console.log(rs.help.get().title);
```

`rs.help.button(el, words)` puts a `?` button with its own words in `el`. `rs.help.open(words)` and `rs.help.close()` open and close the window. `rs.help.clear()` removes the window and the button.

## Number tiles, charts, tabs and a hover box

```javascript
rs.sections.add({id: "stats", label: "Statistics", html: "<div class='rs-kpis' id='kp'></div><div id='ch'></div>"});
document.getElementById("kp").innerHTML = rs.kpi("Roads", "2 800", "primary and secondary", "#0e7c8e");
const s = rs.svg(document.getElementById("ch"), "svg", {viewBox: "0 0 100 20", width: "100%"});
const bar = rs.svg(s, "rect", {x: 0, y: 4, width: 60, height: 12, fill: "var(--accent)"});
rs.hover.on(bar, "<b>60 %</b> of the roads");
```

```javascript
const fr = rs.frame({panel: document.getElementById("sb"), title: "Edit notes", back: "Back", tabs: [["a", "Notes"], ["b", "Links"]]});
fr.body.innerHTML = "<p>The notes of the area.</p>";
fr.bar.innerHTML = "<button type='button'>Save</button>";
fr.addEventListener("back", () => fr.close());
fr.addEventListener("tab", (e) => { fr.body.innerHTML = e.detail.tab === "a" ? "<p>Notes</p>" : "<p>Links</p>"; });
fr.open("a");
fr.close();
```

`rs.frame({panel, title, back, tabs, head})` is the frame of an editor that uses the whole panel. `open(tab)` hides the host's title, body and "Collapse all", and shows the title line (`top`), the `head` row that does not scroll (the tabs, or the editor's own element `head`), one `body` that scrolls and a `bar` at the bottom edge. `close()` shows the host's panel again. The events are `back` and `tab`.

```javascript
const t = rs.dock.table({columns: [{name: "edge_id", type: "BIGINT"}, {name: "name", type: "VARCHAR"}],
                         rows: [[1n, "Street 0"], [2n, "Street 1"]], idColumn: "edge_id"});
rs.dock.add({id: "roads", label: "Roads", el: t.el, note: "2 rows"});
rs.dock.open("roads");
document.addEventListener("rs:dockchange", (e) => console.log(e.detail.open, e.detail.height));
rs.dock.note("roads", "2 rows · sorted");
console.log(rs.dock.isOpen(), rs.dock.height(), rs.dock.list());
rs.dock.show("roads");
rs.dock.close();
rs.dock.remove("roads");
rs.fade(["1", "2"], {opacity: 0.18});   // the other roads fade; the event rs:fadechange
rs.fade(null);
rs.holdPopup("my-card", true);           // a part that shows the road's facts: no road popup while it is in view
rs.holdPopup("my-card", false);
const box = document.createElement("div"); box.style.height = "200px"; document.body.append(box);
const chart = rs.chart(box, {kind: "bar", x: "highway", y: "km",
  columns: [{name: "highway", type: "VARCHAR"}, {name: "km", type: "DOUBLE"}], rows: [["primary", 12.5], ["residential", 30.5]]});
chart.set({kind: "pie"});
```

`rs.dock` is the bottom dock under the map ([The bottom dock](../dashboard-layout.md#the-bottom-dock)). `add({id, label, el, note, actions, closable})` adds a content, `open(id)` and `close()` open and close the dock, `show(id)` shows a content, `note(id, text)` changes its note, `height(px)` gives or sets the height, `list()` gives the ids and `remove(id)` removes a content. `table({columns, rows, idColumn})` gives the dock's table (`el`, `set`). The event `rs:dockchange` has `open`, `id` and `height`.

`rs.holdPopup(key, on)` holds the road popup while a part that shows the road's facts itself is in view (the data dock's road card): a selection then has no popup. The popup comes back when no key holds it.

`rs.tabs.use(nav, onChange)` makes the tabs of a `nav` element work and gives `{select(id), current()}`. `rs.days.use(el, {days, onChange})` builds a day picker in an empty element: a field that opens a calendar of the days with data, the day before and after, and "Latest". It gives `{set(day, quiet), value()}`. [Dashboard parts](../dashboard-parts.md) shows the HTML and the other shared pieces.

## Live data

`live_data=True` must be on in Python. `rs.setData` takes an array of rows, an Arrow table, or the URL of a JSON file. Write `edge_id` as text.

```javascript
const ids = rs.query({highway: "primary"});
const rows = ids.map(id => ({edge_id: String(rs.props(id).edge_id), flow: Math.round(Math.random() * 1000)}));
const r = await rs.setData(rows, {colorBy: "flow", legend: {title: "Random flow"}});
console.log(r);                      // {rows, matched, ms}
console.log(rs.naturalBreaks(rows.map(x => x.flow), 4));
```

`rs.clearData()` takes the data away. See [Live data](../live-data.md) for all options.

## Phone sheet and free area

```javascript
console.log("sheet height:", rs.sheet());        // 0 closed, 1 for 40 %, 2 full, null if the page has no sheet
console.log(rs.freeArea());                      // {lo, hi, top, bottom}: the part of the map that nothing covers
```

`rs.sheet(n)` sets the height of the sheet.

## Street View and Google 3D

These windows need a Google key, so the map above cannot run them.

```js
rsSetStreetView(true);        // street_view="window" only
rsStreetViewStep(20);         // 20 m along the edge
console.log(rsGetStreetViewSpot());
rsSetGoogle3D(true);          // google_3d=True only
```

[Google Street View](../street-view.md) and [Google 3D](../google-3d.md) explain the options.

## Replace the style, and clean up

`rs.setStyle(style)` gives the page a new roads style. Every control that a style gives follows it. `rs.restyle(style)` gives the page a new look on the same tiles (the style of `LiveMap.setLook`): the road layers change in place, and it gives `false` when the new style has other layers. `rs.prefix` is the prefix of the roads style's ids on the map. `rs.error` is `null`, or the error of a style that the dashboard cannot read. `rs.destroy()` removes the listeners of the object.

## Events

All events fire on `document` as `CustomEvent`s. Read the data from `e.detail`. `rs.on(name, fn)` listens for the shorter names (`select`, `deselect`, `filter`, `color`, `basemap` and others), calls `fn` with the `detail` itself, and gives the function that stops the listener.

```javascript
const stop = rs.on("select", d => console.log("selected", d.properties.name));
document.addEventListener("rs:themechange", e => console.log("theme", e.detail.theme), {once: true});
rs.select(rs.query({highway: "primary"})[0]);
stop();
```

The page sends these events: `rs:ready`, `rs:select`, `rs:deselect`, `rs:filterchange`, `rs:colorchange`, `rs:highlightchange`, `rs:themechange`, `rs:basemapchange`, `rs:basemapready`, `rs:buildingschange`, `rs:buildings3dchange`, `rs:buildingsopacitychange`, `rs:terrainchange`, `rs:labelschange`, `rs:overlaychange`, `rs:overlayschange`, `rs:interactionchange`, `rs:tunnelchange`, `rs:roadfillchange`, `rs:viewchange`, `rs:viewselect`, `rs:sectionchange`, `rs:helpchange`, `rs:colormode`, `rs:datachange`, `rs:toolchange`, `rs:toolsready`, `rs:sheetchange`, `rs:layoutchange`, `rs:streetviewchange`, `rs:streetviewmove`, `rs:streetviewspot`, `rs:google3dchange`, `rs:g3dmodechange`, `rs:arrowschange`, `rs:stylechange` and `rs:tableready`. Your page sends `rs:toprowschange` when it changes the state of a row that it added with `rsAddTopRow`: the base-map box then reads the row again.

When each event fires, and its `detail`, are in the [reference](../../reference/javascript.md#events).

**See also:** [Overview](index.md) · [Python SDK](python.md) · [Dashboard layout](../dashboard-layout.md) · [Add to the panel](../dashboard-panel.md) · [Live data](../live-data.md) · [JavaScript API](../../reference/javascript.md)
