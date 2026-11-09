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
  [`SELECT edge_id, lane_num, "use", width_m, source FROM lane_profile`]: {columns: [["edge_id", "BIGINT"], ["lane_num", "INTEGER"], ["use", "VARCHAR"], ["width_m", "DOUBLE"], ["source", "BIGINT"]],
     rows: [[2n, 1, "driving", 3.2500000001, 9223372036854775807n], [2n, 2, "cycling", 1.5, null], [3n, 1, "driving", 3, 7n]]},
  "SELECT edge_id, name FROM same_edges": {columns: [["edge_id", "BIGINT"], ["name", "VARCHAR"]], rows: [[2n, "Street 1"]]},
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
  if((m = sql.match(/^SELECT "(\\w+)", (count\\(\\*\\)|sum\\("(\\w+)"\\)) AS "([^"]+)" FROM \\(([\\s\\S]*)\\) AS rs_a GROUP BY 1/))) {   // the chart's rows for each value of x
    const r = answer(m[5]), xi = r.columns.findIndex(c => c.name === m[1]), yi = m[3] ? r.columns.findIndex(c => c.name === m[3]) : -1, g = new Map();
    for(const row of r.rows){ const k = row[xi]; g.set(k, (g.get(k) || 0) + (yi < 0 ? 1 : Number(row[yi]))); }
    return {columns: [r.columns[xi], {name: m[4], type: "BIGINT"}], rows: [...g].sort((a, b) => b[1] - a[1])}; }
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
def served(tmp_path, **kw):
    shutil.copytree(DASH, tmp_path / "dashboard")
    page = tmp_path / "page.html"
    rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}}, name="Data", **kw).save(page)
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
            # the table has its fixed width: the side column keeps its place with a hint, before and after a card
            w = "() => Math.round(document.querySelector('#rs-dock .rs-dock-table').getBoundingClientRect().width)"
            w0 = page.evaluate(w)
            assert page.is_visible("#rs-dock .rs-dd-side-hint") and w0 > 600, w0
            # the box ends inside the dock and scrolls (Kaveh: "it doesnt have scroll table!" - the box had the height of its rows)
            page.evaluate("data.run('SELECT edge_id, length_m FROM big')")
            page.wait_for_timeout(300)
            fit = page.evaluate("(() => { const b = document.querySelector('#rs-dock .rs-dock-table'), d = document.getElementById('rs-dock'); return [b.getBoundingClientRect().bottom <= d.getBoundingClientRect().bottom + 1, b.scrollHeight > b.clientHeight + 100]; })()")
            assert fit == [True, True], fit
            page.evaluate("data.run('SELECT edge_id, name, highway FROM edges')")
            page.wait_for_timeout(300)
            assert page.evaluate("window.lights.at(-1)") == 6                                    # the roads of the table light
            # the map switch (Kaveh, 2026-11-07): roadstyle's on/off switch at the start of the map group. Off: the map's own colours, the table
            # stays, Colour and Focus are disabled; on again: the light comes back. A closed dock shows nothing. The event `light` and data.light()
            # tell the host whether the table is shown on the map now.
            sw, mb = "#rs-dock .rs-dd-g-map .rs-dd-light input[role=switch]", "#rs-dock .rs-dd-g-map .rs-dd-mb"
            assert page.inner_text("#rs-dock .rs-dd-light") == "On" and page.is_checked(sw) and page.evaluate("data.light()") is True
            assert page.evaluate(f"[...document.querySelectorAll('{mb}')].map(b => b.disabled)") == [False, False]
            page.evaluate("window.shownEv = []; data.addEventListener('light', e => shownEv.push(e.detail.on))")
            page.click("#rs-dock .rs-dd-light")
            page.wait_for_timeout(200)
            assert page.evaluate("window.lights.at(-1)") == 0 and page.is_visible("#rs-dock .rs-dock-table")
            assert not page.is_checked(sw) and page.evaluate("data.light()") is False and page.inner_text("#rs-dock .rs-dd-light") == "Off"
            assert page.evaluate(f"[...document.querySelectorAll('{mb}')].map(b => b.disabled)") == [True, True]
            page.click("#rs-dock .rs-dd-light")
            page.wait_for_timeout(200)
            assert page.evaluate("window.lights.at(-1)") == 6
            page.evaluate("rs.dock.close()")
            page.wait_for_timeout(200)
            assert page.evaluate("window.lights.at(-1)") == 0 and page.evaluate("data.light()") is False
            page.evaluate("rs.dock.open()")
            page.wait_for_timeout(200)
            assert page.evaluate("window.lights.at(-1)") == 6
            assert page.evaluate("shownEv") == [False, True, False, True]                    # each change of what the map shows, once
            # a row click selects its road; the light stays on the other roads (the selected road shows its select purple: it is not in the blue set)
            page.click("#rs-dock tbody tr >> nth=1")
            page.wait_for_timeout(200)
            assert page.evaluate("rs.getState().selection") == "2" and page.evaluate("window.lights.at(-1)") == 5
            assert page.evaluate(w) == w0 and page.is_hidden("#rs-dock .rs-dd-side-hint")
            # the road card beside the table: the name, the class as a chip, the id at its foot; no field of roadstyle's drawing
            card = page.inner_text("#rs-dock .rs-dd-card")
            assert page.inner_text("#rs-dock .rs-dd-rc-name") == "Street 1" and "edge_id 2" in page.inner_text("#rs-dock .rs-dd-rc-id"), card
            assert page.locator("#rs-dock .rs-dd-rc-chip.strong").count() == 1 and "casing" not in card and "__rs" not in card, card
            # the line opens on a click, Ctrl+Enter runs, an error shows in its line, the guard refuses a statement that writes (no query)
            # the open box folds back on a click outside it, and keeps its text
            page.click("#rs-dock .rs-dd-line")
            page.fill("#rs-dock .rs-dd-ta", "SELECT edge_id, name, highway FROM edges -- kept")
            assert "Esc" in page.inner_text("#rs-dock .rs-dd-edit-hint")
            page.mouse.click(640, 200)
            page.wait_for_timeout(100)
            assert page.locator("#rs-dock .rs-dd-ta").count() == 0 and "-- kept" in page.inner_text("#rs-dock .rs-dd-line")
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
            # the icons of the line (Kaveh, 2026-11-07): the download before the line, the tables after Run, then Reset
            order = page.evaluate("[...document.querySelectorAll('#rs-dock .rs-dd-q > *')].map(e => e.classList.contains('rs-dd-tablesb') ? 'tables' : e.title === 'Reset the map and the table' ? 'reset' : e.classList.contains('rs-dd-line') ? 'line' : e.classList.contains('rs-dd-run') ? 'run' : e.classList.contains('rs-dd-ib') ? 'download' : '?')")
            assert order == ["download", "line", "run", "tables", "reset"], order
            # Tables: a click on a table shows its rows
            page.click("#rs-dock .rs-dd-q .rs-dd-tablesb")
            # the list takes the place of the table: a search field, a group for each schema (the page's own "extra" first), a card with the rows
            # the list is in the side column (where the card of a road is), and the table stays in view
            assert page.is_visible("#rs-dock .rs-dd-side .rs-dd-tables") and page.is_visible("#rs-dock .rs-dock-table") and page.is_hidden("#rs-dock .rs-dd-card")
            assert page.evaluate("[...document.querySelectorAll('#rs-dock .rs-dd-tg-h b')].map(b => b.textContent)") == ["extra", "main"]
            assert "6 rows" in page.inner_text("#rs-dock .rs-dd-tcard:has-text('edges')")
            page.fill("#rs-dock .rs-dd-tfind", "sensor")
            assert page.evaluate("[...document.querySelectorAll('#rs-dock .rs-dd-tcard')].filter(b => !b.hidden).map(b => b.querySelector('.rs-dd-tc-name').textContent)") == ["sensors"]
            page.keyboard.press("Escape")
            assert page.is_hidden("#rs-dock .rs-dd-tables") and page.is_visible("#rs-dock .rs-dock-table")
            page.click("#rs-dock .rs-dd-q .rs-dd-tablesb")
            page.click("#rs-dock .rs-dd-tables button:has-text('edges')")
            assert page.is_hidden("#rs-dock .rs-dd-tables")
            page.wait_for_timeout(300)
            assert "SELECT * FROM main.edges" in page.evaluate("window.queries.at(-1)")
            # a DATE that comes as milliseconds shows as a day
            page.evaluate("data.run('SELECT day FROM days')")
            page.wait_for_timeout(200)
            assert page.inner_text("#rs-dock tbody td") == "2026-06-10"
        finally:
            browser.close()
    assert errors == [], errors


