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
const opts = {data, about: "Six test roads.", dialect: "DuckDB", examples: {general: false, groups: ["How many roads are there?"]}, providers: [fake]};
window.ask = askPanel(opts);
window.answers = []; window.errors = [];
ask.addEventListener("answer", e => answers.push(e.detail));
ask.addEventListener("error", e => errors.push(e.detail.message));
window.withOpts = (extra) => { window.ask = askPanel({...opts, ...extra}); };
window.withTools = (tools) => withOpts({tools});    // a host with its own tools
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
def served(tmp_path, **page):
    shutil.copytree(DASH, tmp_path / "dashboard")
    path = tmp_path / "page.html"
    rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}}, name="Ask", **page).save(path)
    path.write_text(path.read_text().replace("</body>", _HOST + "</body>"))
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
            assert page.is_visible(".rs-ask-ex .rs-ask-q") and not page.is_visible(".rs-ask-exbar")
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
            assert len(calls) == 3 and calls[0]["tools"] == ["run_query", "color_roads", "focus_roads", "move_map", "draw_chart", "get_map", "set_map"]
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
            assert turn.locator(".rs-ask-foot summary").first.inner_text() == "1 query · 6 rows · fake-1"      # and the model that answered
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
            assert second.locator(".rs-ask-foot summary").first.inner_text() == "1 query · 3 rows · fake-1"
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
            assert page.locator(".rs-ask-turn").count() == 0 and page.is_visible(".rs-ask-ex .rs-ask-q")
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
            assert r["auth"] == "Bearer test-key-123" and r["body"]["model"] == "gemini-3.8-flash" and r["body"]["tool_choice"] == "auto"
            assert [t["function"]["name"] for t in r["body"]["tools"]] == ["run_query", "color_roads", "focus_roads", "move_map", "draw_chart", "get_map", "set_map"]
            assert "test-key-123" not in json.dumps(r["body"])
            assert page.inner_text(".rs-ask-turn:last-child .rs-ask-by") == "gemini-3.8-flash"            # each card names the model that answered
        finally:
            browser.close()
    assert errors == [], errors



# a long list of long names: before the fix of 2026-11-07, the list covered its own button before it had a place, and closed itself at once
_MODELS = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "whisper-large-v3"] + [f"some-provider/a-long-model-name-{i}-instruct:free" for i in range(20)]


