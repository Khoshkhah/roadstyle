"""The level editor in a page with no server (docs/rust/browser.md, "The level editor in a page"): roadstyle-wasm's makeArea gives the
files of the folder form, and the module dashboard/editor/level_editor.js edits an area kept in the browser (browserStore) on the host's
map. They need the editor's wasm package (rust/roadstyle-wasm/build_editor.sh), Node for the first and Chromium (playwright) for the
second: skipped without them (CI builds no package)."""
import hashlib
import json
import os
import re
import shutil
import struct
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
<style>html,body{margin:0;height:100%}#map{position:fixed;inset:0}</style></head><body><div id="map"></div>
<div id="sb" data-theme="light"><div class="sb-card"><div class="sb-top"><h2>Host steps</h2><button id="sb-hide" title="Hide the panel">x</button></div>
<div class="sb-body" style="display:flex;flex-direction:column">The host's steps</div></div></div>
<script>
// the document's listeners by type (the test's count: a listener left after destroy, or one more after each open, shows here)
window.listening = {};
// the editor's worker (made inside levelEditor): the test stops it
const _Worker = window.Worker;
window.Worker = class extends _Worker { constructor(u, o){ super(u, o); if(String(u).includes("level_worker")) window.lvWorker = this; } };
const _on = document.addEventListener, _off = document.removeEventListener;
document.addEventListener = function(t, ...a){ listening[t] = (listening[t] || 0) + 1; return _on.call(this, t, ...a); };
document.removeEventListener = function(t, ...a){ listening[t] = (listening[t] || 0) - 1; return _off.call(this, t, ...a); };
</script>
<script type="module">
import init, * as pkg from "/level_editor/pkg/roadstyle_wasm.js";
import {levelEditor, browserStore, saveArea, areaIsFor, ensureArea} from "/dashboard/editor/level_editor.js";
window.browserStoreFn = browserStore;                               // for the test of the store alone
window.ensureAreaFn = ensureArea;
import {rsDashboard} from "/dashboard/index.js";
import {rsFirstPaint} from "/dashboard/template.js";
await init();
// the host's panel is the standard dashboard's (data/host_options.json: the classes of <html>, the sheet of a phone, the toolbar)
const opts = await (await fetch("/data/host_options.json")).json();
opts.dashboard.panel.hide = [];
rsFirstPaint(opts.first_paint);
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
// (?basemap: the page's look has a colour option, "Road class", so the legend box has its "Colour by" list)
const hostLook = pkg.resolveLook(JSON.stringify({args: {state: "live", ...(location.search === "?basemap" ? {color_options: {"Road class": {}}} : {})}}));
const hostSources = pkg.styleSources(edges, hostLook, undefined, undefined, "host");
window.hostTable = () => JSON.parse(new TextDecoder().decode(hostSources.roadTable()));   // the host's road table (its RS_SIDE)
const hostSide = window.hostTable();
const hostTiles = pkg.tilesOfSources(hostSources, "hostt://", ["edge_id", "name", "highway"]);
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
// the base map's layer (the water) is an overlay of the host's style: the dashboard's switch for it, and its entry in the legend box
own.metadata["roadstyle:controls"] = {...(own.metadata["roadstyle:controls"] || {}), overlays: [{label: "Water", source: "water", layers: ["water"], color: "#aad3df",
  visible: true, interactive: false, popup: [], tooltip: null, under: true, base: null, select: "road"}]};
