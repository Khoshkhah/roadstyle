---
hide:
  - toc
---

# The data dock

The data dock is one SQL line over a wide table of the result, in the [bottom dock](dashboard-layout.md#the-bottom-dock). The roads of the result light on the map, a click on a row selects its road, and **Colour** and **Focus** keep a change of the map until the person turns it off. It is a JavaScript module that the host page imports. Your page runs the SQL on its own data: roadstyle has no database. Each item below has the same form: a box with **Use it for** and **From Python**, the code in tabs, and **Details** that open on a click.

![The data dock under the map: a query of the bridges and the tunnels of Södermalm, its table, and its roads lit on the map](../img/data-dock.png)

**Try it.** The page below is live: DuckDB runs in the page (duckdb-wasm) with the roads of Södermalm as the table `edges`. Write a
`SELECT` in the line and press **Run**, or click a query in the panel. The roads of the result light on the map, and a click on a row
selects its road. <a href="../../maps/data_dock.html" target="_blank" rel="noopener">Open it on a page of its own</a>.

<iframe src="../../maps/data_dock.html" loading="lazy" title="The data dock, live, with DuckDB in the page" class="rs-demo" style="height:780px"></iframe>

| Group | Item | From Python | Use it for |
|---|---|---|---|
| Use it | [Add it to a page](#add-it-to-a-page) | no | the data dock in your dashboard |
| Use it | [The options](#the-options) | no | what `dataDock` takes |
| Use it | [From JavaScript](#from-javascript) | no | to run SQL and to read the result from code |
| What the person does | [The title row](#the-title-row) | no | the controls of the dock |
| What the person does | [The line](#the-line) | no | to write and run one SQL statement |
| What the person does | [The table](#the-table) | no | the result, sorted and exported |
| What the person does | [Tables](#tables) | no | the list of the tables of your data |
| What the person does | [The map switch](#the-map-switch) | no | the table on the map, or the map's own colours |
| What the person does | [A row](#a-row) | no | one road: its card and its place |
| What the person does | [Table or chart](#table-or-chart) | no | the same result as a chart |
| What the person does | [Colour and focus](#colour-and-focus) | no | to keep a change of the map |

## Use it { .rs-group }

### Add it to a page { .rs-part }

**Use it for:** the data dock in a dashboard page. `query` and `schema` are necessary.<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```javascript
    import {dataDock} from "./dashboard/data/data_dock.js";

    const data = dataDock({
      query: async (sql, {signal}) => myDb.query(sql),        // your database: {columns: [{name, type}], rows: [[...], ...]}
      schema: async () => ({tables: [{name: "main.edges", rows: 2765, about: "One row is one direction of a road."}]}),
      ready: myDb.loaded,                                     // a promise: the data is loaded
      tables: [{name: "sensors", url: "sensors.geojson", about: "Traffic sensors: one point each."}],
      load: (t) => myDb.loadTable(t),                         // loads one of `tables` into the schema "extra"
      roadsBy: (sql, column) => `SELECT edge_id FROM edges WHERE "${column}" IN (SELECT "${column}" FROM (${sql}))`,
      sql: "SELECT edge_id, name, highway FROM edges WHERE highway = 'primary'",
    });
    data.open();
    ```

### The options { .rs-part }

**Use it for:** what `dataDock({...})` takes.<br>
**From Python:** no
{ .rs-facts }

??? info "Details"

    | Option | Default | What it is |
    |---|---|---|
    | `query(sql, {signal})` | (necessary) | Runs one statement on your data. It gives `{columns: [{name, type}], rows}` (a value is a string, number, boolean, `BigInt` or `null`), or it throws an `Error` with the database's message. |
    | `schema()` | (necessary) | `{tables: [{name, rows, about}]}`: the list of tables, and Ask's view of the data. |
    | `ready` | ready at once | A promise that ends when your data is loaded. A run waits for it. |
    | `tables`, `load(t)` | none | Your page's own tables, `[{name, url, about}]`. The data dock gives each one to `load` once at the start, and a run waits for them. A table that does not load does not stop the others. |
    | `idColumn` | `"edge_id"` | The column with the road ids. |
    | `keys`, `roadsBy(sql, column)` | `["osm_id", "name"]`, none | A result with no `idColumn` finds its roads by the first of `keys` that it has: `roadsBy` gives the SQL of the road ids. |
    | `kinds` | none | The objects of your data that are not roads: `{node: {label?, idColumns, needs?, geometryBy(sql, column) | geometryOf(ids, {column, signal}), noShape?, card?(info)}, building: {...}}` (see [Objects of a kind](#objects-of-a-kind)). |
    | `map` | `window.map` | The MapLibre map that the objects of a kind are drawn on. |
    | `sql` | `""` | The start text of the line. |
    | `label` | `"Data"` | The label of the dock. |
    | `limit` | `1000` | The most rows in the table. |
    | `card` | `true` | The road card beside the table, in place of the popup. While the dock shows the data dock, a road that the person selects (a row, a name, Ask, or a click on the map) or an overlay item that the person clicks shows only in the card: the dock holds every popup (`rs.holdPopup`). When the dock closes, the popups come back. |
    | `guard` | `true` | `false`: the person's own SQL does not go through the read-only guard. |

### From JavaScript { .rs-part }

**Use it for:** to run SQL, to show a result that you made, and to read the result from code.<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```javascript
    await data.run("SELECT edge_id, name FROM edges LIMIT 10");
    data.view("chart");
    data.chart({kind: "bar", x: "highway", title: "Roads by class"});
    ```

??? info "Details"

    - `data.run(sql?)` puts `sql` in the line and runs it, and gives the result. `data.show({sql, columns, rows, more})` shows a result that you made.
    - `data.sql()`, `data.result()`, `data.csv()` and `data.stop()` give the line, the result, the CSV text, and stop a run.
    - `data.roads(sql)` gives the road ids (on the map) that the SQL selects by `idColumn`. It refuses a query of more than 100 000 roads.
    - `data.colour(groups, {sql})` and `data.focus(ids, {sql, mode})` add the same layers as the buttons. `data.layers()` lists them.
    - `data.reset()` does what the Reset button does (see [The line](#the-line)).
    - For [Ask](ask.md): `data.idColumn`, `data.keyOf(result)` (the column that finds the roads of a result, or `null`) and `data.roadsOf(result)` (its roads on the map).
    - The events are `run` (`sql`, `columns`, `rows`, `more`, `ms`, `source`), `error` (`sql`, `message`, `source`), `layers`, `light` (`on`, see [The map switch](#the-map-switch)), `reset` (also the document event `rs:dockreset`), `kind` and `kinderror` (see [Objects of a kind](#objects-of-a-kind)), `row` and `cardclose` (see [A row of your own](#a-row-of-your-own)).

## What the person does { .rs-group }

### The title row { .rs-part }

**Use it for:** the controls of the dock. After the label and the note, there are two joined groups: **Table | Chart** and **On | Colour ▾ | Focus ▾** (the map switch first).<br>
**From Python:** no
{ .rs-facts }

??? info "Details"

    - **Table | Chart** is what the dock shows. **On | Colour ▾ | Focus ▾** is the map. The tables button and the download button are on [the line](#the-line).
    - **?** opens a help window with one row for each control.

### The line { .rs-part }

**Use it for:** to write and run one SQL statement. Only one `SELECT` or `WITH` statement runs.<br>
**From Python:** no
{ .rs-facts }

??? info "Details"

    - A click on the line opens it as a text box. **Ctrl+Enter** or **Run** runs it, and **Escape** folds it.
    - The download button (⤓), before the line, saves all the rows of the result as a CSV file. The tables button (a database icon), after **Run**, shows the tables of the data in the side column.
    - The reset button (a circular arrow), after the tables button, has the title "Reset the map and the table". One click gives the map its own colours again and empties the table: the colour layers and the focus go, the lit roads go, the selected road and its card go, and the table has no result. The SQL text stays. The map switch, the camera, the theme and the layers of the page are the person's, and Reset does not change them. One exception: when the page has [Ask](ask.md#get_map-and-set_map), Reset puts back what Ask's `set_map` changed (see there). The event `reset` (and the document event `rs:dockreset`) tells the host.
    - An error shows under the line, in the database's words.
    - The guard refuses a statement that writes, loads, or reads a file or an address.

### The table { .rs-part }

**Use it for:** the result. The note in the title row has the number of rows: "1 000 of 2 765 rows · 3 columns · 5 ms".<br>
**From Python:** no
{ .rs-facts }

??? info "Details"

    - The table shows at most `limit` rows, but the download button (⤓) saves all the rows (at most 1 000 000), and a click on a header sorts all the rows.
    - A DATE shows as `2026-06-10`, a TIMESTAMP as `2026-06-10 08:30:00`, and a geometry as `(32 bytes)`.
    - The column widths are measured once for each result. A sort keeps the columns in place and in the same width.

### Tables { .rs-part }

**Use it for:** the list of the tables of your data. It opens in the side column beside the table or the chart.<br>
**From Python:** no
{ .rs-facts }

??? info "Details"

    - The side column shows the list or the card of a selected road: one of the two at a time, the last one opened. The table and the chart stay in view.
    - The list has a search field (by name or description; Enter opens the first table, Escape closes the list), a group for each schema with its number of tables (the page's own `extra` first), and a card for each table with its name, its number of rows and one line of what it holds.
    - A click on a card shows the table's rows and closes the list: the line gets `SELECT * FROM <table>`, which you can change and run again.

### The map switch { .rs-part }

**Use it for:** the table on the map, or the map's own colours. On, the roads of the table are lit (the highlight set `dock`, in blue: `#2563eb` on a light map and `#5aa9f8` on a dark map, with no see-through; a clicked row keeps roadstyle's select purple), the dock's Colour and Focus layers show, and a page shows its own shapes of the result.<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```js
    data.addEventListener("light", e => myLayer.hidden = !e.detail.on);   // the page's own shapes of the result (nodes, buildings)
    data.light();                                                          // true: the table is shown on the map now
    ```

??? info "Details"

    - The map switch is the dashboard's [on/off switch](dashboard-parts.md#an-onoff-switch) at the start of the map group. It shows **On** or **Off**. The browser keeps the choice.
    - **Off:** the map shows its own colours, and the table stays. The light goes, the Colour and Focus layers are hidden (they stay in their lists), and **Colour ▾** and **Focus ▾** are disabled.
    - **On:** the light, the layers and the two buttons come back. A new Colour or Focus layer (from Ask, for example) turns the switch on.
    - A new table changes the light. A table that a colour or a focus already shows has no light. A closed dock lights nothing.
    - `data.light()` is `true` while the switch is on and the dock is open. The event `light` (`detail.on`) comes when that changes: at a click on the switch, and when the dock opens or closes.
    - `data.showOnMap()` turns the switch on, as a click does, and gives `true` when it was off. Ask calls it before a colour, a focus or a move, because with the switch off the result does not show.

### A row { .rs-part }

**Use it for:** one road. A click on a row selects its road and zooms to it.<br>
**From Python:** no
{ .rs-facts }

??? info "Details"

    - The side column then shows the road's card: its name, its main facts as chips (class, length, speed limit, one-way, the networks), its other fields in small type with rounded numbers, and its id with **Copy id** and **Zoom**.
    - The card leaves out the fields of roadstyle's drawing (`casing_*`, `fill_level` and others).
    - In a result of names, a click selects the roads of that name.
    - A click on an overlay item on the map (a building, a crossing) shows the item in the card: its name, the overlay's name as a chip, its fields (the overlay's popup fields when it has them) and its id with **Copy id**. The close button deselects it. While the dock shows the card, no popup shows, for a road or for an item.

### Objects of a kind { .rs-part }

**Use it for:** a result of nodes, buildings or other objects that are not roads. The dock shows them on the map and in the card by itself.<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```javascript
    const data = dataDock({
      ...,
      kinds: {
        node: {
          label: "Node",                                        // the chip of the card (default: the name of the kind)
          idColumns: ["node_id", "osm_id"],
          geometryBy: (sql, column) => `SELECT n.node_id AS id, ST_AsGeoJSON(n.geom) AS geom, n.name, n.tags
                                        FROM nodes n WHERE n.node_id IN (SELECT "${column}" FROM (${sql}) AS rs_k)`,
        },
      },
    });
    ```

??? info "Details"

    - A kind is `{label?, idColumns, geometryBy(sql, column)}` or `{label?, idColumns, geometryOf(ids, {column, signal})}`: one of the two functions, not both (a kind with both, or with neither, is skipped and reported with `kinderror`). `geometryBy` gives one `SELECT` for the result's own `sql`: its first column is `id`, its second column is `geom` (GeoJSON, as text or as an object), and the other columns are the facts of the card.
    - **`geometryOf(ids, {column, signal})`** is for a host that builds the shapes in JavaScript, for example H3 cells with h3-js. It gets the distinct non-null values of the id column of the result (at most 20 000, in the order of the result) and returns, or resolves to, a list of `{id, geom, ...facts}`: the same shape as a row of `geometryBy`. A value keeps the type that the query adapter gives: a BIGINT stays a `BigInt`, so a 64-bit H3 index keeps all its digits (do not convert it with `Number`). The dock matches an entry to a row with `String(id)` and drops an entry of an id it did not ask for. `signal` aborts when a new result or a Reset makes the call out of date. A result that the table holds whole gives the ids from its rows. A longer result asks the database for its distinct ids.
    - An entry with `geom: null` is a row that is known and has no shape. It counts as found, nothing is drawn, and a click on its row opens the card with the line "on the map: no" and the text of the kind's `noShape` (for example `noShape: "A table of settings."`).
    - The dock looks for roads first. A result that has no roads goes to the kind that finds objects for the most of its ids. A candidate is a kind that has one of its `idColumns` in the result, and all the columns of its optional `needs` (for example `needs: ["lane_num"]`). For each candidate (and each id column), the dock asks `geometryBy` for the first 200 distinct ids of the result. The **coverage** is the share of those ids that get an object. The highest coverage owns the result. A tie goes to the earlier kind in `kinds`, then to the earlier column in `idColumns`. A coverage of 0 means that no kind owns the result. So a name such as `osm_id`, which is a node in one table and a way in another, goes to the table that has the ids, and one id that exists in both tables does not decide. A result with one candidate has no probe. Only the owner loads all its objects.
    - The note of the table says which kind owns the result: "Shown as Building (osm_id)". When some ids have no object, it adds "2 of 3 ids found". To use another kind, select the column under the id name of that kind (`SELECT osm_id AS way_id`). The event `kind` comes once for each result with `detail` `{name, column, coverage, candidates: [{name, column, coverage}]}`; `name` is `null` when no kind owns the result.
    - A query of a kind that fails is not hidden. The dock writes it to the console (`console.error`), sends the event `kinderror` (`detail` `{kind, column, message}`), and adds "the kind node failed: ..." to the note of the table. The kind then has no objects.
    - The objects are blue (`#2563eb`, `#5aa9f8` on a dark map): a dot with a ring for a point, an outline for a line, a fill and an outline for an area. The map switch, the theme and **Reset** control them as they control the road light. The most is 20 000 objects: the note of the table then says "the map shows the first 20 000".
    - **Parts with roles.** `geom` can be a list of parts, `[{role, geom}]`: in `geometryOf` an array of objects, in `geometryBy` the JSON text of the list (DuckDB: `json_group_array(json_object('role', r, 'geom', ST_AsGeoJSON(g)::JSON))`). A turn is a `from` road, a `via` node and a `to` road, in one row. Every part is a feature of the row, so one click selects all of them and the camera shows all of them. The colour of a role is in the look: the palette's `dock.roles` (`from`, `via`, `to`), and a role that the palette does not name takes the next colour of `dock.role_series`, in the order of first use. The host gives no colour. The selected row keeps its role colours over a halo of the select colour, and the card shows a swatch and the name of each role.
    - **A composite key.** An entry of `idColumns` can be an array of columns, `["from_edge", "to_edge"]`. The kind then gets the array in `geometryBy(sql, columns)`, and `geometryOf` gets a list of arrays `[[12, 15], ...]` and returns `id` as an array of the same length (or text with the values joined by `|`). A row with a null in one of the columns has no id. Two rows with one `from_edge` and two `to_edge` are two objects.
    - **`card(info)`** sets the card of a row. `info` is `{id, kind, label, row, facts, parts}`: `row` is the clicked row as `{column: value}`, `facts` the facts of the entry, `parts` the roles of its parts. It returns, or resolves to, `{title?, chip?, rows?, sections?, action?}`. `title`, `chip` and `rows` (`[[name, value], ...]`) replace the default ones. `sections` is a list of `{title?, rows}`: each is a block with a small heading. `action` is `{label, note?, run(info)}`: one block with an optional line of text and one button, above the id line. A card has at most one action. `run` can do anything the host needs (for example `rs.focus([edgeId])`). If it returns a geometry (an object, GeoJSON text or a list of parts), the dock draws it with the selected object in the select look and moves the camera to show both. A new selection or the close button removes it. The event `cardaction` (`{kind, id}`) comes when the button is used.
    - `card` can be async. The dock draws the default card at once and adds "Loading..." where the sections will be. When the promise resolves, the dock draws the whole card. If the person has selected another object by then, the answer is ignored. A promise that rejects, a `card` that throws and an action that fails are not hidden: the message shows in the card (in the action block for an action) and in the console. A kind with no `card` has the default card.
    - **A click on an object on the map** selects it as a click on its row does: the select look, the card, and the mark on its row in the table (the table scrolls to it). The dock looks in a box of 6 px around the point, so a thin line is easy to hit; where objects overlap, the one on top wins. A click that hits no object does what a click on an empty map does (it deselects). A row that the table does not hold (the table has the first rows only) has the card too.
    - **A row with no object** (a row after the first 20 000 ids, an id that the kind has no entry for) opens the card with the line "on the map: no object found for this row". A click on a row never does nothing. A row with `geom: null` says "no" and the `noShape` text.
    - The colours need `window.RS_DOCK` (the look's `dock` section, in the options of the page as `dock`). A page whose options have no `dock` gets an error when it draws a kind, not a guess.
    - A click on a row selects its object: the select purple (a ring for a point, a thick outline for a line or an area), and the camera moves to it (a point: zoom 18). The card has the same look as the card of a road: the title is the `name` column or "label id", the chip is the label, the other columns are rows (a `null` or empty value is left out), a column `tags` (an object, a list of `{key, value}` or JSON text) is one row for each tag, and the id has **Copy id**. The close button of the card removes the selection.
    - A change of the base map or of the theme can remove the layers of the objects: the dock puts them back.
    - The design is [Object kinds in the data dock](../design/dock_kinds.md).

#### The row of a road result

A click on a row of a result with `edge_id` (`lane_profile`, `route_edges`, `edge_levels`) selects the road. The card shows the road and, under it, the section **This row** with the other columns of the clicked row (a lane's `width_m`, a route's `seq`), as the table shows them: a 64-bit id and a text as they are, `null` as `null`, a number with at most 3 decimals. A column that the card already shows with the same value (`edge_id`, `name`, `highway`, ...) is left out, and so is a geometry column. When nothing is left there is no section. A click on the map, or a selection by Ask, shows the road alone.

### A row of your own { .rs-part }

**Use it for:** a row of a result that is not a road (a node, a building, a wall), which your page draws on the map itself. The page hears the click, shows the item on the map, and puts the item's facts in the card.<br>
**From Python:** no
{ .rs-facts }

=== "JavaScript"

    ```javascript
    data.addEventListener("row", async (e) => {                      // a click, or Enter, on a row of the table
      const {columns, row} = e.detail;                               // the values are in the order of the columns
      const facts = columns.map((c, i) => [c.name, row[i]]).filter(([k]) => k !== "geom");
      drawOnMap(await shapeOf(row));                                 // your own drawing: the select look
      data.card({title: row[1], chip: "buildings", rows: facts, id: row[0]});
    });
    data.addEventListener("cardclose", () => clearMyDrawing());      // the person closed the card
    ```

??? info "Details"

    - The event `row` comes for every row, also a road row: `detail.columns` (the columns of the result), `detail.row` (the values, in the order of the columns), `detail.index` (the row's place in the table now) and `detail.rowId` (the value of the `idColumn` as a string, or `null` when the result has none). Ignore what you do not need.
    - The row shows as selected: the accent tint and a bar. A sort keeps the same row selected, because the table knows it by its values.
    - The keys do what a click does: Tab goes to a row, Enter or Space picks it.
    - `data.card({title, chip, rows, id})` fills the card with the same look as the card of an overlay item: the title, the chip, the rows `[[name, value], ...]` (a `null` or empty value is left out), and the `id` with **Copy id**. `data.card(null)` closes the card.
    - The event `cardclose` comes when the card goes away without your call: the close button, a new selection (a road, an overlay item), or a new result. It does not come for your own `data.card(null)`. The row stops being selected. Remove your drawing on the map in `cardclose`.

### Table or chart { .rs-part }

**Use it for:** the same result as a chart ([A chart](dashboard-parts.md#a-chart)). **Kind**, **X** and **Y** change it, and **SVG** downloads it.<br>
**From Python:** no. For a chart in the panel, see [A chart](dashboard-parts.md#a-chart)
{ .rs-facts }

=== "JavaScript"

    ```javascript
    data.chart({kind: "line", x: "hour", y: "vehicles", title: "Vehicles"});
    data.view("table");     // or "chart"
    ```

??? info "Details"

    - The first chart comes from the columns: a date or a time and a number give a line, a text and a number a bar, one number a histogram, two numbers a scatter.
    - A histogram counts all the rows, not only the table's. The **Kind** buttons have a tooltip that says how to use each kind.
    - **X** and **Y** offer only the columns that fit the kind. For a bar or a pie, X is the groups and Y is "(count of rows)" or a measure. For a line, X is a number, a date or a time. For a histogram, X is a measure. For a scatter, X and Y are two measures. A road id, a geometry or a list is never offered. When the kind changes, X and Y move to a column that fits.
    - A bar or a pie whose X is a number with more than 40 values (a length, say) shows the rows in ranges of X: about 6 slices or 12 bars, over all the rows.
    - On a computer, **Kind**, **X** and **Y** are a column at the left of the chart, and the chart has no title line: it uses the full height of the box. **SVG** is in the top right corner. The box scrolls only when the chart is taller than the box (many bars at their least height). On a phone, **Kind**, **X** and **Y** are a row over the chart.
    - In the Chart view, the chart takes the width of the side column while it has no road card and no list of tables. When one of the two opens, the column comes back. The Table view keeps the side column with its hint, so that the table does not change its width.

### Colour and focus { .rs-part }

**Use it for:** to keep a change of the map until the person turns it off. **Colour ▾** colours the roads of the table. **Focus ▾** fades or hides the other roads.<br>
**From Python:** no
{ .rs-facts }

??? info "Details"

    - **Colour ▾.** "+ Colour the roads of this table" gives one colour for each value of a text column with 2 to 8 values (for example `highway`), else one colour, with a legend row for each colour. Each layer has a check box that turns it off and on, and ✕ that removes it.
    - **Focus ▾.** "+ Focus on the roads of this table" keeps these roads, and the other roads fade (`rs.fade`) or hide. One focus is on at a time; **None** turns it off. Each focus has **Fade / Hide** and ✕.
