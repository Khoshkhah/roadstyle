# Ask

Ask is an AI agent in the side panel. The person types a question in words, for example "Which primary roads are longer than 1 km?". The agent writes SQL, runs it through the [data dock](data-dock.md), reads the result and answers in one to three sentences. Each answer puts its SQL and its table into the data dock, so its roads light on the map. The agent can also colour roads, focus on roads and move the map.

The agent uses the person's own key of a free AI service. The browser sends each request directly to that service. There is no model in the browser and no server of roadstyle or of your page.

Ask is a module that a page imports, as the data dock is:

```javascript
import {dataDock} from "./dashboard/data/data_dock.js";
import {askPanel} from "./dashboard/ask/ask_panel.js";

const data = dataDock({query, schema, ready});            // your database: see "The data dock"
const ask = askPanel({
  data,
  about: "A road network of Tartu. One row of edges is one direction of a road.",
  dialect: "DuckDB",
  examples: ["Which streets are longer than 1 km?", "How many one-way roads are there?"],
});
ask.addEventListener("answer", (e) => console.log(e.detail));   // {question, text, sql, rows}
rs.sections.add({id: "ask", label: "Ask", note: "Ask a question about the data", open: () => ask.open()});
```

## The options

| Option | Default | What it is |
|---|---|---|
| `data` | (necessary) | The data dock. Ask runs all its SQL through it: the guard, the row limit and the table. |
| `dashboard` | `window.rs` | The page's dashboard. |
| `about` | `""` | One paragraph about your data. It goes into the prompt. Put here the facts that the model must know, for example which table the map draws. |
| `dialect` | `"SQL"` | The name of the database's SQL. With `"DuckDB"`, the prompt also tells the model how to read the comments of the tables and columns. |
| `examples` | `[]` | Questions that the empty start shows as chips. A click on a chip asks it. |
| `panel` | `#sb` | The host's dashboard panel. Ask uses roadstyle's [editor frame](dashboard-parts.md#an-editor-in-the-panel) in it. |
| `backLabel` | `"Back"` | The text of the back button. |
| `maxSteps` | `6` | The most model calls for one question. |
| `sendRows` | `30` | The most rows of one result that go to the model. |
| `providers` | the five free services | The list of services. A test gives a fake provider here (see [Tests](#tests)). |

The schema of the data dock (`schema()`) gives the prompt its tables. Give `main: true` and `columns: [{name, type, about}]` on the table that the map draws. The prompt has one line for each schema with the table names and their rows, the columns of the main table, and each table of the schema `extra` with its `about`. A prompt of this form stays small (about 4 000 characters), because a free service allows only some thousand tokens a minute.

## The methods and the events

| Method | What it does |
|---|---|
| `open()`, `close()`, `isOpen()` | Shows the Ask view in the panel, or shows the host's cards again. The conversation stays. |
| `ask(question)` | Asks a question. It gives a promise of `{question, text, sql, rows}`, or `null` when the question stops with an error. |
| `stop()` | Stops the question now. |
| `clear()` | Starts a new conversation, as **New** does. |
| `remove(i)` | Removes the question `i` and its answer, as the card's ✕ does. |
| `history()` | The questions and answers of this conversation. |

| Event | `detail` | When |
|---|---|---|
| `answer` | `{question, text, sql, rows}` | The agent gave an answer. |
| `error` | `{question, message}` | The question stopped: no key, a refused key, three failed queries, `maxSteps`, Stop. |
| `back` | none | The person clicked Back. Ask closes by itself. |

## What the person sees

- **The tool row** under the title does not scroll: the service and its model, "?", **Key** and **New**.
- **One card for each question.** The question is the bold title. The answer is plain text: bold and `code` show as bold and code, and a list shows at most 3 items with "… 2 more in the table". The view shows no HTML, no images and no links from the model, and it removes long ids from the text.
- **The footer** counts the query that made the table, "1 query · 625 rows", and opens to its SQL. The other queries of the agent and the failed queries that it fixed are inside it. **Show** puts the card's table back into the dock.
- **The answer's table** is the query with roads (the id column, or a key column of the data dock) that has the most rows, not the last query. When a map tool ran, its roads are the table.
- **A map change** is one line on the card, for example "MAP Focus on 625 roads (the others hidden)". A colour or a focus is a layer in **Colour ▾** or **Focus ▾** of the data dock. A new question, ✕ of a card and **New** do not remove a layer.
- **An error** ends the question with a red line on its card, and the question box works again.
- **The question box** is at the bottom. Enter asks, Shift+Enter is a new line. While the agent works, the send button is a stop square. After the first question, **Examples ▴** above the box shows the example chips.

## The agent

The agent has four tools. Each one takes one read-only `SELECT` or `WITH` statement, and the data dock's guard checks each one.

| Tool | What it does |
|---|---|
| `run_query(sql)` | Runs the SQL. The model gets the column names and types, the first `sendRows` rows, the number of rows and `more_rows`. |
| `color_roads(groups)` | 1 to 8 groups `{label, color, sql}`: a colour layer with a legend row for each group. |
| `focus_roads(sql, mode)` | A focus layer: the other roads fade (`"fade"`) or are hidden (`"hide"`). The camera moves to the roads. |
| `move_map(sql)` | The camera moves to the roads. |

A map tool needs SQL that selects the id column. It uses only the roads that the map draws, at most 100 000. It puts its roads into the dock, with the id, the name, the class and the length of each road (the columns that the main table has). No id goes back to the model: it gets a short text, for example "Focus on 625 roads (the others hidden).".

The loop:

1. Ask waits for the data ("Loading the data…"), then sends the prompt, the earlier questions and answers of the conversation, and the question.
2. A tool call runs. An error of the database goes back to the model as it is, and the model writes new SQL. After 3 failed tool calls one after the other, the question stops.
3. A text is the answer.
4. The call number `maxSteps` goes with `tool_choice: "none"` and the message "Answer now in 1 to 3 short sentences with the results that you have. Do not call more tools." When it gives no text either, the question stops, and its card keeps the queries that ran.

A tool result goes to the model with at most 2 500 characters: Ask halves the rows until it fits.

## The services and the keys

Ask offers only services with a free key. The table is as the services said on 2026-11-05. A service can change its free tier.

| Service | Address | Free key from |
|---|---|---|
| Google Gemini (the default) | `https://generativelanguage.googleapis.com/v1beta/openai` | <https://aistudio.google.com/apikey> |
| Groq | `https://api.groq.com/openai/v1` | <https://console.groq.com/keys> |
| Cerebras | `https://api.cerebras.ai/v1` | <https://cloud.cerebras.ai> |
| Mistral | `https://api.mistral.ai/v1` | <https://console.mistral.ai/api-keys> |
| OpenRouter (only its `:free` models) | `https://openrouter.ai/api/v1` | <https://openrouter.ai/keys> |

All five use one request: `POST {address}/chat/completions` with the key in the header `Authorization: Bearer <key>`. Each one accepts a request from a browser page.

**Key** opens the key form in place of the conversation: the service, the model and the key. **Save** asks the service for its models (`GET {address}/models`) and says "The key works" or the service's own error. When the typed model is not in the list, Ask picks a model with tool support from it. When the service refuses the model during a question (HTTP 404, or HTTP 400 that names the model), Ask picks another model once and sends the request again. On HTTP 429 (the free limit) Ask waits as long as the service says, at most 60 s and at most 2 times, with a count down on the card.

- The key stays only in this browser: `localStorage` `rs-key:ask:<service>`, one key for each service. The service and the model are in `rs-settings:ask`. The key is never in the page file, never in a URL and never in the conversation.
- Other pages on the same address (for example the same github.io site) can read the key. Use a key with a spending limit. **Clear** removes it.
- Ask sends your question, the conversation, the names and descriptions of the tables and columns, and the query results (up to 30 rows each) to the service's address. The key goes only there.

## Safety

The data of a page can come from OSM, and a street name can hold words to the model. With Ask, the worst result is a wrong answer or a wrong colour on the map: no tool changes the data, the guard refuses a statement that writes or reads a file or an address, and the answer is plain text with no links and no images. The guard is a list of refused words, so it is the first line only. A host can add a second line, for example run the SQL of Ask (`source: "ask"`) between `BEGIN TRANSACTION` and `ROLLBACK`.

## Tests

A test needs no key and no network. Give a fake provider with its own `chat`:

```javascript
const fake = {id: "fake", name: "Fake AI", model: "fake-1",
  chat: async ({messages, tools, toolChoice, signal}) => ({content: "Six roads."})};   // an assistant message in the OpenAI form
const ask = askPanel({data, providers: [fake]});
localStorage.setItem("rs-key:ask:fake", "not-a-key");
```

`chat` gives an assistant message in the OpenAI form: `{content}` or `{content: "", tool_calls: [{id, type: "function", function: {name, arguments}}]}`. An error with `status` 429 and a "try again in 2.5s" message makes Ask wait. `tests/test_ask_browser.py` checks Ask with a fake host and a fake provider, the request of a built-in service with `page.route`, and the phone.

### Graph questions

With `dialect: "DuckDB"`, the prompt also has a pattern for graph work in SQL: the shortest distances from one node with `WITH RECURSIVE ... USING KEY (node)` on a table of directed edges (a start node, an end node, a length). For the diameter the model runs it twice, a "double sweep": from any node, then from the farthest node of the first run. On Monaco's driving network each run takes about one second. The prompt tells the model not to compute all the pairs at once, because that is too slow for a page.

### draw_chart

`draw_chart(sql, kind, x, y, title)` draws a chart of the result of its SQL in the data dock: `bar`, `line`, `histogram`, `scatter` or `pie` ([A chart](dashboard-parts.md#a-chart)). The dock switches to its **Chart** view, and the answer card shows a small copy of the chart. **Show** on the card puts its table and its chart in the dock again. The prompt tells the model to use it when the person asks for a chart, a graph, a plot or a diagram, and to aggregate in the SQL (`GROUP BY`). A column that is not in the result, or a kind that does not fit the columns, goes back to the model as an error, as a failed query does.
