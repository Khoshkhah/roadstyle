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

- **The line.** A click on it opens it as a text box. **Ctrl+Enter** or **Run** runs it, and **Escape** folds it. An error shows under the line, in the database's words. Only one `SELECT` or `WITH` statement runs: the guard refuses a statement that writes, loads, or reads a file or an address.
- **The table.** The note in the dock's title row has the number of rows: "1 000 of 2 765 rows · 3 columns · 5 ms". The table shows at most `limit` rows, but **CSV** has all the rows (at most 1 000 000), and a click on a header sorts all the rows. A DATE shows as `2026-06-10`, a TIMESTAMP as `2026-06-10 08:30:00`, and a geometry as `(32 bytes)`.
- **The light.** The roads of the table light on the map (the highlight set `dock`, in roadstyle's select purple). A new table changes the light. A table that a colour or a focus already shows has no light.
- **A row.** A click selects its road and zooms to it. In a result of names, a click selects the roads of that name.
- **Colour ▾.** "+ Colour the roads of this table" gives one colour for each value of a text column with 2 to 8 values (for example `highway`), else one colour, with a legend row for each colour. Each layer has a check box that turns it off and on, and ✕ that removes it.
- **Focus ▾.** "+ Focus on the roads of this table" keeps these roads, and the other roads fade (`rs.fade`) or hide. One focus is on at a time; **None** turns it off. Each focus has **Fade / Hide** and ✕.

## From JavaScript

`data.run(sql?)` puts `sql` in the line and runs it, and gives the result. `data.show({sql, columns, rows, more})` shows a result that you made. `data.sql()`, `data.result()`, `data.csv()` and `data.stop()` give the line, the result, the CSV text, and stop a run. `data.roads(sql)` gives the road ids (on the map) that the SQL selects by `idColumn`. `data.colour(groups, {sql})` and `data.focus(ids, {sql, mode})` add the same layers as the buttons; `data.layers()` lists them. For [Ask](ask.md): `data.idColumn`, `data.keyOf(result)` (the column that finds the roads of a result, or `null`) and `data.roadsOf(result)` (its roads on the map). `data.roads(sql)` refuses a query of more than 100 000 roads. The events are `run` (`sql`, `columns`, `rows`, `more`, `ms`, `source`), `error` (`sql`, `message`, `source`) and `layers`.

`tests/test_data_dock_browser.py` checks the data dock with a fake host.