def test_the_light_of_the_table_is_blue_and_a_selected_row_stays_purple(tmp_path):
    """The roads of the table are lit in blue, with no see-through, and in a lighter blue on a dark map; a clicked row has roadstyle's select purple, so the
    person sees which row is selected among the lit roads (Kaveh, 2026-11-07: "show table items on map has the same color of showing selected item").
    The selected road leaves the blue set, because a highlight set paints over the select look; it comes back when the selection ends."""
    import io
    Image = pytest.importorskip("PIL.Image")
    state = """[0, 1, 2, 3, 4, 5].map(id => { const l = map.getLayer("roads-simple");
        const s = map.getFeatureState({source: l.source, sourceLayer: l.sourceLayer, id}); return [s.rs_hl ?? null, s.rs_hlo ?? null, !!s.select]; })"""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad(); data.open(); data.run('SELECT edge_id, name, highway FROM edges')")
            page.wait_for_function("window.lights.at(-1) === 6")
            assert page.evaluate(state) == [["#2563eb", 1, False]] * 6                                 # blue, whole: the legend's colour is the map's
            page.evaluate("rs.select('2')")
            page.wait_for_function(f"({state}).some(s => s[2])")
            picked = [i for i, s in enumerate(page.evaluate(state)) if s[2]]
            assert len(picked) == 1 and page.evaluate("rs.getState().selection") == "2"
            page.wait_for_function(f"({state})[{picked[0]}][0] === null")                              # the selected road is not in the set
            assert [s[0] for s in page.evaluate(state)] == [None if i == picked[0] else "#2563eb" for i in range(6)]
            # on the map the selected road is purple and a lit neighbour is blue (the road at the middle of the screen, at zoom 17)
            def pixel(row):
                page.evaluate(f"(() => {{ const b = window.RS_SIDE.bboxes[{row}]; map.jumpTo({{center: [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2], zoom: 17}}); }})()")
                page.evaluate("new Promise(ok => { map.once('idle', ok); map.triggerRepaint(); })")
                x, y = page.evaluate("(() => { const r = map.getCanvas().getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
                return Image.open(io.BytesIO(page.screenshot())).convert("RGB").getpixel((int(x), int(y)))
            sel, other = pixel(picked[0]), pixel((picked[0] + 1) % 6)
            assert max(abs(a - b) for a, b in zip(other, (37, 99, 235), strict=True)) < 12, other
            assert sel[0] - other[0] > 60, (sel, other)                                                   # purple has far more red than the blue
            page.evaluate("rs.select(null)")
            page.wait_for_function(f"({state})[{picked[0]}][0] === '#2563eb'")                         # the selection ends: the road is lit again
            page.evaluate("rs.select('2')")
            page.wait_for_function(f"({state})[{picked[0]}][0] === null")
            page.evaluate("rsSetTheme('dark')")
            page.wait_for_function("(() => { const l = map.getLayer('roads-simple'); return map.getFeatureState({source: l.source, sourceLayer: l.sourceLayer, id: %d}).rs_hl === '#5aa9f8'; })()" % ((picked[0] + 1) % 6))
            assert page.evaluate(state) == [[None if i == picked[0] else "#5aa9f8", 1 if i != picked[0] else None, i == picked[0]] for i in range(6)]
        finally:
            browser.close()
    assert errors == [], errors


def test_reset_gives_the_map_its_colours_and_empties_the_table(tmp_path):
    """Reset (Kaveh, 2026-11-07): no colour layer, no focus, no lit road, no selected road and no card; the table has no result and no rows; the SQL text stays;
    the event rs:dockreset and dock.reset() say so. The map switch is the person's and stays on."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad(); data.open(); window.resets = 0; document.addEventListener('rs:dockreset', () => { window.resets++; })")
            page.evaluate("data.run('SELECT edge_id, name, highway FROM edges')")
            page.wait_for_function("window.lights.at(-1) === 6")
            page.evaluate("data.colour([{label: 'primary', color: '#e6194b', ids: ['1', '3', '6']}], {sql: 'colour'}); data.focus(['1', '3'], {sql: 'focus', mode: 'fade'})")
            page.click("#rs-dock tbody tr >> nth=1")
            page.wait_for_function("rs.getState().selection === '2'")
            assert page.evaluate("data.layers().length") == 2 and page.locator("#rs-dock tbody tr").count() == 6
            title = page.get_attribute("#rs-dock .rs-dd-q button[title='Reset the map and the table']", "title")
            assert title == "Reset the map and the table"
            page.click("#rs-dock .rs-dd-q button[title='Reset the map and the table']")
            page.wait_for_function("window.resets === 1 && window.lights.at(-1) === 0")
            assert page.evaluate("data.layers().length") == 0 and page.evaluate("data.result()") is None
            assert page.locator("#rs-dock tbody tr").count() == 0 and page.evaluate("rs.getState().selection") is None
            assert page.evaluate("rs.getState().colors.length") == 0 and page.evaluate("data.sql()").startswith("SELECT edge_id")      # the SQL text stays
            assert page.evaluate("data.light()") is True, "the map switch stays on"
            page.evaluate("data.run('SELECT * FROM main.edges')")                                                  # the dock works after a reset
            page.wait_for_function("window.lights.at(-1) === 1 && document.querySelectorAll('#rs-dock tbody tr').length === 1")
            page.evaluate("data.reset()")
            page.wait_for_function("window.resets === 2 && window.lights.at(-1) === 0")
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


def test_the_road_card_is_the_one_place_for_a_road_while_the_dock_is_open(tmp_path):
    """road_popup is on (the default): a selection from the table, from the page (Ask) or the map shows the card and no popup while the
    dock shows the data dock; when the dock closes, the popup comes back."""
    popups = "document.querySelectorAll('.maplibregl-popup').length"
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad(); data.open(); data.run()")
            page.wait_for_function("document.querySelectorAll('#rs-dock tbody tr').length === 6")
            page.click("#rs-dock tbody tr >> nth=1")
            page.wait_for_timeout(300)
            assert page.evaluate("rs.getState().selection") == "2" and page.is_visible("#rs-dock .rs-dd-card")
            assert page.evaluate(popups) == 0
            page.evaluate("rs.select('3')")                                     # Ask and a click on the map select through the same rsSelect
            page.wait_for_timeout(300)
            assert page.evaluate("rs.getState().selection") == "3" and page.evaluate(popups) == 0
            page.evaluate("rs.dock.close(); rs.select('4')")
            page.wait_for_timeout(300)
            assert page.evaluate(popups) == 1                                   # no card in view: the popup again
        finally:
            browser.close()
    assert errors == [], errors


def test_the_card_shows_an_overlay_item_and_no_popup_shows_while_the_dock_is_open(tmp_path):
    """Kaveh, 2026-11-07: "click on item should show info into sql panel card info", and no popup. While the dock shows the data dock, a click on an
    overlay item (a building) shows its facts in the card, with no popup; the card's close button deselects it. When the dock closes, the popup is back."""
    import geopandas as gpd
    from shapely.geometry import box

    from roadstyle import Overlay
    houses = gpd.GeoDataFrame({"name": ["Town hall"], "building": ["civic"], "levels": [4]},
                              geometry=[box(18.0075, 59.3040, 18.0090, 59.3050)], crs=4326)
    popups = "document.querySelectorAll('.maplibregl-popup').length"
    with served(tmp_path, overlays=[Overlay(houses, label="buildings", popup=["building", "levels"])]) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad(); data.open()")
            page.wait_for_timeout(300)
            # the house in the free part of the map: right of the panel, above the dock
            page.evaluate("""(() => { map.jumpTo({center: [18.00825, 59.3045], zoom: 16}); const q = map.project([18.00825, 59.3045]);
                                      map.panBy([q.x - 800, q.y - 220], {duration: 0}); })()""")
            page.evaluate("new Promise(ok => { map.once('idle', ok); map.triggerRepaint(); setTimeout(ok, 3000); })")
            at = page.evaluate("""(() => { const r = map.getCanvas().getBoundingClientRect(), q = map.project([18.00825, 59.3045]);
                                          return [r.left + q.x, r.top + q.y]; })()""")
            page.mouse.click(*at)
            page.wait_for_timeout(400)
            assert page.evaluate(popups) == 0 and page.is_visible("#rs-dock .rs-dd-card")
            card = page.inner_text("#rs-dock .rs-dd-card")
            assert "Town hall" in card and "buildings" in card and "civic" in card and "4" in card, card
            page.click("#rs-dock .rs-dd-rc-x")
            page.wait_for_timeout(300)
            assert page.is_hidden("#rs-dock .rs-dd-card")
            page.evaluate("rs.dock.close()")
            page.wait_for_timeout(300)
            page.mouse.click(*at)
            page.wait_for_timeout(400)
            assert page.evaluate(popups) == 1                                   # no card in view: the popup again
        finally:
            browser.close()
    assert errors == [], errors


def test_a_click_on_a_row_tells_the_page_and_the_page_fills_the_card(tmp_path):
    """Kaveh, 2026-11-07: "each selecting from table must show that item on map also shows its info in card info". A row of a result that is not a
    road: the event `row` {columns, row, index, rowId} (also with the keys), the row shows as selected (and stays selected when the rows are sorted),
    `data.card({title, chip, rows, id})` fills the card, and the close button, a new selection, a new result or `data.card(null)` close it. The close
    button, a new selection and a new result send `cardclose`; the page's own `data.card(null)` does not."""
    shown = ("data.show({sql: 'SELECT node_id, label, weight FROM nodes', columns: [{name: 'node_id', type: 'BIGINT'}, {name: 'label', type: 'VARCHAR'}, "
             "{name: 'weight', type: 'DOUBLE'}], rows: [[10n, 'Charlie', 1.5], [11n, 'Alpha', 2.5], [12n, 'Bravo', 3.5]]})")
    card = "data.card({title: 'Alpha', chip: 'nodes', rows: [['node_id', 11n], ['weight', 2.5], ['empty', null]], id: 11n})"
    on = "document.querySelector('#rs-dock tbody tr.on td:nth-child(2)') && document.querySelector('#rs-dock tbody tr.on td:nth-child(2)').textContent"
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("releaseLoad(); data.open()")
            page.evaluate("window.rowEv = []; window.nClosed = 0; data.addEventListener('row', e => rowEv.push({columns: e.detail.columns.map(c => c.name), "
                          "row: e.detail.row.map(String), index: e.detail.index, rowId: e.detail.rowId})); data.addEventListener('cardclose', () => nClosed++)")
            page.evaluate(shown)
            page.wait_for_function("document.querySelectorAll('#rs-dock tbody tr').length === 3")
            page.click("#rs-dock tbody tr >> nth=1")
            assert page.evaluate("rowEv") == [{"columns": ["node_id", "label", "weight"], "row": ["11", "Alpha", "2.5"], "index": 1, "rowId": None}]
            assert page.evaluate(on) == "Alpha" and page.is_hidden("#rs-dock .rs-dd-card")             # the page has not filled the card yet
            # the page's card: the title, the chip, the rows (no empty value), the id with Copy id
            page.evaluate(card)
            assert page.is_visible("#rs-dock .rs-dd-card")
            text = page.inner_text("#rs-dock .rs-dd-card")
            assert "Alpha" in text and "nodes" in text and "weight" in text and "2.5" in text and "id 11" in text and "Copy id" in text and "empty" not in text, text
            # a sort keeps the row selected, at its new place
            page.click("#rs-dock th:nth-child(2)")
            assert page.evaluate(on) == "Alpha" and page.evaluate("[...document.querySelectorAll('#rs-dock tbody tr')].findIndex(r => r.classList.contains('on'))") == 0
            page.click("#rs-dock th:nth-child(2)")
            assert page.evaluate(on) == "Alpha" and page.evaluate("[...document.querySelectorAll('#rs-dock tbody tr')].findIndex(r => r.classList.contains('on'))") == 2
            # the keys: Enter on a row does what a click does
            page.focus("#rs-dock tbody tr >> nth=1")
            page.keyboard.press("Enter")
            assert page.evaluate("rowEv.at(-1).row[1]") == "Bravo" and page.evaluate(on) == "Bravo"
            # the close button closes the card, tells the page and clears the row
            page.evaluate(card)
            page.click("#rs-dock .rs-dd-rc-x")
            assert page.is_hidden("#rs-dock .rs-dd-card") and page.evaluate("nClosed") == 1 and page.evaluate(on) is None
            # a new selection (a road) takes the card's place and tells the page
            page.evaluate(card)
            page.evaluate("rs.select('3')")
            page.wait_for_timeout(200)
            assert page.evaluate("nClosed") == 2 and "Street 2" in page.inner_text("#rs-dock .rs-dd-card")
            # a new result closes it
            page.evaluate(card)
            page.evaluate(shown)
            assert page.evaluate("nClosed") == 3 and page.is_hidden("#rs-dock .rs-dd-card")
            # the page's own close sends no event
            page.evaluate(card)
            page.evaluate("data.card(null)")
            assert page.is_hidden("#rs-dock .rs-dd-card") and page.evaluate("nClosed") == 3
            # a bad card is an error; a road row sends `row` with its id
            assert "rows" in page.evaluate("(() => { try { data.card({title: 'x'}); } catch(e) { return e.message; } })()")
            page.evaluate("data.run('SELECT edge_id, name, highway FROM edges')")
            page.wait_for_function("document.querySelectorAll('#rs-dock tbody tr').length === 6")
            page.click("#rs-dock tbody tr >> nth=0")
            assert page.evaluate("rowEv.at(-1).rowId") == "1" and page.evaluate("rowEv.at(-1).columns[0]") == "edge_id"
        finally:
            browser.close()
    assert errors == [], errors


def test_a_road_row_of_another_table_shows_its_own_columns_in_the_card(tmp_path):
    """A result with edge_id (lane_profile: several rows for one road): a click on a row selects the road, and the card has the road and the section "This row" with
    the columns of the clicked row, as the table shows them (a lane's width_m, a 64-bit id). The edge_id and a column that the card already shows are not repeated; a
    result of the road's own columns has no section; a click on the map has none."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate('''releaseLoad(); data.open(); data.run('SELECT edge_id, lane_num, "use", width_m, source FROM lane_profile')''')
            page.wait_for_function("document.querySelectorAll('#rs-dock tbody tr').length === 3")
            sec = "#rs-dock .rs-dd-rc-sec"
            rows = "[...document.querySelectorAll('#rs-dock .rs-dd-rc-sec dt, #rs-dock .rs-dd-rc-sec dd')].map(e => e.textContent)"
            page.click("#rs-dock tbody tr >> nth=0")
            page.wait_for_selector(sec)
            assert page.text_content("#rs-dock .rs-dd-rc-sec-t") == "This row"
            assert page.evaluate(rows) == ["lane num", "1", "use", "driving", "width m", "3.25", "source", "9223372036854775807"], page.evaluate(rows)
            assert "Street 1" in page.inner_text("#rs-dock .rs-dd-card") and page.evaluate("rs.getState().selection") == "2"      # the road's card is there too
            # the second lane of the same road: its own columns, and a null as the table shows it
            page.click("#rs-dock tbody tr >> nth=1")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-sec dd:nth-of-type(3)')?.textContent === '1.5'")
            assert page.evaluate(rows) == ["lane num", "2", "use", "cycling", "width m", "1.5", "source", "null"]
            # the road's own columns, with the values the card shows: no section
            page.evaluate("data.run('SELECT edge_id, name FROM same_edges')")
            page.wait_for_function("document.querySelectorAll('#rs-dock tbody tr').length === 1")
            page.click("#rs-dock tbody tr >> nth=0")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-name')?.textContent === 'Street 1'")
            assert page.locator(sec).count() == 0
            # a click on the map (Ask, the page) selects the road with no row section
            page.evaluate('''data.run('SELECT edge_id, lane_num, "use", width_m, source FROM lane_profile')''')
            page.wait_for_function("document.querySelectorAll('#rs-dock tbody tr').length === 3")
            page.click("#rs-dock tbody tr >> nth=2")
            page.wait_for_selector(sec)
            page.evaluate("rs.select('4')")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-name')?.textContent === 'Street 3'")
            assert page.locator(sec).count() == 0
        finally:
            browser.close()
    assert errors == [], errors
