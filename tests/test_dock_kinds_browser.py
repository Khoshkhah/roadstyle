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
const MANY = Array.from({length: 25000}, (_, i) => BigInt(i + 1));
const PAIRS = [[3n, JSON.stringify([{role: "from", geom: {type: "LineString", coordinates: [[18.001, 59.33], [18.002, 59.33]]}}, {role: "to", geom: {type: "LineString", coordinates: [[18.002, 59.33], [18.003, 59.331]]}}]), "A pair"]];
const LANES = [[5001n, '{"type":"LineString","coordinates":[[18.001,59.32],[18.002,59.32]]}', 1]];
const COLS = {
  "SELECT node_id, name FROM nodes": {columns: [["node_id", "BIGINT"], ["name", "VARCHAR"]], rows: NODES.map(n => [n[0], n[2]])},
  "SELECT osm_id FROM house_ids": {columns: [["osm_id", "BIGINT"]], rows: [[5001n]]},
  "SELECT edge_id, name FROM edges": {columns: [["edge_id", "BIGINT"], ["name", "VARCHAR"]], rows: [[1n, "Street 0"], [2n, "Street 1"]]},
  "SELECT osm_id FROM mixed_ids": {columns: [["osm_id", "BIGINT"]], rows: [[1n], [5001n], [5002n]]},      // 1 is a node, 5001 and 5002 are buildings
  "SELECT osm_id FROM both_ids": {columns: [["osm_id", "BIGINT"]], rows: [[1n], [2n]]},                     // a node and a way each: the full coverage of two kinds
  "SELECT osm_id, lane_num FROM lane_ids": {columns: [["osm_id", "BIGINT"], ["lane_num", "INTEGER"]], rows: [[5001n, 1]]},
  "SELECT h3_cell FROM cells": {columns: [["h3_cell", "BIGINT"]], rows: [[9223372036854775807n], [9223372036854775807n], [5n]]},      // a repeated id and a 64-bit id
  "SELECT h3_cell FROM cells_null": {columns: [["h3_cell", "BIGINT"]], rows: [[9n], [5n]]},                                           // 9 has no shape
  "SELECT h3_cell FROM many_cells": {columns: [["h3_cell", "BIGINT"]], rows: MANY.map(i => [i])},
  "SELECT h3_cell FROM card_cells": {columns: [["h3_cell", "BIGINT"]], rows: [[5n], [6n], [7n], [8n], [10n]]},
  "SELECT h3_cell FROM cells_missing": {columns: [["h3_cell", "BIGINT"]], rows: [[5n], [123456n]]},
  "SELECT h3_cell FROM slow_cells": {columns: [["h3_cell", "BIGINT"]], rows: [[99999999n]]},
  "SELECT from_edge, via_node, to_edge FROM turns": {columns: [["from_edge", "BIGINT"], ["via_node", "BIGINT"], ["to_edge", "BIGINT"]], rows: [[1n, 7n, 2n], [1n, 7n, 3n], [4n, 8n, 5n]]},
  "SELECT pair_id FROM pairs": {columns: [["pair_id", "BIGINT"]], rows: [[3n]]},
  "SELECT bad_id FROM bad": {columns: [["bad_id", "BIGINT"]], rows: [[1n]]},
  "SELECT empty_id FROM empty": {columns: [["empty_id", "BIGINT"]], rows: [[1n]]},
  "SELECT broken_id FROM broken": {columns: [["broken_id", "BIGINT"]], rows: [[1n]]},
  "SELECT shop_id FROM shops": {columns: [["shop_id", "BIGINT"]], rows: [[41n], [42n]]},
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
  if((m = sql.match(/^SELECT "h3_cell" FROM \\(SELECT "h3_cell", row_number\\(\\) OVER \\(\\) AS rs_n FROM \\(([\\s\\S]*)\\) AS rs_d WHERE "h3_cell" IS NOT NULL\\) AS rs_e GROUP BY "h3_cell" ORDER BY min\\(rs_n\\)$/)))
    return {columns: [{name: "h3_cell", type: "BIGINT"}], rows: MANY.map(i => [i])};      // the distinct ids of the long result
  if((m = sql.match(/^SELECT p\\.pair_id AS id, p\\.parts AS geom, p\\.label FROM pairs p WHERE p\\.pair_id IN \\(SELECT "(\\w+)" FROM \\(([\\s\\S]*)\\) AS rs_k\\)$/))) {
    const r = answer(m[2]), i = r.columns.findIndex(c => c.name === m[1]), ids = new Set(r.rows.map(x => x[i]));
    return {columns: ["id", "geom", "label"].map(name => ({name, type: "VARCHAR"})), rows: PAIRS.filter(x => ids.has(x[0]))}; }
  if((m = sql.match(/^SELECT s\\.shop_id AS id, s\\.geom FROM shops s WHERE s\\.shop_id IN \\(SELECT "(\\w+)" FROM \\(([\\s\\S]*)\\) AS rs_k\\)$/)))
    return {columns: ["id", "geom"].map(name => ({name, type: "VARCHAR"})), rows: [[41n, '{"type":"Point","coordinates":[18.011,59.305]}'], [42n, '{"type":"Point","coordinates":[18.012,59.305]}']]};
  if(/FROM rs_roads WHERE/.test(sql)) return {columns: [{name: "edge_id", type: "BIGINT"}], rows: []};      // no road has an osm_id of a node
  const c = COLS[strip(sql)];
  if(!c) throw new Error("Binder Error: unknown SQL");
  return {columns: c.columns.map(([name, type]) => ({name, type})), rows: c.rows};
}
window.queries = []; window.events = []; window.gotIds = null; window.gotColumn = null; window.aborted = false;
const square = (id) => { const x = 18 + Number(BigInt(id) % 1000n) / 10000, y = 59.3 + Number((BigInt(id) / 1000n) % 100n) * 0.001; return {type: "Polygon", coordinates: [[[x, y], [x + 0.00008, y], [x + 0.00008, y + 0.00008], [x, y + 0.00008], [x, y]]]}; };
window.kindCalls = 0; window.lateKinds = {};
const HOST_KINDS = {
  lane: {label: "Lane", idColumns: ["osm_id"], needs: ["lane_num"],      // a candidate only for a result that also has lane_num
    geometryBy: (sql, column) => `SELECT l.osm_id AS id, l.geom, l.lane_num FROM lanes l WHERE l.osm_id IN (SELECT "${column}" FROM (${sql}) AS rs_k)`},
  node: {label: "Node", idColumns: ["node_id", "osm_id"],
    geometryBy: (sql, column) => `SELECT n.node_id AS id, n.geom, n.name, n.tags FROM nodes n WHERE n.node_id IN (SELECT "${column}" FROM (${sql}) AS rs_k)`},
  building: {label: "Building", idColumns: ["osm_id"],
    geometryBy: (sql, column) => `SELECT b.osm_id AS id, b.geom, b.name FROM buildings b WHERE b.osm_id IN (SELECT "${column}" FROM (${sql}) AS rs_k)`},
  way: {label: "Way", idColumns: ["osm_id"],
    geometryBy: (sql, column) => `SELECT w.osm_id AS id, w.geom, w.name FROM ways w WHERE w.osm_id IN (SELECT "${column}" FROM (${sql}) AS rs_k)`},
  cell: {label: "H3 cell", idColumns: ["h3_cell"], noShape: "a test cell with no place",
    async geometryOf(ids, {column, signal}) {
      window.gotIds = ids; window.gotColumn = column;
      if(ids.includes(99999999n)){ await new Promise((ok) => { signal.addEventListener("abort", () => { window.aborted = true; ok(); }); setTimeout(ok, 5000); }); return []; }
      return ids.filter((id) => id !== 123456n).map((id) => ({id, geom: id === 9n ? null : square(id), resolution: 8}));      // 123456 has no entry
    },
    card(info) {      // the card of the cell 5 is a whole card; 6 is slow; 7 fails; 8 is very slow; 10 has an action that fails; the others have the default card
      const id = String(info.id);
      if(id === "5") return {title: "Cell five", chip: "H3 cell \u00b7 res 8", rows: [["resolution", 8], ["empty", null]],
        sections: [{title: "Inside", rows: [["nodes", 143], ["edges", 12]]}, {title: "Parent", rows: [["cell", "8a2a1072b59ffff"]]}],
        action: {label: "Show cell", note: "Draws the cell on the map.", run: () => { window.actionRuns = (window.actionRuns || 0) + 1; return square(777n); }}};
      if(id === "6") return new Promise((ok) => setTimeout(() => ok({sections: [{title: "Inside", rows: [["nodes", 7]]}]}), 600));
      if(id === "7") return Promise.reject(new Error("the count failed"));
      if(id === "8") return new Promise((ok) => setTimeout(() => ok({title: "Slow cell eight"}), 2500));
      if(id === "10") return {action: {label: "Break", run: () => { throw new Error("no cell for this row"); }}};
      return undefined;
    }},
  turn: {label: "Turn", idColumns: [["from_edge", "to_edge"]],      // a composite key; the parts of a turn have a role each
    async geometryOf(ids, {column}) {
      window.gotIds = ids; window.gotColumn = column;
      const x = (id) => 18 + Number(id) / 1000;
      return ids.map(([a, b]) => ({id: [a, b], turn: `${a}-${b}`, geom: [
        {role: "from", geom: {type: "LineString", coordinates: [[x(a), 59.34], [x(a) + 0.0005, 59.34]]}},
        {role: "via", geom: {type: "Point", coordinates: [x(a) + 0.0005, 59.34]}},
        {role: "to", geom: {type: "LineString", coordinates: [[x(a) + 0.0005, 59.34], [x(b), 59.3405]]}},
        ...(b === 3n ? [{role: "extra", geom: {type: "Point", coordinates: [x(b), 59.3405]}}] : [])]}));
    }},
  pair: {label: "Pair", idColumns: ["pair_id"],      // geometryBy: the parts come as JSON text in the second column
    geometryBy: (sql, column) => `SELECT p.pair_id AS id, p.parts AS geom, p.label FROM pairs p WHERE p.pair_id IN (SELECT "${column}" FROM (${sql}) AS rs_k)`},
  bad: {label: "Bad", idColumns: ["bad_id"], geometryOf: async () => [], geometryBy: () => "SELECT 1"},      // both functions
  empty: {label: "Empty", idColumns: ["empty_id"]},                                                              // neither function
  broken: {label: "Broken", idColumns: ["broken_id"], geometryBy: () => "SELECT broken"},      // its SQL fails
};
window.data = dataDock({
  query: async (sql) => { window.queries.push(sql); return answer(sql); },
  schema: async () => ({tables: [{name: "main.nodes", rows: 3, about: "The nodes."}]}),
  roadsBy: (sql, column) => `SELECT edge_id FROM rs_roads WHERE "${column}" IN (SELECT "${column}" FROM (${sql}) AS rs_k)`,
  kinds: location.hash === "#fn" ? async () => { window.kindCalls++; return {...HOST_KINDS, ...window.lateKinds}; } : HOST_KINDS,      // #fn: a function, as a host that adds tables later
  sql: "SELECT node_id, name FROM nodes",
});
for(const n of ["kind", "kinderror", "cardaction"]) data.addEventListener(n, (e) => window.events.push([n, e.detail]));
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


