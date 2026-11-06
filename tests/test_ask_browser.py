"""Ask (dashboard/ask/ask_panel.js, docs/guides/ask.md) with a fake host and a fake provider: the host's `query` answers a few canned results in JavaScript
(no database), and the provider is a script in the page (no key, no network). The agent's retry after a failed query, the answer's table in the data dock,
the card's details, Show, the clean answer text, ✕ of a card, a question during the load, the red line of an error, the stop after 3 failed queries and
after `maxSteps`, Stop, a map tool, the request of a real provider (page.route), and the phone. Skipped without playwright."""
import contextlib
import functools
import http.server
import json
import shutil
import threading
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _ARGS, _edges  # noqa: E402

import roadstyle as rs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "rust/roadstyle-assets/files/static/dashboard"

_HOST = """<script type="module">
import {dataDock} from "./dashboard/data/data_dock.js";
import {askPanel} from "./dashboard/ask/ask_panel.js";
const classes = ["primary", "secondary", "primary", "residential", "secondary", "primary"];
const EDGES = [1, 2, 3, 4, 5, 6].map(i => [BigInt(i), "Street " + (i - 1), classes[i - 1]]);
const CANNED = {
  "SELECT edge_id, name, highway FROM edges": [["edge_id", "BIGINT"], ["name", "VARCHAR"], ["highway", "VARCHAR"]],
  "SELECT edge_id, name FROM edges WHERE highway = 'primary'": [["edge_id", "BIGINT"], ["name", "VARCHAR"]],
  "SELECT edge_id, name FROM edges ORDER BY name LIMIT 2": [["edge_id", "BIGINT"], ["name", "VARCHAR"]],
  "SELECT count(*) AS n FROM edges": [["n", "BIGINT"]],
  "SELECT highway, count(*) AS roads FROM edges GROUP BY highway": [["highway", "VARCHAR"], ["roads", "BIGINT"]],
};
const ROWS = {
  "SELECT edge_id, name, highway FROM edges": EDGES,
  "SELECT edge_id, name FROM edges WHERE highway = 'primary'": EDGES.filter(r => r[2] === "primary").map(r => r.slice(0, 2)),
  "SELECT edge_id, name FROM edges ORDER BY name LIMIT 2": EDGES.slice(0, 2).map(r => r.slice(0, 2)),
  "SELECT count(*) AS n FROM edges": [[6n]],
  "SELECT highway, count(*) AS roads FROM edges GROUP BY highway": [["primary", 3n], ["secondary", 2n], ["residential", 1n]],
};
const strip = s => s.trim().replace(/;\\s*$/, "");
function answer(sql){
  let m;
  if((m = sql.match(/^SELECT \\* FROM \\(\\n?([\\s\\S]*?)\\n?\\) AS rs_q LIMIT (\\d+)$/))) { const r = answer(m[1]); return {columns: r.columns, rows: r.rows.slice(0, +m[2])}; }
  if((m = sql.match(/^SELECT edge_id, name, highway FROM main\\.edges WHERE edge_id IN \\(SELECT edge_id FROM \\(([\\s\\S]*)\\) AS rs_t\\) ORDER BY name$/))) {
    const ids = new Set(answer(m[1]).rows.map(r => r[0]));
    return {columns: CANNED["SELECT edge_id, name, highway FROM edges"].map(([name, type]) => ({name, type})), rows: EDGES.filter(r => ids.has(r[0]))}; }
  const c = CANNED[strip(sql)];
  if(!c) throw new Error("Binder Error: Referenced column \\"lenght\\" not found in FROM clause!");
  return {columns: c.map(([name, type]) => ({name, type})), rows: ROWS[strip(sql)]};
}
let release; window.loaded = new Promise(r => { release = r; }); window.releaseLoad = release;
window.data = dataDock({
  query: async (sql) => answer(sql), ready: window.loaded,
  schema: async () => { if(window.schemaFail) throw new Error("The catalog is not there"); return {tables: [
    {name: "main.edges", rows: 6, main: true, about: "The roads.", columns: [{name: "edge_id", type: "BIGINT", about: "The road's id."}, {name: "name", type: "VARCHAR"}, {name: "highway", type: "VARCHAR"}]},
    {name: "extra.sensors", rows: 3, about: "Traffic sensors: one point each."}]}; },
});
// the fake provider: each call takes the next step of window.script (a function of the request) and keeps the request
window.calls = []; window.script = [];
const fake = {id: "fake", name: "Fake AI", model: "fake-1", base: "https://fake.invalid/v1",
  chat: async (req) => { window.calls.push({messages: JSON.parse(JSON.stringify(req.messages)), toolChoice: req.toolChoice, tools: req.tools.map(t => t.function.name)});
    const next = window.script.shift(); if(!next) throw new Error("The script has no more steps"); return next(req); }};
window.tool = (name, args) => () => ({content: "", tool_calls: [{id: "c" + window.calls.length, type: "function", function: {name, arguments: JSON.stringify(args)}}]});
window.say = (text) => () => ({content: text});
localStorage.setItem("rs-key:ask:fake", "not-a-key");
const opts = {data, about: "Six test roads.", dialect: "DuckDB", examples: ["How many roads are there?"], providers: [fake]};
window.ask = askPanel(opts);
window.answers = []; window.errors = [];
ask.addEventListener("answer", e => answers.push(e.detail));
ask.addEventListener("error", e => errors.push(e.detail.message));
window.makeReal = () => { window.ask = askPanel({...opts, providers: undefined}); };    // the built-in providers (the test routes their address)
rs.sections.add({id: "ask", label: "Ask", note: "Ask a question about the data", open: () => window.ask.open()});
window.lights = [];
document.addEventListener("rs:highlightchange", e => { if(e.detail.set === "dock") window.lights.push(e.detail.ids.length); });
window.hostReady = true;
</script>"""


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextlib.contextmanager
def served(tmp_path):
    shutil.copytree(DASH, tmp_path / "dashboard")
    page = tmp_path / "page.html"
    rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}}, name="Ask").save(page)
    page.write_text(page.read_text().replace("</body>", _HOST + "</body>"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}/page.html"
    finally:
        srv.shutdown()


def _open(p, url, width=1280, height=800):
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_page(viewport={"width": width, "height": height})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.wait_for_function("window.map && map.loaded() && window.rsReady && window.hostReady", timeout=60_000)
    return browser, page, errors


def _ask(page, question, steps):
    """Give the fake provider its steps (JavaScript expressions), ask, and wait for the end of the question."""
    page.evaluate(f"window.script = [{', '.join(steps)}]")
    return page.evaluate("q => ask.ask(q)", question)


def _send_ready(page):
    return page.evaluate("!document.querySelector('.rs-ask-send').classList.contains('stop')")


def test_the_agent_fixes_its_sql_and_its_answer_goes_to_the_dock(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.click("#sb [data-rs-section=ask] .rs-sec-title")
            assert page.is_visible("#ask-head .rs-ask-top") and "Fake AI · fake-1" in page.inner_text("#ask-head")
            assert page.is_visible(".rs-ask-ex .rs-chip") and not page.is_visible(".rs-ask-exbar")
            # a question during the load: "Loading the data…", then the loop. Wrong SQL, right SQL, text: 3 model calls.
            page.evaluate("""window.script = [tool('run_query', {sql: 'SELECT edge_id, lenght FROM edges'}),
                                              tool('run_query', {sql: 'SELECT edge_id, name, highway FROM edges'}),
                                              say('**6** roads. <img src=x onerror="window.bad=1"> The longest is `Street 5`.')];
                             window.first = ask.ask('How many roads?'); 0""")
            page.wait_for_timeout(200)
            assert "Loading the data" in page.inner_text(".rs-ask-turn .step")
            page.evaluate("releaseLoad()")
            page.wait_for_function("window.answers.length === 1")
            calls = page.evaluate("window.calls")
            assert len(calls) == 3 and calls[0]["tools"] == ["run_query", "color_roads", "focus_roads", "move_map", "draw_chart"]
            system = calls[0]["messages"][0]["content"]
            assert "Columns of main.edges" in system and "extra.sensors: Traffic sensors" in system and "Six test roads." in system
            tool_msg = calls[1]["messages"][-1]
            assert tool_msg["role"] == "tool" and 'Referenced column \\"lenght\\" not found' in tool_msg["content"]     # the database's error goes to the model
            # the dock: the good SQL and its 6 rows, lit on the map
            assert page.evaluate("data.sql()") == "SELECT edge_id, name, highway FROM edges"
            assert page.evaluate("document.querySelectorAll('#rs-dock tbody tr').length") == 6 and page.evaluate("window.lights.at(-1)") == 6
            # the answer: bold and code from text nodes, no element of the model; the footer counts one query; the failed one only in the details
            turn = page.locator(".rs-ask-turn").nth(0)
            assert turn.locator(".a b").inner_text() == "6" and turn.locator(".a code").inner_text() == "Street 5"
            assert page.evaluate("document.querySelector('.rs-ask-log img')") is None and page.evaluate("window.bad") is None
            assert "<img" in turn.locator(".a").inner_text()
            assert turn.locator(".rs-ask-foot summary").first.inner_text() == "1 query · 6 rows"
            assert "lenght" not in turn.inner_text() and turn.locator(":scope > .rs-ask-err").count() == 0
            assert turn.locator(".rs-ask-failed summary").text_content() == "1 failed attempt, fixed by the agent"
            assert _send_ready(page) and page.evaluate("window.answers[0].sql") == "SELECT edge_id, name, highway FROM edges"
            assert page.is_visible(".rs-ask-exbar") and not page.is_visible(".rs-ask-ex")
            # the answer's table is the query with roads that has the most rows, not the last query; a list shows 3 items with no ids
            _ask(page, "Which roads are primary?", ["tool('run_query', {sql: \"SELECT edge_id, name FROM edges WHERE highway = 'primary'\"})",
                                                    "tool('run_query', {sql: 'SELECT count(*) AS n FROM edges'})",
                                                    "tool('run_query', {sql: 'SELECT edge_id, name FROM edges ORDER BY name LIMIT 2'})",
                                                    "say('Three are primary:\\n- Street 0 (edge 3363728794791538739)\\n- Street 2\\n- Street 5\\n- Street 7\\n- Street 9')"])
            assert page.evaluate("data.sql()") == "SELECT edge_id, name FROM edges WHERE highway = 'primary'" and page.evaluate("window.lights.at(-1)") == 3
            second = page.locator(".rs-ask-turn").nth(1)
            assert second.locator(".a li").count() == 3 and "3363728794791538739" not in second.inner_text()
            assert second.locator(".rs-ask-more").inner_text() == "… 2 more in the table"
            assert second.locator(".rs-ask-foot summary").first.inner_text() == "1 query · 3 rows"
            assert second.locator(".rs-ask-failed summary").text_content() == "2 more queries of the agent"
            history = page.evaluate("window.calls.at(-4).messages.map(m => m.content)")
            assert "How many roads?" in history                                                   # the earlier turn goes to the model
            # Show: the first card's table back into the dock, lit
            turn.locator(".rs-ask-show").click()
            page.wait_for_function("window.lights.at(-1) === 6")
            assert page.evaluate("data.sql()") == "SELECT edge_id, name, highway FROM edges"
            # ✕ removes the first card, and the next call has no turn of it
            turn.locator(".rs-ask-x").click()
            assert page.locator(".rs-ask-turn").count() == 1 and page.evaluate("ask.history().length") == 1
            _ask(page, "Thanks", ["say('You are welcome.')"])
            sent = page.evaluate("window.calls.at(-1).messages.map(m => m.content)")
            assert "How many roads?" not in sent and "Which roads are primary?" in sent
            # New: the empty start again
            page.click(".rs-ask-new")
            assert page.locator(".rs-ask-turn").count() == 0 and page.is_visible(".rs-ask-ex .rs-chip")
        finally:
            browser.close()
    assert errors == [], errors


def test_errors_end_with_a_red_line_and_the_box_works_again(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad(); ask.open()")
            bad = "tool('run_query', {sql: 'SELECT lenght FROM edges'})"
            # three failed queries one after the other: the stop, and the queries that ran stay in the details
            assert _ask(page, "Bad", [bad, bad, bad]) is None
            turn = page.locator(".rs-ask-turn").last
            assert turn.locator(":scope > .rs-ask-err").inner_text().startswith("Three queries failed one after the other")
            assert turn.locator(".rs-ask-sqls summary").inner_text() == "3 queries ran before the stop" and _send_ready(page)
            # maxSteps: the last call goes with tool_choice "none" and the message to answer now; its text is the answer
            good = "tool('run_query', {sql: 'SELECT edge_id, name, highway FROM edges'})"
            assert _ask(page, "Loop", [good] * 5 + ["say('Six roads.')"])["text"] == "Six roads."
            last = page.evaluate("window.calls.at(-1)")
            assert last["toolChoice"] == "none" and last["messages"][-1]["content"].startswith("Answer now in 1 to 3 short sentences")
            assert page.evaluate("window.calls.slice(-6, -1).every(c => c.toolChoice === 'auto')")
            # ... and when the last call has no text either: an error that keeps the 5 queries
            assert _ask(page, "Loop again", [good] * 6) is None
            turn = page.locator(".rs-ask-turn").last
            assert "The model gave no answer in 6 calls" in turn.locator(":scope > .rs-ask-err").inner_text()
            assert turn.locator(".rs-ask-sqls summary").inner_text() == "5 queries ran before the stop"
            # an error of the schema (outside the loop) ends with a red line too
            page.evaluate("window.schemaFail = true; ask.clear()")
            assert _ask(page, "Schema", ["say('never')"]) is None
            assert "The catalog is not there" in page.locator(".rs-ask-turn > .rs-ask-err").last.inner_text() and _send_ready(page)
            page.evaluate("window.schemaFail = false")
            # Stop: the send button is a stop square while the agent works
            page.evaluate("""window.script = [(req) => new Promise((ok, no) => req.signal.addEventListener('abort', () => no(new DOMException('Aborted', 'AbortError'))))];
                             window.pending = ask.ask('Slow'); 0""")
            page.wait_for_function("document.querySelector('.rs-ask-send').classList.contains('stop')")
            page.click(".rs-ask-send")
            page.wait_for_function("window.errors.at(-1) === 'Stopped.'")
            assert page.locator(".rs-ask-turn > .rs-ask-err").last.inner_text() == "Stopped." and _send_ready(page)
            # with no key: a red line, and the empty start has the note and "Add a key"
            page.evaluate("localStorage.removeItem('rs-key:ask:fake'); ask.clear(); ask.close(); ask.open()")
            assert page.is_visible(".rs-ask-need button:has-text('Add a key')")
            assert _ask(page, "No key", ["say('never')"]) is None
            assert "needs your own key" in page.locator(".rs-ask-turn > .rs-ask-err").inner_text()
            # the box asks with Enter
            page.evaluate("localStorage.setItem('rs-key:ask:fake', 'not-a-key'); window.script = [say('Hello.')]")
            page.fill(".rs-ask-comp textarea", "Hi")
            page.press(".rs-ask-comp textarea", "Enter")
            page.wait_for_function("window.answers.at(-1) && window.answers.at(-1).text === 'Hello.'")
        finally:
            browser.close()
    assert errors == [], errors


def test_a_map_tool_makes_a_layer_and_its_roads_go_to_the_dock(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad(); ask.open()")
            _ask(page, "Show only the primary roads", ["tool('focus_roads', {sql: \"SELECT edge_id, name FROM edges WHERE highway = 'primary'\", mode: 'hide'})",
                                                       "say('The map shows only the 3 primary roads.')"])
            assert page.evaluate("data.layers().map(l => [l.kind, l.mode, l.ids.length])") == [["focus", "hide", 3]]
            assert page.evaluate("rs.getState().filter.ids") == ["1", "3", "6"]
            assert json.loads(page.evaluate("window.calls[1].messages.at(-1).content")) == {"done": "Focus on 3 roads (the others hidden)."}
            assert "WHERE edge_id IN (SELECT edge_id FROM (" in page.evaluate("data.sql()")
            assert page.evaluate("document.querySelectorAll('#rs-dock tbody tr').length") == 3
            assert page.evaluate("window.lights.at(-1)") == 0                                   # the focus shows the roads: no light over them
            turn = page.locator(".rs-ask-turn").last
            assert "Focus on 3 roads" in turn.locator(".rs-ask-map").inner_text() and turn.locator(".rs-ask-show").count() == 1
            # a query with no id column: the error goes to the model; the card ✕ and New keep the layer
            _ask(page, "Zoom", ["tool('move_map', {sql: 'SELECT count(*) AS n FROM edges'})", "say('I cannot.')"])
            assert "must select the column edge_id" in page.evaluate("window.calls.at(-1).messages.at(-1).content")
            page.click(".rs-ask-new")
            assert len(page.evaluate("data.layers()")) == 1
        finally:
            browser.close()
    assert errors == [], errors


def test_a_real_provider_gets_the_key_only_in_its_header(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        seen = []

        def gemini(route):
            req = route.request
            seen.append({"url": req.url, "auth": req.headers.get("authorization"), "body": req.post_data_json})
            if len(seen) == 1:
                route.fulfill(status=401, content_type="application/json", body='{"error": {"message": "API key not valid."}}')
            else:
                route.fulfill(status=200, content_type="application/json", body='{"choices": [{"message": {"role": "assistant", "content": "Six roads."}}]}')
        try:
            page.route("https://generativelanguage.googleapis.com/**", gemini)
            page.evaluate("releaseLoad(); localStorage.setItem('rs-key:ask:gemini', 'test-key-123'); makeReal(); ask.open()")
            assert page.evaluate("ask.ask('How many?')") is None
            assert "Google Gemini refused the request (HTTP 401): API key not valid." in page.inner_text(".rs-ask-turn .rs-ask-err")
            assert page.evaluate("ask.ask('How many?')")["text"] == "Six roads."
            r = seen[-1]
            assert r["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions" and "test-key-123" not in r["url"]
            assert r["auth"] == "Bearer test-key-123" and r["body"]["model"] == "gemini-2.5-flash" and r["body"]["tool_choice"] == "auto"
            assert [t["function"]["name"] for t in r["body"]["tools"]] == ["run_query", "color_roads", "focus_roads", "move_map", "draw_chart"]
            assert "test-key-123" not in json.dumps(r["body"])
        finally:
            browser.close()
    assert errors == [], errors


def test_the_phone_keeps_the_tool_row_and_the_box_in_view(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url, 390, 844)
        try:
            page.evaluate("releaseLoad(); ask.open()")
            for i in range(4):
                _ask(page, f"Question {i}", ["tool('run_query', {sql: 'SELECT edge_id, name, highway FROM edges'})", "say('Six roads. ' + 'More words. '.repeat(20))"])
            page.wait_for_timeout(600)                                                          # the sheet goes to its full height
            moved = page.evaluate("""(() => { const b = document.getElementById('ask-body'), top = () => document.querySelector('.rs-ask-top').getBoundingClientRect().top;
                                              b.scrollTop = 0; const t0 = top(); b.scrollTop = 99999; return [b.scrollTop > 0, top() - t0]; })()""")
            assert moved == [True, 0], moved                                                     # the body scrolls, the tool row does not
            box = page.evaluate("(() => { const r = document.querySelector('.rs-ask-comp').getBoundingClientRect(); return [r.left, r.right, r.bottom]; })()")
            assert box[0] >= 0 and box[1] <= 390 and box[2] <= 844, box
            assert page.evaluate("document.scrollingElement.scrollWidth") <= 390
        finally:
            browser.close()
    assert errors == [], errors


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_ask_view_is_readable_in_the_theme(tmp_path, theme):
    from test_dashboard_themes_browser import _PROBE
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url, 1400, 900)
        try:
            page.evaluate(f"rsSetTheme({json.dumps(theme)}); releaseLoad(); localStorage.removeItem('rs-key:ask:fake'); ask.open()")
            page.wait_for_timeout(300)
            found = {"empty": page.evaluate(_PROBE, ["#sb", theme == "dark"])}
            page.evaluate("localStorage.setItem('rs-key:ask:fake', 'not-a-key')")
            _ask(page, "Primary?", ["tool('run_query', {sql: 'SELECT x'})", "tool('run_query', {sql: \"SELECT edge_id, name FROM edges WHERE highway = 'primary'\"})",
                                    "say('**3** roads. `Street 5`.\\n- a\\n- b\\n- c\\n- d')"])
            _ask(page, "Bad", ["tool('run_query', {sql: 'SELECT x'})"] * 3)
            page.evaluate("document.querySelectorAll('.rs-ask-turn details').forEach(d => d.open = true)")
            found["answers"] = page.evaluate(_PROBE, ["#sb", theme == "dark"])
            page.click(".rs-ask-keyb")
            found["key form"] = page.evaluate(_PROBE, ["#sb", theme == "dark"])
            problems = {k: sorted({" | ".join(str(x) for x in f if x != "") for f in v})[:6] for k, v in found.items() if v}
            assert not problems, json.dumps(problems, indent=1)
        finally:
            browser.close()
    assert errors == [], errors


def test_draw_chart_shows_the_chart_in_the_dock_and_a_copy_in_the_card(tmp_path):
    """The tool draw_chart: the dock shows the chart of its SQL, the card a small copy; Show brings the chart back; a column that is not in the result is
    an error that goes back to the model."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad(); ask.open()")
            _ask(page, "A pie chart of the road classes", [
                "tool('draw_chart', {sql: 'SELECT highway, count(*) AS roads FROM edges GROUP BY highway', kind: 'pie', x: 'highway', y: 'nope'})",
                "tool('draw_chart', {sql: 'SELECT highway, count(*) AS roads FROM edges GROUP BY highway', kind: 'pie', x: 'highway', y: 'roads', title: 'Roads by class'})",
                "say('Half of the 6 roads are primary.')"])
            assert "draw_chart" in page.evaluate("window.calls[0].tools")
            assert "nope" in page.evaluate("window.calls[1].messages.at(-1).content")                 # the bad spec: an error for the model
            assert page.is_visible("#rs-dock .rs-dd-chart") and page.locator("#rs-dock .rs-dd-chart svg path").count() == 3
            card = page.locator(".rs-ask-turn").last
            assert card.locator(".rs-ask-chart svg path").count() == 3 and "Half of the 6 roads" in card.inner_text()
            page.click("#rs-dock .rs-dd-view button:has-text('Table')")
            card.locator(".rs-ask-show").click()
            page.wait_for_timeout(200)
            assert page.is_visible("#rs-dock .rs-dd-chart svg")                                           # Show: the chart again
        finally:
            browser.close()
    assert errors == [], errors
