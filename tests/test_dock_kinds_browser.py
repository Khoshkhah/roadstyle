"""The kinds of the data dock (docs/design/dock_kinds.md, dashboard/data/kinds.js): a result with no roads that has a node or a building id column lights its
objects on the map in the blue of the road light (the dark blue on a dark map), a click on a row selects the object (a purple ring, the camera, the card with the
title, the label, the facts and the tags), Reset and the map switch remove the objects, and the name `osm_id` goes to the kind that has the id (a node table
or a building table). A page with no `kinds` is the page of today. Skipped without playwright."""
import contextlib
import functools
import http.server
import io
import shutil
import threading
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
Image = pytest.importorskip("PIL.Image")

from test_dashboard_sections_browser import _ARGS, _edges  # noqa: E402

import roadstyle as rs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "rust/roadstyle-assets/files/static/dashboard"

# the host: two kinds, as duckOSM's objectKinds gives them. `node` has the id columns node_id and osm_id, `building` has osm_id: the name osm_id is in both.
_HOST = """<script type="module">
import {dataDock} from "./dashboard/data/data_dock.js";
const NODES = [[1n, '{"type":"Point","coordinates":[18.001,59.305]}', "Node A", {highway: "crossing", note: "zebra"}],
               [2n, '{"type":"Point","coordinates":[18.003,59.305]}', null, {}],
               [3n, '{"type":"Point","coordinates":[18.005,59.305]}', "Node C", {}]];
const BUILDINGS = [[5001n, '{"type":"Polygon","coordinates":[[[18.0015,59.3],[18.0025,59.3],[18.0025,59.301],[18.0015,59.301],[18.0015,59.3]]]}', "House"],
                   [5002n, '{"type":"Polygon","coordinates":[[[18.0035,59.3],[18.0045,59.3],[18.0045,59.301],[18.0035,59.301],[18.0035,59.3]]]}', "Shed"]];
const WAYS = [[1n, '{"type":"LineString","coordinates":[[18.001,59.31],[18.002,59.31]]}', "Way 1"], [2n, '{"type":"LineString","coordinates":[[18.003,59.31],[18.004,59.31]]}', "Way 2"]];
const LANES = [[5001n, '{"type":"LineString","coordinates":[[18.001,59.32],[18.002,59.32]]}', 1]];
const COLS = {
  "SELECT node_id, name FROM nodes": {columns: [["node_id", "BIGINT"], ["name", "VARCHAR"]], rows: NODES.map(n => [n[0], n[2]])},
  "SELECT osm_id FROM house_ids": {columns: [["osm_id", "BIGINT"]], rows: [[5001n]]},
  "SELECT edge_id, name FROM edges": {columns: [["edge_id", "BIGINT"], ["name", "VARCHAR"]], rows: [[1n, "Street 0"], [2n, "Street 1"]]},
  "SELECT osm_id FROM mixed_ids": {columns: [["osm_id", "BIGINT"]], rows: [[1n], [5001n], [5002n]]},      // 1 is a node, 5001 and 5002 are buildings
  "SELECT osm_id FROM both_ids": {columns: [["osm_id", "BIGINT"]], rows: [[1n], [2n]]},                     // a node and a way each: the full coverage of two kinds
  "SELECT osm_id, lane_num FROM lane_ids": {columns: [["osm_id", "BIGINT"], ["lane_num", "INTEGER"]], rows: [[5001n, 1]]},
  "SELECT broken_id FROM broken": {columns: [["broken_id", "BIGINT"]], rows: [[1n]]},
  "SELECT 1 AS one": {columns: [["one", "INTEGER"]], rows: [[1]]},
};
const strip = s => s.trim().replace(/;\\s*$/, "");
function answer(sql){
  let m;
  if((m = sql.match(/^SELECT \\* FROM \\(\\n?([\\s\\S]*?)\\n?\\) AS rs_q LIMIT (\\d+)$/))) { const r = answer(m[1]); return {columns: r.columns, rows: r.rows.slice(0, +m[2])}; }
  // the geometry of the node kind and of the building kind: id, geom, then the facts
  if((m = sql.match(/^SELECT n\\.node_id AS id, n\\.geom, n\\.name, n\\.tags FROM nodes n WHERE n\\.node_id IN \\(SELECT "(\\w+)" FROM \\(([\\s\\S]*)\\) AS rs_k\\)$/))) {
    const r = answer(m[2]), i = r.columns.findIndex(c => c.name === m[1]), ids = new Set(r.rows.map(x => x[i]));
    return {columns: ["id", "geom", "name", "tags"].map(name => ({name, type: "VARCHAR"})), rows: NODES.filter(n => ids.has(n[0])).map(n => [n[0], n[1], n[2], n[3]])}; }
  if((m = sql.match(/^SELECT b\\.osm_id AS id, b\\.geom, b\\.name FROM buildings b WHERE b\\.osm_id IN \\(SELECT "(\\w+)" FROM \\(([\\s\\S]*)\\) AS rs_k\\)$/))) {
    const r = answer(m[2]), i = r.columns.findIndex(c => c.name === m[1]), ids = new Set(r.rows.map(x => x[i]));
    return {columns: ["id", "geom", "name"].map(name => ({name, type: "VARCHAR"})), rows: BUILDINGS.filter(b => ids.has(b[0]))}; }
  if((m = sql.match(/^SELECT \\* FROM \\(VALUES ([\\s\\S]*)\\) AS rs_p\\("(\\w+)"\\)$/)))      // the probe of the dock: the first ids as a table
    return {columns: [{name: m[2], type: "BIGINT"}], rows: [...m[1].matchAll(/\\((\\d+)\\)/g)].map(x => [BigInt(x[1])])};
  if((m = sql.match(/^SELECT w\\.osm_id AS id, w\\.geom, w\\.name FROM ways w WHERE w\\.osm_id IN \\(SELECT "(\\w+)" FROM \\(([\\s\\S]*)\\) AS rs_k\\)$/))) {
    const r = answer(m[2]), i = r.columns.findIndex(c => c.name === m[1]), ids = new Set(r.rows.map(x => x[i]));
    return {columns: ["id", "geom", "name"].map(name => ({name, type: "VARCHAR"})), rows: WAYS.filter(w => ids.has(w[0]))}; }
  if((m = sql.match(/^SELECT l\\.osm_id AS id, l\\.geom, l\\.lane_num FROM lanes l WHERE l\\.osm_id IN \\(SELECT "(\\w+)" FROM \\(([\\s\\S]*)\\) AS rs_k\\)$/))) {
    const r = answer(m[2]), i = r.columns.findIndex(c => c.name === m[1]), ids = new Set(r.rows.map(x => x[i]));
    return {columns: ["id", "geom", "lane_num"].map(name => ({name, type: "VARCHAR"})), rows: LANES.filter(l => ids.has(l[0]))}; }
  if(/FROM rs_roads WHERE/.test(sql)) return {columns: [{name: "edge_id", type: "BIGINT"}], rows: []};      // no road has an osm_id of a node
  const c = COLS[strip(sql)];
  if(!c) throw new Error("Binder Error: unknown SQL");
  return {columns: c.columns.map(([name, type]) => ({name, type})), rows: c.rows};
}
window.queries = []; window.events = [];
window.data = dataDock({
  query: async (sql) => { window.queries.push(sql); return answer(sql); },
  schema: async () => ({tables: [{name: "main.nodes", rows: 3, about: "The nodes."}]}),
  roadsBy: (sql, column) => `SELECT edge_id FROM rs_roads WHERE "${column}" IN (SELECT "${column}" FROM (${sql}) AS rs_k)`,
  kinds: {
    lane: {label: "Lane", idColumns: ["osm_id"], needs: ["lane_num"],      // a candidate only for a result that also has lane_num
      geometryBy: (sql, column) => `SELECT l.osm_id AS id, l.geom, l.lane_num FROM lanes l WHERE l.osm_id IN (SELECT "${column}" FROM (${sql}) AS rs_k)`},
    node: {label: "Node", idColumns: ["node_id", "osm_id"],
      geometryBy: (sql, column) => `SELECT n.node_id AS id, n.geom, n.name, n.tags FROM nodes n WHERE n.node_id IN (SELECT "${column}" FROM (${sql}) AS rs_k)`},
    building: {label: "Building", idColumns: ["osm_id"],
      geometryBy: (sql, column) => `SELECT b.osm_id AS id, b.geom, b.name FROM buildings b WHERE b.osm_id IN (SELECT "${column}" FROM (${sql}) AS rs_k)`},
    way: {label: "Way", idColumns: ["osm_id"],
      geometryBy: (sql, column) => `SELECT w.osm_id AS id, w.geom, w.name FROM ways w WHERE w.osm_id IN (SELECT "${column}" FROM (${sql}) AS rs_k)`},
    broken: {label: "Broken", idColumns: ["broken_id"], geometryBy: () => "SELECT broken"},      // its SQL fails
  },
  sql: "SELECT node_id, name FROM nodes",
});
for(const n of ["kind", "kinderror"]) data.addEventListener(n, (e) => window.events.push([n, e.detail]));
window.hostReady = true;
</script>"""


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextlib.contextmanager
def served(tmp_path):
    shutil.copytree(DASH, tmp_path / "dashboard")
    page = tmp_path / "page.html"
    rs.render_dashboard(_edges(), basemap="blank", name="Kinds").save(page)
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