@pytest.mark.parametrize(("theme", "width"), [("light", 1280), ("dark", 1280), ("light", 390)])
def test_geometry_of_gets_the_distinct_ids_and_keeps_a_64_bit_id(tmp_path, theme, width):
    """A kind with geometryOf (no SQL): it gets the distinct non-null ids of the id column, as BigInt, and the column. Its entries are drawn like the rows of
    geometryBy, and a click on a row gives the card."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url, width=width, height=844 if width < 500 else 800)
        try:
            page.evaluate(f"rsSetTheme('{theme}'); data.open(); data.run('SELECT h3_cell FROM cells')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 2")
            assert page.evaluate("gotIds.map(String)") == ["9223372036854775807", "5"]                        # the repeated id once, no digit lost
            assert page.evaluate("gotIds.every(i => typeof i === 'bigint')") and page.evaluate("gotColumn") == "h3_cell"
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds')") == ["Polygon:9223372036854775807", "Polygon:5"]
            assert not any("VALUES" in q for q in page.evaluate("queries"))                                   # one candidate: no probe, and no SQL of the kind
            page.click("#rs-dock tbody tr >> nth=1")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds-sel')?.length === 1")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-name')?.textContent === 'H3 cell 9223372036854775807'")
            assert "resolution" in page.inner_text("#rs-dock .rs-dd-card")
            assert page.evaluate("map.getPaintProperty('rs-dock-kinds-fill', 'fill-color')") == ("#5aa9f8" if theme == "dark" else "#2563eb")
            assert page.evaluate("document.documentElement.scrollWidth") <= width
        finally:
            browser.close()
    assert errors == [], errors


def test_an_entry_with_no_shape_is_known_but_not_drawn(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("data.open(); data.run('SELECT h3_cell FROM cells_null')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 1")
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds')") == ["Polygon:5"]
            assert "ids found" not in _note(page)                                                              # both ids count as found
            page.click("#rs-dock tbody tr >> nth=0")                                                          # the row of id 9
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-name')?.textContent === 'H3 cell 9'")
            assert "no: a test cell with no place" in page.inner_text("#rs-dock .rs-dd-card")
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds-sel')") == []
        finally:
            browser.close()
    assert errors == [], errors


def test_a_long_result_gives_geometry_of_the_first_20000_ids(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("data.open(); data.run('SELECT h3_cell FROM many_cells')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 19999", timeout=60_000)      # id 9 has no shape in this host
            assert page.evaluate("gotIds.length") == 20000 and page.evaluate("String(gotIds[0]) + ',' + String(gotIds[19999])") == "1,20000"
            page.wait_for_function("document.querySelector('#rs-dock .rs-dock-note')?.textContent.includes('the map shows the first 20\\u2009000 ids')")
        finally:
            browser.close()
    assert errors == [], errors


def test_a_new_result_aborts_the_call_of_the_old_one(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("data.open(); data.run('SELECT h3_cell FROM slow_cells')")
            page.wait_for_function("gotIds && gotIds.length === 1 && String(gotIds[0]) === '99999999'")
            assert page.evaluate("aborted") is False
            page.evaluate("data.run('SELECT 1 AS one')")
            page.wait_for_function("aborted === true")
        finally:
            browser.close()
    assert errors == [], errors


def test_a_kind_with_both_functions_or_with_neither_is_skipped_and_reported(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        logs = []
        page.on("console", lambda m: logs.append(m.text) if m.type == "error" else None)
        try:
            for sql, kind in (("SELECT bad_id FROM bad", "bad"), ("SELECT empty_id FROM empty", "empty")):
                page.evaluate(f"data.open(); data.run('{sql}')")
                page.wait_for_function(f"events.some(e => e[0] === 'kinderror' && e[1].kind === '{kind}')")
                assert page.evaluate(f"({_DRAWN})('rs-dock-kinds')") == []
                assert any(f'the kind "{kind}" failed' in t and "not both" in t for t in logs), logs
                assert f"the kind {kind} failed" in _note(page)
        finally:
            browser.close()
    assert errors == [], errors


def _palette(name="amber"):
    import yaml

    return yaml.safe_load((ROOT / f"rust/roadstyle-assets/files/data/palettes/{name}.yaml").read_text())["dock"]


_COLOURS = "(layer) => { const e = map.getPaintProperty(layer, 'line-color'); return Array.isArray(e) ? Object.fromEntries(e.slice(2, -1).reduce((a, v, i, l) => i % 2 ? a : [...a, [v, l[i + 1]]], [])) : e; }"


@pytest.mark.parametrize(("theme", "width"), [("light", 1280), ("dark", 1280), ("light", 390)])
def test_parts_with_roles_have_the_palette_colours_and_a_composite_key_is_a_row(tmp_path, theme, width):
    """A turn is three parts (a `from` road, a `via` node, a `to` road), one row. Its key is two columns. A role has the colour of the palette in the theme; a role
    that the palette does not name takes the first colour of `role_series`. The selected row keeps its colours over a halo."""
    pal = _palette()
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url, width=width, height=844 if width < 500 else 800)
        try:
            page.evaluate(f"rsSetTheme('{theme}'); data.open(); data.run('SELECT from_edge, via_node, to_edge FROM turns')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 10")      # 3 rows of 3 parts, and 1 extra part
            assert [list(map(str, i)) for i in page.evaluate("gotIds")] == [["1", "2"], ["1", "3"], ["4", "5"]]      # two rows with one from_edge are two objects
            ids = page.evaluate(f"({_DRAWN})('rs-dock-kinds')")
            assert sorted(set(i.split(":")[1] for i in ids)) == ["1|2", "1|3", "4|5"]
            got = page.evaluate(f"({_COLOURS})('rs-dock-kinds-line')")
            want = {r: pal["roles"][r][theme] for r in ("from", "via", "to")} | {"extra": pal["role_series"][0][theme]}
            assert got == want, (got, want)
            page.wait_for_function("document.querySelector('#rs-dock .rs-dock-note')?.textContent.includes('Shown as Turn (from_edge + to_edge)')")
            page.click("#rs-dock tbody tr >> nth=1")                                                    # the turn 1-3: it has the extra part
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds-sel')?.length === 4")
            assert set(i.split(":")[1] for i in page.evaluate(f"({_DRAWN})('rs-dock-kinds-sel')")) == {"1|3"}
            assert page.evaluate("map.getLayer('rs-dock-kinds-sel-halo') !== undefined")                  # the select halo under the colours
            assert page.evaluate("map.getPaintProperty('rs-dock-kinds-sel-halo', 'line-color')") == pal["selected"]
            page.wait_for_function("!map.isMoving()")
            # the camera shows every part of the turn
            assert page.evaluate("(() => { const b = map.getBounds(); return [[18.001, 59.34], [18.003, 59.3405]].every(c => b.contains(c)); })()")
            card = page.inner_text("#rs-dock .rs-dd-card")
            assert "Turn 1|3" in card and all(r in card for r in ("from", "via", "to", "extra")), card
            assert page.evaluate("document.querySelectorAll('#rs-dock .rs-dd-rc-part .rs-dd-sw').length") == 4
            assert page.evaluate("document.documentElement.scrollWidth") <= width
        finally:
            browser.close()
    assert errors == [], errors


def test_geometry_by_gives_parts_as_json_text(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("data.open(); data.run('SELECT pair_id FROM pairs')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 2")
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds')") == ["LineString:3", "LineString:3"]
            pal = _palette()
            assert page.evaluate(f"({_COLOURS})('rs-dock-kinds-line')") == {"from": pal["roles"]["from"]["light"], "to": pal["roles"]["to"]["light"]}
        finally:
            browser.close()
    assert errors == [], errors


def test_a_page_without_the_dock_colours_is_an_error_not_a_guess(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("window.RS_DOCK = null; data.open(); data.run()")
            page.wait_for_function("true")
            page.wait_for_timeout(1500)
            assert any("window.RS_DOCK" in e for e in errors), errors
        finally:
            browser.close()


def test_every_palette_has_the_dock_colours():
    import yaml

    for f in sorted((ROOT / "rust/roadstyle-assets/files/data/palettes").glob("*.yaml")):
        d = yaml.safe_load(f.read_text())["dock"]
        assert {"result", "selected", "roles", "role_series"} <= set(d), f.name
        assert {"from", "via", "to"} <= set(d["roles"]) and len(d["role_series"]) >= 3, f.name
        for pair in [d["result"], *d["roles"].values(), *d["role_series"]]:
            assert set(pair) == {"light", "dark"}, f.name


_CONTRAST = """([sel, dark]) => {
  const rgb = (c) => c.match(/[\\d.]+/g).map(Number), lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const bg = (el) => { for(let e = el; e; e = e.parentElement){ const c = rgb(getComputedStyle(e).backgroundColor); if(c.length < 4 || c[3] > 0.5) return c.length < 4 || c[3] > 0 ? c : [255, 255, 255]; } return [255, 255, 255]; };
  const out = [];
  for(const el of document.querySelectorAll(sel)){
    const b = bg(el), f = rgb(getComputedStyle(el).color), l1 = lum(f), l2 = lum(b);
    out.push({text: el.textContent, ratio: (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05), bgLum: l2});
  }
  return out;
}"""


@pytest.mark.parametrize(("theme", "width"), [("light", 1280), ("dark", 1280), ("light", 390)])
def test_a_kind_card_has_sections_and_one_action(tmp_path, theme, width):
    """The card of a kind (`card(info)`): the title, the chip, the rows, the sections, then one block with a button, then the id. The button calls `run`, which
    gives a geometry: it is drawn with the object, in the select look, and the camera shows both. The text has a contrast of 4.5 in both themes."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url, width=width, height=844 if width < 500 else 800)
        try:
            page.evaluate(f"rsSetTheme('{theme}'); data.open(); data.run('SELECT h3_cell FROM card_cells')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 5")
            page.click("#rs-dock tbody tr >> nth=0")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-name')?.textContent === 'Cell five'")
            assert page.evaluate("[...document.querySelector('#rs-dock .rs-dd-card').children].map(e => e.className)") == [
                "rs-dd-rc-hd", "rs-dd-rc-chips", "rs-dd-rc-rows", "rs-dd-rc-sec", "rs-dd-rc-sec", "rs-dd-rc-act", "rs-dd-rc-foot"]
            card = page.inner_text("#rs-dock .rs-dd-card")
            assert "H3 cell \u00b7 res 8" in card and "resolution" in card and "empty" not in card, card      # a null row is left out
            assert page.evaluate("[...document.querySelectorAll('#rs-dock .rs-dd-rc-sec-t')].map(e => e.textContent)") == ["Inside", "Parent"]
            assert page.inner_text("#rs-dock .rs-dd-rc-act") .startswith("Draws the cell on the map.") and "Show cell" in page.inner_text("#rs-dock .rs-dd-rc-act")
            for sel in (".rs-dd-rc-sec-t", ".rs-dd-rc-act-t", ".rs-dd-rc-act button", ".rs-dd-rc-rows dt"):
                for c in page.evaluate(f"({_CONTRAST})(['#rs-dock {sel}', {str(theme == 'dark').lower()}])"):
                    assert c["ratio"] >= 4.5, (sel, c)
                    assert theme == "light" or c["bgLum"] < 0.2, (sel, c)                                      # no light surface in the dark theme
            assert page.evaluate("document.documentElement.scrollWidth") <= width
            # the button: run once, the cell far away is drawn with the object, the camera shows both
            page.click("#rs-dock .rs-dd-rc-act button")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds-sel')?.length === 2")
            assert page.evaluate("actionRuns") == 1 and page.evaluate("events.filter(e => e[0] === 'cardaction').map(e => e[1])") == [{"kind": "cell", "id": "5"}]
            page.wait_for_function("!map.isMoving()")
            assert page.evaluate("(() => { const b = map.getBounds(); return [[18.0005, 59.3], [18.0777, 59.3]].every(c => b.contains(c)); })()")
            # the close button removes the object and what the action drew
            page.click("#rs-dock .rs-dd-rc-x")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds-sel')?.length === 0")
            assert len(page.evaluate(f"({_DRAWN})('rs-dock-kinds')")) == 5
        finally:
            browser.close()
    assert errors == [], errors


