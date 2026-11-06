# The data dock

The data dock is one SQL line over a wide table of the result, in the [bottom dock](dashboard-layout.md#the-bottom-dock). The roads of the result light on the map, a click on a row selects its road, and **Colour** and **Focus** keep a change of the map until the person turns it off. Your page runs the SQL on its own data: roadstyle has no database.

The data dock is a module that a page imports, as the [design panel](design-panel.md) is:

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

## The options

| Option | Default | What it is |
|---|---|---|
| `query(sql, {signal})` | (necessary) | Runs one statement on your data. It gives `{columns: [{name, type}], rows}` (a value is a string, number, boolean, `BigInt` or `null`), or it throws an `Error` with the database's message. |
| `schema()` | (necessary) | `{tables: [{name, rows, about}]}`: the **Tables** list, and Ask's view of the data. |
| `ready` | ready at once | A promise that ends when your data is loaded. A run waits for it. |
| `tables`, `load(t)` | none | Your page's own tables, `[{name, url, about}]`. The data dock gives each one to `load` once at the start, and a run waits for them. A table that does not load does not stop the others. |
| `idColumn` | `"edge_id"` | The column with the road ids. |
| `keys`, `roadsBy(sql, column)` | `["osm_id", "name"]`, none | A result with no `idColumn` finds its roads by the first of `keys` that it has: `roadsBy` gives the SQL of the road ids. |
| `sql` | `""` | The start text of the line. |
| `label` | `"Data"` | The label of the dock. |
| `limit` | `1000` | The most rows in the table. |
| `card` | `true` | The road card beside the table, in place of the popup. |
| `guard` | `true` | `false`: the person's own SQL does not go through the read-only guard. |

## What the person does

- **The title row.** After the label and the note, the controls are three joined groups: **Table | Chart** (what the dock shows), **Tables | CSV** (the data), and **Light | Colour ▾ | Focus ▾** (the map). Then **?** opens a help window with one row for each control.
- **Tables.** The list of the tables opens in the side column beside the table or the chart, where the card of a selected road shows: one of the two at a time, the last one opened. The table and the chart stay in view. It has a search field (by name or description; Enter opens the first table, Escape closes the list), a group for each schema with its number of tables (the page's own `extra` first), and a card for each table with its name, its number of rows and one line of what it holds. A click on a card shows the table's rows and closes the list: the line gets `SELECT * FROM <table>`, which you can change and run again.
- **The line.** A click on it opens it as a text box. **Ctrl+Enter** or **Run** runs it, and **Escape** folds it. An error shows under the line, in the database's words. Only one `SELECT` or `WITH` statement runs: the guard refuses a statement that writes, loads, or reads a file or an address.
- **The table.** The note in the dock's title row has the number of rows: "1 000 of 2 765 rows · 3 columns · 5 ms". The table shows at most `limit` rows, but **CSV** has all the rows (at most 1 000 000), and a click on a header sorts all the rows. A DATE shows as `2026-06-10`, a TIMESTAMP as `2026-06-10 08:30:00`, and a geometry as `(32 bytes)`.
- **The light.** The roads of the table light on the map (the highlight set `dock`, in roadstyle's select purple). A new table changes the light. A table that a colour or a focus already shows has no light. **Light** in the title row turns the light off and on: off, the map shows its own colours and the table stays. The browser keeps the choice. A closed dock lights nothing.
- **A row.** A click selects its road and zooms to it. The side column then shows the road's card: its name, its main facts as chips (class, length, speed limit, one-way, the networks), its other fields in small type with rounded numbers, and its id with **Copy id** and **Zoom**. The card leaves out the fields of roadstyle's drawing (`casing_*`, `fill_level` and others). In a result of names, a click selects the roads of that name.
- **Table | Chart.** The same result as a chart ([A chart](dashboard-parts.md#a-chart)). The first chart comes from the columns: a date or a time and a number give a line, a text and a number a bar, one number a histogram, two numbers a scatter. **Kind**, **X** and **Y** change it, and **SVG** downloads it. A histogram counts all the rows, not only the table's. `data.chart({kind, x, y, title})` shows a chart from JavaScript, and `data.view("table" | "chart")` switches the view. The **Kind** buttons have a tooltip that says how to use each kind. On a computer, **Kind**, **X** and **Y** are a column at the left of the chart, and the chart has no title line: it uses the full height of the box. **SVG** is in the top right corner of the chart. The box of the chart scrolls only when the chart is taller than the box (many bars at their least height). On a phone, **Kind**, **X** and **Y** are a row over the chart. **X** and **Y** offer only the columns that fit the kind (for a bar or a pie, X is the groups and Y is "(count of rows)" or a measure; for a line, X is a number, a date or a time; for a histogram, X is a measure; for a scatter, X and Y are two measures). A road id, a geometry or a list is never offered. When the kind changes, X and Y move to a column that fits. A bar or a pie whose X is a number with more than 40 values (a length, say) shows the rows in ranges of X: about 6 slices or 12 bars, over all the rows. In the Chart view, the chart takes the width of the side column while it has no road card and no list of tables; when one of the two opens, the column comes back. The Table view keeps the side column with its hint, so that the table does not change its width. For a chart in the panel from Python, see [Charts](charts.md).
- **Colour ▾.** "+ Colour the roads of this table" gives one colour for each value of a text column with 2 to 8 values (for example `highway`), else one colour, with a legend row for each colour. Each layer has a check box that turns it off and on, and ✕ that removes it.
- **Focus ▾.** "+ Focus on the roads of this table" keeps these roads, and the other roads fade (`rs.fade`) or hide. One focus is on at a time; **None** turns it off. Each focus has **Fade / Hide** and ✕.

## From JavaScript

`data.run(sql?)` puts `sql` in the line and runs it, and gives the result. `data.show({sql, columns, rows, more})` shows a result that you made. `data.sql()`, `data.result()`, `data.csv()` and `data.stop()` give the line, the result, the CSV text, and stop a run. `data.roads(sql)` gives the road ids (on the map) that the SQL selects by `idColumn`. `data.colour(groups, {sql})` and `data.focus(ids, {sql, mode})` add the same layers as the buttons; `data.layers()` lists them. For [Ask](ask.md): `data.idColumn`, `data.keyOf(result)` (the column that finds the roads of a result, or `null`) and `data.roadsOf(result)` (its roads on the map). `data.roads(sql)` refuses a query of more than 100 000 roads. The events are `run` (`sql`, `columns`, `rows`, `more`, `ms`, `source`), `error` (`sql`, `message`, `source`) and `layers`.

`tests/test_data_dock_browser.py` checks the data dock with a fake host.
