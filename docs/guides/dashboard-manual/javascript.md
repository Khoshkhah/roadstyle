# JavaScript

<p class="lead">Call each piece of a dashboard from JavaScript, and see the result on the map at the same time.</p>

<iframe id="rs-testbed" src="../../../maps/dashboard_testbed.html" title="A dashboard to try the JavaScript blocks on" class="rs-testbed"></iframe>

Push **Run** under a block: a large window opens with the map and the change on it, and the output of the block under the map. Close it with ✕, Escape or a click outside. Each **Run** starts from a new map. The panel shows only for a block that uses it; its button opens it by hand. A block marked `js` needs a Google key or a page option that this map does not have, so it has no button. The page has one object, `window.rs`. The global `rs*` functions of the [reference](../../reference/javascript.md) do the same jobs. Each item has the same form: a box with **Use it for** and **From Python**, the code in tabs, and **Details** that open on a click.

| Group | Item | From Python | Use it for |
|---|---|---|---|
| Start | [Wait for the page](#wait-for-the-page) | `page_script=` | code that runs when `rs` is ready |
| Start | [Find and read roads](#find-and-read-roads) | no | the ids and the rows of roads |
| The map | [Select, highlight and focus](#select-highlight-and-focus) | no | a road like a click, a light on a set |
| The map | [Filter and color](#filter-and-color) | `color_options=` | show some roads, color roads |
| The map | [Theme, base map, overlays, views](#theme-base-map-overlays-views) | `basemap=`, `views=` | the look of the map |
| The map | [Save and share the state](#save-and-share-the-state) | no | a link that restores the page |
| Panel and toolbox | [Sections of the panel](#sections-of-the-panel) | `dashboard={"panel": ...}` | your own blocks in the panel |
| Panel and toolbox | [Legend rows and color modes](#legend-rows-and-color-modes) | `dashboard={"legend": ...}` | your own legend rows and "Colour by" list |
| Panel and toolbox | [Toolbox](#toolbox) | `dashboard={"toolbar": ...}` | your own tools |
| Panel and toolbox | [Parts](#parts) | see the page | help, tiles, tabs, charts, dock |
| Data | [Live data: a new day](#live-data-a-new-day) | `live_data=True` | numbers and colors from your own rows |
| Data | [A day picker](#a-day-picker) | `page_script=` | one day of data at a time |
| The page | [Drive the map from your own page](#drive-the-map-from-your-own-page) | `m.html` | your own panel beside the map |
| The page | [Phone sheet and free area](#phone-sheet-and-free-area) | no | the bottom sheet, the part of the map in view |
| The page | [Street View and Google 3D](#street-view-and-google-3d) | `street_view=`, `google_3d=` | the two windows |
| The page | [Replace the style, and clean up](#replace-the-style-and-clean-up) | no | a new roads style |
| The page | [Events](#events) | no | to know when something changes |

## Start { .rs-group }

### Wait for the page { .rs-part }

**Use it for:** your code. `rs.ready(fn)` runs `fn` now if the page is ready, and on the event `rs:ready` if not.<br>
**From Python:** `page_script=` runs your text before the page is ready: put it in `rs.ready(() => ...)`
{ .rs-facts }

=== "Python"

    ```python
    rs.render_dashboard(edges, page_script="rs.ready(() => console.log('ready'))")
    ```

=== "JavaScript"

    ```javascript
    rs.ready(() => console.log("ready, contract", rs.contract));
    ```

??? info "Details"

    - The event `rs:ready` fires once, so a listener that you add later never runs.

### Find and read roads { .rs-part }

**Use it for:** the ids of roads (`rs.query`, `rs.find`) and the row of one road (`rs.props`).<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```javascript
    const ids = rs.query({highway: "primary"});      // columns that equal a value
    console.log(ids.length, "primary roads");
    console.log(rs.find("gatan").length, "roads with gatan in a field");
    console.log(rs.props(ids[0]));
    ```

??? info "Details"

    - These ids are roadstyle's ids, not your `edge_id`. See [Ids past 2**53](../../reference/javascript.md#ids-past-253).

## The map { .rs-group }

### Select, highlight and focus { .rs-part }

**Use it for:** a road as if the person clicked it (`rs.select`), the camera on a set (`rs.focus`), and a light on a set (`rs.highlight`).<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```javascript
    const ids = rs.query({highway: "primary"});
    rs.select(ids[0]);          // like a click: glow, popup, road card
    rs.focus(ids);              // fit the camera to the set
    rs.highlight(ids.slice(0, 5));
    ```

    ```javascript
    const rows = rsQuery(p => p.highway === "primary");
    rsHighlight(rows.slice(0, 3), {set: "edit", color: "#2563eb", opacity: 1});
    rsHighlight(rows.slice(3, 6), {set: "turn", color: "#16a34a"});   // opacity: the look's selection opacity
    rsHighlight([], {set: "turn"});                                     // clears only this set
    ```

??? info "Details"

    - `rs.select(null)` clears the selection. `rs.highlight([])` clears the glow.
    - The second block lights more than one group of roads, each in its own colour. Each group has a set name. The light is as wide as the road at every zoom.
    - When a road is in two sets, the set that you set last has the road. `rsHighlight` uses the road rows, as `rsQuery` gives them.
    - Each change sends `rs:highlightchange` with `set` and `ids`.
    - A tool of your page that works on other objects can hold the road hover: `rs.holdHover("my-tool", true)`, and `false` at the end. No road lights up, and a click still selects the road. `rs.holdSelectLook("my-tool", true)` keeps `rs:select` but draws no select look, so your page draws its own selection.

### Filter and color { .rs-part }

**Use it for:** to show some roads (`rs.setFilter`) and to color roads (`rs.setColorBy`, `rs.color`).<br>
**From Python:** `color_options=` gives the names for `rs.setColorBy`. The filter has no keyword
{ .rs-facts }

=== "JavaScript"

    ```javascript
    rs.setFilter({classes: ["primary", "secondary", "tertiary"], tunnels: false});   // also: bridges, access, ids
    rs.setColorBy("Speed limit");                   // a name from color_options
    rs.color([{color: "#ef4444", ids: rs.query({highway: "primary"})}]);
    ```

??? info "Details"

    - `rs.color(null)` removes your colors. `rs.setFilter({})` shows all roads again.
    - `rs.can(part)` is false for a part that the page cannot apply, for example a color option that the style does not have.

### Theme, base map, overlays, views { .rs-part }

**Use it for:** the look of the map.<br>
**From Python:** yes, `basemap=`, `views=`, `hillshade=`, `terrain=`
{ .rs-facts }

=== "JavaScript"

    ```javascript
    rsSetTheme("dark");
    rs.setBasemap("blank");
    rs.setView("Casing only");          // a name from views=
    rs.setTunnelStyle({strength: 80});
    ```

??? info "Details"

    - `rsHillshade(on)` and `rsTerrain(on)` switch the hillshade and the 3D terrain of the base-map box. With no argument they tell whether the switch is on.
    - `rsTerrainTunnels(mode)` (`"fade"`, `"hide"` or `"show"`) sets what a tunnel does while the terrain is on.
    - `rs.setOverlay(label, visible)` shows or hides one overlay of the page.
    - `rs.basemaps()` gives the base maps of the page as `[{key, label}]`.
    - `rsSetBridges`, `rsSetTunnels` and `rsSetClasses` are the single-control forms of `rs.setFilter`.
    - `rsBuildingsOpacity(value)` sets the opacity of the 3D buildings of a vector base map, from 0 to 1 (the *Opacity* slider under the *3D buildings* row of the base-map box). No argument gives the opacity now. The event is `rs:buildingsopacitychange` (`opacity`).

### Save and share the state { .rs-part }

**Use it for:** a link that restores the page. `rs.getState()` gives a copy of the state. `rs.setState(part)` applies a part of it. `rs.link()` gives the part that differs from the start.<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```javascript
    rs.setFilter({classes: ["primary"]});
    const link = rs.link();
    console.log(link);
    rs.setState({classes: null});       // back to all classes
    ```

??? info "Details"

    - `rs.link()` gives a `#rs=` link. A page opened with that link applies it.
    - `rs.setState` applies the part through the controls.

## Panel and toolbox { .rs-group }

<a id="the-same-from-javascript"></a>

### Sections of the panel { .rs-part }

**Use it for:** your own blocks in the panel. Add a part of roadstyle (`part`: `"query"`, `"road_card"` or `"chart"`) or your own HTML (`html`).<br>
**From Python:** yes, `dashboard={"panel": {"sections": [...]}}` ([Dashboards](../dashboards.md#the-panel-starts-empty))
{ .rs-facts }

=== "JavaScript"

    ```javascript
    rs.sections.add({id: "q", label: "Query", part: "query", text: "p.highway == 'primary'"});
    rs.sections.add({id: "road", label: "Selected road", part: "road_card", fields: ["name", "highway"]});
    rs.sections.add({id: "classes", label: "Roads by class", part: "chart", chart: {kind: "bar", x: "highway"}});
    rs.sections.add({id: "flow", label: "Vehicles per hour", part: "chart",
                     chart: {kind: "line", x: "hour", y: "vehicles", data: [{hour: 7, vehicles: 820}, {hour: 8, vehicles: 1140}]}});
    document.addEventListener("rs:chartpick", (e) => console.log(e.detail.id, e.detail.row));   // a click on a mark of your own rows
    rs.sections.add({id: "notes", label: "Notes", before: "road", fold: true,
                     html: "<p>Text of the page</p><button class='sb-primary' id='go'>Go</button>"});
    document.getElementById("go").onclick = () => rs.focus(rs.query({highway: "primary"}));
    rs.sections.add({id: "edit", label: "Edit levels", note: "No edits", open: () => openMyEditor()});   // one click opens your editor
    rs.sections.note("edit", "5 edits applied");
    console.log(rs.sections.list());
    ```

??? info "Details"

    - Other calls: `get(id)`, `hide(id)`, `show(id)`, `remove(id)`, `fold(id, on)`, `foldAll(on)` and `folded(id)`.
    - A section with a `label` is a card. A section with `fold: true` or `background: false` needs a `label`.
    - `open` (a function, JavaScript only) makes a [card that opens something](../dashboard-parts.md#a-card-that-opens-something).
    - The event `rs:sectionchange` comes with `detail.id` and `detail.state`.

### Legend rows and color modes { .rs-part }

**Use it for:** your own rows in the legend (`rs.legend`) and your own "Colour by" list (`rs.colorModes`).<br>
**From Python:** `dashboard={"legend": {"rows": [...]}}` for the rows. The "Colour by" list has no keyword
{ .rs-facts }

=== "JavaScript"

    ```javascript
    rs.legend.add({id: "sensors", color: "#16a34a", label: "Sensors", shape: "circle"});
    rs.colorModes.set(["Traffic", "Counted"], {active: "Traffic", onChange: name => console.log("mode", name)});
    console.log(rs.legend.list(), rs.colorModes.active);
    ```

??? info "Details"

    - `rs.legend.remove(id)` removes a row.
    - `rs.colorModes.select(name)` picks a mode. `rs.colorModes.clear()` takes the list away.

### Toolbox { .rs-part }

**Use it for:** your own tool in the bar. `rs.tools.add` adds it.<br>
**From Python:** yes, `dashboard={"toolbar": {...}}` ([Layout and toolbox](../dashboard-layout.md#the-toolbox))
{ .rs-facts }

=== "JavaScript"

    ```javascript
    rs.tools.add({id: "export", title: "Export", icon: "&#8681;", onClick: () => console.log("pressed")});
    console.log(rs.tools.list().map(t => t.id));
    ```

??? info "Details"

    - `rs.tools.bind(id, {onClick})` gives a tool its behavior. `open(id)` and `close(id)` open and close the box of a tool. `remove(id)` removes a tool of your page.
    - `ready()` shows a bar that `toolbar.hold` keeps hidden.
    - The built-in tools are `theme`, `navigate`, `street_view`, `google_3d`, `basemap`, `roads`, `buildings`, `legend`, `settings` and `attribution`.

### Parts { .rs-part }

**Use it for:** the shared parts. Each one has its own code on [Dashboard parts](../dashboard-parts.md).<br>
**From Python:** see each part
{ .rs-facts }

[The help window](../dashboard-parts.md#a-help-window) · [number tiles](../dashboard-parts.md#number-tiles) (`rs.kpi`) · [tabs](../dashboard-parts.md#tabs) (`rs.tabs`) · [the editor frame](../dashboard-parts.md#an-editor-in-the-panel) (`rs.frame`) · [the hover box](../dashboard-parts.md#a-hover-box) (`rs.hover`) · [a chart](../dashboard-parts.md#a-chart) (`rs.chart`) · [a day picker](../dashboard-parts.md#a-day-picker) (`rs.days`) · [the bottom dock](../dashboard-parts.md#the-bottom-dock) (`rs.dock`) · [the parts for a form, a list and a message](#form-list-and-message-parts)

### Form, list and message parts { .rs-part }

**Use it for:** a period, an hour, a value, a search, a file, a message, a menu and a long list in your panel. Each one has its own code on [Dashboard parts](../dashboard-parts.md).<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```javascript
    rs.sections.add({id: "period", label: "Period", html: "<div id='per'></div><div id='hr'></div><div id='lst'></div>"});
    rs.days.range(document.getElementById("per"), {unit: "week", min: "2026-09-01", max: "2026-11-06", onChange: ([from, to]) => console.log(from, to)});
    rs.hours.use(document.getElementById("hr"), {value: [7, 9], range: true, label: "Rush hours"});
    rs.more(document.getElementById("lst"), {items: rs.find("Storgatan"), page: 5, noun: "roads", render: id => `<div class="rs-qrow"><b>${id}</b></div>`});
    rs.sections.button("period", {icon: "<svg viewBox='0 0 16 16'><circle cx='8' cy='8' r='5'/></svg>", title: "Zoom to the period", onClick: () => {}});
    rs.panel.bar().innerHTML = "<span>3 fixes not saved</span><button type='button' class='sb-primary'>Build</button>";
    rs.toast("The period is set.", {kind: "ok"});
    ```

??? info "Details"

    - `rs.days.range(el, {unit, min, max, value, onChange})` is a period: from a day to a day, a week or a month.
    - `rs.hours.use(el, {value, range, onChange})` is the hour picker: a field that opens a list of the hours.
    - `rs.slider`, `rs.number` and `rs.colorPick` are a slider, a number field with "−" and "+", and a colour picker. `rs.number` has `disabled` (and `disabled(on)` on its handle) and `snap: false`, which keeps a typed value.
    - `rs.search` is a search field with suggestions (`end` puts your icon button inside the field), `rs.drop` a file drop zone, `rs.progress` a progress bar and `rs.busy(button, promise)` a button that waits.
    - `rs.mapBusy(text)` puts a veil with a ring and your text over the free part of the map, and `rs.mapBusy(null)` takes it away.
    - `rs.toast(text, {kind})` is a message that goes after some seconds, and `await rs.confirm({title, ok, danger})` is the confirm dialog in place of `confirm()`.
    - `rs.menu(button, items)` and `rs.menu.button(items)` are an action menu.
    - `rs.toggle(button, onChange)` is a button that stays pressed.
    - `rs.more(el, {items, page, render})` shows a long list page by page.
    - `rs.sections.add({..., step: 3})` puts a step number in a card's title row, and `rs.sections.done(id, true)` changes it to a check mark.
    - `rs.sections.button(id, {icon, title, onClick})` is an icon button in a card's title row, and `rs.panel.bar()` is the fixed bar at the bottom edge of the panel.

## Data { .rs-group }

### Live data: a new day { .rs-part }

**Use it for:** colors from your own numbers. Build the page once. For each new day, call `rs.setData`: there is no new style and no reload.<br>
**From Python:** yes, `live_data=True`
{ .rs-facts }

=== "JavaScript"

    ```javascript
    const ids = rs.query({highway: "primary"});
    const rows = ids.map(id => ({edge_id: String(rs.props(id).edge_id), flow: Math.round(Math.random() * 1000)}));
    const r = await rs.setData(rows, {colorBy: "flow", legend: {title: "Random flow"}});
    console.log(r);                      // {rows, matched, ms}
    console.log(rs.naturalBreaks(rows.map(x => x.flow), 4));
    ```

**Write `edge_id` as text** (`"edge_id": "7203945719283746"`). The ids of duckOSM are 64-bit numbers, and a JSON number above 2^53 is not exact in a browser: the road is not found.

??? info "Details"

    - `rs.setData(rows, options)` takes an array of objects, an Arrow table, or **the URL of a JSON file** with such an array. Each row has an `edge_id` and the columns that you name in the options.
    - The call gives a Promise with `{rows, matched, ms}`, and the event `rs:datachange` fires. When `matched` is much smaller than `rows`, the ids do not match.
    - A call for the next day **replaces** the values of the day before. The legend (in the toolbox box *Colour by and legend*) and the colors follow.
    - `rs.clearData()` takes the data away. A click on a road shows the joined values in the popup, and in the road card when the page has one.

    | Option | Meaning |
    |---|---|
    | `colorBy` | the column that gives the colour: a number goes in one of `classes` sets, a text gets one colour for each value |
    | `classes` | the number of sets for a number, default 7. `classes: 0`, or a `vmin` or `vmax`, gives a smooth ramp from `vmin` to `vmax` (the range of the data when you leave them out) |
    | `breaks` | your own cut points, for example `[200, 800]` gives 3 sets. The same colours then mean the same numbers on every day |
    | `widthBy`, `widthRange` | a column that gives a **factor** of the drawn width (from `widthRange[0]` to `widthRange[1]`, default `[1, 3]`). Do not use it for numbers like the flow: the two carriageways of a street have the same width, and the factor makes one cover the other. Show the flow in the colour |
    | `ramp`, `stepped` | your own list of colours (the default is `data.live_ramp` of the palette); `stepped: true` takes the nearest colour of a smooth ramp, with hard edges |
    | `nodata` | the colour of a road with no row (default: the page's no-data colour) |
    | `key` | the column that names the road (default `edge_id`; `"row"` for the number of the road's row) |
    | `fields` | the columns that the popup, the tooltip and the panel show, for example `["flow"]`. Default: every column except the key column |
    | `legend` | `false`: no legend; `{title: "..."}`: change the legend |

    **The colour sets.** A number goes in one of `classes` sets. The cut points are the **natural breaks** of the numbers you give (the Fisher–Jenks method): the numbers inside a set are as close as possible, and the sets are as different as possible. The sets have different numbers of members. One very busy street does not use up the colour bar: it gets a set of its own. Set 1 gets the first colour of the ramp, the last set gets the last colour.

    The legend shows the lowest and the highest number of each set, and how many roads are in it: `100 – 400 (9)`. The cut points come from the data of the call, so each day has its own. To compare two days by colour, give the same `breaks` to both. The default ramp goes from blue through green and yellow to red. Its colours have a medium brightness, so they show on the light map and on the dark map.

    To show the same data in more than one way (the flow, then who was counted), give the names to `rs.colorModes.set([...], {onChange})` (see [Legend rows and color modes](#legend-rows-and-color-modes)). Call `rs.setData` in `onChange` with that mode's column.

### A day picker { .rs-part }

**Use it for:** one day of data at a time. The picker is [a part of the panel](../dashboard-parts.md#a-day-picker): it follows both themes.<br>
**From Python:** `page_script=` adds the code, with no edit of the HTML
{ .rs-facts }

=== "Python"

    ```python
    days = ["2026-10-27", "2026-10-28", "2026-10-29"]

    m = rs.render_dashboard(
        edges, live_data=True, name="Flow by day",
        dashboard={"panel": {"sections": [{"id": "day", "label": "Day", "html": "<div id='day'></div>"}]}},
        page_script="""
          rs.ready(() => {
            const show = day => rs.setData(`flow-${day}.json`, {colorBy: "flow", legend: {title: "Flow, " + day}});
            const picker = rs.days.use(document.getElementById("day"), {days: %s, onChange: show});
            show(picker.value());
          });
        """ % days,
    )
    m.save("flow.html")
    ```

??? info "Details"

    - Serve the page and the JSON files from one folder (`python -m http.server`): a page opened from disk cannot load files.
    - To add a day, write its `flow-<day>.json` and add the day to `days`.

## The page { .rs-group }

### Drive the map from your own page { .rs-part }

**Use it for:** your own panel beside the map. Put it before `</body>` and drive the map with the `window.rs*` functions and the `rs:*` events.<br>
**From Python:** yes, `m.html` is the saved page as a string
{ .rs-facts }

The example and the traps of a host page (ids past 2**53, a fixed side panel that covers the map) are in the [JavaScript API](../../reference/javascript.md#drive-the-map-from-your-own-page).

### Phone sheet and free area { .rs-part }

**Use it for:** the height of the bottom sheet on a phone (`rs.sheet`) and the part of the map that nothing covers (`rs.freeArea`).<br>
**From Python:** no. The page turns to its phone form by itself
{ .rs-facts }

=== "JavaScript"

    ```javascript
    console.log("sheet height:", rs.sheet());        // 0 closed, 1 for 40 %, 2 full, null if the page has no sheet
    console.log(rs.freeArea());                      // {lo, hi, top, bottom}: the part of the map that nothing covers
    ```

??? info "Details"

    - `rs.sheet(n)` sets the height of the sheet.

### Street View and Google 3D { .rs-part }

**Use it for:** the two windows. They need a Google key, so the map above cannot run them.<br>
**From Python:** yes, `street_view=` and `google_3d=`. See [Google Street View](../street-view.md) and [Google 3D](../google-3d.md)
{ .rs-facts }

=== "JavaScript"

    ```js
    rsSetStreetView(true);        // street_view="window" only
    rsStreetViewStep(20);         // 20 m along the edge
    console.log(rsGetStreetViewSpot());
    rsSetGoogle3D(true);          // google_3d=True only
    ```

### Replace the style, and clean up { .rs-part }

**Use it for:** a new roads style (`rs.setStyle`, `rs.restyle`) and the end of the page (`rs.destroy`).<br>
**From Python:** no
{ .rs-facts }

??? info "Details"

    - `rs.setStyle(style)` gives the page a new roads style. Every control that a style gives follows it.
    - `rs.restyle(style)` gives the page a new look on the same tiles (the style of `LiveMap.setLook`): the road layers change in place, and it gives `false` when the new style has other layers.
    - `rs.prefix` is the prefix of the roads style's ids on the map. `rs.error` is `null`, or the error of a style that the dashboard cannot read.
    - `rs.destroy()` removes the listeners of the object.

### Events { .rs-part }

**Use it for:** to know when something changes. All events fire on `document` as `CustomEvent`s. Read the data from `e.detail`.<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```javascript
    const stop = rs.on("select", d => console.log("selected", d.properties.name));
    document.addEventListener("rs:themechange", e => console.log("theme", e.detail.theme), {once: true});
    rs.select(rs.query({highway: "primary"})[0]);
    stop();
    ```

??? info "Details"

    - `rs.on(name, fn)` listens for the shorter names (`select`, `deselect`, `filter`, `color`, `basemap` and others), calls `fn` with the `detail` itself, and gives the function that stops the listener.
    - Your page sends `rs:toprowschange` when it changes a row that it added with `rsAddTopRow`: the base-map box then reads the row again.
    - The list of events, when each one fires and its `detail` are in the [reference](../../reference/javascript.md#events).

**See also:** [Dashboards](../dashboards.md) · [Layout and toolbox](../dashboard-layout.md) · [Dashboard parts](../dashboard-parts.md) · [JavaScript API](../../reference/javascript.md)
