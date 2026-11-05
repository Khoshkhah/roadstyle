# The bottom dock, the data dock and Ask

Status: **design, for Kaveh's review** (2026-11-05). No code yet. The code starts after Kaveh approves this design.

A mock-up on Monaco (outside the repository) found three points, which are in this text now: the dock must be opaque, the panel's
control rules must also apply in the dock, and the dashboard needs an error colour (`--rs-err`).

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
| [3. Ask](#3-ask) | An AI agent in the side panel. It uses the person's own key. Its only tool is a read-only query of the data dock. | A page with the data dock |

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
- **Height.** The grip is a strip of 8 px on the top edge of the dock, with the cursor `row-resize`. The person drags it. The height is
  at least 120 px and at most 70 % of the window. The page keeps the height and the open state in this browser
  (`rs-dock:<location.pathname>`), as the docked Street View keeps its share. A double click on the grip closes the dock or opens it again.
- **Closed.** A closed dock is its title row only (32 px): the tabs, the note, and a button with an up arrow. The map ends above this row.
  A click on a tab or on the arrow opens the dock.
- **Title row.** The tabs are `rs-tabs` and show only when the dock has two or more contents. With one content, the row shows its
  label as a title. At the right: "Collapse" (closes the dock) and, for a content that the person can remove, "x".
- **Look.** The dock has `--bg`, a `--line` border on its top edge, and `--ink` text. It is opaque: the dock is not over the map, so
  `--rs-tb-bg` (40 % opacity) shows the page's white background through it in the dark theme.
- **Controls.** `dashboard.css` gives buttons, text boxes and `sb-primary` their look only inside the panel (`#sb`). The same rules also
  apply in the dock (`#rs-dock`), else its buttons are white in the dark theme.

### The layout on a phone

At 700 px or less the dock is a bottom sheet, as the panel, Street View and Google 3D are (`windows.js`).

- The sheet has the same heights as the panel's sheet: closed, 40 % and full, and the same grip (44 px with an arrow).
- One sheet is open at a time. When the dock opens, the panel's sheet goes to 0 and Street View and Google 3D close. When one of them
  opens, the dock closes. `windows.js` gets one more listener of `rs:dockchange` for this, next to its listeners of
  `rs:streetviewchange` and `rs:google3dchange`.
- A closed dock is a small button "Data" (the label of its content) next to the grip of the panel's sheet, so that the person can find
  it again.
- A wide table scrolls sideways inside the dock. The first column stays in view. The page itself never scrolls sideways.

### The dock's table

Each content of the dock is the page's own element. For the common content, a table, the dock gives one part, so that every page has
the same table:

```js
const t = rs.dock.table({
  columns: [{name: "edge_id", type: "BIGINT"}, {name: "name", type: "VARCHAR"}, {name: "length_m", type: "DOUBLE"}],
  rows: [[8121729169906061189n, "Riia", 1240.5]],
  idColumn: "edge_id",       // optional: the column with the road ids
  more: true,                // optional: the rows are not all the rows ("1000 of more")
});
rs.dock.add({id: "roads", label: "Roads", el: t.el});
t.set({columns, rows});      // new rows in the same table
```

- It uses the existing classes `rs-scroll` and `rs-table` ([Dashboard parts](../guides/dashboard-parts.md#a-list-or-a-table-that-scrolls)):
  the header row stays in view, numbers are at the right, the row under the pointer has a tint. The table fills the height of the dock.
- The columns are side by side. A long text is cut at 40 characters with "...", and the full text is in its tooltip.
- A BIGINT (a JavaScript `BigInt`) shows exactly. An id is read as text (`String(value)`), never as a `Number`, because a 64-bit
  `edge_id` does not fit a `Number` ([JavaScript API](../reference/javascript.md)).
- `null` shows as a muted "null".
- With `idColumn`, a click on a row selects that road and zooms to it: `rs.select(id)` and `rs.focus(id)`.
- Over 1000 rows, the table draws only the rows in view (it keeps one height per row). This keeps a table of 50 000 rows fast.

The table does not sort when the person clicks a header. The SQL has `ORDER BY` for that. A sort can come later, if a page needs it.

## 2. The data dock

### What it does

The data dock is one content of the bottom dock. It has two rows:

1. **The query line.** It shows the SQL that made the table. It is one line by default (the SQL on one line, cut with "..."). A click
   opens it to a text box of up to 10 lines. Run or Ctrl+Enter (Cmd+Enter on a Mac) runs the SQL. Escape folds the line again.
2. **The table** (the dock's table above), with a bar: the number of rows and the time, **CSV**, and **Show on map**.

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
| `idColumn` | `"edge_id"` | The column with the road ids. A result without this column has no "Show on map", and a click on a row does nothing. |
| `sql` | `""` | The start text of the line. |
| `label` | `"Data"` | The tab of the dock. |
| `limit` | `1000` | The most rows in the table. The data dock asks for one more row, so it knows that there are more. |
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
  it runs, Run becomes Stop. The note of the tab is "12 rows" or "1000 of more".
- **An error.** The line stays open, and a red line under it shows the database's message. The old table stays. The colour is a new
  token, `--rs-err` (`#b91c1c` light, `#fca5a5` dark), with a contrast of 4.5 or more in both themes. Ask uses it for a failed query.
  The dashboard has no error colour now: `--rs-chart-miss` is a grey.
- **CSV.** Downloads the rows of the table as `<label>.csv`: a header row, comma separated, a text with a comma, a quote or a new line in
  quotes, a `BigInt` exactly, `null` as empty. The file has the rows of the table only (at most `limit`). The note in the bar says so when
  there are more.
- **Show on map.** When the result has `idColumn`, the button lights those roads with `rs.highlight(ids)` and zooms to them with
  `rs.focus(ids)`. A second click (or a new run) takes the light away (`rs.highlight([])`). An id that is not on the map is not lit, and
  the bar says "40 of 42 roads are on the map".
- **A click on a row** selects that road and zooms to it (`rs.select(id)`, `rs.focus(id)`). The row stays marked.
- **The list of tables.** A small button "Tables" in the line opens a list of the tables and their columns (from `schema()`), with the
  description of each column in its tooltip. A click on a name puts it in the line at the cursor.

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

Ask is a card in the side panel. The person types a question in words, for example "Which primary roads are longer than 1 km?". An
agent writes SQL, runs it with the data dock, reads the result, and writes a short answer. Each answer puts its SQL and its table into the
data dock and lights the roads.

The agent uses the person's own key. The browser sends the requests directly to the provider. There is no model in the browser and no
server of roadstyle or of the page.

### The API

```js
import {askPanel} from "./dashboard/ask/ask_panel.js";

const ask = askPanel({
  dashboard: rs,
  data,                                         // the data dock: the agent's only tool runs through it
  about: "A road network of Tartu, built by duckOSM in this browser. One row of edges is one direction of a road.",
  dialect: "DuckDB",
  examples: ["Which streets are longer than 1 km?", "How many one-way roads are there?"],
});
ask.addEventListener("answer", e => console.log(e.detail));   // {question, text, sql, rows}
```

| Option | Default | What it is |
|---|---|---|
| `dashboard` | `window.rs` | The page's dashboard. |
| `data` | (necessary) | The data dock. Ask uses its `schema()`, its guard, its row limit and its table. |
| `about` | `""` | One or two sentences about the data. They go into the prompt. |
| `dialect` | `"SQL"` | The name of the database's SQL, for the prompt (`"DuckDB"`). |
| `examples` | `[]` | Questions that the empty card shows as chips. A click on a chip asks it. |
| `section` | `{id: "ask", label: "Ask"}` | The card in the panel: the options of `rs.sections.add` (`after`, `before`, `fold`). The card does not fold by itself. |
| `maxSteps` | `6` | The most model calls for one question. |
| `sendRows` | `30` | The most rows of one result that go to the model. |
| `providers` | the two built-in providers | For the tests: a fake provider (see [The tests](#the-tests)). |

| Method | What it does |
|---|---|
| `ask(question)` | Asks a question, as the person does. It gives a promise of the answer. |
| `stop()` | Aborts the question now. |
| `clear()` | Starts a new conversation (the model forgets the earlier questions). |
| `history()` | The questions and answers of this conversation. |

| Event | `detail` | When |
|---|---|---|
| `answer` | `{question, text, sql, rows}` | The agent gave an answer |
| `error` | `{question, message}` | The question stopped with an error (no key, a refused key, too many failed queries) |

### The card

```
+----------------------------------+
| Ask                          (?) |
| Gemini · gemini-flash   Settings |
| +------------------------------+ |
| | Which primary roads are lo.. | |
| +------------------------------+ |
|                  [New] [ Ask ]   |
| -------------------------------- |
| You: Which primary roads are ... |
| 14 primary roads are longer      |
| than 1 km. The longest is Riia   |
| (2.3 km).                        |
| > 2 queries · 14 rows  [Table]   |
+----------------------------------+
```

- The first row shows the provider and the model, and a link "Settings" that opens the Settings box of the toolbox
  (`window.rsOpenSettings`, which exists for the Google key).
- With no key, the card shows "Ask needs your own key of Gemini or of an OpenAI-compatible service." and a button "Add a key" that opens
  the Settings box.
- The question box is a `<textarea>` of 2 lines. Enter asks, Shift+Enter is a new line. While the agent works, Ask becomes Stop and the
  card shows each step on one muted line: "Writing SQL", "Running query 1", "Query 1 failed: Referenced column "lenght" not found. Trying
  again", "Writing the answer".
- The conversation is a scroll area (`rs-scroll`, in `_PS_AREAS`). The answer is plain text (`textContent`). The card shows no HTML, no
  images and no links from the model.
- "> 2 queries" opens the SQL of each step. "Table" opens the data dock on the answer's table.
- "New" starts a new conversation.

### The agent loop

```
question
  -> model(system prompt + schema + conversation + question, tools: [run_query])
       - gives a tool call run_query(sql):
           guard(sql) -> data.run(sql, {source: "ask"}) -> the result (or the error)
           -> to the model, and loop again
       - gives text: this is the answer -> stop
  stops also after maxSteps model calls, after 3 failed queries one after the other, or on Stop
```

1. Ask reads `data.schema()` once for each conversation and writes the schema text (see [The schema](#the-schema)).
2. Ask sends the system prompt, the schema text, the earlier turns of this conversation and the question to the model, with one tool:
   `run_query`.
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
6. On a desktop, the data dock opens by itself on an answer with a table. On a phone it does not, because one sheet is open at a time and
   the person is in the panel's sheet. The card shows "Table" and the roads are lit on the map.

A question costs 2 to `maxSteps` model calls. Most questions take 2 or 3.

### The prompt

The system prompt is short, and it is one file (`ask/prompt.txt`), so a change of it is a change of data and not of code:

```text
You answer questions about the data of a map page. The data is in a {dialect} database.
{about}

You have one tool: run_query. It runs one read-only SQL statement (SELECT or WITH) and gives
the first rows of the result. The page shows the result of your last query as a table and
lights the roads of the rows on the map.

Rules:
- Use only the tables and columns of the schema below. Do not guess a name.
- When the answer is about roads, select the column {idColumn}, so that the page can light them.
- Use readable column names (AS) and round numbers.
- Only one statement. No INSERT, UPDATE, DELETE, CREATE, DROP, COPY, ATTACH, SET or PRAGMA.
- When a query fails, read the error, fix the SQL and run it again.
- Answer in the language of the question, in one to three short sentences, with the numbers.
  Do not repeat the table: the page shows it.
- If the data cannot answer the question, say so.

Schema:
{schema}
```

### The schema

The host's `schema()` gives the tables:

```js
{tables: [
  {name: "edges", about: "The directed road edges. A two-way road has two rows.", rows: 12345,
   columns: [
     {name: "edge_id", type: "BIGINT", about: "The id of the edge. Select it to light the roads."},
     {name: "highway", type: "VARCHAR", about: "The OSM road class.", values: ["residential", "service", "primary", "secondary"]},
     {name: "length_m", type: "DOUBLE", about: "The length in metres."},
   ]},
]}
```

`about` is what the column means: the unit, what one row is, what `null` means. The host knows this, and roadstyle does not. `values`
(optional) is a few common values of a column of names or classes: the model then writes `highway = 'primary'` and not
`highway = 'Primary'`.

Ask writes it as compact text, one line for each column:

```text
TABLE edges (12345 rows): The directed road edges. A two-way road has two rows.
  edge_id BIGINT: The id of the edge. Select it to light the roads.
  highway VARCHAR: The OSM road class. Values: residential, service, primary, secondary.
  length_m DOUBLE: The length in metres.
```

The schema text is at most 12 000 characters. When it is longer, Ask first removes the `values`, then the `about` of the columns, and
last the tables that come after the limit (the host gives the important tables first). A test checks the cut.

For duckOSM Studio, the host reads the tables and the types from `information_schema.columns` and adds the `about` texts from a file of
its own (the meaning of each duckOSM column). This is the host's work, not roadstyle's.

### The providers

Two providers, with one interface in `ask/providers.js`:

```js
// a provider: one call of the model
{id, name, call({system, messages, tools, signal}) -> {text} | {toolCalls: [{id, name, args}]}}
```

| Provider | Request | The key goes in |
|---|---|---|
| Gemini | `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, with `systemInstruction`, `contents` and `tools: [{functionDeclarations}]` | the header `x-goog-api-key` |
| OpenAI-compatible | `POST {address}/chat/completions`, with `messages` and `tools: [{type: "function", function}]` | the header `Authorization: Bearer <key>` |

The OpenAI-compatible address covers these services. The Settings box has them in a list, and the person can also type an address:

| Service | Address |
|---|---|
| Groq | `https://api.groq.com/openai/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| OpenAI | `https://api.openai.com/v1` |

The default model of each provider and the addresses are in a data file, `ask/providers.json`, so a new model name is a change of data.
The person can type another model in the Settings box.

Not checked yet: that each of the four services accepts a request from a browser page (CORS) and gives tool calls in this form. The
first step of the build checks each one from a page on `localhost` with a real key, and this design is changed if one does not.

### The keys and the settings

The keys go in the **Keys** part of roadstyle's Settings box, the same as the Google key (`settings.js`, `_stKeys`). The Ask rows show
only on a page that has Ask.

| Setting | localStorage key | What it is |
|---|---|---|
| Gemini key | `rs-key:gemini` | A key row as the Google key has: Save, Clear, Show |
| OpenAI-compatible key | `rs-key:openai` | The same |
| Ask with | `rs-settings:ask` → `provider` | A two-way switch (`rs-seg`): Gemini or OpenAI-compatible. Only when both keys are saved |
| Address | `rs-settings:ask` → `address` | The OpenAI-compatible address: a list of the three services and a text box |
| Model | `rs-settings:ask` → `model.<provider>` | A text box, with the default of `providers.json` as its placeholder |

- A key stays only in this browser (localStorage). It is never in the page file, never in a URL and never in the conversation. It goes only
  in the header of a request to the provider's own address.
- An Ask key needs no reload: Ask reads it at each question. The Google key needs a reload because Street View reads it at the start.
- **Clear** removes the key from this browser.
- The Settings box says under the Ask keys: "The key stays in this browser. Other pages on the same address (for example the same
  github.io site) can read it. Use a key with a spending limit." This is true: localStorage belongs to the origin, and all GitHub Pages
  of one user share one origin.

### The privacy notice

On the first question to a provider, the card shows this notice in place of the answer, and the question waits:

> **Before Ask sends your question**
>
> Ask sends these to **generativelanguage.googleapis.com** (Google Gemini):
>
> - your question and the earlier questions and answers of this conversation;
> - the names of the tables and the columns, and their descriptions;
> - the results of the queries that the agent runs (up to 30 rows each).
>
> Your key goes to the same address, and only there. Nothing goes to roadstyle or to the author of this page. Google can keep and use
> what it gets, by its own terms.
>
> [Accept] [Cancel]

- The notice names the real address of the provider (for an OpenAI-compatible service, the host of the address in the settings).
- **Accept** keeps the consent in this browser (`rs-ask:consent` → `{<host>: <notice version>}`) and sends the question. **Cancel**
  sends nothing.
- A new address, or a new version of the notice (a change of what goes), shows the notice again.
- The fake provider of the tests has no host, and the test checks that no model call happens before Accept.

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
design the worst result is a wrong answer: the only tool reads, a query cannot read a file or an address, and the answer is plain text
with no links and no images.

## Where the code goes

| File | What it holds | In every page (`files.txt`) |
|---|---|---|
| `dashboard/dock.js` | The bottom dock, `rs.dock`, `rs.dock.table` | Yes (about 4 KB) |
| `dashboard/dashboard.css` | The CSS of the three parts, with the theme tokens; `--rs-dock-h` for the parts that end above the dock; the new token `--rs-err`; the panel's control rules also for `#rs-dock` | Yes |
| `dashboard/data/data_dock.js` | The data dock | No: a module that a page imports, as the design panel is |
| `dashboard/data/guard.js` | The read-only guard and the row limit | No |
| `dashboard/ask/ask_panel.js` | The card and the agent loop | No |
| `dashboard/ask/providers.js`, `ask/providers.json` | The two providers, the addresses and the default models | No |
| `dashboard/ask/prompt.txt` | The system prompt | No |
| `docs/guides/dashboard-layout.md` | The bottom dock: desktop and phone | |
| `docs/guides/data-dock.md`, `docs/guides/ask.md` | The two guides, as `design-panel.md` | |
| `docs/guides/dashboard-parts.md`, `docs/reference/javascript.md`, `index.d.ts` | The rows of `rs.dock` and of the two modules | |

Changes in existing parts, all small and with no change of look on a page without a dock:

| File | Change |
|---|---|
| `toolbar.js` | The low edge of a box is the top of the dock, not `innerHeight`. A bar at a side is centred in the part above the dock |
| `windows.js` | One sheet at a time also for the dock (a listener of `rs:dockchange`) |
| `settings.js` | The Ask rows in Keys (only on a page with Ask) |
| `panelscroll.js`, `dashboard.css` | The dock's table and the Ask conversation in `_PS_AREAS` |
| `api.js` | `rs.dock` |

## The tests

No test needs a key or the network. CI runs them all.

| Test | What it checks |
|---|---|
| `tests/data_units.js` in `tests/test_data_dock_browser.py` | The guard: a list of SQL that it accepts (with comments, strings that hold `DROP`, `WITH`, a `;` at the end) and a list that it refuses (two statements, each refused word, `read_csv`, `FROM 'x.parquet'`, `'https://...'`, `query('...')`). The row limit wrap. The CSV text (a comma, a quote, a new line, a `BigInt`, `null`). An id as exact text. |
| `tests/test_data_dock_browser.py` | A dashboard page with a fake host `query` in JavaScript (no DuckDB): the line folds and opens, Run and Ctrl+Enter, the error line, "Show on map" lights the right roads (`rs.getState().highlight`), a click on a row selects and zooms, the CSV download, Stop. |
| `tests/test_dock_browser.py` | The bottom dock: the map ends at the dock, the panel and the toolbox and the corner box end above it, the grip drags the height between 120 px and 70 %, the height and the state stay after a reload, `rs:dockchange`. In `layout="dock"` and with `street_view="dock"` the dock is as wide as the map. At 390 × 844: the dock is a sheet, one sheet at a time (dock, panel, Street View), a wide table scrolls inside the dock and the page does not scroll sideways. |
| `tests/test_ask_browser.py` | Ask with a **fake provider** (an object with `call()` that gives scripted answers). The script: a tool call with wrong SQL, then a tool call with right SQL, then text. The test checks: 3 model calls, the error text of the database goes to the model, the dock shows the last SQL and its table, the roads are lit, the answer is plain text. Also: the stop after 3 failed queries and after `maxSteps`, Stop, no model call before Accept, the notice again for a new address, a model text with `<img>` shows as text. |
| `tests/test_ask_providers_browser.py` | The two providers' requests and answers, with `page.route` on their addresses (no network): the body has the tool, the key is in the header and not in the URL, a tool call and a text are read right, an HTTP 400, 401 and 429 give a clear error in the card. |
| `tests/test_dashboard_themes_browser.py` | The dock, the data dock (with a table, an error line and the open line), the Ask card (with an answer and the notice) and the Ask rows of Settings, in the light and the dark theme: contrast 4.5 or more, no light surface in the dark theme. |
| `tests/test_dashboard_scroll_browser.py` | The dock's table and the Ask conversation. |

Before the merge, Kaveh looks at the page on a phone and on a desktop, in both themes.

## The order of the work

Each step is one PR, with its tests and its guide.

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