def test_an_async_card_loads_and_a_newer_selection_wins(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        logs = []
        page.on("console", lambda m: logs.append(m.text) if m.type == "error" else None)
        try:
            page.evaluate("data.open(); data.run('SELECT h3_cell FROM card_cells')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 5")
            page.click("#rs-dock tbody tr >> nth=1")                                                         # the cell 6: slow
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-card')?.textContent.includes('Loading')")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-sec-t')?.textContent === 'Inside'")
            assert "Loading" not in page.inner_text("#rs-dock .rs-dd-card") and "nodes" in page.inner_text("#rs-dock .rs-dd-card")
            # a rejected promise shows its message, and the console has it
            page.click("#rs-dock tbody tr >> nth=2")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-note.err')?.textContent === 'the count failed'")
            assert any("the count failed" in t for t in logs), logs
            # a slow card (cell 8) and a click on the cell 5 at once: the card of the cell 5 stays when the slow one comes
            page.click("#rs-dock tbody tr >> nth=3")
            page.click("#rs-dock tbody tr >> nth=0")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-name')?.textContent === 'Cell five'")
            page.wait_for_timeout(3000)
            assert page.inner_text("#rs-dock .rs-dd-rc-name") == "Cell five"
        finally:
            browser.close()
    assert errors == [], errors