def test_the_model_box_lists_the_keys_models_and_a_pick_takes_effect_at_once(tmp_path):
    """The Model row is a select box. With a saved key it lists the key's chat models when the form opens (no speech model); a pick is the model
    of the next request, with no Save. The list is long, as OpenRouter's and Gemini's are, and opens."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        chats = []

        def groq(route):
            if route.request.url.endswith("/models"):
                return route.fulfill(status=200, content_type="application/json", body=json.dumps({"data": [{"id": i} for i in _MODELS]}))
            chats.append(route.request.post_data_json)
            route.fulfill(status=200, content_type="application/json", body='{"choices": [{"message": {"role": "assistant", "content": "Six roads."}}]}')
        try:
            page.route("https://api.groq.com/**", groq)
            page.evaluate("""releaseLoad(); localStorage.setItem('rs-key:ask:groq', 'test-key-123');
                             localStorage.setItem('rs-settings:ask', JSON.stringify({provider: 'groq'})); makeReal(); ask.open()""")
            page.click(".rs-ask-keyb")
            opts = "[...document.querySelectorAll('.rs-ask-krow')[1].querySelectorAll('option')].map(o => o.value)"
            page.wait_for_function(opts + f".length === {len(_MODELS)}")                      # Auto, and the models without the speech model
            assert page.evaluate(opts) == ["auto"] + [i for i in _MODELS if i != "whisper-large-v3"]
            page.locator(".rs-ask-krow").nth(1).locator(".rs-sel-btn").click()
            page.locator(".rs-sel-list").get_by_text("llama-3.3-70b-versatile").click()
            assert page.evaluate("JSON.parse(localStorage.getItem('rs-settings:ask')).model.groq") == "llama-3.3-70b-versatile"
            assert page.inner_text(".rs-ask-keynote") == "Ask uses Groq · llama-3.3-70b-versatile now."              # kept at once, no Save
            assert page.inner_text(".rs-ask-keyb") == "AI" and not page.is_visible(".rs-ask-btns .rs-ask-save")      # no Save key without a typed key
            page.fill(".rs-ask-key input[type=password]", "another-key")
            assert page.inner_text(".rs-ask-btns .rs-ask-save") == "Save key" and not page.is_visible(".rs-ask-done")      # one filled button
            page.fill(".rs-ask-key input[type=password]", "")
            assert not page.is_visible(".rs-ask-btns .rs-ask-save")
            assert page.locator(".rs-ask-btns button:visible").all_inner_texts() == ["Clear", "Done"]           # Done at the end of the form
            page.click(".rs-ask-done")
            assert not page.is_visible(".rs-ask-key")                                                         # Done closes the form
            assert "llama-3.3-70b-versatile" in page.inner_text(".rs-ask-who")
            assert page.evaluate("ask.ask('How many?')")["text"] == "Six roads." and chats[-1]["model"] == "llama-3.3-70b-versatile"
        finally:
            browser.close()
    assert errors == [], errors


_OK = '{"choices": [{"message": {"role": "assistant", "content": "Six roads."}}]}'


def test_auto_asks_the_next_service_at_once_and_the_card_names_who_answered(tmp_path):
    """Provider Auto: the services that have a key, in the order of the list. Gemini's free limit (429) gives the question to Groq at once, with no
    wait; the card says "Groq · openai/gpt-oss-120b" and that Gemini could not answer. When no service can answer, the red line names each try."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        seen, groq_ok = [], {"on": True}

        def gemini(route):
            seen.append(("gemini", route.request.post_data_json["model"]))
            route.fulfill(status=429, content_type="application/json", body='{"error": {"message": "Quota exceeded. Please retry in 50s."}}')

        def groq(route):
            seen.append(("groq", route.request.post_data_json["model"]))
            if groq_ok["on"]:
                return route.fulfill(status=200, content_type="application/json", body=_OK)
            route.fulfill(status=503, content_type="application/json", body='{"error": {"message": "over capacity"}}')
        try:
            page.route("https://generativelanguage.googleapis.com/**", gemini)
            page.route("https://api.groq.com/**", groq)
            page.evaluate("""releaseLoad(); localStorage.setItem('rs-key:ask:gemini', 'k1'); localStorage.setItem('rs-key:ask:groq', 'k2');
                             localStorage.setItem('rs-settings:ask', JSON.stringify({provider: 'auto'})); makeReal(); ask.open()""")
            assert page.inner_text(".rs-ask-who") == "Auto · 2 services"
            t0 = page.evaluate("performance.now()")
            assert page.evaluate("ask.ask('How many?')")["text"] == "Six roads."
            assert page.evaluate("performance.now()") - t0 < 3000                                        # no wait on the 429
            assert seen == [("gemini", "gemini-3.8-flash"), ("groq", "openai/gpt-oss-120b")], seen
            assert page.inner_text(".rs-ask-turn .rs-ask-by") == "gpt-oss-120b"                        # only the model that answered, short
            groq_ok["on"] = False
            assert page.evaluate("ask.ask('How many again?')") is None
            line = page.evaluate("[...document.querySelectorAll('.rs-ask-turn')].at(-1).querySelector('.rs-ask-err').innerText")
            assert "No service could answer" in line and "Google Gemini · gemini-3.8-flash (HTTP 429)" in line and "Groq · openai/gpt-oss-120b (HTTP 503)" in line, line
            page.click(".rs-ask-keyb")
            assert page.evaluate("[...document.querySelectorAll('.rs-ask-krow')[0].querySelectorAll('option')].map(o => o.value)")[0] == "auto"
            assert page.evaluate("[...document.querySelectorAll('.rs-ask-order li')].map(l => l.innerText)") == [
                "Google Gemini · gemini-3.8-flash", "Groq · openai/gpt-oss-120b", "OpenRouter (free models) · no key", "Z.ai (GLM) · no key", "Claude (paid) · no key"]
        finally:
            browser.close()
    assert errors == [], errors