// ?basemap: the standard Base map box too (the page's base maps), and the editor is opened by the test, after the box has been read
const withBase = location.search === "?basemap";
const host = rsDashboard(map, {style: own, prefix: "host-", basemap_switcher: withBase, ...(withBase ? {basemaps: opts.basemaps, ontop: opts.ontop} : {}), dashboard: opts.dashboard});
window.host = host;
const panel = document.getElementById("sb");
if(location.search === "?no-dashboard"){                         // the host's dashboard not given: an error, no second dashboard
  try { await levelEditor({map, panel, pkgUrl: "/level_editor/pkg/roadstyle_wasm.js", store}); window.ready = "made a second dashboard"; }
  catch(e){ window.ready = e.message; }
  throw new Error("stop");
}
window.hostMap = map;
// a store of its own with the area (saveArea) and the editor started on it with the map's levels (the option `levels`), as duckosm-rust's
// page does it
window.openWith = async (key, levels, edgeHash) => {
  const s = browserStore(key, "Monaco test");
  if(!(await areaIsFor(s, edgeHash))) await saveArea(s, a, edgeHash);
  window.editor = await levelEditor({map, panel, pkgUrl: "/level_editor/pkg/roadstyle_wasm.js", store: s, dashboard: host, prefix: "host-", levels});
  return [window.editor.answer().resolve, await areaIsFor(s, edgeHash), await areaIsFor(browserStore("other-" + key), edgeHash)];
};
// the option `area` (ensureArea inside the editor): a store, the host's edges() and the edge hash
window.openArea = async (store, area) => {
  window.editor = await levelEditor({map, panel, pkgUrl: "/level_editor/pkg/roadstyle_wasm.js", store, dashboard: host, prefix: "host-", area});
  return window.editor.areaInfo;
};
window.edgesBytes = edges;
window.hostSources = Object.fromEntries(map.getStyle().layers.filter(l => l.id.startsWith("host-")).map(l => [l.id, l.source]));
window.counts = () => JSON.stringify(Object.fromEntries(Object.entries(listening).filter(e => e[1])));
window.before = counts();
window.solved = [];
window.backs = 0;
// ?dark: the page is in the dark theme before the editor opens; ?carto: the page's own look (another palette) is given to the editor
window.lookText = location.search === "?carto" ? pkg.resolveLook(JSON.stringify({palette: "carto", args: {state: "live"}})).toJson() : location.search === "?basemap" ? hostLook.toJson() : null;
if(location.search === "?dark") window.rsSetTheme("dark");
window.openEditor = async () => { const t = performance.now();
  const ed = await levelEditor({map, panel, pkgUrl: "/level_editor/pkg/roadstyle_wasm.js", store, dashboard: host, prefix: "host-", look: window.lookText});
  ed.addEventListener("back", () => window.backs++);
  ed.addEventListener("solved", async e => window.solved.push({rows: e.detail.levelsCsv.trim().split("\\n").length - 1, draw: (await e.detail.draw()).length}));
  window.editor = ed; return performance.now() - t;
};
// the option host: the editor on the host's roads and road table; replaceRoads keeps the rows that it gets
window.replaced = [];
window.hostLookText = hostLook.toJson();
window.workerCalls = [];                                         // the types of the messages to any worker (the editor's worker is made inside levelEditor)
const post = Worker.prototype.postMessage;
Worker.prototype.postMessage = function(m, ...r){ if(m && typeof m.type === "string"){ window.workerCalls.push(m.type); } return post.call(this, m, ...r); };
window.openHosted = async (levels) => {
  window.RS_SIDE = hostSide;
  window.workerCalls.length = 0;
  const t = performance.now();
  window.editor = await levelEditor({map, panel, pkgUrl: "/level_editor/pkg/roadstyle_wasm.js", store, dashboard: host, prefix: "host-",
    host: {replaceRoads: async rows => { window.replaced.push(rows); }}, look: window.hostLookText, levels});
  return performance.now() - t;
};
if(!withBase) await window.openEditor();
window.ready = a.roadCount;
</script></body></html>"""


class _Files(SimpleHTTPRequestHandler):
    """The static folder, the vendored MapLibre at /vendor/, the editor's package at /level_editor/pkg/, the test page and the edges."""

    def translate_path(self, path):
        if path.startswith("/vendor/"):
            return str(ASSETS / path.lstrip("/"))
        if path.startswith("/level_editor/pkg/"):
            return str(PKG.parent / path.removeprefix("/level_editor/pkg/"))
        if path.startswith("/data/"):
            return str(ASSETS / path.lstrip("/"))
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
def test_browser_store_keeps_a_file_in_memory_when_the_browser_cannot_and_tells_how_much():
    """`memoryFallback: true`: with no private file system, save keeps the file in memory (a warning in the console), load gives it as a text or as
    bytes, and lostBytes() is its size. Without the option, save is an error. A store that works has lostBytes() 0."""
    pw = pytest.importorskip("playwright.sync_api")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Files, directory=str(STATIC)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page()
            warnings = []
            page.on("console", lambda m: warnings.append(m.text) if m.type == "warning" else None)
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/test.html?no-dashboard")
            page.wait_for_function("window.ready", timeout=60000)
            got = page.evaluate("""async () => {
              const out = {};
              const ok = window.browserStoreFn("fb-ok", "ok", {memoryFallback: true});
              await ok.save("a.csv", "x,y\\n1,2\\n");
              out.ok = [(await ok.load("a.csv")).body, ok.lostBytes()];
              Object.defineProperty(navigator.storage, "getDirectory", {value: () => { throw new Error("no private file system"); }, configurable: true});
              const plain = window.browserStoreFn("fb-plain");
              try { await plain.save("a.csv", "1"); out.plain = "saved"; } catch(e){ out.plain = e.message; }
              const s = window.browserStoreFn("fb-mem", "mem", {memoryFallback: true});
              out.missing = await s.load("none.csv");
              await s.save("pairs.csv", "a,b\\n1,2\\n");
              out.text = (await s.load("pairs.csv")).body;
              out.bytes = Array.from((await s.load("pairs.csv", true)).body);
              out.lost = s.lostBytes();
              await s.save("pairs.csv", "a,b\\n1,2\\n3,4\\n");          // the same file again: the newest text, the size of the newest
              out.again = [(await s.load("pairs.csv")).body, s.lostBytes()];
              await s.save("roads.parquet", new Uint8Array([1, 2, 3]));
              out.parquet = [Array.from((await s.load("roads.parquet", true)).body), s.lostBytes()];
              return out;
            }""")
            assert got["ok"] == ["x,y\n1,2\n", 0]
            assert "no private file system" in got["plain"], got["plain"]
            assert got["missing"] is None
            assert got["text"] == "a,b\n1,2\n" and got["bytes"] == list(b"a,b\n1,2\n") and got["lost"] == 8
            assert got["again"] == ["a,b\n1,2\n3,4\n", 12]
            assert got["parquet"] == [[1, 2, 3], 15]
            assert any("pairs.csv is not kept in the browser" in w for w in warnings), warnings
            b.close()
    finally:
        server.shutdown()


