"""The level editor in a page with no server (docs/rust/browser.md, "The level editor in a page"): roadstyle-wasm's makeArea gives the
files of the folder form, and the module dashboard/editor/level_editor.js edits an area kept in the browser (browserStore) on the host's
map. They need the editor's wasm package (rust/roadstyle-wasm/build_editor.sh), Node for the first and Chromium (playwright) for the
second: skipped without them (CI builds no package)."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "rust" / "roadstyle-assets" / "files"
STATIC = ASSETS / "static"
# the editor's wasm package: build_editor.sh writes it to $CARGO_TARGET_DIR/editor-pkg/ (else rust/target/editor-pkg/)
PKG = Path(os.environ.get("CARGO_TARGET_DIR") or ROOT / "rust" / "target") / "editor-pkg" / "roadstyle_wasm.js"
EDGES = ROOT / "rust" / "roadstyle-rs" / "tests" / "data" / "level_area" / "edges.parquet"
needs_pkg = pytest.mark.skipif(not PKG.exists(), reason="no editor wasm package (rust/roadstyle-wasm/build_editor.sh)")


def test_the_panels_colour_variables_have_values():
    """Each --lv-* variable that the panel (static/level_editor.html) uses is defined, and no definition is the variable itself (a loop
    has no value: the segment buttons lost their background so, 2026-10-24)."""
    import re

    text = (STATIC / "level_editor.html").read_text()
    defined = dict(re.findall(r"--(lv-[a-z0-9-]+):([^;}]*)", text))
    used = set(re.findall(r"var\(--(lv-[a-z0-9-]+)\)", text))      # with no fallback (var(--lv-kb,0px): the module sets it)
    assert used <= set(defined), used - set(defined)
    assert not [k for k, v in re.findall(r"--(lv-[a-z0-9-]+):([^;}]*)", text) if f"var(--{k})" in v]


@needs_pkg
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


PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<script src="/vendor/maplibre-gl.js"></script><link rel="stylesheet" href="/vendor/maplibre-gl.css">
<link rel="stylesheet" href="/dashboard/dashboard.css"><link rel="stylesheet" href="/popup.css">
<style>html,body{margin:0;height:100%}#map{position:absolute;inset:0}</style></head><body><div id="map"></div><div id="panel"></div>
<script>
// the document's listeners by type (the test's count: a listener left after destroy, or one more after each open, shows here)
window.listening = {};
const _on = document.addEventListener, _off = document.removeEventListener;
document.addEventListener = function(t, ...a){ listening[t] = (listening[t] || 0) + 1; return _on.call(this, t, ...a); };
document.removeEventListener = function(t, ...a){ listening[t] = (listening[t] || 0) - 1; return _off.call(this, t, ...a); };
</script>
<script type="module">
import init, * as pkg from "/level_editor/pkg/roadstyle_wasm.js";
import {levelEditor, browserStore} from "/dashboard/editor/level_editor.js";
import {rsDashboard} from "/dashboard/index.js";
await init();
// the host's part: the area made in the page and kept in the browser, and the host's own map
const a = pkg.makeArea(new Uint8Array(await (await fetch("/edges.parquet")).arrayBuffer()), JSON.stringify({id_col: "edge_id"}));
const store = browserStore("test-area", "Monaco test");
window.stored = async n => (await store.load(n))?.body ?? null;     // a text file of the store
window.writeAgain = async () => { for(const [n, v] of [["roads.parquet", a.roads], ["pairs.csv", a.pairs]]) await store.save(n, v); };  // as a page on each open
for(const [n, v] of [["roads.parquet", a.roads], ["pairs.csv", a.pairs], ["edits.csv", a.edits]]) await store.save(n, v);
const map = new maplibregl.Map({container: "map", style: {version: 8, glyphs: "/fonts/{fontstack}/{range}.pbf", sources: {}, layers: []},
  center: [7.42, 43.73], zoom: 15});
// the host's own page, as duckosm-rust's has it: a base map layer and its roads style, both with its prefix, and its one dashboard
await map.once("load");
map.addSource("host-water", {type: "geojson", data: {type: "Feature", properties: {}, geometry: {type: "Polygon",
  coordinates: [[[7.41, 43.72], [7.43, 43.72], [7.43, 43.74], [7.41, 43.74], [7.41, 43.72]]]}}});
map.addLayer({id: "host-water", type: "fill", source: "host-water", paint: {"fill-color": "#aad3df"}});
// its roads as vector tiles, in one tile source with its base map (duckosm-rust's page: the base map's layers are other source
// layers of the roads' source)
const edges = new Uint8Array(await (await fetch("/edges.parquet")).arrayBuffer());
const hostTiles = pkg.tileSources(pkg.makeSources(edges, pkg.resolveLook(JSON.stringify({args: {state: "live"}})), undefined, undefined, "host"),
  "hostt://", ["edge_id", "name", "highway"]);
maplibregl.addProtocol("hostt", async (q) => { const [source, z, x, y] = q.url.slice("hostt://".length).split("/");
  return {data: hostTiles.tile(source, +z, +x, +y)}; });
const own = JSON.parse(hostTiles.style());
for(const [k, v] of Object.entries(own.state || {})) map.setGlobalStateProperty(k, v.default ?? null);     // a live style's state
for(const [id, im] of Object.entries(own.metadata["roadstyle:images"] || {}))
  map.addImage("host-" + id, (await map.loadImage(im.url)).data, {sdf: im.sdf, pixelRatio: im.pixelRatio});
for(const [id, src] of Object.entries(own.sources)) map.addSource("host-" + id, src);
for(const l of own.layers) map.addLayer({...JSON.parse(JSON.stringify(l).replaceAll('"oneway"', '"host-oneway"')), id: "host-" + l.id, source: "host-" + l.source});
map.addLayer({id: "host-land", type: "fill", source: "host-roads", "source-layer": "landuse", paint: {"fill-color": "#eeeeee"}});
window.hostRoads = own.layers.map(l => "host-" + l.id);
const host = rsDashboard(map, {style: own, prefix: "host-", basemap_switcher: false});
window.host = host;
const panel = document.getElementById("panel");
if(location.search === "?no-dashboard"){                         // the host's dashboard not given: an error, no second dashboard
  try { await levelEditor({map, container: panel, pkgUrl: "/level_editor/pkg/roadstyle_wasm.js", store}); window.ready = "made a second dashboard"; }
  catch(e){ window.ready = e.message; }
  throw new Error("stop");
}
window.hostMap = map;
window.hostSources = Object.fromEntries(map.getStyle().layers.filter(l => l.id.startsWith("host-")).map(l => [l.id, l.source]));
window.counts = () => JSON.stringify(Object.fromEntries(Object.entries(listening).filter(e => e[1])));
window.before = counts();
window.solved = [];
window.openEditor = async () => {
  const ed = await levelEditor({map, container: panel, pkgUrl: "/level_editor/pkg/roadstyle_wasm.js", store, dashboard: host, prefix: "host-"});
  ed.addEventListener("solved", async e => window.solved.push({rows: e.detail.levelsCsv.trim().split("\\n").length - 1, draw: (await e.detail.draw()).length}));
  window.editor = ed;
};
await window.openEditor();
window.ready = a.roadCount;
</script></body></html>"""