def test_model_auto_asks_the_next_model_of_the_key(tmp_path):
    """Model Auto: the key's models in the order of the automatic pick (rankModels). A busy model gives the question to the next model at once."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        seen = []

        def groq(route):
            if route.request.url.endswith("/models"):
                return route.fulfill(status=200, content_type="application/json",
                                     body=json.dumps({"data": [{"id": i} for i in ["allam-2-7b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "openai/gpt-oss-120b"]]}))
            seen.append(route.request.post_data_json["model"])
            if len(seen) == 1:
                return route.fulfill(status=503, content_type="application/json", body='{"error": {"message": "over capacity"}}')
            route.fulfill(status=200, content_type="application/json", body=_OK)
        try:
            page.route("https://api.groq.com/**", groq)
            page.evaluate("""releaseLoad(); localStorage.setItem('rs-key:ask:groq', 'k2');
                             localStorage.setItem('rs-settings:ask', JSON.stringify({provider: 'groq', model: {groq: 'auto'}})); makeReal(); ask.open()""")
            assert page.inner_text(".rs-ask-who") == "Groq · Auto"
            assert page.evaluate("ask.ask('How many?')")["text"] == "Six roads."
            assert seen == ["openai/gpt-oss-120b", "qwen/qwen3.8-27b"], seen
            assert page.inner_text(".rs-ask-turn .rs-ask-by") == "qwen3.8-27b"
            page.click(".rs-ask-keyb")
            opts = "[...document.querySelectorAll('.rs-ask-krow')[1].querySelectorAll('option')].map(o => o.value)"
            page.wait_for_function(opts + ".length > 1")
            assert page.evaluate(opts)[0] == "auto" and page.evaluate("document.querySelectorAll('.rs-ask-krow')[1].querySelector('select').value") == "auto"
        finally:
            browser.close()
    assert errors == [], errors


def test_claude_is_a_paid_service_with_its_browser_header(tmp_path):
    """Claude (paid): its requests carry the key as a Bearer header and the header anthropic-dangerous-direct-browser-access, which Anthropic needs
    for a call from a browser page. The key form says "Get a key" (not "a free key"), and the card names Claude and its model."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        seen = []

        def claude(route):
            seen.append({"url": route.request.url, "auth": route.request.headers.get("authorization"),
                         "browser": route.request.headers.get("anthropic-dangerous-direct-browser-access"),
                         "version": route.request.headers.get("anthropic-version"), "body": route.request.post_data_json})
            if route.request.url.endswith("/models"):
                return route.fulfill(status=200, content_type="application/json", body='{"data": [{"id": "claude-opus-5-5"}, {"id": "claude-sonnet-5-5"}, {"id": "claude-haiku-5-5"}]}')
            route.fulfill(status=200, content_type="application/json", body=_OK)
        try:
            page.route("https://api.anthropic.com/**", claude)
            page.evaluate("""releaseLoad(); localStorage.setItem('rs-key:ask:claude', 'test-key-123');
                             localStorage.setItem('rs-settings:ask', JSON.stringify({provider: 'claude'})); makeReal(); ask.open()""")
            assert page.inner_text(".rs-ask-who") == "Claude (paid) · claude-sonnet-5-5"
            assert page.evaluate("ask.ask('How many?')")["text"] == "Six roads."
            r = seen[-1]
            assert r["url"] == "https://api.anthropic.com/v1/chat/completions" and r["auth"] == "Bearer test-key-123" and r["browser"] == "true"
            assert "temperature" not in r["body"]                                                        # Claude's new models refuse it
            assert r["body"]["model"] == "claude-sonnet-5-5" and page.inner_text(".rs-ask-turn .rs-ask-by") == "claude-sonnet-5-5"
            page.click(".rs-ask-keyb")
            assert page.inner_text(".rs-ask-key > a") == "Get a key from Claude (paid)"
            page.wait_for_function("document.querySelectorAll('.rs-ask-krow')[1].querySelectorAll('option').length === 4")
            assert seen[-1]["browser"] == "true" and seen[-1]["version"] == "2023-06-01"                # the model list too
        finally:
            browser.close()
    assert errors == [], errors


_NO_MONEY = '{"error": {"code": "1113", "message": "Insufficient balance or no resource package. Please recharge."}}'