@needs_pkg
def test_ensure_area_makes_the_area_once_for_an_edge_hash_and_the_editor_makes_it_again_after_a_loss():
    pw = pytest.importorskip("playwright.sync_api")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Files, directory=str(STATIC)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": 1300, "height": 850})
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/test.html?basemap")       # ?basemap: the test opens the editor
            page.wait_for_function("window.ready", timeout=60000)
            got = page.evaluate("""async () => {
              const out = {}, store = window.browserStoreFn("ea-1", "ea"), pkgUrl = "/level_editor/pkg/roadstyle_wasm.js";
              let calls = 0;
              const edges = async () => { calls++; return window.edgesBytes; };
              const a = await window.ensureAreaFn({store, edgeHash: "h1", edges, pkgUrl, prepare: false});
              out.first = [a.made, a.roadCount > 100, a.pairCount > 0, Array.isArray(a.warnings), calls];
              const b = await window.ensureAreaFn({store, edgeHash: "h1", edges, pkgUrl, prepare: false});
              out.same = [b.made, calls];                                      // the same hash: not made again, edges() not called
              const c = await window.ensureAreaFn({store, edgeHash: "h2", edges, pkgUrl, prepare: false});
              out.other = [c.made, calls];
              const d = await window.ensureAreaFn({store, edgeHash: "h2", edges, pkgUrl, prepare: false, force: true});
              out.force = [d.made, calls];
              try { await window.ensureAreaFn({store, edgeHash: "h3", pkgUrl}); } catch(e){ out.noEdges = e.message; }
              // the editor makes the area itself, and again once when the store lost its files after it was made
              const s2 = window.browserStoreFn("ea-2", "ea2");
              calls = 0;
              const info = await window.openArea(s2, {edges, edgeHash: "h9"});
              out.open = [info.made, calls, window.editor.roads.length > 100];
              window.editor.destroy();
              const real = s2.load;
              let lost = true;                                                  // the files are gone: the first loads of the area's roads and pairs give null
              s2.load = async (n, bytes) => (lost && (n === "roads.parquet" || n === "pairs.csv")) ? null : real(n, bytes);
              const save = s2.save;
              s2.save = async (n, d) => { if(n === "roads.parquet") lost = false; return save(n, d); };
              const again = await window.openArea(s2, {edges, edgeHash: "h9"});
              out.retry = [again.made, calls, window.editor.roads.length > 100];
              return out;
            }""")
            assert got["first"] == [True, True, True, True, 1], got
            assert got["same"] == [False, 1] and got["other"] == [True, 2] and got["force"] == [True, 3], got
            assert "give edges()" in got["noEdges"], got
            assert got["open"] == [True, 1, True], got
            assert got["retry"] == [True, 2, True], got
            b.close()
    finally:
        server.shutdown()


@needs_pkg
def test_the_editor_sends_an_error_event_when_its_worker_stops_and_not_after_destroy():
    pw = pytest.importorskip("playwright.sync_api")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Files, directory=str(STATIC)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": 1300, "height": 850})
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/test.html")
            page.wait_for_function("window.ready", timeout=60000)
            page.evaluate("window.errs = []; window.editor.addEventListener('error', e => window.errs.push(e.detail))")
            # the worker stops (an error event on the Worker object, as the browser sends it when the script fails): the editor tells the host
            page.evaluate("window.lvWorker.dispatchEvent(new ErrorEvent('error', {message: 'out of memory'}))")
            assert page.evaluate("window.errs") == [{"message": "the worker stopped: out of memory", "fatal": True}]
            # a destroyed editor is not heard any more
            page.evaluate("window.editor.destroy()")
            page.evaluate("window.lvWorker.dispatchEvent(new ErrorEvent('error', {message: 'again'}))")
            assert len(page.evaluate("window.errs")) == 1
            b.close()
    finally:
        server.shutdown()