class _Files(SimpleHTTPRequestHandler):
    """The static folder, the vendored MapLibre at /vendor/, the editor's package at /level_editor/pkg/, the test page and the edges."""

    def translate_path(self, path):
        if path.startswith("/vendor/"):
            return str(ASSETS / path.lstrip("/"))
        if path.startswith("/level_editor/pkg/"):
            return str(PKG.parent / path.removeprefix("/level_editor/pkg/"))
        if path == "/edges.parquet":
            return str(EDGES)
        return super().translate_path(path)

    def do_GET(self):
        if self.path.split("?")[0] == "/test.html":
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


@needs_pkg
def test_the_editor_module_edits_an_area_kept_in_the_browser_with_the_hosts_dashboard():
    pw = pytest.importorskip("playwright.sync_api")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Files, directory=str(STATIC)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": 1300, "height": 850})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            base = f"http://127.0.0.1:{server.server_address[1]}/test.html"
            page.goto(base + "?no-dashboard")
            page.wait_for_function("window.ready", timeout=60000)
            assert page.evaluate("window.ready").startswith("level editor: this page has a dashboard"), page.evaluate("window.ready")
            page.goto(base)
            page.wait_for_function("window.ready", timeout=60000)
            errors.clear()
            roads = page.evaluate("window.ready")
            assert page.evaluate("window.rs === window.host"), "the editor uses the host's dashboard, not a second one"
            assert page.evaluate("hostMap.getStyle().layers.some(l => l.id.startsWith('host-roads'))"), "the editor's roads with the host's prefix"
            assert page.evaluate("!!hostMap.getLayer('host-water') && !!hostMap.getLayer('host-land')"), "the host's base map stays"
            assert page.evaluate("!!hostMap.getSource('host-roads') && !!hostMap.getSource('host-lv-roads')"), "the host's source and the editor's"
            # the host's own roads went (the layers of the roles of its style's roadstyle:sources): every road layer is the editor's
            assert page.evaluate("hostMap.getStyle().layers.filter(l => l.id.startsWith('host-roads')).every(l => l.source === 'host-lv-roads')")
            stored = page.evaluate("stored('levels.csv')")
            assert stored and len(stored.strip().split("\n")) > roads, "the first solve saved levels.csv in the browser"
            assert page.locator("#lv").count() == 1, "the panel is in the host's container"
            # the lean road table: only the fields that the page reads (reads.json's table), live data's id and the road that a click picks
            want = set(json.loads((STATIC / "dashboard" / "reads.json").read_text())["table"]) | {"edge", "road"}
            got = page.evaluate("[...new Set(window.RS_SIDE.props.flatMap(Object.keys))]")
            assert "road" in got and set(got) <= want, set(got) - want
            # the first open solved the whole area; levels_info.json keeps the key of its inputs (roadstyle-levels' inputs_key: the SHA-256
            # of roads.parquet, pairs.csv and edits.csv), which are the folder form's bytes
            assert page.evaluate("window.editor.answer().resolve.how") == "full"
            import pyarrow.parquet as pq

            from roadstyle import _engine
            folder = Path(tempfile.mkdtemp())
            _engine.rust().make_area(pq.read_table(EDGES), str(folder))
            key = ":".join(hashlib.sha256((folder / f).read_bytes()).hexdigest() for f in ("roads.parquet", "pairs.csv", "edits.csv"))
            assert json.loads(page.evaluate("stored('levels_info.json')"))["inputs"] == key
            # a head's length through the panel's API: drawing only, so no solve (level_editor.py's change); the host hears it, the store has
            # heads.csv
            road = page.evaluate("window.editor.roads[0].road")
            # the engine is in the worker: the page has no LevelArea of its own
            assert page.evaluate("!!window.editor && !('area' in window.editor)")
            said = page.evaluate("r => window.lvApi('/api/apply', {ops: [{op: 'head', road: r, end: 'end', m: '7'}]})", road)
            assert said["ok"] and said["redrawn"] and said["said"] == "not solved again (heads and caps are drawing only)", said
            page.wait_for_function("window.solved.length === 1", timeout=30000)
            solved = page.evaluate("window.solved")
            assert len(solved) == 1 and solved[0]["rows"] > roads and solved[0]["draw"] > 0, solved
            assert road in page.evaluate("stored('heads.csv')")
            assert page.evaluate("window.editor.files") == ["edits.csv", "heads.csv", "caps.csv", "levels.csv"]
            # close, open again, close: the same listeners each time, none left; the host's roads, base map and dashboard back
            opened = page.evaluate("counts()")
            back = "JSON.stringify(Object.fromEntries(hostMap.getStyle().layers.filter(l => l.id.startsWith('host-')).map(l => [l.id, l.source])))"
            for _ in range(2):
                page.evaluate("window.editor.destroy()")
                assert page.evaluate("counts()") == page.evaluate("window.before"), "no listener of the editor left"
                assert page.evaluate(back) == page.evaluate("JSON.stringify(window.hostSources)"), "the host's layers as they were"
                assert page.evaluate("!document.getElementById('lv') && !hostMap.getLayer('lv-ends') && !hostMap.getSource('host-lv-roads')")
                assert page.evaluate("window.rs === window.host && !window.lvApi && !document.body.classList.contains('lv-open')")
                page.evaluate("writeAgain()")                  # the same area written again (newer files): the stored levels still hold
                page.evaluate("window.openEditor()")
                page.wait_for_function("!!document.getElementById('lv') && !!window.lvApi", timeout=60000)
                assert page.evaluate("counts()") == opened, "one listener of each kind after each open"
                assert page.evaluate("window.editor.answer().resolve.how") == "stored", "no solve on an open with the same inputs"
            # a worker that stops (here: its script throws as it loads) rejects the waiting call (worker/call.js), not a call that never settles
            said = page.evaluate("""async () => { const {caller} = await import('/dashboard/worker/call.js');
              const w = new Worker(URL.createObjectURL(new Blob(['throw new Error("boom")'], {type: 'text/javascript'})), {type: 'module'});
              try { await caller(w)({type: 'x'}); return 'settled'; } catch(e){ return e.message; } }""")
            assert said.startswith("the worker stopped"), said
            # browserStore keeps the texts in the private file system: a pairs.csv over localStorage's 5 MB (Burnaby's), and a text that
            # an older version kept in localStorage moves there once
            said = page.evaluate("""async () => { const {browserStore} = await import('/dashboard/editor/level_editor.js');
              const s = browserStore('big-area'), big = 'relation,a,b,a_end,b_end,enabled\\n' + 'cross,1,2,start,end,1\\n'.repeat(300000);
              await s.save('pairs.csv', big);
              localStorage.setItem('lv:big-area:edits.csv', 'old edits');
              const edits = (await s.load('edits.csv')).body;
              return [big.length, (await s.load('pairs.csv')).body === big, edits, localStorage.getItem('lv:big-area:edits.csv'),
                      (await s.load('edits.csv')).body, await s.load('caps.csv')]; }""")
            assert said[0] > 5_500_000 and said[1:] == [True, "old edits", None, "old edits", None], said
            # the panel follows the page's theme: the system's dark, unless the page sets data-theme on <html>
            bg = "getComputedStyle(document.querySelector('#lv header')).backgroundColor"
            assert page.evaluate(bg) == "rgb(255, 255, 255)"
            page.emulate_media(color_scheme="dark")
            assert page.evaluate(bg) == "rgb(36, 42, 52)"
            page.evaluate("document.documentElement.dataset.theme = 'light'")
            assert page.evaluate(bg) == "rgb(255, 255, 255)"
            assert not [e for e in errors if e != "boom"], errors      # "boom": the stopped worker's own error, which the page reports too
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