def test_zai_uses_its_free_model_and_no_balance_is_not_a_wait(tmp_path):
    """Z.ai's model list names only paid models: Save keeps the free model glm-4.5-flash. Z.ai answers a paid model with no balance with HTTP 429
    "Insufficient balance": a wait does not help, so Ask shows the error at once, after one request."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        chats, money = [], {"n": 1}

        def zai(route):
            req = route.request
            if req.url.endswith("/models"):
                return route.fulfill(status=200, content_type="application/json", body='{"data": [{"id": "glm-4.5"}, {"id": "glm-5.3"}, {"id": "glm-5.3-flash"}]}')
            chats.append(req.post_data_json)
            if money["n"] > 0:
                money["n"] -= 1
                return route.fulfill(status=429, content_type="application/json", body=_NO_MONEY)
            route.fulfill(status=200, content_type="application/json", body='{"choices": [{"message": {"role": "assistant", "content": "Six roads."}}]}')
        try:
            page.route("https://api.z.ai/**", zai)
            page.evaluate("""releaseLoad(); localStorage.setItem('rs-key:ask:zai', 'test-key-123');
                             localStorage.setItem('rs-settings:ask', JSON.stringify({provider: 'zai'})); makeReal(); ask.open()""")
            page.click(".rs-ask-keyb")
            assert page.evaluate("[...document.querySelectorAll('.rs-ask-krow')[0].querySelectorAll('option')].map(o => o.value)") == ["auto", "gemini", "groq", "openrouter", "zai", "claude"]
            page.fill(".rs-ask-key input[type=password]", "test-key-123")                           # Save key shows only with a typed key
            page.click(".rs-ask-btns .rs-ask-save")
            page.wait_for_function("document.querySelector('.rs-ask-keynote').textContent.startsWith('Saved.')")
            assert "Ask uses glm-4.5-flash" in page.inner_text(".rs-ask-keynote")
            assert page.evaluate("[...document.querySelectorAll('.rs-ask-krow')[1].querySelectorAll('option')].map(o => o.value)") == ["auto", "glm-4.5-flash"]
            assert page.evaluate("JSON.parse(localStorage.getItem('rs-settings:ask')).model.zai") == "glm-4.5-flash"
            t0 = page.evaluate("performance.now()")
            assert page.evaluate("ask.ask('How many?')") is None
            assert page.evaluate("performance.now()") - t0 < 3000 and len(chats) == 1                 # no wait, no second request
            line = page.inner_text(".rs-ask-turn .rs-ask-err")
            assert "Z.ai (GLM) refused the request (HTTP 429): Insufficient balance" in line and "free limit" not in line, line
            assert page.evaluate("ask.ask('How many?')")["text"] == "Six roads." and chats[-1]["model"] == "glm-4.5-flash"
        finally:
            browser.close()
    assert errors == [], errors


_BUSY = '[{"error": {"code": 503, "message": "The model is overloaded. Please try again later.", "status": "UNAVAILABLE"}}]'


def test_a_busy_service_is_tried_again_and_its_error_says_busy(tmp_path):
    """Kaveh's screenshot: "Google Gemini refused the request (HTTP 503): [{." A 503 is a busy service, not a refusal, and Google sends its
    error as a list. Ask waits and tries again (at most 2 times); when the service stays busy, the red line says "busy" with Google's words."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        seen = []
        busy = {"n": 1}

        def gemini(route):
            seen.append(1)
            if busy["n"] > 0:
                busy["n"] -= 1
                route.fulfill(status=503, content_type="application/json", body=_BUSY)
            else:
                route.fulfill(status=200, content_type="application/json", body='{"choices": [{"message": {"role": "assistant", "content": "Six roads."}}]}')
        try:
            page.route("https://generativelanguage.googleapis.com/**", gemini)
            page.evaluate("releaseLoad(); localStorage.setItem('rs-key:ask:gemini', 'test-key-123'); makeReal(); ask.open()")
            assert page.evaluate("ask.ask('How many?')")["text"] == "Six roads." and len(seen) == 2       # one 503, then the answer
            busy["n"] = 3
            assert page.evaluate("ask.ask('How many again?')") is None
            line = page.evaluate("[...document.querySelectorAll('.rs-ask-turn')].at(-1).querySelector('.rs-ask-err').innerText")
            assert len(seen) == 5 and "Google Gemini is busy now (HTTP 503): The model is overloaded." in line and "refused" not in line and "[{" not in line, line
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