@needs_pkg
def test_the_open_takes_off_the_pages_selection_and_popups():
    """A road that the page selected and its popup are not the editor's: the editor calls rsDeselect and removes the popups when it opens."""
    pw = pytest.importorskip("playwright.sync_api")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Files, directory=str(STATIC)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": 1300, "height": 850})
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/test.html?basemap")       # ?basemap: the test opens the editor
            page.wait_for_function("window.ready", timeout=60000)
            page.evaluate("""() => { window.deselected = 0; const o = window.rsDeselect; window.rsDeselect = (...a) => { window.deselected++; return o && o(...a); };
              new maplibregl.Popup().setLngLat([7.42, 43.73]).setHTML("a road").addTo(window.hostMap); }""")
            assert page.evaluate("document.querySelectorAll('.maplibregl-popup').length") == 1
            page.evaluate("window.openEditor()")
            page.wait_for_function("window.editor", timeout=60000)
            assert page.evaluate("document.querySelectorAll('.maplibregl-popup').length") == 0
            assert page.evaluate("window.deselected") >= 1
            b.close()
    finally:
        server.shutdown()


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
            assert page.locator("#lv").count() == 1 and page.locator("#sb .sb-card #lv").count() == 1, "the editor is in the host's panel"
            assert page.evaluate("document.querySelector('#sb .sb-body').style.display") == "none", "the host's body is kept, hidden"
            assert page.locator("#sb .sb-top #lv-back").inner_text() == "← Steps" and page.locator("#sb .sb-top .rs-frame-title .t").inner_text() == "Edit levels"
            assert page.locator("#sb-hide").is_visible(), "the host's hide button stays"
            # the lean road table: only the fields that the page reads (reads.json's table), live data's id, the road that a click picks
            # and the two ends of a road for the marks ● start and ■ end
            want = set(json.loads((STATIC / "dashboard" / "reads.json").read_text())["table"]) | {"edge", "road", "modes", "s_lon", "s_lat", "e_lon", "e_lat"}
            got = page.evaluate("[...new Set(window.RS_SIDE.props.flatMap(Object.keys))]")
            assert "road" in got and set(got) <= want, set(got) - want
            # the first open solved the whole area; levels_info.json keeps the key of its inputs (roadstyle-levels' inputs_key: the SHA-256
            # of roads.parquet, pairs.csv and edits.csv), which are the folder form's bytes
            assert page.evaluate("window.editor.answer().resolve.how") == "full"
            assert page.evaluate("window.editor.dirty") is False, "no Apply yet"
            import pyarrow.parquet as pq

            from roadstyle import _engine
            folder = Path(tempfile.mkdtemp())
            _engine.rust().make_area(pq.read_table(EDGES), str(folder))
            key = ":".join(hashlib.sha256((folder / f).read_bytes()).hexdigest() for f in ("roads.parquet", "pairs.csv", "edits.csv"))
            assert json.loads(page.evaluate("stored('levels_info.json')"))["inputs"] == key
            # a head's length through the panel's API: drawing only, so no solve (level_editor.py's change); the host hears it, the store has
            # heads.csv
            road = page.evaluate("window.editor.roads[0]")
            # the engine is in the worker: the page has no LevelArea of its own
            assert page.evaluate("!!window.editor && !('area' in window.editor)")
            said = page.evaluate("r => window.lvApi('/api/apply', {ops: [{op: 'head', road: r, end: 'end', m: '7'}]})", road)
            assert said["ok"] and said["redrawn"] and said["said"] == "not solved again (heads and caps are drawing only)", said
            # the editor's own map is built once (at open); a change redraws only the changed edges (relevel), it builds no new generation of all tiles
            calls = page.evaluate("window.workerCalls")
            assert calls.count("build") == 1 and calls.count("relevel") == 1, calls
            assert said["facts"][road]["heads_own"] == [False, True] and said["facts"][road]["levels"], said["facts"]
            # the panel's other questions: the page asks the worker for the roads that they name (2026-10-26)
            f = said["facts"][road]
            edge = f["directions"][0]["edge"]
            assert page.evaluate("q => window.lvApi('/api/find?q=' + q)", edge)[0]["road"] == road
            ref = page.evaluate("window.editor.facts(window.editor.roads).then(fs => Object.values(fs).map(f => f.edge_ref).find(Boolean))")
            hits = page.evaluate("q => window.lvApi('/api/find?q=' + encodeURIComponent(q))", ref.upper())
            assert hits and all("levels" in h for h in hits) and any(h["edge_ref"] == ref for h in hits), (ref, hits)
            rel = page.evaluate("r => window.lvApi('/api/relations?a=' + r)", edge)
            assert rel["a"] == road and road in rel["roads"] and all(r["ra"] == road or r["rb"] == road for r in rel["rows"]), rel
            gu = page.evaluate("window.lvApi('/api/given_up')")
            assert all(k in gu["roads"] for r in gu["rows"] for k in (r["a"], r["b"])), gu
            page.wait_for_function("window.solved.length === 1", timeout=30000)
            solved = page.evaluate("window.solved")
            assert len(solved) == 1 and solved[0]["rows"] > roads and solved[0]["draw"] > 0, solved
            assert road in page.evaluate("stored('heads.csv')")
            assert page.evaluate("window.editor.files") == ["edits.csv", "heads.csv", "caps.csv", "levels.csv"]
            # the help window (rs.help of the host's dashboard): the editor's words with the "<- Steps" line, and the ? button next to its title
            assert page.evaluate("window.host.help.get().title") == "Edit levels"
            assert page.evaluate("window.host.help.get().terms.some((t) => t[0] === '\u2190 Steps')")
            assert page.evaluate("!!document.querySelector('.rs-frame-title #rs-help-btn')")
            # close, open again, close: the same listeners each time, none left; the host's roads, base map and dashboard back
            opened = page.evaluate("counts()")
            back = "JSON.stringify(Object.fromEntries(hostMap.getStyle().layers.filter(l => l.id.startsWith('host-')).map(l => [l.id, l.source])))"
            for _ in range(2):
                page.evaluate("window.editor.destroy()")
                assert page.evaluate("counts()") == page.evaluate("window.before"), "no listener of the editor left"
                assert page.evaluate("window.host.help.get() === null && !document.getElementById('rs-help-btn') && !document.getElementById('rs-help')"), "the help went"
                assert page.evaluate(back) == page.evaluate("JSON.stringify(window.hostSources)"), "the host's layers as they were"
                assert page.evaluate("!document.getElementById('lv') && !hostMap.getLayer('lv-ends') && !hostMap.getSource('host-lv-roads')")
                assert page.evaluate("window.rs === window.host && !window.lvApi && !document.querySelector('.rs-frame-title')")
                assert page.evaluate("document.querySelector('#sb .sb-body').style.display") == "flex", "the host's body as it was"
                assert page.evaluate("getComputedStyle(document.querySelector('#sb .sb-top h2')).display") != "none", "the host's title as it was"
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
            # the panel follows the host panel's theme (#sb[data-theme], the standard tokens)
            ink = "getComputedStyle(document.querySelector('#lv')).color"
            assert page.evaluate(ink) == "rgb(22, 24, 29)"
            page.evaluate("document.getElementById('sb').dataset.theme = 'dark'")
            assert page.evaluate(ink) == "rgb(233, 236, 241)"
            page.evaluate("document.getElementById('sb').dataset.theme = 'light'")
            # the map's levels (the option `levels`): with the area's edge_hash (roadstyle_levels::edge_hash: sha256 of the sorted ids, 8 bytes
            # little endian, 32 hex characters), the editor starts from them with no solve; with another one it solves and says why
            ids = sorted(int(x) for x in pq.read_table(EDGES, columns=["edge_id"]).column(0).to_pylist())
            hsh = hashlib.sha256(b"".join(struct.pack("<q", i) for i in ids)).hexdigest()[:32]
            levels_csv = page.evaluate("stored('levels.csv')")
            page.evaluate("window.editor.destroy()")
            got = page.evaluate("([csv, h]) => openWith('given-area', {csv, edge_hash: h}, h)", [levels_csv, hsh])
            assert got[0]["how"] == "given" and got[1] is True and got[2] is False, got
            page.evaluate("window.editor.destroy()")
            got = page.evaluate("([csv, h]) => openWith('other-hash', {csv, edge_hash: '0' + h.slice(1)}, h)", [levels_csv, hsh])
            assert got[0]["how"] == "full" and "other edges" in got[0]["why"], got
            # the option host: no map of the editor's own (no source, no protocol, the host's layers as they are); the host's road table
            # gets each edge's road; an apply gives replaceRoads only the rows of the edges that changed; destroy takes the fields off
            page.evaluate("window.editor.destroy()")
            ms = page.evaluate("openHosted()")
            page.evaluate("window.editor.destroy()")
            old = page.evaluate("window.openEditor()")
            page.evaluate("window.editor.destroy()")
            ms = page.evaluate("openHosted()")
            print(f"own map open: {old:.0f} ms")
            assert page.evaluate(back) == page.evaluate("JSON.stringify(window.hostSources)"), "the host's layers as they were"
            assert page.evaluate("!hostMap.getSource('host-lv-roads') && window.RS_SIDE.props.every(p => p.road != null)")
            assert page.evaluate("window.editor.answer().resolve.how") == "stored"
            # the open on the host's roads builds no map: its worker is not asked to draw, style or cut anything (the guard of the fast open)
            calls = page.evaluate("window.workerCalls")
            assert calls and not {"build", "draw", "tile"} & set(calls), calls
            # the host's picks are the editor's: the colours that the host's look gives its select and hover are swapped in the host's road layers
            # (picked road 1 here green), and the host's own paint comes back with destroy
            sel = page.evaluate("JSON.parse(window.hostLookText).selection.select")
            paint = "hostMap.getStyle().layers.filter(l => l.id.startsWith('host-')).map(l => JSON.stringify(l.paint)).join()"
            assert sel not in page.evaluate(paint) and "#e53935" in page.evaluate(paint), "the editor's red replaces the host's select colour at open"
            page.evaluate("window.lvHighlight([[[0], '#00ff00']])")
            assert "#00ff00" in page.evaluate(paint), "a picked road has its colour"
            road = page.evaluate("window.editor.facts([window.editor.roads[0]]).then(f => Object.values(f)[0])")
            said = page.evaluate("r => window.lvApi('/api/apply', {ops: [{op: 'head', road: r, end: 'start', m: '3'}]})", road["road"])
            assert said["ok"] and " · drawn in " in said["said"], said
            rows = page.evaluate("window.replaced")
            assert len(rows) == 1 and {r["edge"] for r in rows[0]} == {d["edge"] for d in road["directions"]}, (rows, road)
            assert all(3 in (float(r["head_start_m"]), float(r["head_end_m"])) for r in rows[0]), rows[0]
            calls = page.evaluate("window.workerCalls")
            assert not {"build", "draw", "tile"} & set(calls), ("a change on the host's roads builds no map", calls)
            page.evaluate("window.editor.destroy()")
            assert sel in page.evaluate(paint) and "#00ff00" not in page.evaluate(paint) and "#e53935" not in page.evaluate(paint), "the host's own paint is back"
            assert page.evaluate("window.RS_SIDE.props.every(p => !('road' in p) && !('s_lon' in p)) && !window.RS_SIDE.lvFields")
            # the engine is kept: with the same edge hash, the next open has no init and no open call (the worker and its area are the first open's),
            # and prepareEditor makes it before the open
            page.evaluate("([csv, h]) => openHosted({csv, edge_hash: h})", [levels_csv, hsh])
            first = page.evaluate("window.workerCalls")
            assert "init" in first and "open" in first, first
            page.evaluate("window.editor.destroy()")
            page.evaluate("([csv, h]) => openHosted({csv, edge_hash: h})", [levels_csv, hsh])
            again = page.evaluate("window.workerCalls")
            assert "init" not in again and "open" not in again and "levelsOf" in again, again
            assert page.evaluate("window.editor.answer().resolve.how") in ("stored", "given")
            page.evaluate("window.editor.destroy()")
            page.evaluate("([csv, h]) => openHosted({csv, edge_hash: '0' + h.slice(1)})", [levels_csv, hsh])        # another hash: a new engine
            assert "open" in page.evaluate("window.workerCalls")
            page.evaluate("window.editor.destroy()")
            print(f"host open: {ms:.0f} ms")
            assert not [e for e in errors if e != "boom"], errors      # "boom": the stopped worker's own error, which the page reports too
            b.close()
    finally:
        server.shutdown()