def test_an_action_that_fails_shows_its_message(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        logs = []
        page.on("console", lambda m: logs.append(m.text) if m.type == "error" else None)
        try:
            page.evaluate("data.open(); data.run('SELECT h3_cell FROM card_cells')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 5")
            page.click("#rs-dock tbody tr >> nth=4")                                                         # the cell 10: the action breaks
            page.click("#rs-dock .rs-dd-rc-act button")
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-act .rs-dd-rc-note.err')?.textContent === 'no cell for this row'")
            assert any("no cell for this row" in t for t in logs), logs
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds-sel')") == ["Polygon:10"]                        # the object stays selected
        finally:
            browser.close()
    assert errors == [], errors


def _xy(page, lon, lat):
    page.evaluate("new Promise(ok => { map.once('idle', ok); map.triggerRepaint(); })")
    return page.evaluate(f"(() => {{ const r = map.getCanvas().getBoundingClientRect(), p = map.project([{lon}, {lat}]); return [r.left + p.x, r.top + p.y]; }})()")


@pytest.mark.parametrize(("theme", "width"), [("light", 1280), ("dark", 1280), ("light", 390)])
def test_a_click_on_an_object_on_the_map_selects_it_and_marks_its_row(tmp_path, theme, width):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url, width=width, height=844 if width < 500 else 800)
        try:
            page.evaluate(f"rsSetTheme('{theme}'); data.open(); data.run()")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 3")
            page.evaluate("map.jumpTo({center: [18.005, 59.305], zoom: 16.5})")                              # on the node C (a phone shows only the middle)
            x, y = _xy(page, 18.005, 59.305)
            page.mouse.click(x + 4, y + 3)                                                                # a little beside it: the box of 6 px
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-name')?.textContent === 'Node C'")
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds-sel')") == ["Point:3"]
            assert page.evaluate("[...document.querySelectorAll('#rs-dock tbody tr.on')].map(tr => tr.dataset.i)") == ["2"]      # its row is marked
            # a click on empty map is a click on empty map, as before: the object is deselected and no new card opens
            page.wait_for_function("!map.isMoving()")
            empty = page.evaluate("""() => { const r = map.getCanvas().getBoundingClientRect();      // a point of the canvas with nothing on it and no feature under it
              for(let y = r.top + 40; y < r.bottom - 40; y += 25) for(let x = r.left + 40; x < r.right - 40; x += 25)
                if(document.elementFromPoint(x, y) === map.getCanvas() && !map.queryRenderedFeatures([[x - r.left - 12, y - r.top - 12], [x - r.left + 12, y - r.top + 12]]).length) return [x, y];
              return null; }""")
            assert empty, "no empty point on the map"
            page.mouse.click(*empty)
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds-sel')?.length === 0")
            assert len(page.evaluate(f"({_DRAWN})('rs-dock-kinds')")) == 3                                  # the lit objects stay
            assert page.evaluate("document.documentElement.scrollWidth") <= width
        finally:
            browser.close()
    assert errors == [], errors