_DRAWN = "(src) => map.getSource(src) ? map.getSource(src).serialize().data.features.map(f => f.geometry.type + ':' + (f.properties.rs_id ?? '')) : null"


def _pixel_at(page, lon, lat):
    page.evaluate("new Promise(ok => { map.once('idle', ok); map.triggerRepaint(); })")
    x, y = page.evaluate(f"(() => {{ const r = map.getCanvas().getBoundingClientRect(), p = map.project([{lon}, {lat}]); return [Math.round(r.left + p.x), Math.round(r.top + p.y)]; }})()")
    return Image.open(io.BytesIO(page.screenshot())).convert("RGB").getpixel((x, y))


def _near(c, d, tol=14):
    return all(abs(a - b) <= tol for a, b in zip(c, d, strict=True))


def test_nodes_light_in_blue_and_a_row_selects_a_node(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("data.open(); data.run()")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 3")
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds')") == ["Point:1", "Point:2", "Point:3"]
            assert page.evaluate("map.getPaintProperty('rs-dock-kinds-dot', 'circle-color')") == "#2563eb"
            page.evaluate("map.jumpTo({center: [18.003, 59.305], zoom: 17})")
            assert _near(_pixel_at(page, 18.003, 59.305), (37, 99, 235))                                  # a lit node is blue
            # a click on the row of Node A: the purple ring, the camera, the card
            page.click("#rs-dock tbody tr >> nth=0")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds-sel')?.length === 1")
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds-sel')") == ["Point:1"]
            page.wait_for_function("map.getZoom() >= 18 && !map.isMoving()")
            assert _near(_pixel_at(page, 18.001, 59.305), (124, 77, 255), 24)                              # the selected node is purple
            card = page.inner_text("#rs-dock .rs-dd-card")
            assert "Node A" in card and "Node" in card and "zebra" in card and "crossing" in card and "id 1" in card, card
            # the node without a name: "Node 2"
            page.click("#rs-dock tbody tr >> nth=1")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-name').textContent === 'Node 2'")
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds-sel')") == ["Point:2"]
            # the close button of the card removes the selection, not the lit nodes
            page.click("#rs-dock .rs-dd-rc-x")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds-sel')?.length === 0")
            assert len(page.evaluate(f"({_DRAWN})('rs-dock-kinds')")) == 3
            # the dark theme: the dark blue
            page.evaluate("rsSetTheme('dark')")
            assert page.evaluate("map.getPaintProperty('rs-dock-kinds-dot', 'circle-color')") == "#5aa9f8"
            # a theme change while the objects are drawn takes the style: the objects are there again
            page.evaluate("rsSetTheme('light'); rsSetTheme('dark')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 3 && map.getPaintProperty('rs-dock-kinds-dot', 'circle-color') === '#5aa9f8'")
            # Reset: no object, no selection, no rows
            page.click("#rs-dock tbody tr >> nth=2")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds-sel')?.length === 1")
            page.click("#rs-dock .rs-dd-q button[title='Reset the map and the table']")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 0 && (" + _DRAWN + ")('rs-dock-kinds-sel')?.length === 0")
            assert page.locator("#rs-dock tbody tr").count() == 0
        finally:
            browser.close()
    assert errors == [], errors


def test_objects_that_come_while_the_style_loads_are_drawn_when_it_is_ready(tmp_path):
    """A dark page: the theme swaps the style, and the result arrives before the style is ready. The layers are put in when it is."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("rsSetTheme('dark'); data.open(); data.run()")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 3", timeout=20_000)
            assert page.evaluate("map.getPaintProperty('rs-dock-kinds-dot', 'circle-color')") == "#5aa9f8"
        finally:
            browser.close()
    assert errors == [], errors


def test_the_name_osm_id_goes_to_the_kind_that_has_the_id(tmp_path):
    """osm_id is an id column of the node kind and of the building kind. The nodes are tried first and give no row for 5001, so the building kind owns the
    result and draws its area. A result with road ids is a road result: the kinds draw nothing."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("data.open(); data.run('SELECT osm_id FROM house_ids')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 1")
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds')") == ["Polygon:5001"]
            page.click("#rs-dock tbody tr >> nth=0")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-name')?.textContent === 'House'")
            assert "Building" in page.inner_text("#rs-dock .rs-dd-card")
            # a result of a column that no kind knows: nothing is drawn
            page.evaluate("data.run('SELECT 1 AS one')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 0")
        finally:
            browser.close()
    assert errors == [], errors


def test_the_phone_shows_the_card_of_a_node(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url, width=390, height=844)
        try:
            page.evaluate("data.open(); data.run()")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 3")
            page.click("#rs-dock tbody tr >> nth=0")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-name')?.textContent === 'Node A'")
            assert page.evaluate("document.documentElement.scrollWidth") <= 390
            assert page.is_visible("#rs-dock .rs-dd-card")
        finally:
            browser.close()
    assert errors == [], errors


def _note(page):
    return page.inner_text("#rs-dock .rs-dock-note")


@pytest.mark.parametrize(("theme", "width"), [("light", 1280), ("dark", 1280), ("light", 390)])
def test_the_kind_with_the_most_objects_owns_a_weak_id_name(tmp_path, theme, width):
    """osm_id is an id column of the node, the building and the way kind. Ids 1, 5001 and 5002: one node and two buildings. The old rule gave the result to the
    first kind with one row (the nodes); now the building kind owns it (coverage 2 of 3). The note says which kind owns the result."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url, width=width, height=844 if width < 500 else 800)
        try:
            page.evaluate(f"rsSetTheme('{theme}'); data.open(); data.run('SELECT osm_id FROM mixed_ids')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 2")
            assert sorted(page.evaluate(f"({_DRAWN})('rs-dock-kinds')")) == ["Polygon:5001", "Polygon:5002"]
            page.wait_for_function("document.querySelector('#rs-dock .rs-dock-note')?.textContent.includes('Shown as Building (osm_id)')")
            assert "2 of 3 ids found" in _note(page), _note(page)
            ev = page.evaluate("events.filter(e => e[0] === 'kind').pop()[1]")
            assert ev["name"] == "building" and ev["column"] == "osm_id" and abs(ev["coverage"] - 2 / 3) < 1e-9
            assert [(c["name"], round(c["coverage"], 2)) for c in ev["candidates"]] == [("node", 0.33), ("building", 0.67), ("way", 0.33)]   # lane needs lane_num
            # one probe for each candidate (the ids as a VALUES table), then one full load for the owner
            qs = page.evaluate("queries")
            assert sum("VALUES" in q for q in qs) == 3 and sum("LIMIT 20001" in q for q in qs) == 1, qs
        finally:
            browser.close()
    assert errors == [], errors


def test_full_coverage_in_two_kinds_goes_to_the_earlier_kind_and_needs_removes_a_candidate(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            # ids 1 and 2 are a node and a way each: the tie goes to the node kind, which is the earlier of the two
            page.evaluate("data.open(); data.run('SELECT osm_id FROM both_ids')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 2")
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds')") == ["Point:1", "Point:2"]
            page.wait_for_function("document.querySelector('#rs-dock .rs-dock-note')?.textContent.includes('Shown as Node (osm_id)')")
            assert "ids found" not in _note(page)
            # the lane kind is first in the list, but only a result with lane_num makes it a candidate
            page.evaluate("data.run('SELECT osm_id, lane_num FROM lane_ids')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.[0] === 'LineString:5001'")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dock-note')?.textContent.includes('Shown as Lane (osm_id)')")
        finally:
            browser.close()
    assert errors == [], errors


def test_a_failing_kind_query_is_reported(tmp_path):
    """The query of a kind fails: console.error, the event kinderror and a line in the note. The kind has no rows."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        logs = []
        page.on("console", lambda m: logs.append(m.text) if m.type == "error" else None)
        try:
            page.evaluate("data.open(); data.run('SELECT broken_id FROM broken')")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dock-note')?.textContent.includes('the kind broken failed')")
            assert "unknown SQL" in _note(page)
            assert page.evaluate("events.filter(e => e[0] === 'kinderror').length") == 1
            ev = page.evaluate("events.filter(e => e[0] === 'kinderror')[0][1]")
            assert ev["kind"] == "broken" and ev["column"] == "broken_id" and "unknown SQL" in ev["message"]
            assert any('the kind "broken" failed' in t for t in logs), logs
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds')") == []
        finally:
            browser.close()
    assert [e for e in errors if "unknown SQL" not in e] == [], errors