@needs_pkg
def test_the_editor_keeps_the_dashboards_theme_its_layers_and_its_palette():
    """The editor draws its own roads on the host's map. The dashboard's theme (rs_theme) stays while it draws, and follows a change made inside the editor; the base map's
    layers (the overlays of the host's style) keep their switch and their list; and with the page's look the roads have the page's palette."""
    pw = pytest.importorskip("playwright.sync_api")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Files, directory=str(STATIC)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch()
            roads = "JSON.stringify(hostMap.getLayer('host-roads-simple').paint._values['line-color'].value?.expression ?? hostMap.getStyle().layers.find(l => l.id === 'host-roads-simple').paint['line-color'])"
            page = b.new_page(viewport={"width": 1300, "height": 850})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            base = f"http://127.0.0.1:{server.server_address[1]}/test.html"
            page.goto(base + "?dark")
            page.wait_for_function("window.ready", timeout=60000)
            # the editor's roads style has its own state (rs_theme "light" among them): the map's own value stays
            assert page.evaluate("hostMap.getGlobalState().rs_theme") == "dark" and page.evaluate("document.documentElement.dataset.rsTheme") == "dark"
            assert page.evaluate("window.RS_OVERLAYS.length") == 1 and page.evaluate("rsGetOverlays()"), "the host's overlays are still the dashboard's"
            page.evaluate("rsSetOverlays(false)")
            assert page.evaluate("hostMap.getLayoutProperty('host-water', 'visibility')") == "none"       # the switch still hides the base map's layer
            page.evaluate("rsSetOverlays(true)")
            page.evaluate("rsSetTheme('light')")                                                        # a change made while the editor is open
            assert page.evaluate("hostMap.getGlobalState().rs_theme") == "light"
            page.evaluate("rsSetTheme('dark')")
            assert page.evaluate("hostMap.getGlobalState().rs_theme") == "dark"
            page.evaluate("window.editor.destroy()")
            assert page.evaluate("hostMap.getGlobalState().rs_theme") == "dark" and page.evaluate("window.RS_OVERLAYS.length") == 1
            plain = page.evaluate(roads)
            # the standard Base map box and the legend box list the same things before and inside the editor: the maps, the one switch for the area's layers, their list
            page.goto(base + "?basemap")
            page.wait_for_function("window.ready", timeout=60000)
            rows = """() => { const out = {}; for (const [tool, box] of [['basemap', '.bm-menu'], ['legend', '#rs-color-box']]) { host.tools.open(tool);
                out[tool] = document.querySelector(box).innerText.replace(/\\s+/g, ' ').trim(); host.tools.close(tool); } out.switch = rsGetOverlays(); return out; }"""
            before = page.evaluate(rows)
            assert "Map layers" in before["basemap"] and "Road class" in before["legend"] and "Water" in before["legend"] and before["switch"] is True, before
            page.evaluate("window.openEditor()")
            page.wait_for_function("!!window.lvApi", timeout=60000)
            assert page.evaluate(rows) == before, (before, page.evaluate(rows))
            page.evaluate("window.editor.destroy()")
            assert page.evaluate(rows) == before, "and the same after it is closed"
            page.goto(base + "?carto")
            page.wait_for_function("window.ready", timeout=60000)
            carto = page.evaluate(roads)
            assert "#e892a2" in carto and "#e892a2" not in plain, "the page's palette (carto's motorway) is the editor's"
            assert not [e for e in errors if e != "boom"], errors
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