def test_a_click_a_few_pixels_from_a_thin_line_selects_the_whole_object(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("data.open(); data.run('SELECT pair_id FROM pairs')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 2")
            page.evaluate("map.jumpTo({center: [18.002, 59.33], zoom: 17})")
            x, y = _xy(page, 18.0015, 59.33)                                                              # on the `from` line
            page.mouse.click(x, y - 5)
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-name')?.textContent === 'Pair 3'")
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds-sel')") == ["LineString:3", "LineString:3"]   # both parts
        finally:
            browser.close()
    assert errors == [], errors


def test_a_row_with_no_object_gets_a_card_with_the_reason(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            page.evaluate("data.open(); data.run('SELECT h3_cell FROM cells_missing')")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 1")
            assert "1 of 2 ids found" in _note(page), _note(page)
            page.click("#rs-dock tbody tr >> nth=1")                                                      # the id 123456: the kind has no entry for it
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-name')?.textContent === 'H3 cell 123456'")
            assert "no object found for this row" in page.inner_text("#rs-dock .rs-dd-card")
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds-sel')") == []
        finally:
            browser.close()
    assert errors == [], errors


def test_the_table_marks_a_row_far_down_a_long_table(tmp_path):
    """rs.dock.table(...).choose(match): the row is marked and scrolled to, and a long table draws it."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            out = page.evaluate("""() => {
              const rows = Array.from({length: 5000}, (_, i) => [BigInt(i + 1), "row " + (i + 1)]);
              const t = rs.dock.table({columns: [{name: "n", type: "BIGINT"}, {name: "label", type: "VARCHAR"}], rows, onRow: () => {}});
              t.el.style.cssText = "position:fixed;left:0;top:0;width:400px;height:200px;overflow:auto;z-index:99999";
              document.body.append(t.el);
              const i = t.choose((r) => r[0] === 4000n);
              const on = t.el.querySelector("tr.on"), box = t.el.getBoundingClientRect(), tr = on && on.getBoundingClientRect();
              const miss = t.choose((r) => r[0] === 99999n);
              return {i, onI: on && on.dataset.i, visible: !!tr && tr.top >= box.top - 1 && tr.bottom <= box.bottom + 1, scrolled: t.el.scrollTop, miss, left: t.el.querySelectorAll("tr.on").length};
            }""")
            assert out["i"] == 3999 and out["onI"] == "3999" and out["visible"] and out["scrolled"] > 100_000, out
            assert out["miss"] == -1 and out["left"] == 0, out                                              # no row: the mark goes
        finally:
            browser.close()
    assert errors == [], errors


def test_20000_objects_draw_and_one_click_selects_one(tmp_path):
    """The limit of the map: 20 000 objects (hexagon-sized squares here). The test records the time to draw them and the time from a click on the map to the card."""
    import time

    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url)
        try:
            t0 = time.time()
            page.evaluate("data.open(); data.run('SELECT h3_cell FROM many_cells')")
            page.wait_for_function("map.getSource('rs-dock-kinds') && map.getSource('rs-dock-kinds').serialize().data.features.length === 19999", timeout=90_000)      # id 9 has no shape
            drawn = time.time() - t0
            page.evaluate("map.jumpTo({center: [18.02344, 59.30104], zoom: 18})")
            x, y = _xy(page, 18.02344, 59.30104)                                                          # the middle of the square of the id 1234
            t1 = time.time()
            page.mouse.click(x, y)
            page.wait_for_function("document.querySelector('#rs-dock .rs-dd-rc-name')?.textContent === 'H3 cell 1234'", timeout=30_000)
            clicked = time.time() - t1
            print(f"20 000 objects: drawn in {drawn:.1f} s, a click to the card in {clicked:.1f} s")
            assert drawn < 60 and clicked < 10, (drawn, clicked)
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds-sel')") == ["Polygon:1234"]
            # Reset removes the objects and the selection
            page.click("#rs-dock .rs-dd-q button[title='Reset the map and the table']")
            page.wait_for_function("map.getSource('rs-dock-kinds').serialize().data.features.length === 0 && map.getSource('rs-dock-kinds-sel').serialize().data.features.length === 0")
        finally:
            browser.close()
    assert errors == [], errors


# a kind that the host adds after the page has started (docs/design/dock_kinds_function.md)
_SHOP = """window.lateKinds = {shop: {label: "Shop", idColumns: ["shop_id"],
  geometryBy: (sql, column) => `SELECT s.shop_id AS id, s.geom FROM shops s WHERE s.shop_id IN (SELECT "${column}" FROM (${sql}) AS rs_k)`}}"""
_SETDATA = "window.sets = 0; const src = map.getSource('rs-dock-kinds'); const sd = src.setData.bind(src); src.setData = (d) => { window.sets++; return sd(d); }; null"


def test_a_function_gives_the_kinds_and_a_kind_added_later_is_used_for_the_next_result(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url + "#fn")
        try:
            page.wait_for_function("window.kindCalls >= 1")                                                      # the function is called at the start
            page.evaluate("data.open(); data.run('SELECT shop_id FROM shops')")
            page.wait_for_function("window.kindCalls >= 2")
            page.wait_for_timeout(300)
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds')") in (None, [])                                   # no kind has shop_id yet
            page.evaluate(_SHOP)                                                                                  # a table is added; no reload
            page.evaluate("data.run('SELECT shop_id FROM shops')")                                                # the next result
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 2")
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds')") == ["Point:41", "Point:42"]
            assert "Shown as Shop" in _note(page), _note(page)
            page.click("#rs-dock tbody tr >> nth=0")                                                              # the row has its object and its card
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds-sel')?.length === 1")
            assert "Shop 41" in page.inner_text("#rs-dock .rs-dd-card")
        finally:
            browser.close()
    assert errors == [], errors


def test_refresh_kinds_picks_the_owner_of_the_result_that_is_open(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url + "#fn")
        try:
            page.evaluate("data.open(); data.run('SELECT shop_id FROM shops')")
            page.wait_for_function("window.kindCalls >= 2")
            page.wait_for_timeout(300)
            page.evaluate(_SHOP)
            page.evaluate("data.refreshKinds()")                                                                  # no new run
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 2")
            assert page.evaluate("data.result().__own.name") == "shop"
        finally:
            browser.close()
    assert errors == [], errors


@pytest.mark.parametrize("hash_", ["#fn", ""])
def test_refresh_kinds_does_not_redraw_or_lose_the_row_if_the_same_kind_still_owns_the_result(tmp_path, hash_):
    """An array host (hash_ empty) is unchanged: refreshKinds does nothing."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = _open(p, url + hash_)
        try:
            page.evaluate("data.open(); data.run()")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds')?.length === 3")
            page.click("#rs-dock tbody tr >> nth=0")
            page.wait_for_function("(" + _DRAWN + ")('rs-dock-kinds-sel')?.length === 1")
            page.evaluate(_SETDATA)
            page.evaluate(_SHOP)                                                                                  # a new kind that does not touch this result
            page.evaluate("data.refreshKinds()")
            page.wait_for_timeout(500)
            assert page.evaluate("window.sets") == 0
            assert page.evaluate(f"({_DRAWN})('rs-dock-kinds-sel')") == ["Point:1"]
            assert "Node A" in page.inner_text("#rs-dock .rs-dd-card")
            if hash_:
                assert page.evaluate("window.kindCalls") >= 2                                                     # it did read the function
        finally:
            browser.close()
    assert errors == [], errors