def test_ask_as_a_tab_in_the_panel_has_no_back_button(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("withOpts({tab: 'Map'})")
            tabs = page.locator(".rs-panel-tabs .rs-tab")
            assert tabs.all_inner_texts() == ["Map", "Ask"] and page.evaluate("document.querySelector('.rs-panel-tabs .on').dataset.tab") == "map"
            tabs.nth(1).click()
            assert page.evaluate("ask.isOpen()") and page.evaluate("document.querySelector('.rs-panel-tabs .on').dataset.tab") == "ask"
            assert page.locator("#ask-back").count() == 0 and page.locator(".rs-panel-tabs").is_visible()      # the tab row stays, there is no Back
            tabs.nth(0).click()
            assert not page.evaluate("ask.isOpen()") and page.evaluate("document.querySelector('.rs-panel-tabs .on').dataset.tab") == "map"
            page.evaluate("ask.open()")                                                                          # open from code: the tab follows
            assert page.evaluate("document.querySelector('.rs-panel-tabs .on').dataset.tab") == "ask"
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
            assert page.evaluate("getComputedStyle(document.querySelector('.rs-frame-bar')).borderTopWidth") == "0px"   # no line above Examples: the box has its edge
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
            assert page.is_visible("#rs-dock .rs-dd-chart") and page.locator("#rs-dock .rs-dd-chartel svg path").count() == 3
            card = page.locator(".rs-ask-turn").last
            assert card.locator(".rs-ask-chart svg path").count() == 3 and "Half of the 6 roads" in card.inner_text()
            box = "(() => { const e = document.querySelector('.rs-ask-turn:last-child .rs-ask-chart'); return [e.scrollHeight <= e.clientHeight + 1, e.scrollWidth <= e.clientWidth + 1]; })()"
            assert page.evaluate(box) == [True, True], "the small copy has no scroll"
            page.click("#rs-dock .rs-dd-view button:has-text('Table')")
            card.locator(".rs-ask-show").click()
            page.wait_for_timeout(200)
            assert page.is_visible("#rs-dock .rs-dd-chartel svg")                                           # Show: the chart again
        finally:
            browser.close()
    assert errors == [], errors


def test_the_duckdb_prompt_has_the_graph_rule(tmp_path):
    """Kaveh: "compute diameter of driving network" got "there is no graph function". With dialect DuckDB the prompt has the shortest-path pattern
    (WITH RECURSIVE ... USING KEY) and the sweeps for the diameter: forward from the 4 nodes at the edges of the map, then backward."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad(); ask.open()")
            _ask(page, "What is the diameter of the network?", ["say('About 4 km.')"])
            system = page.evaluate("window.calls[0].messages[0].content")
            assert "USING KEY (src, node)" in system and "reversed edges" in system and "Never compute all pairs at once" in system
        finally:
            browser.close()
    assert errors == [], errors


def test_a_road_click_while_ask_is_open_opens_the_dock_card_and_no_popup(tmp_path):
    """Ask closed: a click on a road opens its popup, and the road's tooltip closes (it showed through the popup). Ask open: no popup; the data
    dock opens with the road in its card (Kaveh, 2026-11-06). Ask closed again: the popup again."""
    popups = "document.querySelectorAll('.maplibregl-popup:not(.rs-tip)').length"
    with served(tmp_path, road_tooltip=["highway"]) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad()")
            x, y = page.evaluate("(() => { const q = map.project([18.002, 59.305]); return [q.x, q.y]; })()")
            page.mouse.move(x, y)
            page.wait_for_selector(".maplibregl-popup.rs-tip", timeout=5000)
            page.mouse.click(x, y)
            page.wait_for_timeout(300)
            assert page.evaluate(popups) == 1 and page.locator(".rs-tip").count() == 0
            page.evaluate("document.querySelector('.maplibregl-popup-close-button').click()")
            page.click("#sb [data-rs-section=ask] .rs-sec-title")
            page.mouse.click(x, y)
            page.wait_for_timeout(300)
            assert page.evaluate(popups) == 0 and page.evaluate("rs.dock.isOpen()")
            assert "Street 2" in page.inner_text("#rs-dock .rs-dd-card")
            page.click(".rs-frame-back")
            page.evaluate("rs.dock.close()")
            page.mouse.click(x, y)
            page.wait_for_timeout(300)
            assert page.evaluate(popups) == 1
        finally:
            browser.close()
    assert errors == [], errors


def test_a_map_tool_turns_the_map_switch_on_and_a_ring_shows_the_work(tmp_path):
    """The dock's map switch is off: a focus would not show, so Ask turns the switch on and the card says so. While a question runs, its step line has a
    turning ring (decisions of 2026-11-07)."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad(); ask.open(); data.open()")
            page.locator(".rs-dd-light").click()                                                        # the switch off
            assert page.evaluate("document.querySelector('.rs-dd-light input').checked") is False
            _ask(page, "Show only the primary roads", ["tool('focus_roads', {sql: \"SELECT edge_id, name FROM edges WHERE highway = 'primary'\", mode: 'hide'})",
                                                      "say('Three primary roads.')"])
            assert page.evaluate("document.querySelector('.rs-dd-light input').checked") is True and page.evaluate("data.light()") is True
            assert "The map switch of the data dock is on again" in page.inner_text(".rs-ask-turn")
            ring = page.evaluate("(() => { const p = document.createElement('p'); p.className = 'step'; p.textContent = 'Asking'; document.querySelector('.rs-ask-turn').append(p); return getComputedStyle(p, '::before').animationName; })()")
            assert ring == "rs-spin"
        finally:
            browser.close()
    assert errors == [], errors


