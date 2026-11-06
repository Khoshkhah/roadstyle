"""The data dock (dashboard/data/data_dock.js, docs/guides/data-dock.md) with a fake host: `query` answers a few canned results in JavaScript (no database),
and understands the dock's own wraps (the row limit, the count, the sort). The SQL line folds and opens, Ctrl+Enter runs it, the guard refuses a statement
that writes, and an error shows in its line. The result's roads light (the highlight set "dock"), a row click selects and zooms, a row of names selects its
roads. Over the row limit the note has the true count, the CSV has all the rows and a sort is over all the rows. Colour and Focus make layers in their
lists. The page's own tables load before the first run, and a DATE shows as a day. Skipped without playwright."""
import contextlib
import functools
import http.server
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
const classes = ["primary", "secondary", "primary", "residential", "secondary", "primary"];
const CANNED = {
  "SELECT edge_id, name, highway FROM edges": {columns: [["edge_id", "BIGINT"], ["name", "VARCHAR"], ["highway", "VARCHAR"]],
     rows: [1, 2, 3, 4, 5, 6].map(i => [BigInt(i), "Street " + (i - 1), classes[i - 1]])},
  "SELECT edge_id, length_m FROM big": {columns: [["edge_id", "BIGINT"], ["length_m", "DOUBLE"]],
     rows: Array.from({length: 2765}, (_, i) => [BigInt(i % 6 + 1), (i * 7919) % 2765 + 0.5])},
  "SELECT name FROM edges": {columns: [["name", "VARCHAR"]], rows: [["Street 1"], ["Street 4"]]},
  "SELECT * FROM main.edges": {columns: [["edge_id", "BIGINT"], ["name", "VARCHAR"]], rows: [[1n, "Street 0"]]},
  "SELECT day FROM days": {columns: [["day", "Date32<DAY>"]], rows: [[1781049600000]]},
};
window.queries = []; window.loads = [];
const strip = s => s.trim().replace(/;\\s*$/, "");
function answer(sql){
  let m;
  if((m = sql.match(/^SELECT \\* FROM \\(\\n?([\\s\\S]*?)\\n?\\) AS rs_q LIMIT (\\d+)$/))) { const r = answer(m[1]); return {columns: r.columns, rows: r.rows.slice(0, +m[2])}; }
  if((m = sql.match(/^SELECT count\\(\\*\\) AS n FROM \\(([\\s\\S]*)\\) AS rs_c$/))) return {columns: [{name: "n", type: "BIGINT"}], rows: [[BigInt(answer(m[1]).rows.length)]]};
  if((m = sql.match(/^SELECT \\* FROM \\(([\\s\\S]*)\\) AS rs_s ORDER BY "(\\w+)" (ASC|DESC) NULLS LAST$/))) {
    const r = answer(m[1]), i = r.columns.findIndex(c => c.name === m[2]), k = m[3] === "ASC" ? 1 : -1;
    return {columns: r.columns, rows: [...r.rows].sort((a, b) => k * (a[i] < b[i] ? -1 : a[i] > b[i] ? 1 : 0))}; }
  if(/FROM rs_roads WHERE/.test(sql)) return {columns: [{name: "edge_id", type: "BIGINT"}], rows: [[2n], [5n]]};
  const c = CANNED[strip(sql)];
  if(!c) throw new Error("Binder Error: Referenced column \\"nope\\" not found in FROM clause!");
  return {columns: c.columns.map(([name, type]) => ({name, type})), rows: c.rows};
}
let release; const loadedTables = new Promise(r => { release = r; });
window.releaseLoad = release;
window.data = dataDock({
  query: async (sql) => { window.queries.push(sql); return answer(sql); },
  schema: async () => ({tables: [{name: "main.edges", rows: 6, about: "The roads."}, {name: "extra.sensors", rows: 3, about: "Traffic sensors."}]}),
  tables: [{name: "sensors", url: "sensors.geojson", about: "Traffic sensors."}],
  load: async (t) => { window.loads.push(t.name); await loadedTables; },
  roadsBy: (sql, column) => `SELECT edge_id FROM rs_roads WHERE "${column}" IN (SELECT "${column}" FROM (${sql}) AS rs_k)`,
  sql: "SELECT edge_id, name, highway FROM edges",
});
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
    rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}}, name="Data").save(page)
    page.write_text(page.read_text().replace("</body>", _HOST + "</body>"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}/page.html"
    finally:
        srv.shutdown()


def _open(p, url):
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.wait_for_function("window.map && map.loaded() && window.rsReady && window.hostReady", timeout=60_000)
    return browser, page, errors


def test_the_line_the_guard_the_light_and_a_row(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("data.open()")
            # the page's table loads first: a run waits for it, with "Loading the data…"
            page.evaluate("() => { window.first = data.run(); }")                               # not awaited: it waits for the table
            page.wait_for_timeout(200)
            assert page.evaluate("window.loads") == ["sensors"] and "Loading" in page.inner_text("#rs-dock .rs-dock-note")
            page.evaluate("releaseLoad()")
            page.wait_for_function("document.querySelectorAll('#rs-dock tbody tr').length === 6")
            assert page.inner_text("#rs-dock .rs-dock-note").startswith("6 rows · 3 columns")
            assert page.evaluate("window.lights.at(-1)") == 6                                    # the roads of the table light
            # a row click selects its road; the light stays
            page.click("#rs-dock tbody tr >> nth=1")
            page.wait_for_timeout(200)
            assert page.evaluate("rs.getState().selection") == "2" and page.evaluate("window.lights.at(-1)") == 6
            # the line opens on a click, Ctrl+Enter runs, an error shows in its line, the guard refuses a statement that writes (no query)
            page.click("#rs-dock .rs-dd-line")
            page.fill("#rs-dock .rs-dd-ta", "SELECT nope FROM edges")
            page.keyboard.press("Control+Enter")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-err').textContent.length > 0")
            assert "nope" in page.inner_text("#rs-dock .rs-dd-err") and not page.inner_text("#rs-dock .rs-dd-err").endswith("!.")
            n = page.evaluate("window.queries.length")
            page.fill("#rs-dock .rs-dd-ta", "DROP TABLE edges")
            page.keyboard.press("Control+Enter")
            page.wait_for_timeout(200)
            assert "Found: DROP" in page.inner_text("#rs-dock .rs-dd-err") and page.evaluate("window.queries.length") == n
            # a result of names: its roads through the host's roadsBy; a row click selects them
            page.evaluate("data.run('SELECT name FROM edges')")
            page.wait_for_function("window.lights.at(-1) === 2")
            page.click("#rs-dock tbody tr >> nth=0")
            page.wait_for_timeout(300)
            assert page.evaluate("rs.getState().selection") == "2"
            # Tables: a click on a table shows its rows
            page.click("#rs-dock .rs-dd-acts button:has-text('Tables')")
            page.click("#rs-dock .rs-dd-tables button:has-text('edges')")
            page.wait_for_timeout(300)
            assert "SELECT * FROM main.edges" in page.evaluate("window.queries.at(-1)")
            # a DATE that comes as milliseconds shows as a day
            page.evaluate("data.run('SELECT day FROM days')")
            page.wait_for_timeout(200)
            assert page.inner_text("#rs-dock tbody td") == "2026-06-10"
        finally:
            browser.close()
    assert errors == [], errors


def test_over_the_row_limit_the_count_the_csv_and_the_sort_cover_all_rows(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad(); data.open()")
            page.evaluate("data.run('SELECT edge_id, length_m FROM big')")
            assert page.inner_text("#rs-dock .rs-dock-note").startswith("1 000 of 2 765 rows")
            assert page.evaluate("data.csv().then(t => t.split('\\n').length)") == 2766
            page.click("#rs-dock th:nth-child(2)")
            page.wait_for_timeout(300)
            first = float(page.inner_text("#rs-dock tbody tr:first-child td:nth-child(2)"))
            assert first == 0.5, first                                                            # the true minimum of all 2765 rows
            assert any("ORDER BY \"length_m\" ASC" in q for q in page.evaluate("window.queries"))
        finally:
            browser.close()
    assert errors == [], errors


def test_colour_and_focus_are_layers_in_their_lists(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad(); data.open()")
            page.evaluate("data.run()")
            # Colour: one colour for each value of highway (3 values); the light goes (the colours show the roads)
            page.click("#rs-dock .rs-dd-acts button:has-text('Colour')")
            page.click(".rs-dd-menu .rs-dd-menu-add")
            page.wait_for_timeout(300)
            groups = page.evaluate("rs.getState().colors.map(g => g.ids.length)")
            assert sorted(groups) == [1, 2, 3], groups
            assert page.evaluate("window.lights.at(-1)") == 0
            assert page.inner_text("#rs-dock .rs-dd-acts button:has-text('Colour') .rs-dd-count") == "1"
            page.click(".rs-dd-menu .rs-dd-menu-row input[type=checkbox]")                     # off: an undo that can be undone
            page.wait_for_timeout(200)
            assert page.evaluate("rs.getState().colors") == []
            page.keyboard.press("Escape")
            # Focus: the other roads fade; Hide hides them; None ends it
            page.evaluate("data.run('SELECT name FROM edges')")
            page.click("#rs-dock .rs-dd-acts button:has-text('Focus')")
            page.click(".rs-dd-menu .rs-dd-menu-add")
            page.wait_for_timeout(300)
            assert page.evaluate("rs.getState().fade") == ["2", "5"]
            page.click(".rs-dd-menu .rs-dd-seg button:has-text('Hide')")
            page.wait_for_timeout(200)
            assert page.evaluate("[rs.getState().fade, rs.getState().filter.ids]") == [None, ["2", "5"]]
            page.click(".rs-dd-menu .rs-dd-menu-row:has-text('None') input")
            page.wait_for_timeout(200)
            assert page.evaluate("[rs.getState().fade, rs.getState().filter.ids]") == [None, None]
            # the same roads again: the same layer, not a second one
            page.click(".rs-dd-menu .rs-dd-menu-add")
            page.wait_for_timeout(200)
            assert page.evaluate("data.layers().filter(l => l.kind === 'focus').length") == 1
        finally:
            browser.close()
    assert errors == [], errors
