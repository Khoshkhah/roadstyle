"""The four requests of the dashboard (adapter.js, docs/design/memory_budget.md, "Step 2"): a page with no road table gets the rows of its roads, their
lines, the queries of its data dock and a window of frames from the page's adapter; `rsHttpAdapter` speaks the addresses of way D. Skipped without
playwright."""
import functools
import http.server
import json
import shutil
import struct
import threading
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _ARGS, _edges, _open  # noqa: E402

import roadstyle as rs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "rust/roadstyle-assets/files/static/dashboard"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


_ADAPTER = """() => { window.calls = [];
  const adapter = {
    rows: async (source, ids) => { calls.push(["rows", source, ids]); return ids.map(i => i === 99 ? null : ({name: "Road " + i, highway: "primary", edge_id: i})); },
    lines: async (ids) => { calls.push(["lines", ids]); return ids.map(i => [[18.0 + i * 1e-3, 59.30], [18.0 + i * 1e-3, 59.31]]); },
    query: async (sql) => { calls.push(["query", sql]); return {columns: [{name: "n", type: "INTEGER"}], rows: [[1]]}; },
    schema: async () => ({tables: [{name: "main.edges", rows: 6}]}),
  };
  window.RS_SIDE = null; if (O) O.road_table = null;           // a page with no road table: way D
  rs.setAdapter(adapter); return true; }"""


def _page(tmp_path):
    path = tmp_path / "a.html"
    rs.render_dashboard(_edges(), basemap="blank").save(path)
    return path


def test_a_page_with_no_road_table_reads_its_rows_and_lines_from_the_adapter(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, _page(tmp_path))
        try:
            page.evaluate(_ADAPTER)
            assert page.evaluate("RoadTable.has(2)") is False
            page.evaluate("Promise.all([RoadTable.load(2), RoadTable.load(3)])")           # two roads in one turn: one request
            assert page.evaluate("calls.filter(c => c[0] === 'rows')") == [["rows", "roads", [2, 3]]]
            assert page.evaluate("RoadTable.props(2).name") == "Road 2" and page.evaluate("RoadTable.line(3)[0][0]") == pytest.approx(18.003)
            page.evaluate("RoadTable.load(2)")                                              # a loaded road is not asked again
            page.evaluate("RoadTable.load(99).then(() => RoadTable.load(99))")             # a road that the adapter has not got is asked one time
            page.wait_for_timeout(200)
            assert len([c for c in page.evaluate("calls") if c[0] == "rows"]) == 2
            page.evaluate("rsSelect(4)")                                                    # a selection waits for the row, then shows it
            page.wait_for_function("document.querySelector('.rs-card, .maplibregl-popup, #rs-info')?.textContent.includes('Road 4')", timeout=10_000)
            assert page.evaluate("rs.request.row('roads', 5).then(r => r.name)") == "Road 5"
        finally:
            browser.close()
    assert errors == []


_HOST = """<script type="module">
import {dataDock} from "./dashboard/data/data_dock.js";
window.asked = [];
rs.setAdapter({query: async (sql) => { asked.push(sql); return {columns: [{name: "edge_id", type: "BIGINT"}, {name: "name", type: "VARCHAR"}], rows: [[2n, "Street 1"]]}; },
               schema: async () => ({tables: [{name: "main.edges", rows: 6}]})});
window.data = dataDock({sql: "SELECT edge_id, name FROM edges"});        // no query and no schema: the adapter's
window.hostReady = true;
</script>"""


def test_the_data_dock_takes_the_query_and_the_schema_of_the_adapter(tmp_path):
    shutil.copytree(DASH, tmp_path / "dashboard")
    page_file = tmp_path / "page.html"
    rs.render_dashboard(_edges(), basemap="blank").save(page_file)
    page_file.write_text(page_file.read_text().replace("</body>", _HOST + "</body>"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch(args=_ARGS)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{srv.server_port}/page.html")
            page.wait_for_function("window.map && map.loaded() && window.rsReady && window.hostReady", timeout=60_000)
            try:
                assert page.evaluate("data.schema().then(s => s.tables[0].name)") == "main.edges"
                page.evaluate("data.open()")
                page.evaluate("data.run('SELECT edge_id, name FROM edges')")
                page.wait_for_function("document.querySelectorAll('#rs-dock tbody tr').length === 1", timeout=10_000)
                assert any("FROM edges" in q for q in page.evaluate("asked"))
            finally:
                browser.close()
        assert errors == []
    finally:
        srv.shutdown()


def test_a_request_with_no_adapter_function_is_an_error_not_a_default(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, _page(tmp_path))
        try:
            assert "the page has no adapter" in page.evaluate("(async () => { try { await rs.request.query('x'); } catch (e) { return e.message; } })()")
            page.evaluate("rs.setAdapter({rows: async () => []})")
            assert "the adapter has no frames" in page.evaluate("(async () => { try { await rs.request.frames(0, 1); } catch (e) { return e.message; } })()")
        finally:
            browser.close()
    assert errors == []


def _frames(n, values):
    out = struct.pack("<II", n, len(values))
    for i in range(n):
        out += struct.pack("<d", float(i)) + struct.pack(f"<{len(values)}f", *[v + i for v in values])
    return out


def test_the_http_adapter_speaks_the_addresses_of_way_d(tmp_path):
    seen = []

    def route(r):
        req = r.request
        seen.append((req.method, req.url.split("adapter.test", 1)[1]))
        u = req.url
        if "/tiles/roads/0/0/1" in u:
            return r.fulfill(status=204)
        if "/tiles/" in u:
            return r.fulfill(content_type="application/octet-stream", body=bytes([1, 2, 3, 4]))
        if "/rows/roads" in u:
            ids = json.loads(req.post_data)
            return r.fulfill(content_type="application/json", body=json.dumps([{"id": i, "name": f"Road {i}"} for i in ids]))
        if u.endswith("/query"):
            return r.fulfill(content_type="application/json", body=json.dumps(
                {"columns": [{"name": "osm_id", "type": "BIGINT"}, {"name": "name", "type": "VARCHAR"}], "rows": [["9007199254740993", "a"], [None, "b"]]}))
        if "/frames" in u:
            return r.fulfill(content_type="application/octet-stream", body=_frames(2, [1.5, 2.5, 3.5]))
        return r.fulfill(status=500, body="no such address")

    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, _page(tmp_path))
        try:
            page.route("http://adapter.test/**", route)
            page.evaluate("rs.setAdapter(rsHttpAdapter('http://adapter.test/'))")
            assert page.evaluate("rs.request.tile('roads', 0, 0, 1)") is None
            assert page.evaluate("rs.request.tile('roads', 3, 4, 5).then(t => [...t])") == [1, 2, 3, 4]
            assert page.evaluate("rs.request.row('roads', 7).then(r => r.name)") == "Road 7"
            # a BIGINT keeps all its digits: the adapter makes a BigInt from the text
            assert page.evaluate("rs.request.query('SELECT osm_id').then(r => [typeof r.rows[0][0], String(r.rows[0][0]), r.rows[1][0]])") == ["bigint", "9007199254740993", None]
            assert page.evaluate("rs.request.frames(0, 2).then(f => f.map(x => [x.t, [...x.values]]))") == [[0, [1.5, 2.5, 3.5]], [1, [2.5, 3.5, 4.5]]]
            with pytest.raises(Exception, match="500"):
                page.evaluate("rs.request.schema()")
        finally:
            browser.close()
    assert ("POST", "/rows/roads") in seen and ("POST", "/query") in seen and ("GET", "/frames?from=0&to=2") in seen
    assert errors == []
