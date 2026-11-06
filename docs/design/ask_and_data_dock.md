# The bottom dock, the data dock and Ask

Status: **design, for Kaveh's review** (2026-11-05). No code yet. The code starts after Kaveh approves this design.

The mock-up runs on **roadstyle 0.28.0** from PyPI (it started on 0.27.1, which has no accent ring on an open card that folds).

A mock-up on Monaco (outside the repository) found three points, which are in this text now: the dock must be opaque, the panel's
control rules must also apply in the dock, and the dashboard needs an error colour (`--rs-err`).

Kaveh's review of the mock-up (2026-11-05) changed three more points:

1. The result table had a bad layout: four columns spread over the full width, headers centred above left-aligned values, and the
   actions on a row of their own. Now the columns have their own width, a number is at the right under a right-aligned header, each
   header shows its type, and the actions are in the title row of the dock ([The data dock](#2-the-data-dock)).
2. The Ask card had a scroll area inside the scrolling panel: two scrolls, one in the other. Now Ask is a view that takes the whole
   panel, as the design panel does, and the panel's body is the only scroll ([Ask](#3-ask)).
3. The question box must stay in view when the person scrolls the panel. Now it stands at the bottom of the panel (see 5).

Also: the credits box in the bottom corner (`#rs-scalebox`) hides while the dock is open.

Later the same day, Kaveh also asked for these:

4. The road's card stands beside the table in the dock, in place of the map's popup ([The road card in the dock](#the-road-card-in-the-dock)).
5. Ask has no scroll in the panel's body: the view fills the panel, and the conversation is its only scroll. The question box is a plain
   row at the bottom of the view. A sticky box over the conversation looked like a white box on the panel and let text show under it.
6. No privacy notice card before the first question ([What goes to the provider](#what-goes-to-the-provider)).
7. The result table must scroll. In the mock-up the table's box took the height of all its rows (27 916 px for 1000 rows) and the dock
   cut it, so it did not scroll. Now the box has the height of the dock, and it scrolls up and down and sideways. Its two scrollbars are
   always visible ([The dock's table](#the-docks-table)).
8. Each question with its answer is a card that the person can remove. A failed query that the agent fixed does not show as a red error
   above a right answer: it goes into the details ([The view](#the-view)).
9. The agent can also change the map: colour roads, filter the map, and move the map ([The map tools](#the-map-tools)). It still
   cannot change the data.
10. The agent sees all the host's data, not one table ([The schema](#the-schema)). The conversation scrolls by the panel's own protocol
   (`rs-pbody`). **Key** is a button, and its form has "Back to chat". The question box is one box with a round send button. A page with
   Ask has the card look of the panel by default.

## Problem

duckOSM Studio (`Khoshkhah/duckosm-studio`) builds a road network into DuckDB in the browser. Until 2026-11-05 it had an SQL box in
card 5 of its side panel. The box was removed:

- The card folded by itself about 3 s after a build, so the box went away while the person typed.
- The result box was 257 px wide. A table of roads has 10 or more columns, so the box showed only 2 or 3 of them.

Kaveh's conclusion: SQL cannot live in a vertical panel. It needs a wide dock under the map. Kaveh also wants a person to ask a question
in words and get the SQL, the table and the roads on the map. A free model in the browser was rejected. Only the person's own API key is
in scope.

This design adds three parts to the roadstyle dashboard:

| Part | What it is | Who uses it |
|---|---|---|
| [1. The bottom dock](#1-the-bottom-dock) | A wide area under the map, as wide as the map, with a grip that changes its height. A bottom sheet on a phone. | Any page: an attribute table, a list of changes, sensor readings |
| [2. The data dock](#2-the-data-dock) | One query line above a wide result table, in the bottom dock | A page that can run SQL on its own data |
| [3. Ask](#3-ask) | An AI agent in the side panel. It uses the person's own key. Its tools are a read-only query of the data dock and three map tools (colour, filter, move). It cannot change the data. | A page with the data dock |

roadstyle knows no DuckDB. The host page gives two functions: `query(sql)` and `schema()`.

## Rules that this design follows

- The dashboard standard is Kaveh's. The three parts use the standard's tokens, cards, tabs, scroll areas, sheet and windows. They do not
  change the look of other parts.
- Each part works in the light and the dark theme, with the theme tokens only (`--ink`, `--mut`, `--bg`, `--card`, `--line`, `--accent`,
  `--accent-fill`, `--rs-box-bg`, `--rs-tb-*`).
- At 700 px or less, each part has its phone form.
- Each part has a browser test, a place in `tests/test_dashboard_themes_browser.py`, and each scroll area is in `_PS_AREAS`
  (`panelscroll.js`, `dashboard.css`) and in `tests/test_dashboard_scroll_browser.py` (`AGENTS.md`).
- No key goes into a page file. No request goes to a server of roadstyle or of the page's author.

## 1. The bottom dock

### What it does

The bottom dock is a layout part of every dashboard, as the panel and the windows are. It has no content of its own. A page or a part
puts one or more contents in it. A dock with no content is not on the page.

### The API

```js
const el = document.createElement("div");          // the page's own content: a table, a chart, a list
rs.dock.add({id: "changes", label: "Changes", el});  // the dock shows on the page, closed
rs.dock.open("changes");                            // open the dock and show this content
rs.dock.close();
document.addEventListener("rs:dockchange", e => console.log(e.detail));   // {open, id, height}
```

| Method | What it does |
|---|---|
| `add({id, label, el, note})` | Adds a content. `label` is its tab. `note` is a short text after the tab (for example "12 rows"). An `id` that is used twice is an error. |
| `remove(id)` | Removes a content. The dock goes away when no content stays. |
| `open(id?)`, `close()`, `isOpen()` | Opens the dock (with the content `id`, else the last content), closes it, gives its state. |
| `show(id)` | Shows the content `id` and does not change the open state. |
| `note(id, text)` | Changes the note of a content. |
| `height()`, `height(px)` | Gives or sets the open height (desktop). |
| `list()` | The ids of the contents, in their order. |

| Event | `detail` | When |
|---|---|---|
| `rs:dockchange` | `{open, id, height}` | The dock opens, closes, changes its content, or the person drags its height |

`rs.dock` is in `rs` (`api.js`) and in `index.d.ts`. The dock is `dashboard/dock.js` and is in `files.txt`: it is small (about 4 KB with
its CSS), and a page that does not call `rs.dock.add` has no dock on the screen.

### The layout on a desktop

```
+-------------------------------------------------------------+
| +---------+                                           [bar] |
| |  panel  |                 map                       [   ] |
| |         |                                           [   ] |
| |         |                                           [   ] |
| +---------+                                                 |
|=========================== grip ============================|
| [Data] [Changes]  12 rows                  [Collapse] [x]   |
| SELECT name, highway, length_m FROM edges WHERE ...    [Run]|
| name          | highway   | length_m | maxspeed | lanes | ... |
| Riia          | primary   | 1 240.5  | 50       | 2     | ... |
+-------------------------------------------------------------+
```

- **Width.** The dock has the left and the right edge of the map. In `layout="overlay"` the map fills the window, so the dock is as wide
  as the window. The floating panel and the toolbox stay above the dock. In `layout="dock"` the panel is a column of its own, so the
  dock is under the map only. With `street_view="dock"`, the dock ends at the divider of Street View.
- **The map gets shorter.** An open dock sets `html.rs-dock-open` and the CSS variable `--rs-dock-h` (its height). The map container
  ends at the top of the dock, and the map calls `map.resize()`. This is the method of the docked Street View (`html.rs-sv-docked` and
  `--rs-sv-w`). The free part of the map (`freeArea`, `rsFreePad`) then follows by itself, because it reads the map container.
- **The other parts end above the dock.** The floating panel, the toolbox, the boxes of the toolbox and the box in the bottom corner
  (scale, zoom, credits) read `--rs-dock-h`. In `toolbar.js`, the low edge of a box is `innerHeight` now. It becomes the top of the dock.
  This is the only change in an existing part, and it does not change the look of a page without a dock.
- **Height.** The grip is a strip of 8 px on the top edge of the dock, with the cursor `row-resize`. It has no colour of its own: while the
  pointer is on it, or while it is dragged, the dock's top edge is `--accent`, as a 2 px inset shadow of the dock. An inset shadow follows
  the round top corners; a line on the grip went straight across them (Kaveh, 2026-11-05). The person drags it. The height is
  at least 120 px and at most 70 % of the window. The page keeps the height and the open state in this browser
  (`rs-dock:<location.pathname>`), as the docked Street View keeps its share. A double click on the grip closes the dock or opens it again.
- **Closed.** A closed dock is its title row only (32 px): the tabs, the note, and a button with an up arrow. The map ends above this row.
  A click on a tab or on the arrow opens the dock.
- **Title row.** The tabs are `rs-tabs` and show only when the dock has two or more contents. With one content, the row shows its
  label as a title. The note follows (for the data dock: "10 rows · 3 columns · 2 ms"). At the right: the actions of the content (for the
  data dock: Tables, CSV, Show on map), then "Collapse" and, for a content that the person can remove, "x". The actions hide while the
  dock is closed.
- **Credits.** The box in the bottom corner (scale, zoom number, credits: `#rs-scalebox`) hides while the dock is open on a desktop, and
  shows again when the dock closes (Kaveh, 2026-11-05). On a phone the credits button is in the bar, so nothing changes there.
- **Edge to edge, round top corners.** The dock uses all the width and goes down to the bottom of the window, with no gap at the left, the
  right or the bottom (Kaveh, 2026-11-05). Its two top corners are round (14 px, as the panel's card), and with the card look the map
  goes on under the dock, so the map shows behind these corners. A soft shadow above the dock (`0 -4px 18px rgba(0,0,0,.16)`) and a
  `--line` on its top edge separate it from the map. With the card look, the panel's card and the bar end 16 px above the dock.
  (A dock that floated as a card, with a margin on three sides, was tried in the mock-up and refused: the table needs all the room.)
- **Look and transparency.** The dock has a `--line` on its top edge and `--ink` text. With the card look the map goes on under the dock,
  so the dock is the panel's glass: the background of the panel's card, `--rs-card-bg`, with its blur (6 px). It follows the person's
  slider "Card behind the text" in Settings together with the panel (Kaveh, 2026-11-05: "what about transparency of sql panel?"). The table
  (`--bg`) and the road card (`--card`) stay solid boxes on the glass: their text reads well, and the rows do not show through the fixed
  header. With the frame look the dock is opaque (`--bg`): only the page's background is behind it, and a see-through dock showed the white
  page in the dark theme.
- **Controls.** `dashboard.css` gives buttons, text boxes and `sb-primary` their look only inside the panel (`#sb`). The same rules also
  apply in the dock (`#rs-dock`), else its buttons are white in the dark theme.

### The toolbox and the dock

The toolbox never covers the dock (Kaveh, 2026-11-05: "it has issue in toolbox overlapping"). The mock-up found two overlaps: on a
window of 650 px the bar at the right edge went 32 px into the dock, and on every window the Settings box went 15 px into it, because
`toolbar.js` measures against the bottom of the window.

- **The boxes of the toolbox.** In `keepInside` (toolbar.js), the low edge of a box is the dock's top (4 px above it), not `innerHeight`:
  one line. The box moves up, and scrolls when it is still too tall. `keepInside` runs again on a change of the dock's height.
- **A bar at a side** has the free height above the dock as its largest height (`max-height`). It is a column flexbox that wraps, so in a
  short space it takes a second column, as it does in a short window now. It is centred in the free part.
- **A bar along the bottom** ends above the dock (8 px; 24 px with the card look).
- **A bar along the top** does not change.
- **A shorter box must scroll** (a fault of roadstyle now, which the dock makes common; Kaveh, 2026-11-05: "scroll bug! I can't scroll
  it"). `keepInside` clears `maxHeight` at the start of each fit, so for a moment the box has nothing to scroll and the browser sets its
  `scrollTop` to 0. And `panelscroll.js` adds the class `rs-scrolling` on each scroll, which `keepInside` watches: so each scroll ran a fit
  and jumped back to the top. Two changes in `keepInside`: keep `scrollTop` across the fit, and no fit for a change of `rs-scrolling` only.
  Checked in the mock-up at 1200 × 560 with the bar at the top and at the right: the base map, Settings and Roads boxes scroll to their
  end with the wheel. Without a dock, the same fault shows in a short window.

Measured in the mock-up at 1366 × 900, 768, 650 and 560 px: the bar and an open Settings box end above the dock in each case.

**The place of a bar along the top or the bottom** (Kaveh, 2026-11-05: "for top we should have middle, left and right as option"): a new
option of the toolbox, beside its edge.

| | Option | Settings box | Where |
|---|---|---|---|
| `left` | `dashboard={"toolbar": {"position": "top", "align": "left"}}` | "Toolbar place": Left | 8 px after the panel's card (or the window's edge) |
| `middle` (default) | `"align": "middle"` | Middle | in the middle of the free part, as now |
| `right` | `"align": "right"` | Right | 8 px from the edge on the other side |

The row "Toolbar place" shows in the Settings box under "Toolbar" only while the bar is at the top or the bottom. The person's choice is
kept in this browser with the other layout choices (`savePlace("align", v)`). The code is one change in `followPanels` (overlay.js): it
sets `left` from `lo`, `hi` and the width of the bar in place of the middle only. A page with Ask (duckOSM Studio) starts with the bar at
the **top right** (Kaveh's choice): the map then has the full height at the right, and the panel has the left.

### The layout on a phone

At 700 px or less the dock is a bottom sheet, as the panel, Street View and Google 3D are (`windows.js`).

- The sheet has the same heights as the panel's sheet: closed, 40 % and full, and the same grip (44 px with an arrow).
- One sheet is open at a time. When the dock opens, the panel's sheet goes to 0 and Street View and Google 3D close. When one of them
  opens, the dock closes. `windows.js` gets one more listener of `rs:dockchange` for this, next to its listeners of
  `rs:streetviewchange` and `rs:google3dchange`.
- A closed dock is a small round button "Data · 10 rows" at the right, above the panel's sheet. It hides while the panel's sheet is full.
- A wide table scrolls sideways inside the dock. The first column stays in view. The page itself never scrolls sideways.

### The dock's table

Each content of the dock is the page's own element. For the common content, a table, the dock gives one part, so that every page has
the same table:

```js
const t = rs.dock.table({
  columns: [{name: "edge_id", type: "BIGINT"}, {name: "name", type: "VARCHAR"}, {name: "length_m", type: "DOUBLE"}],
  rows: [[8121729169906061189n, "Riia", 1240.5]],
  idColumn: "edge_id",       // optional: the column with the road ids
  more: true,                // optional: the rows are not all the rows ("1000 rows (there are more)")
});
rs.dock.add({id: "roads", label: "Roads", el: t.el});
t.set({columns, rows});      // new rows in the same table
```

- It is a box with a `--line` border and 8 px corners, in an `rs-scroll` area ([Dashboard parts](../guides/dashboard-parts.md#a-list-or-a-table-that-scrolls)).
  The box is as wide as its columns, and it scrolls sideways when the columns are wider than the dock. The columns do not stretch to fill
  the dock: a table of 3 columns is narrow and stays at the left.
- The box has the height of the dock, never the height of its rows, so it scrolls up and down. A test scrolls a table of 1000 rows with
  the mouse wheel and checks that the box ends inside the dock and that the header row stays at the top.
- The two scrollbars of the box are always visible (thin, the dashboard's thumb colour: `--ink` at `--rs-thumb`). This is different from
  the other scroll areas, where the scrollbar shows only under the pointer: in a data table, the person must see at once that there are
  more rows and more columns. A browser test must start Chromium without `--hide-scrollbars` to see them.
- Each column has its own width (`width: max-content`), and a cell is at most 320 px wide. A longer text is cut with "...", and the full
  text is in its tooltip.
- The header row has the `--card` background and stays in view. Each header shows the column name and, under it in small muted capitals,
  its SQL type (VARCHAR, BIGINT, DOUBLE). The tooltip of a header is the column's description from `schema()`.
- A number column is at the right, its header too, with tabular figures, so the digits line up. Text, a boolean and an id column are at
  the left.
- Each row has a `--line` under it, and every second row has a light tint. The row under the pointer has an accent tint, and the selected
  row a stronger one.
- The first column stays in view when the table scrolls sideways (a line at its right edge shows it).
- A BIGINT (a JavaScript `BigInt`) shows exactly. An id is read as text (`String(value)`), never as a `Number`, because a 64-bit
  `edge_id` does not fit a `Number` ([JavaScript API](../reference/javascript.md)).
- `null` shows as a muted "null".
- With `idColumn`, a click on a row selects that road and zooms to it: `rs.select(id)` and `rs.focus(id)`.
- Over 1000 rows, the table draws only the rows in view (it keeps one height per row). This keeps a table of 50 000 rows fast.

**Sort** (Kaveh, 2026-11-05: "we need to add sort part for each column"). A click on a column header sorts by that column: rising, then
falling, then the order of the SQL again. The sorted header has the accent colour and the arrow of the table part (`th[data-sort]`; the
rule is also for `#rs-dock`, because `dashboard.css` has it only in `#sb`). A result of 1000 rows or fewer sorts in the browser at once.
A longer one runs its SQL again inside `SELECT * FROM (...) ORDER BY "<column>" ASC|DESC NULLS LAST`, so the first 1000 rows are really
the smallest or the largest of all the rows. The order follows the type: numbers (also a 64-bit `BigInt`) as numbers, text in the order
of the language with numbers in it as numbers, and `null` last. The CSV follows the same order.

**The 1000 rows on the screen** (the option `limit`) stay as they are: nobody reads more rows in a table, and a person makes a long result
shorter with the SQL. The limit is only about what is drawn, never about the data:

- The note gives the true count: "1 000 of 2 765 rows" (one more query: `SELECT count(*) FROM (...)`).
- **CSV** has all the rows (the SQL runs again with no limit of 1000; at most 1 000 000).
- **Show on map** lights all the roads of the result, not only the first 1000 (the SQL runs again for the ids; at most 100 000, as the
  map tools). Before, a result of 2 765 roads lit 1000 of them, and nothing said so.

## 2. The data dock

### What it does

The data dock is one content of the bottom dock. It has two rows:

1. **The query line** and **Run**. The line shows the SQL that made the table, in a monospace font. It is one line by default (the SQL
   on one line, cut with "..."). A click opens it to a text box of up to 10 lines. Run or Ctrl+Enter (Cmd+Enter on a Mac) runs the SQL.
   Escape folds the line again.
2. **The table** (the dock's table above).

The note and the actions (**Tables**, **CSV**, **Show on map**) are in the title row of the dock, so they take no row of their own:

```
| Data  10 rows · 3 columns · 2 ms                    [Tables] [CSV] [Show on map]  v |
| SELECT highway AS road_class, count(*) AS edges, round(sum(len...         [ Run ]  |
| +---------------------------+                                                      |
| | road_class | edges |   km |                                                      |
| | VARCHAR    |BIGINT |DOUBLE|                                                      |
| | residential|   919 | 31.66|                                                      |
| | service    |   781 | 20.12|                                                      |
| +---------------------------+                                                      |
```

There is no separate SQL editor. The query line is the editor.

### The API

```js
import {dataDock} from "./dashboard/data/data_dock.js";

const data = dataDock({
  dashboard: rs,
  query: async (sql, {signal}) => duck.query(sql),       // the host runs SQL on its own data
  schema: async () => tablesAndColumns(),                  // the tables, the columns and what each one means
  idColumn: "edge_id",                                     // the column with the road ids
  sql: "SELECT highway, count(*) AS edges FROM edges GROUP BY 1 ORDER BY 2 DESC",   // the start text (optional)
  label: "Data",                                           // the tab of the dock
  limit: 1000,                                             // the most rows in the table
});
data.run();                                                // run the SQL of the line
data.run("SELECT * FROM edges WHERE highway = 'primary'"); // put this SQL in the line and run it
data.addEventListener("run", e => console.log(e.detail));  // {sql, columns, rows, more, ms, source}
```

| Option | Default | What it is |
|---|---|---|
| `dashboard` | `window.rs` | The page's dashboard. |
| `query(sql, {signal})` | (necessary) | Runs one statement on the host's data. It gives `{columns: [{name, type}], rows: [[...], ...]}` (a value is a JavaScript string, number, boolean, `BigInt` or `null`), or it throws an `Error` with the database's message. `signal` is an `AbortSignal`: Stop aborts it. |
| `schema()` | (necessary) | Gives the tables (see [The schema](#the-schema)). Ask uses it, and the data dock uses it for its list of the tables. |
| `ready` | none (ready at once) | A promise that ends when the host's data is loaded. Run and Ask wait for it. |
| `idColumn` | `"edge_id"` | The column with the road ids. |
| `keys` | `["osm_id", "name"]` | Other columns that find roads when a result has no `idColumn` (see [The roads of a result](#the-roads-of-a-result)). |
| `roadsBy(sql, column)` | none | The host's lookup: the SQL that gives the road ids of the result `sql` by its `column`. duckOSM Studio: ``SELECT edge_id FROM driving.edges WHERE "<column>" IN (SELECT "<column>" FROM (<sql>))``. Without it, only `idColumn` finds roads. |
| `sql` | `""` | The start text of the line. |
| `label` | `"Data"` | The tab of the dock. |
| `limit` | `1000` | The most rows in the table. The data dock asks for one more row, so it knows that there are more. |
| `card` | `true` | The road card beside the table, in place of the popup (see [The road card in the dock](#the-road-card-in-the-dock)). |
| `guard` | `true` | `true`: the person's SQL also goes through the read-only guard (see [The read-only guard](#the-read-only-guard)). `false`: only the agent's SQL does. |

| Method | What it does |
|---|---|
| `run(sql?, {source})` | Puts `sql` in the line (else uses the line) and runs it. It gives the result, or throws the error. `source` is `"person"` (default) or `"ask"`. |
| `show({sql, columns, rows, more})` | Shows a result that the host made. Does not run. |
| `sql()` | The text of the line now. |
| `result()` | The result now: `{sql, columns, rows, more}`. |
| `showOnMap()` | The same as the button. |
| `csv()` | The text of the CSV file. |
| `stop()` | Aborts the run. |
| `open()`, `close()` | Opens or closes the bottom dock with this content. |

| Event | `detail` | When |
|---|---|---|
| `run` | `{sql, columns, rows, more, ms, source}` | After each run that worked |
| `error` | `{sql, message, source}` | After a run that failed |

### The parts of the data dock

- **Run.** The data dock checks the SQL with the guard (when `guard` is on), adds the row limit, calls `query`, and shows the table. While
  it runs, Run becomes Stop. The note is "12 rows · 4 columns · 6 ms" or "1000 rows (there are more) · ...".
- **An error.** The line stays open, and a red line under it shows the database's message. The old table stays. The colour is a new
  token, `--rs-err` (`#b91c1c` light, `#fca5a5` dark), with a contrast of 4.5 or more in both themes. Ask uses it for a failed query.
  The dashboard has no error colour now: `--rs-chart-miss` is a grey.
- **CSV.** Downloads the rows of the table as `<label>.csv`: a header row, comma separated, a text with a comma, a quote or a new line in
  quotes, a `BigInt` exactly, `null` as empty. The file has the rows of the table only (at most `limit`). The note in the bar says so when
  there are more.
- **Show on map.** When the result has `idColumn`, the button lights those roads with `rs.highlight(ids)` and zooms to them with
  `rs.focus(ids)`. A second click (or a new run) takes the light away (`rs.highlight([])`). An id that is not on the map is not lit, and
  the bar says "40 of 42 roads are on the map".
- **A click on a row** selects that road and zooms to it (`rs.select(id)`, `rs.focus(id)`). The row stays marked, and the road's card
  opens beside the table.
- **The list of tables.** The button "Tables" in the title row opens a list of the tables and their columns (from `schema()`), with the
  description of each column in its tooltip. A click on a name puts it in the line at the cursor.

### The help of the two parts

Each part has a "?" of roadstyle's help part (`rs.help.button`, [Dashboard parts](../guides/dashboard-parts.md#a-help-window)): the same
button and the same window as the panel's own help (Kaveh, 2026-11-05: "add helper to both sql and ask panel").

| Part | Where the "?" is | The words |
|---|---|---|
| The data dock | in its title row, after the note | What the dock is; the SQL line (only SELECT or WITH: the data does not change), Tables, CSV, Show on map (also for a table of street names), a click on a row, the top edge (drag, double click); the 1000-row limit |
| Ask | in its top row, after the provider and the model | What Ask does; Key (the free keys, the key stays in this browser), Examples, an answer card (its SQL, Map, Table, ✕), MAP and Undo, New; what goes to the AI service, and that an AI service can be wrong |

A host can give its own words with the options `help` of `dataDock` and of `askPanel` (`{title, intro, terms, note}`), or `help: false`.

### The roads of a result

A model often writes `SELECT DISTINCT name FROM ...` for "which roads ...", although the prompt asks for `edge_id` (Kaveh's test with Groq,
2026-11-05: the answer named three streets, and nothing lit on the map; "it is the same!"). A rule that the model can break is not enough,
so the data dock finds the roads of a result itself:

1. The result has `idColumn`: these are the roads.
2. Else the first of `keys` that the result has (`osm_id`, then `name`): the host's `roadsBy(sql, column)` gives the road ids of all the
   values of that column. Monaco: the three street names became 95 road edges.
3. Else the result has no roads: no Show on map, and the answer card has no Map.

The same lookup serves a click on a row (the roads of that row's name: "Tunnel Albert II" lit its 7 edges), Show on map, the Map button
of an answer and the light after an answer. The prompt also says it plainly: "Also for a list of street names: `SELECT edge_id, name ...`
(no DISTINCT), not `SELECT DISTINCT name`."

### The road card in the dock

A click on a row of the table, or on a road of the map, shows the road's fields in a card at the right of the table, in the dock. The
map's popup is off (`road_popup=False`), so one click has one place for its fields.

```
| SELECT edge_id, name, highway, round(length_m) AS length_m, ...                     [ Run ] |
| +----------------------------------------------------------+  +----------------------+     |
| | edge_id     | name             | highway | length_m | ...|  | Road               x |     |
| | 1943370...  | Tunnel Albert II | primary |      672 |    |  | Tunnel Albert II     |     |
| | 6194277...  | Tunnel Rainier   | primary |      353 |    |  | edge_id  1943370...  |     |
| +----------------------------------------------------------+  | highway      primary |     |
```

- The card is roadstyle's existing part `road_card` (`roadcard.js`), with no change. It fills on `rs:select` and empties on
  `rs:deselect`, so a click on the map and a click on a row show the same card. The card shows the same fields as the popup.
- The card is 320 px wide and stands right after the table. The table's box then has at most the width of the dock minus the card.
  The card has a title row "Road" and a close button (`rs.select(null)`). The card scrolls by itself when the road has many fields.
- A click on a road of the map opens the dock (when it is closed) and marks the road's row when the table has it.
- On a phone the card covers the table inside the dock sheet. Its close button shows the table again.
- `dataDock({card: true})` turns this on (the default). A page that wants the popup gives `card: false` and keeps `road_popup`.

### The row limit

The data dock does not send the person's SQL as it is. It sends:

```sql
SELECT * FROM (
<the SQL, without a ; at its end>
) AS rs_q LIMIT 1001
```

This puts the limit on every statement and also stops a second statement: `SELECT * FROM (DROP TABLE edges)` is not correct SQL. A test
checks that an `ORDER BY` in the SQL keeps its order through this wrap in DuckDB.

## 3. Ask

### What it does

Ask is a view that takes the whole side panel, as the design panel and the level editor do. A card of the host opens it, and Back shows
the host's cards again. The person types a question in words, for example "Which primary roads are longer than 1 km?". An
agent writes SQL, runs it with the data dock, reads the result, and writes a short answer. Each answer puts its SQL and its table into the
data dock and lights the roads.

The agent uses the person's own key. The browser sends the requests directly to the provider. There is no model in the browser and no
server of roadstyle or of the page.

### The API

```js
import {askPanel} from "./dashboard/ask/ask_panel.js";

const ask = askPanel({
  dashboard: rs,
  data,                                         // the data dock: every tool of the agent runs its SQL through it
  about: "A road network of Tartu, built by duckOSM in this browser. One row of edges is one direction of a road.",
  dialect: "DuckDB",
  examples: ["Which streets are longer than 1 km?", "How many one-way roads are there?"],
});
ask.addEventListener("answer", e => console.log(e.detail));   // {question, text, sql, rows}
rs.sections.add({id: "ask", label: "Ask", note: "Ask a question about the data", open: () => ask.open()});   // an "open" card
```

| Option | Default | What it is |
|---|---|---|
| `dashboard` | `window.rs` | The page's dashboard. |
| `data` | (necessary) | The data dock. Ask uses its `schema()`, its guard, its row limit and its table. |
| `about` | `""` | One or two sentences about the data. They go into the prompt. |
| `dialect` | `"SQL"` | The name of the database's SQL, for the prompt (`"DuckDB"`). |
| `examples` | `[]` | Questions that the empty card shows as chips. A click on a chip asks it. |
| `panel` | `#sb` | The host's dashboard panel. Ask draws into its `.sb-body`, as the design panel does. |
| `backLabel` | `"Back"` | The text of the back button. |
| `maxSteps` | `6` | The most model calls for one question. |
| `sendRows` | `30` | The most rows of one result that go to the model. |
| `providers` | the two built-in providers | For the tests: a fake provider (see [The tests](#the-tests)). |

| Method | What it does |
|---|---|
| `open()`, `close()`, `isOpen()` | Shows the Ask view in the panel (the host's cards hide), or shows the host's cards again. The conversation stays. |
| `ask(question)` | Asks a question, as the person does. It gives a promise of the answer. |
| `stop()` | Aborts the question now. |
| `clear()` | Starts a new conversation (the model forgets the earlier questions). |
| `remove(i)` | Removes the question `i` and its answer, as its ✕ does. |
| `history()` | The questions and answers of this conversation. |

| Event | `detail` | When |
|---|---|---|
| `answer` | `{question, text, sql, rows}` | The agent gave an answer |
| `error` | `{question, message}` | The question stopped with an error (no key, a refused key, too many failed queries) |
| `back` | none | The person clicks Back. Ask closes by itself. |

### The look of the panel

A page with Ask has the **card** look of the panel by default (`dashboard={"panel": {"look": "card"}}`; Kaveh, 2026-11-05): the panel
floats as a card with round corners and a margin, and the conversation reads as one card. duckOSM Studio sets it. The dashboard's own
default stays `frame` for other pages, and a look that the person keeps in Settings still wins.

### The view

```
+----------------------------------+
| Monaco                     [<>][]|   the panel's title row
| [< Back] Gemini · flash  Settings  [New]
| -------------------------------- |
| +------------------------------+ |   one card for each question
| | Which primary roads are    x | |   the question (bold) and its remove button
| | longer than 300 m?           | |
| | 5 primary road edges are     | |   the answer
| | longer than 300 m. The ...   | |
| | > 1 query · 5 rows   [Table] | |   the query that made the table
| +------------------------------+ |
| -------------------------------- |   only the conversation scrolls
| +----------------------+ [ Ask ] |   the question box: always at the bottom
| | Ask a question ...   |         |
| +----------------------+         |
+----------------------------------+
```

- **One scroll, by the panel's protocol.** While Ask is open, the panel's body (`.sb-body`) does not scroll: the view fills it exactly (a
  flex column of three rows: the top row, the conversation and the question box). Only the conversation scrolls. It is a panel scroll box,
  as the design panel's pane is: the class `rs-pbody` with `data-head` = the top row (class `rs-phead`), and `initPanelScroll()` after it
  is made. Its scrollbar space (`scrollbar-gutter: stable`, 10 px) goes out into the panel's margin with a negative margin of the same
  width, on the side of the scrollbar, so the cards line up with Back and with the question box (all start at the same x). So it has the
  panel's scrollbar at the outer edge of the panel (shown only under the pointer or while it scrolls), the line under
  the top row while it is scrolled, and the 38 px fade at the bottom edge while more is below. (The mock-up first used `rs-scroll`, the part
  for a list in a card: Kaveh saw the wrong scrollbar and no fade.)
- **The question box stays in view.** It is the last row of the view and never scrolls. It is one box (`--card`, a `--line` border, 14 px
  corners, the accent ring while it has the focus) with the text and a round send button inside it, at the bottom right: 32 px, `--accent-fill`,
  an up arrow. The box is 44 px high and grows with the text to 6 lines. While the agent works, the button is a stop square (Stop). Enter
  asks, Shift+Enter is a new line. (The mock-up first had a separate textarea and an "Ask" button of a different height: Kaveh found it not
  well aligned.)
- **Order.** The oldest question is at the top and the newest at the bottom, next to the question box. After each step the panel
  scrolls to the end.
- The top row has Back, the provider and the model, **Key** and **New** (a new conversation). Key and New are buttons of the same look. Key
  is filled while the key form is open ([The keys](#the-keys)). (A teal word "Key" did not look clickable.)
- An empty conversation shows one line about what Ask does, and the `examples` as chips. A click on a chip asks it.
- **The examples stay one click away.** After the first question, a small muted button **Examples ▴** is above the question box. It opens
  the same chips as a list over the chat, just above the box. A click on a chip asks it and closes the list, and a click outside closes
  it. The conversation stays. (Before, the chips were gone after the first question, and only New brought them back: Kaveh, 2026-11-05.)
  "New" shows the empty start again, with its hint and chips.
- With no key, the view shows "Ask needs your own key. Google Gemini and Groq give a free key." with the two links, and a button "Add a
  key" that opens the key form.
- **A card for each question.** A question and its answer are one card with an outline: a `--line` border, 12 px corners and no
  background, so the panel shows through it (Kaveh chose this look from the mock-up, 2026-11-05, over a card with a fill and over a
  card with no border). The question
  is its bold title. The answer is plain text (`textContent`). The view shows no HTML, no images and no links from the model.
- **Remove.** The ✕ at the right of the question removes the card. It also removes that question and its answer from the conversation
  that goes to the model with the next question, so the person can take away a wrong turn and ask again. When no card stays, the view
  shows the empty start again (the hint and the example chips). "New" removes all the cards.
- The question box is a `<textarea>`. Enter asks, Shift+Enter is a new line. While the agent works, Ask becomes Stop and the
  view shows each step on one muted line: "Writing SQL", "Running query 1", "Query 1 failed: Referenced column "lenght" not found. Trying
  again", "Writing the answer". All the step lines go when the answer comes.
- **One query.** The footer counts the query that made the table: "1 query · 5 rows". It opens to that SQL.
- **Each answer keeps its table and its map** (Kaveh, 2026-11-05: "table bottom doesnt work", "we should have map bottom too", "by default
  after answer apply both table and map"). A card keeps the result that it put into the dock and the map changes that it made. Its footer
  has two buttons at the right, **Map** and **Table**:
  - **Table** puts this answer's table back into the dock (its SQL in the line) and opens the dock. Before, Table only opened the dock,
    which showed the newest table: after a second question, the first card's Table showed the second table.
  - **Map** shows this answer's roads again and zooms to them: for a query, it lights the rows of its table (`rs.highlight`); for a filter
    or a colour, it applies that change again (also after its Undo, which then works again) and takes away the light of another answer. A
    card with no road ids has no Map.
  - **After each answer, both at once:** the dock shows the answer's table (it opens on a desktop) and the map shows its roads.
  - **Which table is the answer's.** When the answer changed the map (filter, colour, move), its table is the roads of the last map tool,
    not a later query of the model. A model often runs a small helper query after a filter, for its sentence ("… ORDER BY length_m DESC
    LIMIT 5" for "the longest"), and the dock showed those 5 rows in place of the 625 filtered roads (Kaveh, 2026-11-05: "why it limits to
    5?"). The helper query stays in the card's details ("1 query · 5 rows").
- **Bold and code.** A model writes `**bold**` and `` `code` ``. The view shows them as bold and as code, built from text nodes, so no HTML
  of the model goes into the page.
- **A short answer, not the table** (Kaveh, 2026-11-05: "not good", about an answer that listed 5 rows with their 19-digit `edge_id`
  values). The prompt says: "Answer in 1 to 3 short sentences: the count and the one or two most important facts, by street name. Never
  write edge_id values or a list of the rows." A model can still do it, so the view also cleans the text:
  - Lines that start with `- `, `* ` or `1. ` are a real list (`<ul>`), not text with dashes and an empty line.
  - A raw id goes: "edge 3363728794791538739", and any number of 12 digits or more. The table has the ids; a person reads the names.
  - A list of more than 3 items shows 3 and "… 2 more in the table", a link that opens this answer's table.
- **A failed query that the agent fixed** is not an error for the person. It shows only inside the open details, as a muted line "1
  failed attempt, fixed by the agent", which opens to the failed SQL and the database's message (in `--rs-err`). A red error shows in the
  card only when the question fails as a whole: after 3 failed queries, at `maxSteps`, with no key or a refused key.
- The error text is the database's first line, with no second full stop after its own "!" or ".".

### The agent loop

```
question
  -> model(system prompt + schema + conversation + question, tools: [run_query, color_roads, filter_roads, move_map])
       - gives a tool call run_query(sql):
           guard(sql) -> data.run(sql, {source: "ask"}) -> the result (or the error)
           -> to the model, and loop again
       - gives a tool call of a map tool:
           guard(sql) -> the ids -> rs.color / rs.setFilter / rs.focus -> a short result (or the error)
           -> to the model, and loop again
       - gives text: this is the answer -> stop
  stops also after maxSteps model calls, after 3 failed queries one after the other, or on Stop
```

1. Ask reads `data.schema()` once for each conversation and writes the schema text (see [The schema](#the-schema)).
2. Ask sends the system prompt, the schema text, the earlier turns of this conversation and the question to the model, with four tools:
   `run_query` and the three [map tools](#the-map-tools).
3. When the model calls `run_query(sql)`:
   - The guard checks the SQL. A refused SQL goes back to the model as an error ("Only one SELECT or WITH statement is allowed. Found:
     DROP.").
   - The data dock runs it, with the row limit. An error of the database goes back to the model as it is. The model then writes new SQL.
     This is the retry.
   - A result goes back to the model as: the column names and types, the first `sendRows` rows as JSON arrays, the number of rows, and
     "more rows: yes" when the result was cut. A text value is cut at 200 characters.
4. When the model gives text, that text is the answer. The last query that worked is the answer's query: the data dock shows its SQL and
   its table, and Ask calls "Show on map" when the table has `idColumn`.
5. The loop stops with an error after `maxSteps` model calls, or after 3 failed queries one after the other. The card shows the last error.
   **No silent stop:** any error of the agent (also one outside the loop, for example in the schema) ends the question with a red line on
   its card, and the question box works again. (Kaveh, 2026-11-05: a card with the question and nothing else.)
0. **The data first.** The host's data can still be loading when the person asks: duckOSM Studio loads a build, and the mock-up loaded 46
   tables through an ssh tunnel. The host gives `ready` (a promise; default: ready at once). Ask waits for it, with the step line "Loading
   the data…", before it reads the schema; the data dock's Run waits for it too. Before this, a question asked during the load stopped at
   once with "Cannot read properties of undefined (reading 'query')", and the card showed nothing. The test is "all the data is loaded",
   not "the database is open": the mock-up's first fix waited only for the connection, which opens before the tables load, and a question
   during the load then failed with "reading 'name'" (the main table was not there yet).
6. On a desktop, the data dock opens by itself on an answer with a table. On a phone it does not, because one sheet is open at a time and
   the person is in the panel's sheet. The view shows "Table" and the roads are lit on the map.

A question costs 2 to `maxSteps` model calls. Most questions take 2 or 3.

### The map tools

Kaveh added these on 2026-11-05. Each one changes only what the person sees on the map, never the data, and each one is a call of the
`rs` API that already exists. Each tool takes SQL that selects the `idColumn` of the roads, so the agent finds the roads with the same
SQL as for a question, and the same guard checks it.

| Tool | Arguments | What the page does | `rs` call |
|---|---|---|---|
| `color_roads` | `groups: [{label, color, sql}]` (1 to 8 groups; `color` is `#rrggbb`) | Colours the roads of each group and adds one row for each group to the legend (a `line` mark). A group with the label of an earlier group replaces it. | `rs.color([{color, ids}])`, `rs.legend.add` |
| `filter_roads` | `sql` | Shows only the roads of the query and zooms to them. | `rs.setFilter({ids})`, `rs.focus(ids)` |
| `move_map` | `sql` | Zooms to the roads of the query. | `rs.focus(ids)` |

Ask also has the read tool `describe_table(name)`: it gives the columns of one table with their types and meanings (the host's
`describe(name)`), so the prompt needs to list only the map's own table in full.

- **Limit.** A map tool needs every id, not 1000. Its SQL has the row limit `mapLimit` (default 100 000). Over the limit, the tool does
  nothing and tells the model to make the query narrower.
- **What goes back to the model:** a short text, for example "Coloured 1151 roads (One-way) and 1614 roads (Two-way)." No ids go to
  the provider.
- **No id column:** the tool gives the error "The query must select the column edge_id." back to the model, which fixes the SQL.
- **The dock follows the map.** Each map tool also puts its roads into the data dock: `idColumn`, the name, the class and the length of
  each road (the host's main table gives these columns), and for `color_roads` a first column `colour` with the label of the group. The
  dock opens on a desktop. So the table is what the map shows, **Show on map** is there, and a click on a row selects that road and opens
  its card. (Before, the dock kept the person's older table, with no `edge_id`, and Kaveh saw "no Show on map", 2026-11-05.) The SQL in the
  dock's line is the tool's SQL inside `WHERE edge_id IN (...)`, so the person can change it and run it again. A `;` at the end of the
  model's SQL is removed first.
- **The card.** Each change of the map is one line in the answer's card: a small "MAP" label, the text ("Shows only 625 roads"), and
  **Undo** for a colour or a filter. A move has no Undo. The footer is the same as for a query: "▸ 2 map queries" (the SQL) at the left and
  **Table** at the right.
- **Undo.** The page keeps the map changes of each card. Undo takes away the changes of that card. The ✕ of a card also takes away its
  changes, and "New" takes away all of them. The page then paints the map again from the changes of the cards that stay, so two cards
  can colour different roads at the same time.
- **Only Ask's own changes.** Undo and ✕ remove only the colours, the legend rows and the filter that Ask made. The page's own colours
  (`colorBy`, live data) and the person's own filter in the roads box stay.
- **Kept out:** a tool that changes the data (OSM tags, levels, the network). It needs a confirm step before each change. The base map,
  the theme and the 3D view are also kept out for now: the person changes them with one click in the toolbox.

### The prompt

The system prompt is short, and it is one file (`ask/prompt.txt`), so a change of it is a change of data and not of code:

```text
You answer questions about the data of a map page. The data is in a {dialect} database.
{about}

You have four tools. Each one takes read-only SQL (one SELECT or WITH statement).
- run_query(sql): gives the first rows of the result. The page shows the result of your last
  query as a table and lights the roads of the rows on the map.
- color_roads(groups): colours roads on the map. Each group has a label, a colour (#rrggbb) and
  SQL that selects {idColumn}. The legend shows the labels.
- filter_roads(sql): shows only the roads that the SQL selects ({idColumn}).
- move_map(sql): zooms the map to the roads that the SQL selects ({idColumn}).
Use a map tool only when the person asks to see, show, colour, filter or zoom.
You cannot change the data.

Rules:
- Use only the tables and columns of the schema below. Do not guess a name.
- When the answer is about roads, select the column {idColumn}, so that the page can light them.
- Use readable column names (AS) and round numbers.
- Answer in 1 to 3 short sentences: the count and the one or two most important facts, by street name
  (for example the longest). Never write edge_id values or a list of the rows: the page shows the table.
- Only one statement. No INSERT, UPDATE, DELETE, CREATE, DROP, COPY, ATTACH, SET or PRAGMA.
- When a query fails, read the error, fix the SQL and run it again.
- Answer in the language of the question, in one to three short sentences, with the numbers.
  Do not repeat the table: the page shows it.
- If the data cannot answer the question, say so.

Schema:
{schema}
```

### The schema

The agent sees **all the host's data** (Kaveh, 2026-11-05: "just need to access more"). The duckOSM database of Monaco has 46 tables in 9
schemas (`driving`, `walking`, `cycling`, `bus`, `features`, `raw`, `mm`, `main`, `visualization`) and about 400 columns. A prompt with every
column is too large for a free tier: a free tier allows some thousand tokens a minute, and each model call sends the prompt again. So the
prompt has two levels:

1. **Every table, one line each:** its name, its number of rows and one sentence about it.
2. **The columns of the map's own table only** (the table of `idColumn`), each with its type and its meaning.

The agent asks for the meaning of a table and for the columns of any other table with a fifth tool, `describe_table(name)`, when it
needs them.

### The token budget

A free tier has a limit of tokens for each minute, and each step of the agent sends the whole prompt again. On 2026-11-05 Kaveh's
question "name them" on Groq's free tier stopped with HTTP 429: "Limit 8000, Used 6717, Requested 3402" tokens per minute. The prompt
with one line of description for each of the 46 tables was about 2 800 tokens. So:

| Rule | Value | Monaco, measured |
|---|---|---|
| The tables in the prompt | one line for each schema: the table names with their rows, no description (`driving: edges 2765, nodes 1719, ...`) | 46 tables in 9 lines |
| The columns in the prompt | only the main table's; a meaning is cut at a word, at most 60 characters, with "…" | 30 columns |
| The prompt in all | at most 4 000 characters | 3 918 characters, about 1 340 tokens with the tools (before: about 2 800) |
| One tool result | at most 2 500 characters: the rows are halved until it fits (`rows_sent` tells the model) | 30 rows of 7 columns became 15 rows |
| A question of 3 steps | under 5 000 tokens | about 4 700 |

**HTTP 429.** The page reads the wait time (the header `Retry-After`, or "try again in 15.9s" in the message), shows "Groq's free limit:
waiting 16 s" on the card's step line with a count down, and sends the request again: at most 2 times, and only for a wait of 60 s or
less. Stop ends the wait. A longer wait (a daily limit) is an error on the card with the provider's own text.

The host gives two functions:

```js
schema()            // -> {tables: [{name: "driving.edges", rows: 2765, about: "One row per direction of a road ...", main: true,
                    //      columns: [{name, type, about}]}, {name: "features.buildings", rows: 1262, about: "..."}, ...]}
describe(name)      // -> [{name, type, about}]: the columns of one table, for the tool describe_table
```

`columns` is necessary only on the main table (`main: true`). `about` is what a table or a column means: the unit, what one row is, what
`null` means. The host knows this, and roadstyle does not.

Ask writes it as compact text:

```text
TABLE driving.edges (2765 rows): One row per direction of a road: a two-way road has two edges.
  edge_id BIGINT: the edge's id. The same on every rebuild and in every mode.
  oneway BOOLEAN: TRUE when the edge has no reverse twin of the same way. Never NULL.
  ...
TABLE features.buildings (1262 rows): Base-map layer 'buildings' (Shortbread classes): osm_id, osm_type, kind, name, tags, geom.
TABLE raw.nodes (34326 rows): The OSM nodes of the area as read from the PBF: osm_id, lat, lon, tags (MAP of all OSM tags).
...
```

A line about a table is at most 140 characters, and a column's meaning at most 160. The host's `about` option (one paragraph for the
prompt) holds the facts of its database that the model must know, for example for duckOSM Studio: "The map shows the driving network: only
the `edge_id` of `driving.edges` lights roads", "Geometry is GEOMETRY in longitude / latitude; the spatial functions `ST_*` work" and "In
this DuckDB, `tags['k']` gives a list: use `tags['k'][1]`".

**For duckOSM Studio** the descriptions come from duckOSM's own reference, `docs/reference/database.md`: each `### table` section has a
table of `| column | type | description |`. The mock-up reads that file and writes the descriptions into DuckDB as comments
(`COMMENT ON TABLE`, `COMMENT ON COLUMN`: 206 column comments for Monaco). The host then reads them back with `duckdb_tables()` and
`duckdb_columns()`, so the descriptions travel with the database file. This is the host's work, not roadstyle's. (The mock-up, as a DuckDB
host, tells the model to read `duckdb_columns()` with `run_query` in place of the tool `describe_table`.)

Checked in the mock-up: with all 46 tables, the person's SQL and the agent can join any of them, the spatial functions work
(`ST_Area_Spheroid` found the largest building, Grimaldi Forum, 15 617 m²) and the raw OSM tags can be read.

### The providers

One provider code, in `ask/providers.js`: the OpenAI-compatible request. Google gives an OpenAI-compatible address for Gemini, so this
one code covers Gemini too, and a second code for Gemini's own API is not necessary (found with the mock-up, 2026-11-05).

```js
// a provider: one call of the model
{id, name, call({system, messages, tools, signal}) -> {text} | {toolCalls: [{id, name, args}]}}
```

| Request | The key goes in |
|---|---|
| `POST {address}/chat/completions`, with `messages` and `tools: [{type: "function", function}]` | the header `Authorization: Bearer <key>` |

Ask offers **only services with a free key** (Kaveh, 2026-11-05). A person can try Ask with no payment. The Settings box has them in a list,
with a link to the page that gives the key:

| Service | Address | Free key from | Note |
|---|---|---|---|
| Google Gemini (the default) | `https://generativelanguage.googleapis.com/v1beta/openai` | https://aistudio.google.com/apikey | free tier, no card |
| Groq | `https://api.groq.com/openai/v1` | https://console.groq.com/keys | free tier, no card |
| Cerebras | `https://api.cerebras.ai/v1` | https://cloud.cerebras.ai | free tier |
| Mistral | `https://api.mistral.ai/v1` | https://console.mistral.ai/api-keys | free "Experiment" plan (a phone number to sign up) |
| OpenRouter | `https://openrouter.ai/api/v1` | https://openrouter.ai/keys | only its free models (names that end in `:free`); the model list shows only these |

Services that need credits (xAI Grok, OpenAI) are not in the list. A free tier has a limit of requests for each minute and each day; one
question uses 2 to `maxSteps` requests.

Checked on 2026-11-05: each of the five addresses accepts a request from a browser page (CORS) from `http://localhost:8852`. The free
tiers are as the services said on that day; a service can change them, so the guide `ask.md` names the date.

The addresses are in a data file, `ask/providers.json`. **The model is not a fixed name.** The names of the models change often: on
2026-11-05 the mock-up's default for Groq, `llama-3.3-70b-versatile`, was refused with HTTP 404 ("does not exist or you do not have
access to it"). So the page takes the model from the provider's own list:

1. On **Save** of a key, the page asks for the list (`GET {address}/models`; Google names a model `models/<name>`, and the page removes
   that prefix). The Model field gets the list.
2. If the model that the person typed is in the list, the page uses it. Else it picks one: the first match of a preference list of
   models with tool support in `providers.json` (for example `gpt-oss-120b`, `kimi-k2`, `llama-4-maverick`, `qwen3`, `gemini-*-flash`),
   and never a model for speech, images, embeddings or safety (`whisper`, `guard`, `tts`, `embed`, `image`). The note says which model
   Ask uses, and why when it is not the typed one.
3. If the provider refuses the model during a question (HTTP 404, or HTTP 400 that names the model), the page picks another model from
   the list the same way, keeps it, and sends the request again, once.

Not checked yet: that each service gives tool calls in this form with a real key. The first step of the build checks each one.

### The keys

The key form is **in the Ask view**, not in roadstyle's Settings box: the person gets the key where the person needs it, and the
Settings box does not change. **Key** in the top row shows the form in place of the conversation. The form has a title row "Your key"
with **‹ Back to chat**. After a Save that works, the form says "The key works: 12 models. Ask uses …" and goes back to the chat by
itself after 1.6 s.

| Field | localStorage key | What it is |
|---|---|---|
| Provider | `rs-settings:ask` → `provider` | A list of the five free services of `providers.json` (Gemini first), with the link "Get a free key from ..." under it |
| Model | `rs-settings:ask` → `model.<provider>` | A text box with the models of the provider as its list ([The providers](#the-providers)) |
| Key | `rs-key:ask:<provider>` | One key for each provider, because a key works only with its own service: the person can keep keys of two services and switch. Save, Clear. Save asks the provider for its models (`GET {address}/models`) and says "The key works" or the provider's own error |

- A key stays only in this browser (localStorage). It is never in the page file, never in a URL and never in the conversation. It goes only
  in the header of a request to the provider's own address.
- An Ask key needs no reload: Ask reads it at each question. The Google key needs a reload because Street View reads it at the start.
- **Clear** removes the key from this browser.
- The key form says under the key: "The key stays in this browser. Other pages on the same address (for example the same
  github.io site) can read it. Use a key with a spending limit." This is true: localStorage belongs to the origin, and all GitHub Pages
  of one user share one origin.

### What goes to the provider

Kaveh removed the notice card (2026-11-05): no card stops the first question. The person adds the key, and that is the choice to use the
provider. The key form says under the key, in one muted line, what goes to the provider:

> Ask sends your question, the conversation, the names and descriptions of the tables and columns, and the query results (up to 30 rows
> each) to the provider's address. The key goes only there.

The guide `docs/guides/ask.md` says the same.

### The read-only guard

The guard is a function of roadstyle (`data/guard.js`), with no DuckDB: `guard(sql)` gives `{ok: true, sql}` or
`{ok: false, reason}`. It always checks the agent's SQL. It checks the person's SQL when the data dock has `guard: true` (the default).

1. It reads the SQL without its comments (`--`, `/* */`), its string literals and its quoted names, and checks only what is left. The SQL
   that runs is the person's or the agent's text without change.
2. It removes one `;` at the end. Another `;` is refused: "Only one statement is allowed."
3. The first word must be `SELECT` or `WITH`.
4. These words are refused anywhere: `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `CREATE`, `DROP`, `ALTER`, `TRUNCATE`, `ATTACH`, `DETACH`,
   `COPY`, `EXPORT`, `IMPORT`, `INSTALL`, `LOAD`, `PRAGMA`, `SET`, `RESET`, `CALL`, `CHECKPOINT`, `VACUUM`, `USE`, `BEGIN`, `COMMIT`,
   `ROLLBACK`.
5. Functions that read files or the network, or that run SQL from a text, are refused: `read_*`, `*_scan`, `glob`, `sniff_csv`,
   `query`, `query_table`, `getenv`. A string literal directly after `FROM` or `JOIN` (DuckDB reads a file name there) is refused, and so
   is a string literal that has `://`.
6. The data dock adds the row limit ([The row limit](#the-row-limit)).

The guard is a list of refused words, so it is the first line only. The host is the second line. For duckOSM Studio this design
recommends: the host runs the agent's SQL (`source: "ask"`) between `BEGIN TRANSACTION` and `ROLLBACK`, so a change that the guard did
not see is undone. This is the host's work and is not in roadstyle.

Why it matters: the data of a page comes from OSM, and a street name can hold words to the model ("prompt injection"). With this
design the worst result is a wrong answer or a wrong colour on the map (Undo takes it away): no tool changes the data, a query cannot read a file or an address, and the answer is plain text
with no links and no images.

## One hover for the whole dashboard

Kaveh (2026-11-05): "some of the buttons on the dashboard don't have hover! is not it as default every activation part of dashboard has
hover?" and then "use a consistent hover for every part. check all part of the roadstyle dashboard for that".

**The audit.** A browser test opens every state of the dashboard (the toolbox and each of its boxes, the panel's title row, cards that fold
or open, tabs, a two-way switch, chips, a link, a plain and a primary button, a list, the day picker and its calendar, the help window, the
road card, the dock, Ask and its key form, and the hidden panel), puts the pointer on every clickable control (at most two of each kind in
each place), and reads what changes: the control, its parent row and its children. Before the change, in the light theme: **61 kinds of
control, 13 different hover looks** (a grey background, an accent border and text, brighter, a shadow, an underline, and mixes), and **15
with no hover at all**: among them the help window's close, the roads box's "All" and its rows, the month arrow of the day picker, a
`<details>` summary, the provider list, the dock's buttons and Ask's send button. Two faults of roadstyle came out too: the panel's hide and
show buttons have no hover, and the template's `#sb button:hover` also colours a **disabled** button ("Latest" of the day picker).

**The rule: every control reacts, in one of three looks, by its kind.**

| Kind | Hover (and keyboard focus) | Examples |
|---|---|---|
| Not filled | the background is the new token `--rs-hover-bg` (`--accent` at 12 %, so it follows the theme), and the text or the icon is `--accent`; a border, if the control has one, is `--accent` | the toolbox's buttons, ✕, "?", fold, hide and show panel, plain buttons, chips, tabs and a switch that are not filled, the rows of the boxes, table rows and headers, the day picker, a list, a summary |
| Filled | brighter: `filter: brightness(1.1)` | a primary button, the open tab, Run, Ask's send button, Key while its form is open, "Shown on map" |
| A link | underlined (a link has no underline until then) | "Get a free key …", links in the help window |

A disabled control has no hover. Keyboard focus (`:focus-visible`) has the same look and a 2 px `--accent` ring. **A card's title row is not a
control of its own:** the general rule leaves it to the card rules of the standard (a card that folds: an accent title under the pointer,
and an accent ring and title while it is open; a card that opens something: a tint of the whole card, stronger under the pointer). The
first try of the rule tinted the title button and the title row each on its own, and they did not line up (Kaveh: "wrong style for
opened card"). The dock's top edge keeps
its own drag look (the accent edge). **After the change, in both themes:** 50 controls have the tint, 6 the brighter look, 2 the underline;
the 2 disabled ones have none.

## Where the code goes

| File | What it holds | In every page (`files.txt`) |
|---|---|---|
| `dashboard/dock.js` | The bottom dock, `rs.dock`, `rs.dock.table` | Yes (about 4 KB) |
| `dashboard/dashboard.css` | The CSS of the three parts, with the theme tokens; `--rs-dock-h` for the parts that end above the dock; the new token `--rs-err`; the panel's control rules also for `#rs-dock` | Yes |
| `dashboard/data/data_dock.js` | The data dock | No: a module that a page imports, as the design panel is |
| `dashboard/data/guard.js` | The read-only guard and the row limit | No |
| `dashboard/ask/ask_panel.js` | The view and the agent loop | No |
| `dashboard/ask/providers.js`, `ask/providers.json` | The two providers, the addresses and the default models | No |
| `dashboard/ask/prompt.txt` | The system prompt | No |
| `docs/guides/dashboard-layout.md` | The bottom dock: desktop and phone | |
| `docs/guides/data-dock.md`, `docs/guides/ask.md` | The two guides, as `design-panel.md` | |
| `docs/guides/dashboard-parts.md`, `docs/reference/javascript.md`, `index.d.ts` | The rows of `rs.dock` and of the two modules | |

Changes in existing parts, all small and with no change of look on a page without a dock:

| File | Change |
|---|---|
| `dashboard.css`, the page template | **One hover** (see [One hover for the whole dashboard](#one-hover-for-the-whole-dashboard)): the token `--rs-hover-bg`; the three looks in place of the 13 of now; the panel's hide and show buttons; `#sb button:hover:not(:disabled)`; links underlined on hover only. A change of the look of every page, so it is a separate PR, before the dock |
| `toolbar.js` | `keepInside` keeps a box's scroll across its fit and does not fit again for the class `rs-scrolling` (a fault now: a box that it makes shorter cannot scroll). The low edge of a box is the dock's top, not `innerHeight` (`keepInside`). A bar at a side has the free height above the dock as its largest height, and is centred there; a bar along the bottom ends above the dock |
| `overlay.js` | `followPanels`: the place of a bar along the top or the bottom, `left`, `middle` or `right` (`toolbar.align`) |
| `settings.js`, `placement.js` | The row "Toolbar place" (only for a bar at the top or the bottom); the choice is kept as the other layout choices |
| `docs/reference/parameters.md`, `dashboard-layout.md` | `toolbar.align` |
| `windows.js` | One sheet at a time also for the dock (a listener of `rs:dockchange`) |
| `panelscroll.js`, `dashboard.css` | The dock's table in `_PS_AREAS` (the Ask conversation is in the panel's own scroll) |
| `api.js` | `rs.dock` |

## The tests

No test needs a key or the network. CI runs them all.

| Test | What it checks |
|---|---|
| `tests/data_units.js` in `tests/test_data_dock_browser.py` | The guard: a list of SQL that it accepts (with comments, strings that hold `DROP`, `WITH`, a `;` at the end) and a list that it refuses (two statements, each refused word, `read_csv`, `FROM 'x.parquet'`, `'https://...'`, `query('...')`). The row limit wrap. The CSV text (a comma, a quote, a new line, a `BigInt`, `null`). An id as exact text. |
| `tests/test_data_dock_browser.py` | A dashboard page with a fake host `query` in JavaScript (no DuckDB): the line folds and opens, Run and Ctrl+Enter, the error line, "Show on map" lights the right roads (`rs.getState().highlight`), a click on a row selects and zooms, the CSV download, Stop. With 2 765 rows: the note says "1 000 of 2 765 rows", Show on map lights 2 765, the CSV has 2 765 rows; a click on a header sorts rising, falling and back, over all the rows (the first value is the true minimum), also for `BigInt` ids and text with `null`. |
| `tests/test_dock_browser.py` | The bottom dock: the map ends at the dock, the panel and the toolbox and the corner box end above it, the grip drags the height between 120 px and 70 %, the height and the state stay after a reload, `rs:dockchange`. In `layout="dock"` and with `street_view="dock"` the dock is as wide as the map. At 390 × 844: the dock is a sheet, one sheet at a time (dock, panel, Street View), a wide table scrolls inside the dock and the page does not scroll sideways. |
| `tests/test_ask_browser.py` | Ask with a **fake provider** (an object with `call()` that gives scripted answers). The script: a tool call with wrong SQL, then a tool call with right SQL, then text. The test checks: 3 model calls, the error text of the database goes to the model, the dock shows the last SQL and its table, the roads are lit, the answer is plain text, the footer says "1 query" and the failed query is only in the details. A ✕ removes a card, and the next model call has no turn of it. After three answers (a query, a filter, a zoom): the first card's Table shows its own 5 rows in the dock; Undo of the filter card and then its Map apply the filter again; the first card's Map lights its 5 roads; `**x**` in an answer is a `<b>`; an answer that lists 5 rows with their ids shows 3 items with no ids and "… 2 more in the table". Also: a question asked while `ready` waits shows "Loading the data…" and then its answer; an error thrown by `schema()` ends the question with a red line, and the box works again; the stop after 3 failed queries and after `maxSteps`, Stop, a model text with `<img>` shows as text. |
| `tests/test_ask_tools_browser.py` | The map tools with the fake provider: `color_roads` with 2 groups colours the right roads and adds 2 legend rows; `filter_roads` sets the id filter; `move_map` moves the camera; Undo and ✕ take away only that card's changes and keep the page's own colours and filter; "New" takes away all; after each map tool the dock has the tool's roads with `edge_id` and Show on map, and a click on a row opens the road card; a query without `edge_id` and a query over `mapLimit` give an error to the model; no id goes into a request to the provider. |
| `tests/test_dock_toolbar_browser.py` | With the dock open, at 1366 × 900, 768, 650 and 560 px and the bar at each of the four edges: the bar and each open box of the toolbox end above the dock, and a box taller than its room scrolls to its end with the wheel and stays there. A bar along the top or the bottom with `align` left, middle and right: 8 px after the panel's card, in the middle of the free part, 8 px from the other edge; the choice in Settings stays after a reload. |
| `tests/test_ask_align_browser.py` | At 1440 and 1920 px, with the card look and the frame look: the dock touches the left, right and bottom edges of the window; its top corners are round with the card look; the gap between the panel's card and the dock is 16 px; the cards of the conversation, Back and the question box have the same left and right x. |
| `tests/test_ask_budget_browser.py` | The prompt of the Monaco test data is at most 4 000 characters; a tool result is at most 2 500; a fake provider answers 429 with "try again in 2.5s" once: the card shows the count down, and the request goes again after the wait; a 429 with a wait over 60 s is an error on the card. |
| `tests/test_ask_providers_browser.py` | The two providers' requests and answers, with `page.route` on their addresses (no network): the body has the tool, the key is in the header and not in the URL, a tool call and a text are read right, an HTTP 400, 401 and 429 give a clear error in the view. |
| `tests/test_dashboard_hover_browser.py` | The hover audit above, in both themes: every enabled clickable control changes under the pointer, with one of the three looks for its kind; a disabled control does not change. |
| `tests/test_dashboard_themes_browser.py` | The dock (with the card look at the slider values 1, 0.7 and 0.4, and with the frame look), the data dock (with a table, an error line and the open line), the Ask view (empty, and with answers) and the Ask rows of Settings, in the light and the dark theme: contrast 4.5 or more, no light surface in the dark theme. |
| `tests/test_dashboard_scroll_browser.py` | The dock's table. The Ask view: the panel's body is its only scroll, and the question box is in view at each scroll position. |

Before the merge, Kaveh looks at the page on a phone and on a desktop, in both themes.

## The order of the work

Each step is one PR, with its tests and its guide.

0. **One hover for the dashboard**: the rule and its audit test. It changes every page a little, so it goes first and alone.
1. **The bottom dock** and `rs.dock.table`. A page can then show a table under the map.
2. **The data dock** with the guard and the row limit.
3. **duckOSM Studio** uses the data dock (in its own repository): `query` and `schema` from its DuckDB, and the `about` texts of its
   columns. This is the first real user, and it shows if the API is right before Ask is built on it.
4. **Ask** with the two providers, after a check of each service from a browser page with a real key.
5. **duckOSM Studio** adds Ask.

## Decisions for Kaveh

1. **The width of the dock in `layout="overlay"`.** This design: as wide as the map, so as wide as the window, and the floating panel
   ends above the dock. The other choice: the dock starts at the edge of the panel, and the panel keeps its full height. The first gives
   the widest table, which was the problem of the old box.
2. **The person's own SQL.** This design: the guard checks it too (`guard: true`), so the data dock never changes the data. A page that
   wants the person to write (for example `CREATE TABLE`) sets `guard: false`.
3. **The dock opens by itself on an answer** on a desktop, and not on a phone.
4. **The order of the work** above: the data dock in duckOSM Studio before Ask.