@needs_pkg
def test_the_editor_on_a_phone(tmp_path):
    """The editor on a phone (390 x 844, device scale 3, touch): the panel is a sheet at the bottom (layout "auto" up to 700 px wide), a tap
    on a road picks it (the wide tap line), a head's change is solved, the handle folds and opens the sheet, and a dashboard window at the
    bottom (Street View, Google 3D) folds it."""
    pw = pytest.importorskip("playwright.sync_api")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Files, directory=str(STATIC)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch()
            ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True)
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/test.html")
            page.wait_for_function("window.ready && !!document.getElementById('lv')", timeout=60000)
            assert page.evaluate("document.body.classList.contains('lv-sheet') && document.body.dataset.lvSheet") == "half"
            top = page.evaluate("document.getElementById('lv').getBoundingClientRect().top")
            assert 380 < top < 470, top                                           # half the height: the map keeps the top
            page.wait_for_timeout(1500)                                           # the tiles of the editor's roads
            # a road under the map's free part, and a tap on it
            xy = page.evaluate(f"""() => {{ const m = window.hostMap;
              for(const f of m.queryRenderedFeatures({{layers: ['host-lv-tap']}})){{
                const c = f.geometry.coordinates, pt = m.project(c[Math.floor(c.length / 2)]);
                if(pt.x > 40 && pt.x < 350 && pt.y > 120 && pt.y < {top} - 40) return [pt.x, pt.y, f.properties.road]; }} return null; }}""")
            assert xy, "a road above the sheet"
            page.touchscreen.tap(xy[0], xy[1])
            page.wait_for_function("document.querySelectorAll('#lv-cards [data-hroad]').length > 0", timeout=20000)
            # an end: the start head to 3 m by its slider (applied when the slider is let go)
            page.evaluate("""() => { const i = document.querySelector('#lv-cards input[data-hend=start]'); i.value = '3';
              i.dispatchEvent(new Event('input', {bubbles: true})); i.dispatchEvent(new Event('change', {bubbles: true})); }""")
            # a head is drawing only: saved at once, with no solve and not in the list (no Apply)
            page.wait_for_function("document.getElementById('lv-toast').textContent.startsWith('Heads saved')", timeout=60000)
            assert "not solved again" in page.inner_text("#lv-toast") and page.evaluate("document.getElementById('lv-queue-sec').hidden")
            # 44 px targets
            for sel in ("#lv .tabs button", "#lv-cards .seg button", "#lv .find input"):
                assert page.evaluate(f"document.querySelector('{sel}').getBoundingClientRect().height") >= 44, sel
            page.screenshot(path=str(tmp_path / "phone.png"))
            # the handle: half -> full -> fold -> half
            for want in ("full", "fold", "half"):
                page.locator("#lv-handle").tap()
                assert page.evaluate("document.body.dataset.lvSheet") == want
            page.wait_for_timeout(300)
            assert page.evaluate("document.getElementById('lv').getBoundingClientRect().top") == pytest.approx(top, abs=2)
            # a dashboard window at the bottom: the sheet folds
            page.evaluate("const w = document.createElement('div'); w.className = 'rs-svw'; document.body.appendChild(w);")
            page.wait_for_function("document.body.dataset.lvSheet === 'fold'", timeout=5000)
            assert not errors, errors
            b.close()
    finally:
        server.shutdown()