VIEWS = {"desktop": dict(viewport={"width": 1400, "height": 900}),
         "phone": dict(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True)}


@needs_pkg
@pytest.mark.parametrize("view", VIEWS)
def test_the_editor_works_in_the_hosts_panel(view):
    """The editor in the host's standard panel, on a desktop (1400 x 900) and a phone (390 x 844, touch): the host's body is kept and the title line
    is "← Steps" and "Edit levels" with the host's hide button; the apply bar is at the bottom edge of the panel (the phone's sheet) only while
    changes wait and stays when the body scrolls; Apply solves; "← Steps" with waiting changes asks apply, discard or stay; the edits.csv download
    is in the History tab; close puts the host's panel back and clears the picked roads' colour. $LV_SHOTS: a folder for a screenshot."""
    pw = pytest.importorskip("playwright.sync_api")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Files, directory=str(STATIC)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    phone = view == "phone"
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_context(**VIEWS[view]).new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("dialog", lambda d: d.accept())
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/test.html")
            page.wait_for_function("window.ready && !!document.getElementById('lv')", timeout=60000)
            page.wait_for_timeout(1500)                                           # the tiles of the editor's roads
            def box(sel):
                return page.evaluate(f"(() => {{ const r = document.querySelector({sel!r}).getBoundingClientRect(); return {{top: r.top, bottom: r.bottom, left: r.left, right: r.right, h: r.height}}; }})()")
            def tap(sel):
                page.locator(sel).tap() if phone else page.locator(sel).click()
            # open: the top line, three tabs, no apply bar; on a phone the panel is the sheet at the bottom
            assert page.locator("#sb #lv-back").inner_text() == "← Steps" and page.locator("#sb .rs-frame-title .t").inner_text() == "Edit levels"
            assert page.evaluate("[...document.querySelectorAll('#lv-tabs button')].map(b => b.dataset.t).join()") == "ends,edit,history,given"
            assert page.evaluate("document.getElementById('lv').dataset.mode") == "ends", "the editor opens in Road ends"
            assert page.evaluate("document.getElementById('lv-bar').hidden") and not page.locator("#lv-bar").is_visible()
            assert page.evaluate("!document.querySelector('#lv-toggle, #lv-handle') && !document.body.classList.contains('lv-open')"), "no frame or fold button of its own"
            sb = box("#sb")
            if phone:
                assert sb["bottom"] == pytest.approx(844, abs=1) and 280 < sb["top"] < 560, sb      # 40 %: the map stays in view, because you pick the roads on it
            else:
                # the panel's width (the dashboard default, 400 px) and side are the host's; the default card look floats it 8 px from the edges
                assert sb["left"] == 8 and sb["right"] - sb["left"] == pytest.approx(400, abs=1) and sb["h"] > 870, sb
            # a road on the map: a click (a tap on a phone) picks it, and the dashboard's own glow marks it
            top = sb["top"] if phone else 900
            xy = page.evaluate(f"""() => {{ const m = window.hostMap;
              for(const f of m.queryRenderedFeatures({{layers: ['host-lv-tap']}})){{
                const c = f.geometry.coordinates, pt = m.project(c[Math.floor(c.length / 2)]);
                if(pt.x > {80 if phone else 420} && pt.x < {350 if phone else 1300} && pt.y > 120 && pt.y < {top} - 60) return [pt.x, pt.y, f.properties.road]; }} return null; }}""")
            assert xy, "a road in the free part of the map"
            (page.touchscreen.tap if phone else page.mouse.click)(xy[0], xy[1])
            page.wait_for_function("document.querySelectorAll('#lv-cards .card').length === 1", timeout=20000)
            page.wait_for_timeout(300)
            assert page.evaluate("document.querySelectorAll('#lv-cards .card .x').length") == 1, "one pick for each click"
            # a cap goes to the list as every change does: nothing is applied, saved or drawn until Apply (Discard takes it out)
            n0 = page.evaluate("window.solved.length")
            page.evaluate("() => { for (const b of document.querySelectorAll('#lv-cards [data-cap] button')) b.click(); }")
            page.wait_for_function("!document.getElementById('lv-bar').hidden", timeout=20000)
            assert page.evaluate("window.solved.length") == n0 and page.inner_text("#lv-wait").endswith(("waiting ▴", "waiting ▾")), "a cap waits for Apply"
            page.evaluate("document.getElementById('lv-discard').click()")
            page.wait_for_function("document.getElementById('lv-bar').hidden", timeout=20000)
            # Road ends has one road: a second road replaces the first, and the rules and the Add form do not show
            roads = page.evaluate("[window.editor.roads[0], window.editor.roads.at(-1)]")
            page.evaluate("""r => { for (const x of r) document.dispatchEvent(new CustomEvent('rs:select', {detail: {properties: {road: x}, lvTap: true}})); }""", roads)
            page.wait_for_timeout(500)
            assert page.evaluate("document.querySelectorAll('#lv-cards .card').length") == 1, "Road ends: one road"
            assert not page.locator("#lv-add-sec").is_visible() and not page.locator("#lv-rel-sec").is_visible()
            # Stacking: two roads, their rules and the Add form; no caps or heads
            tap("#lv-tabs button[data-t=edit]")
            assert page.evaluate("document.getElementById('lv').dataset.mode") == "stack"
            # two roads and an order wish: the changes wait in the apply bar
            def stage(top=0, kind="order"):
                page.evaluate("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))")   # Esc clears the pair (the panel has no clear link)
                page.evaluate("""r => { for (const x of r) document.dispatchEvent(new CustomEvent('rs:select', {detail: {properties: {road: x}, lvTap: true}})); }""", roads)
                page.wait_for_function("document.querySelectorAll('#lv-cards .lv-pick').length === 2", timeout=20000)
                page.evaluate("k => document.querySelector(`#lv-kind [data-k=\"${k}\"]`).click()", kind)
                page.evaluate("t => document.querySelector(`#lv-top-seg button[data-v=\"${t}\"]`).click()", top)
                page.evaluate("document.getElementById('lv-add').click()")
                # a rule that makes a loop with the rules there are: the panel's conflict box, and Add anyway puts it in the list
                page.wait_for_function("!document.getElementById('lv-bar').hidden || !document.getElementById('lv-conflict').hidden", timeout=20000)
                if page.locator("#lv-anyway").count():
                    page.evaluate("document.getElementById('lv-anyway').click()")
            stage()
            page.wait_for_function("!document.getElementById('lv-bar').hidden", timeout=20000)
            assert not page.locator("#lv-cards .caps").first.is_visible() and not page.locator("#lv-cards .hd").first.is_visible(), "Stacking: no caps or heads"
            assert page.inner_text("#lv-wait").startswith("1 waiting")
            bar, sb, fb = box("#lv-bar"), box("#sb"), box("#lv .rs-frame-bar")
            assert page.evaluate("document.getElementById('lv-bar').parentElement.classList.contains('rs-frame-bar')")   # the apply bar is in the frame's bar
            assert sb["bottom"] - 24 <= fb["bottom"] <= sb["bottom"], (fb, sb)       # at the bottom edge of the panel (of the sheet), with the frame's margins
            for sel in ("#lv-apply", "#lv-discard"):
                assert page.locator(sel).is_visible()
                if phone:
                    assert box(sel)["h"] >= 44, sel
            page.evaluate("document.querySelector('#lv-body').scrollTop = 400")      # the panel scrolls, the bar stays
            assert box("#lv-bar") == bar
            assert page.evaluate("document.getElementById('lv-queue').hidden"), "the list of the waiting changes opens on a tap"
            tap("#lv-wait")
            assert page.locator("#lv-queue .q").count() == 1 and page.locator("#lv-queue").is_visible()
            tap("#lv-wait")
            if os.environ.get("LV_SHOTS"):
                page.screenshot(path=str(Path(os.environ["LV_SHOTS"]) / f"{view}.png"))
            # Discard: the bar goes
            tap("#lv-discard")
            assert page.evaluate("document.getElementById('lv-bar').hidden") and page.evaluate("document.querySelector('#lv').classList.contains('has-bar')") is False
            # Apply and solve: one solve, the rule in edits.csv, the bar goes
            n = page.evaluate("window.solved.length")
            before = page.evaluate("stored('edits.csv')").count("\n")
            stage()
            page.wait_for_function("!document.getElementById('lv-bar').hidden", timeout=20000)
            tap("#lv-apply")
            page.wait_for_function(f"window.solved.length === {n + 1} && document.getElementById('lv-bar').hidden", timeout=60000)
            assert page.evaluate("stored('edits.csv')").count("\n") == before + 1
            # the editor knows that an Apply happened, and gives its four files as texts (the host writes them into its own tables)
            assert page.evaluate("window.editor.dirty") is True
            files = page.evaluate("window.editor.exportFiles()")
            assert sorted(files) == ["caps.csv", "edits.csv", "heads.csv", "levels.csv"]
            assert files["edits.csv"] == page.evaluate("stored('edits.csv')") and files["levels.csv"].startswith("edge,casing_start")
            # "← Steps" with no change waiting leaves at once
            assert page.evaluate("window.backs") == 0
            tap("#lv-back")
            assert page.evaluate("window.backs") == 1
            # with changes waiting it asks: Stay stays (a new rule: the order is in edits.csv now, and a copy is refused)
            stage(kind="stack")
            page.wait_for_function("!document.getElementById('lv-bar').hidden", timeout=20000)
            tap("#lv-back")
            assert page.locator("#lv-ask").is_visible() and not page.locator("#lv-bar-main").is_visible() and "1 waiting" in page.inner_text("#lv-ask-t")
            assert page.evaluate("window.backs") == 1
            tap("#lv-ask-stay")
            assert page.locator("#lv-bar-main").is_visible() and not page.locator("#lv-ask").is_visible() and page.evaluate("window.backs") == 1
            # Discard leaves, with nothing waiting
            tap("#lv-back")
            tap("#lv-ask-discard")
            assert page.evaluate("window.backs") == 2 and page.evaluate("document.getElementById('lv-bar').hidden")
            # Apply leaves after the solve
            stage(1)
            page.wait_for_function("!document.getElementById('lv-bar').hidden", timeout=20000)
            n = page.evaluate("window.solved.length")
            tap("#lv-back")
            tap("#lv-ask-apply")
            page.wait_for_function(f"window.backs === 3 && window.solved.length === {n + 1}", timeout=60000)
            assert page.evaluate("stored('edits.csv')").count("\n") == before + 2
            # each applied rule has its time (the readers ignore the column)
            edits = page.evaluate("stored('edits.csv')").strip().split("\n")
            assert edits[0].endswith(",time") and re.search(r",\d{4}-\d\d-\d\d \d\d:\d\d$", edits[-1]), edits[-1]
            # the downloads of edits.csv, heads.csv and caps.csv are in the History tab
            tap("#lv-tabs button[data-t=history]")
            for name in ("edits.csv", "heads.csv", "caps.csv"):
                assert page.locator(f"#lv [data-dl='{name}']").is_visible()
                with page.expect_download() as d:
                    tap(f"#lv [data-dl='{name}']")
                assert d.value.suggested_filename == name
            # close: the host's panel as it was, and the picked roads' colour cleared
            page.evaluate("window.colorCalls = []; const o = window.rsColor; window.rsColor = (...a) => { colorCalls.push(a); return o(...a); }")
            page.evaluate("window.editor.destroy()")
            assert page.evaluate("colorCalls.some(a => a[0] === null)"), "destroy clears rsColor"
            assert page.evaluate("document.querySelector('#sb .sb-body').style.display") == "flex" and not page.locator("#sb .rs-frame-title").count()
            assert page.locator("#sb .sb-top h2").is_visible() and (phone or page.locator("#sb-hide").is_visible())
            assert not [e for e in errors if e != "boom"], errors
            b.close()
    finally:
        server.shutdown()
