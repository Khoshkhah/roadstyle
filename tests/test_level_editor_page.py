"""The level editor in a page with no server (docs/rust/browser.md, "The level editor in a page"): roadstyle-wasm's makeArea gives the
files of the folder form, and the module dashboard/editor/level_editor.js edits an area kept in the browser (browserStore) on the host's
map. They need the editor's wasm package (rust/roadstyle-wasm/build_editor.sh), Node for the first and Chromium (playwright) for the
second: skipped without them (CI builds no package)."""
import json
import shutil
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "roadstyle" / "static"
PKG = STATIC / "level_editor" / "pkg" / "roadstyle_wasm.js"
EDGES = ROOT / "rust" / "roadstyle-rs" / "tests" / "data" / "level_area" / "edges.parquet"
pytestmark = pytest.mark.skipif(not PKG.exists(), reason="no editor wasm package (rust/roadstyle-wasm/build_editor.sh)")


@pytest.mark.skipif(shutil.which("node") is None, reason="no node")
def test_make_area_in_the_page_gives_the_folder_forms_files(tmp_path):
    import pyarrow.parquet as pq

    from roadstyle import _engine
    if not _engine.available():
        pytest.skip("the Rust extension roadstyle._rust is not built")
    script = f"""
import {{initSync, makeArea}} from {json.dumps(PKG.as_uri())};
import {{readFileSync, writeFileSync}} from "node:fs";
initSync({{module: readFileSync({json.dumps(str(PKG.with_name("roadstyle_wasm_bg.wasm")))})}});
const a = makeArea(readFileSync({json.dumps(str(EDGES))}), JSON.stringify({{id_col: "edge_id"}}));
writeFileSync({json.dumps(str(tmp_path / "roads.parquet"))}, a.roads);
writeFileSync({json.dumps(str(tmp_path / "pairs.csv"))}, a.pairs);
writeFileSync({json.dumps(str(tmp_path / "edits.csv"))}, a.edits);
console.log(JSON.stringify([a.roadCount, a.pairCount]));"""
    (tmp_path / "make.mjs").write_text(script)
    out = subprocess.run(["node", str(tmp_path / "make.mjs")], capture_output=True, text=True, check=True)
    folder = tmp_path / "folder"
    roads, pairs, _ = _engine.rust().make_area(pq.read_table(EDGES), str(folder))
    assert json.loads(out.stdout) == [roads, pairs]
    for f in ("roads.parquet", "pairs.csv", "edits.csv"):
        assert (tmp_path / f).read_bytes() == (folder / f).read_bytes(), f


PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<script src="/vendor/maplibre-gl.js"></script><link rel="stylesheet" href="/vendor/maplibre-gl.css">
<link rel="stylesheet" href="/dashboard/dashboard.css"><link rel="stylesheet" href="/popup.css">
<style>html,body{margin:0;height:100%}#map{position:absolute;inset:0}</style></head><body><div id="map"></div><div id="panel"></div>
<script type="module">
import init, * as pkg from "/level_editor/pkg/roadstyle_wasm.js";
import {levelEditor, browserStore} from "/dashboard/editor/level_editor.js";
await init();
// the host's part: the area made in the page and kept in the browser, and the host's own map
const a = pkg.makeArea(new Uint8Array(await (await fetch("/edges.parquet")).arrayBuffer()), JSON.stringify({id_col: "edge_id"}));
const store = browserStore("test-area", "Monaco test");
for(const [n, v] of [["roads.parquet", a.roads], ["pairs.csv", a.pairs], ["edits.csv", a.edits]]) await store.save(n, v);
const map = new maplibregl.Map({container: "map", style: {version: 8, glyphs: "/fonts/{fontstack}/{range}.pbf", sources: {}, layers: []},
  center: [7.42, 43.73], zoom: 15});
const ed = await levelEditor({map, container: document.getElementById("panel"), pkg, store});
window.solved = [];
ed.addEventListener("solved", e => window.solved.push({rows: e.detail.levelsCsv.trim().split("\\n").length - 1, draw: e.detail.draw().length}));
window.editor = ed;
window.ready = a.roadCount;
</script></body></html>"""


class _Files(SimpleHTTPRequestHandler):
    """The static folder, the vendored MapLibre at /vendor/, the test page and the edges."""

    def translate_path(self, path):
        if path.startswith("/vendor/"):
            return str(ROOT / "src" / "roadstyle" / path.lstrip("/"))
        if path == "/edges.parquet":
            return str(EDGES)
        return super().translate_path(path)

    def do_GET(self):
        if self.path == "/test.html":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *a):
        pass


def test_the_editor_module_edits_an_area_kept_in_the_browser():
    pw = pytest.importorskip("playwright.sync_api")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Files, directory=str(STATIC)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": 1300, "height": 850})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/test.html")
            page.wait_for_function("window.ready", timeout=60000)
            roads = page.evaluate("window.ready")
            stored = page.evaluate("localStorage.getItem('lv:test-area:levels.csv')")
            assert stored and len(stored.strip().split("\n")) > roads, "the first solve saved levels.csv in the browser"
            assert page.locator("#lv").count() == 1, "the panel is in the host's container"
            # a head's length through the panel's API: solved again, the host hears it, the store has heads.csv
            road = page.evaluate("JSON.parse(window.editor.area.facts())[0].road")
            said = page.evaluate("r => window.lvApi('/api/apply', {ops: [{op: 'head', road: r, end: 'end', m: '7'}]})", road)
            assert said["ok"] and said["redrawn"], said
            solved = page.evaluate("window.solved")
            assert len(solved) == 1 and solved[0]["rows"] > roads and solved[0]["draw"] > 0, solved
            assert road in page.evaluate("localStorage.getItem('lv:test-area:heads.csv')")
            assert page.evaluate("window.editor.files") == ["edits.csv", "heads.csv", "caps.csv", "levels.csv"]
            assert not errors, errors
            b.close()
    finally:
        server.shutdown()


def test_the_level_edges_query_gives_duckosms_load_roads():
    """duckosmPlan's level_edges (roadstyle-io's duckosm.rs, what a page gives makeArea) has the rows and columns of duckOSM's load_roads
    (the input of `duckosm levels`): one rule for both. Needs a duckOSM file ($DUCKOSM_DB, else ../duckOSM/monaco.duckdb) and duckOSM."""
    import os

    import pandas as pd

    from roadstyle import _engine
    db = Path(os.environ.get("DUCKOSM_DB") or ROOT.parent / "duckOSM" / "monaco.duckdb")
    if not db.is_file() or not _engine.available():
        pytest.skip(f"no duckOSM file at {db} or no roadstyle._rust")
    load_roads = pytest.importorskip("duckosm.levels").load_roads
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect(str(db), read_only=True)
    con.execute("LOAD spatial")
    tq, cq = _engine.rust().duckosm_catalog_sql(con.execute("SELECT current_database()").fetchone()[0])
    plan = json.loads(_engine.rust().duckosm_plan(con.execute(tq).fetchall(), con.execute(cq).fetchall(), "all", True, "[]"))
    got, want = con.execute(plan["level_edges"]).df(), load_roads(db)
    assert len(got) == len(want)
    norm = lambda v: None if v is None or (not isinstance(v, (list, str, bytes)) and pd.isna(v)) else (v.item() if hasattr(v, "item") else v)  # noqa: E731
    for c in got.columns:
        if c == "geometry":
            assert all(bytes(a) == b.wkb for a, b in zip(got[c], want.geometry, strict=True))
        else:
            assert [norm(v) for v in got[c]] == [norm(v) for v in want[c]], c