def test_set_map_changes_the_theme_both_ways(tmp_path):
    """The theme in get_map and set_map: before 2026-11-07, Ask could make the page dark only by a dark base map, and "light" could not be done."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad(); ask.open()")
            _ask(page, "Dark theme, please", ["tool('get_map', {})", "tool('set_map', {theme: 'dark'})", "say('Dark.')"])
            assert json.loads(page.evaluate("window.calls[1].messages.at(-1).content"))["theme"] == "light"            # get_map names it
            assert page.evaluate("[document.documentElement.dataset.rsTheme, document.querySelector('#sb').dataset.theme]") == ["dark", "dark"]
            done = json.loads(page.evaluate("window.calls[2].messages.at(-1).content"))
            assert done["done"] == "Map: theme dark." and done["map"]["theme"] == "dark"
            _ask(page, "Light theme again", ["tool('set_map', {theme: 'light'})", "say('Light.')"])
            assert page.evaluate("[document.documentElement.dataset.rsTheme, document.querySelector('#sb').dataset.theme]") == ["light", "light"]
            _ask(page, "Blue theme", ["tool('set_map', {theme: 'blue'})", "say('No.')"])
            assert "light" in page.evaluate("window.calls.at(-1).messages.at(-1).content") and page.evaluate("document.documentElement.dataset.rsTheme") == "light"
        finally:
            browser.close()
    assert errors == [], errors


def test_get_map_and_set_map_change_the_map_and_a_host_tool_is_added(tmp_path):
    import geopandas as gpd
    from shapely.geometry import box
    water = rs.Overlay(gpd.GeoDataFrame(geometry=[box(18.0, 59.30, 18.005, 59.305)], crs=4326), kind="fill", label="Water", popup=[])
    with served(tmp_path, overlays=[water]) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("""withTools([{name: 'host_row', description: 'Select row n of the host table.', parameters: {n: {type: 'number'}}, required: ['n'],
                                          step: (a) => 'Row ' + a.n, run: async (a, c) => { window.hostGot = [a.n, Object.keys(c)]; return {done: 'Row ' + a.n + '.'}; }}]);
                             releaseLoad(); ask.open()""")
            bases = page.evaluate("rs.basemaps().map(b => b.key)")
            other = next(k for k in bases if k != page.evaluate("rs.getState().basemap"))

            def reply(i):
                return json.loads(page.evaluate(f"window.calls[{i}].messages.at(-1).content"))
            _ask(page, "Turn off the water, go to 18.01 59.305 in 3D, other base map", [
                "tool('get_map', {})",
                f"tool('set_map', {{overlays: {{water: false, Nodes: true}}, basemap: '{other.upper()}', view3d: true, roadFill: false, camera: {{center: [18.01, 59.305], zoom: 15}}}})",
                "tool('host_row', {n: 4})", "say('Done.')"])
            tools = page.evaluate("window.calls[0].tools")
            assert tools[-3:] == ["get_map", "set_map", "host_row"]
            assert "set_map(" in page.evaluate("window.calls[0].messages[0].content")
            first = reply(1)                                                                       # get_map: what can change
            assert first["overlays"] == [{"label": "Water", "on": True}] and {"key": other, "label": first["basemaps"][bases.index(other)]["label"]} in first["basemaps"]
            assert first["view3d"] is False and first["roadFill"] is True and len(first["camera"]["center"]) == 2
            second = reply(2)                                                                      # set_map: the new state; the unknown layer is named
            assert second["done"].startswith("Map: Water off, base map ") and second["done"].endswith(", 3D view on, road fill off, camera.")
            assert second["not_found"] == ['layer "Nodes"'] and second["map"]["overlays"] == [{"label": "Water", "on": False}]
            state = page.evaluate("rs.getState()")
            assert state["overlays"]["Water"]["visible"] is False and state["view3d"] is True and state["roadFill"] is False
            assert state["basemap"] == other and abs(state["camera"]["center"][0] - 18.01) < 1e-6 and abs(state["camera"]["center"][1] - 59.305) < 1e-6
            got = page.evaluate("window.hostGot")                                                  # the host tool: its arguments and the context of the question
            assert got[0] == 4 and {"ok", "failed", "maps"} <= set(got[1])
            assert reply(3) == {"done": "Row 4."}
            assert "Map: Water off" in page.locator(".rs-ask-turn").last.locator(".rs-ask-map").first.inner_text()
            # a wrong camera and an unknown base map go back to the model as the words of the tool
            _ask(page, "Zoom far", ["tool('set_map', {camera: {zoom: 99}})", "tool('set_map', {basemap: 'nope'})", "say('No.')"])
            assert "zoom must be 0 to 22" in page.evaluate("window.calls.at(-2).messages.at(-1).content")
            assert json.loads(page.evaluate("window.calls.at(-1).messages.at(-1).content"))["done"] == "Nothing changed."
            # a host tool with a name in use is refused
            msg = page.evaluate("() => { try{ withTools([{name: 'set_map', run: () => 0}]); }catch(e){ return e.message; } }")
            assert 'the tool name "set_map" is already in use' in msg
        finally:
            browser.close()
    assert errors == [], errors


@pytest.mark.parametrize("size", [(1280, 600), (390, 600)])
def test_a_long_examples_list_stays_in_the_free_space_and_scrolls(tmp_path, size):
    """Kaveh, 2026-11-07: "bug in showing examples. it needs scroll too". 7 long examples do not fit above the question box: the list has the free
    space as its maximum height and scrolls inside (the panel's scroll rules); the keys walk the examples, and Escape closes the list."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url, *size)
        try:
            page.evaluate("""withOpts({examples: {general: false, groups: Array.from({length: 7}, (_, i) => 'Question number ' + (i + 1) + ': which streets of this district have more than two lanes, are one-way and are longer than one kilometre?')}});
                             releaseLoad(); ask.open()""")
            _ask(page, "Hi", ["say('Hello.')"])
            page.click(".rs-ask-exb")
            geo = """() => { const r = (s) => document.querySelector(s).getBoundingClientRect(), l = r('.rs-ask-exlist'), list = document.querySelector('.rs-ask-exlist'),
                      first = document.querySelector('.rs-ask-exlist > :first-child').getBoundingClientRect(), last = document.querySelector('.rs-ask-exlist > :last-child').getBoundingClientRect();
                      return {top: l.top, bottom: l.bottom, body: r('#ask-body').top, comp: r('.rs-ask-comp').top, scrolls: list.scrollHeight > list.clientHeight + 2,
                              st: list.scrollTop, first: [first.top, first.bottom], last: [last.top, last.bottom]}; }"""
            g = page.evaluate(geo)
            assert g["scrolls"], g                                                                 # the list is longer than the free space: the test means something
            assert g["top"] >= g["body"] - 1 and g["bottom"] <= g["comp"], g                       # inside the free space above the question box
            assert g["first"][0] >= g["top"] and g["first"][1] <= g["bottom"], g                   # the first example is in view
            rules = page.evaluate("(() => { const e = document.querySelector('.rs-ask-exlist'), cs = getComputedStyle(e); return [cs.overflowY, cs.overscrollBehaviorY, cs.scrollbarWidth, !!e.dataset.rsScroll]; })()")
            assert rules == ["auto", "contain", "thin", True], rules                               # the panel's scroll rules
            page.evaluate("document.querySelector('.rs-ask-exlist').scrollTop = 99999")
            g = page.evaluate(geo)
            assert g["last"][0] >= g["top"] and g["last"][1] <= g["bottom"], g                     # the last one is reachable
            # the keys: from the button, Up goes to the last example, and Up again to the first; Down goes back; Escape closes the list
            page.focus(".rs-ask-exb")
            inside = """() => { const a = document.activeElement, l = document.querySelector('.rs-ask-exlist').getBoundingClientRect(), r = a.getBoundingClientRect();
                         return [a.parentElement.classList.contains('rs-ask-exlist') ? [...a.parentElement.children].indexOf(a) : -1, r.top >= l.top - 1 && r.bottom <= l.bottom + 1]; }"""
            page.keyboard.press("ArrowUp")
            assert page.evaluate(inside) == [6, True]
            for _ in range(6):
                page.keyboard.press("ArrowUp")
            assert page.evaluate(inside) == [0, True] and page.evaluate("document.querySelector('.rs-ask-exlist').scrollTop") <= 10      # at most the padding of the list
            page.keyboard.press("ArrowDown")
            assert page.evaluate(inside) == [1, True]
            page.keyboard.press("Escape")
            assert not page.is_visible(".rs-ask-exlist") and page.evaluate("document.activeElement.className") == "rs-ask-exb"
            assert page.evaluate("document.querySelector('.rs-ask-exb').getAttribute('aria-expanded')") == "false"
            page.click(".rs-ask-exb")                                                              # it opens at the top again
            assert page.evaluate("document.querySelector('.rs-ask-exlist').scrollTop") == 0
        finally:
            browser.close()
    assert errors == [], errors


def test_examples_in_groups_have_headings_in_both_lists_and_the_keys_skip_them(tmp_path):
    """Kaveh, 2026-11-07: "maybe we should categorize them in example list too". `examples` takes strings and groups {title, items}: a heading above its
    chips in the start list and in the drop-up list; the arrow keys walk over the chips only; a flat list has no heading."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad(); ask.open()")
            assert page.evaluate("document.querySelectorAll('.rs-ask-ex .rs-ask-q').length") == 1 and page.evaluate("document.querySelectorAll('.rs-ask-grp').length") == 0   # a flat list: no heading
            page.evaluate("""document.querySelector('.rs-ask').remove();                          // the first Ask view of the host goes; a new one has the groups
                             withOpts({examples: {general: false, groups: ['Plain one?', {title: 'Changes', items: ['Which objects did I change?', 'When?']}, {title: 'Empty', items: []},
                                                  {title: 'Colours', items: ['Colour the primary roads red']}]}});
                             ask.open()""")
            start = page.evaluate("[...document.querySelectorAll('.rs-ask-ex > .rs-ask-grp, .rs-ask-ex > .rs-ask-q')].map(e => e.className.slice(7) + ':' + e.textContent)")
            assert start == ["q:Plain one?", "grp:Changes", "q:Which objects did I change?", "q:When?", "grp:Colours", "q:Colour the primary roads red"], start
            page.evaluate("window.script = [say('Done.')]")
            page.locator(".rs-ask-ex:visible .rs-ask-q").nth(1).click()                              # a chip of a group asks its question
            page.wait_for_function("window.calls.length === 1 && !document.querySelector('.rs-ask-send').classList.contains('stop')")      # the answer is done
            assert page.evaluate("window.calls[0].messages.at(-1).content") == "Which objects did I change?"
            page.click(".rs-ask-exb")
            drop = page.evaluate("[...document.querySelectorAll('.rs-ask-exlist > *')].map(e => e.className.slice(7) + ':' + e.textContent)")
            assert drop == start, drop
            assert page.evaluate("getComputedStyle(document.querySelector('.rs-ask-exlist .rs-ask-grp')).textTransform") == "uppercase"
            page.focus(".rs-ask-exb")
            order = []
            for _ in range(5):
                page.keyboard.press("ArrowUp")
                order.append(page.evaluate("document.activeElement.textContent"))
            assert order == ["Colour the primary roads red", "When?", "Which objects did I change?", "Plain one?", "Plain one?"], order     # the headings are skipped
            page.keyboard.press("Escape")
            assert not page.is_visible(".rs-ask-exlist")
        finally:
            browser.close()
    assert errors == [], errors


def test_with_no_examples_option_the_general_groups_show_and_the_hosts_own_come_after(tmp_path):
    """Kaveh, 2026-11-07: the example questions must work for any data. No `examples`: the general groups (no name of a table or a column of a project).
    A host's own strings and groups come after them; `{general: false, groups}` gives only the host's own."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("ask.open(); document.querySelector('.rs-ask').remove(); withOpts({examples: undefined}); ask.open()")
            heads = page.evaluate("[...document.querySelectorAll('.rs-ask-ex > .rs-ask-grp')].map(e => e.textContent)")
            assert heads == ["Know the data", "Find and count", "Show on the map", "Colour and focus", "The map and the layers", "Charts"], heads
            text = page.evaluate("document.querySelector('.rs-ask-ex').textContent")
            assert "Switch to the satellite base map." in text and "edge_id" not in text and "length" not in text
            page.evaluate("document.querySelector('.rs-ask').remove(); withOpts({examples: ['Own question?', {title: 'Mine', items: ['Own two?']}]}); ask.open()")
            tail = page.evaluate("[...document.querySelectorAll('.rs-ask-ex > .rs-ask-q, .rs-ask-ex > .rs-ask-grp')].map(e => e.textContent).slice(-3)")
            assert tail == ["Own question?", "Mine", "Own two?"], tail
            page.evaluate("document.querySelector('.rs-ask').remove(); withOpts({examples: {general: false, groups: []}}); ask.open()")
            assert page.evaluate("document.querySelectorAll('.rs-ask-ex .rs-ask-q').length") == 0
        finally:
            browser.close()
    assert errors == [], errors
