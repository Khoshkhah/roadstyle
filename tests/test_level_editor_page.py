"""The level editor in a page with no server (docs/rust/browser.md, "The level editor in a page"): roadstyle-wasm's makeArea gives the
files of the folder form, and the module dashboard/editor/level_editor.js edits an area kept in the browser (browserStore) on the host's
map. They need the editor's wasm package (rust/roadstyle-wasm/build_editor.sh), Node for the first and Chromium (playwright) for the
second: skipped without them (CI builds no package)."""
import hashlib
import json
import os
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
const _on = document.addEventListener, _off = document.removeEventListener;
document.addEventListener = function(t, ...a){ listening[t] = (listening[t] || 0) + 1; return _on.call(this, t, ...a); };
document.removeEventListener = function(t, ...a){ listening[t] = (listening[t] || 0) - 1; return _off.call(this, t, ...a); };
</script>
<script type="module">
import init, * as pkg from "/level_editor/pkg/roadstyle_wasm.js";
import {levelEditor, browserStore, saveArea, areaIsFor} from "/dashboard/editor/level_editor.js";
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
const hostSources = pkg.styleSources(edges, pkg.resolveLook(JSON.stringify({args: {state: "live"}})), undefined, undefined, "host");
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
const host = rsDashboard(map, {style: own, prefix: "host-", basemap_switcher: false, dashboard: opts.dashboard});
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
window.hostSources = Object.fromEntries(map.getStyle().layers.filter(l => l.id.startsWith("host-")).map(l => [l.id, l.source]));
window.counts = () => JSON.stringify(Object.fromEntries(Object.entries(listening).filter(e => e[1])));
window.before = counts();
window.solved = [];
window.backs = 0;
window.openEditor = async () => { const t = performance.now();
  const ed = await levelEditor({map, panel, pkgUrl: "/level_editor/pkg/roadstyle_wasm.js", store, dashboard: host, prefix: "host-"});
  ed.addEventListener("back", () => window.backs++);
  ed.addEventListener("solved", async e => window.solved.push({rows: e.detail.levelsCsv.trim().split("\\n").length - 1, draw: (await e.detail.draw()).length}));
  window.editor = ed; return performance.now() - t;
};
// the option host: the editor on the host's roads and road table; replaceRoads keeps the rows that it gets
window.replaced = [];
window.openHosted = async () => {
  window.RS_SIDE = hostSide;
  const t = performance.now();
  window.editor = await levelEditor({map, panel, pkgUrl: "/level_editor/pkg/roadstyle_wasm.js", store, dashboard: host,
    host: {replaceRoads: async rows => { window.replaced.push(rows); }}});
  return performance.now() - t;
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
            assert page.locator("#sb .sb-top .lv-back").inner_text() == "← Steps" and page.locator("#sb .sb-top .t").inner_text() == "Edit levels"
            assert page.locator("#sb-hide").is_visible(), "the host's hide button stays"
            # the lean road table: only the fields that the page reads (reads.json's table), live data's id and the road that a click picks
            want = set(json.loads((STATIC / "dashboard" / "reads.json").read_text())["table"]) | {"edge", "road", "modes"}
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
            road = page.evaluate("window.editor.roads[0]")
            # the engine is in the worker: the page has no LevelArea of its own
            assert page.evaluate("!!window.editor && !('area' in window.editor)")
            said = page.evaluate("r => window.lvApi('/api/apply', {ops: [{op: 'head', road: r, end: 'end', m: '7'}]})", road)
            assert said["ok"] and said["redrawn"] and said["said"] == "not solved again (heads and caps are drawing only)", said
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
            # close, open again, close: the same listeners each time, none left; the host's roads, base map and dashboard back
            opened = page.evaluate("counts()")
            back = "JSON.stringify(Object.fromEntries(hostMap.getStyle().layers.filter(l => l.id.startsWith('host-')).map(l => [l.id, l.source])))"
            for _ in range(2):
                page.evaluate("window.editor.destroy()")
                assert page.evaluate("counts()") == page.evaluate("window.before"), "no listener of the editor left"
                assert page.evaluate(back) == page.evaluate("JSON.stringify(window.hostSources)"), "the host's layers as they were"
                assert page.evaluate("!document.getElementById('lv') && !hostMap.getLayer('lv-ends') && !hostMap.getSource('host-lv-roads')")
                assert page.evaluate("window.rs === window.host && !window.lvApi && !document.querySelector('.lv-title')")
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
            road = page.evaluate("window.editor.facts([window.editor.roads[0]]).then(f => Object.values(f)[0])")
            said = page.evaluate("r => window.lvApi('/api/apply', {ops: [{op: 'head', road: r, end: 'start', m: '3'}]})", road["road"])
            assert said["ok"] and " · drawn in " in said["said"], said
            rows = page.evaluate("window.replaced")
            assert len(rows) == 1 and {r["edge"] for r in rows[0]} == {d["edge"] for d in road["directions"]}, (rows, road)
            assert all(3 in (float(r["head_start_m"]), float(r["head_end_m"])) for r in rows[0]), rows[0]
            page.evaluate("window.editor.destroy()")
            assert page.evaluate("window.RS_SIDE.props.every(p => !('road' in p) && !('s_lon' in p)) && !window.RS_SIDE.lvFields")
            print(f"host open: {ms:.0f} ms")
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
            assert page.locator("#sb .lv-back").inner_text() == "← Steps" and page.locator("#sb .lv-title .t").inner_text() == "Edit levels"
            assert page.evaluate("[...document.querySelectorAll('#lv-tabs button')].map(b => b.dataset.t).join()") == "edit,history,given"
            assert page.evaluate("document.getElementById('lv-bar').hidden") and not page.locator("#lv-bar").is_visible()
            assert page.evaluate("!document.querySelector('#lv-toggle, #lv-handle') && !document.body.classList.contains('lv-open')"), "no frame or fold button of its own"
            sb = box("#sb")
            if phone:
                assert sb["bottom"] == pytest.approx(844, abs=1) and 280 < sb["top"] < 560, sb
            else:
                assert sb["left"] == 0 and sb["right"] == pytest.approx(400, abs=1) and sb["h"] > 880, sb      # the panel's width (the dashboard default, 400 px) and side are the host's
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
            # two roads and an order wish: the changes wait in the apply bar
            roads = page.evaluate("[window.editor.roads[0], window.editor.roads.at(-1)]")
            def stage(top=0):
                page.evaluate("document.getElementById('lv-clear').click()")
                page.evaluate("""r => { for (const x of r) document.dispatchEvent(new CustomEvent('rs:select', {detail: {properties: {road: x}, lvTap: true}})); }""", roads)
                page.wait_for_function("document.querySelectorAll('#lv-cards .card').length === 2", timeout=20000)
                page.evaluate("t => document.querySelector(`#lv-top-seg button[data-v=\"${t}\"]`).click()", top)
                page.evaluate("document.getElementById('lv-add').click()")
            stage()
            page.wait_for_function("!document.getElementById('lv-bar').hidden", timeout=20000)
            assert page.inner_text("#lv-wait").startswith("1 waiting")
            bar, sb = box("#lv-bar"), box("#sb")
            assert sb["bottom"] - 16 <= bar["bottom"] <= sb["bottom"], (bar, sb)       # at the bottom edge of the panel (of the sheet)
            for sel in ("#lv-apply", "#lv-discard"):
                assert page.locator(sel).is_visible()
                if phone:
                    assert box(sel)["h"] >= 44, sel
            page.evaluate("document.querySelector('#lv .scroll[data-tab=edit]').scrollTop = 400")      # the panel scrolls, the bar stays
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
            # "← Steps" with no change waiting leaves at once
            assert page.evaluate("window.backs") == 0
            tap("#lv-back")
            assert page.evaluate("window.backs") == 1
            # with changes waiting it asks: Stay stays
            stage()
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
            # the edits.csv download is in the History tab
            tap("#lv-tabs button[data-t=history]")
            assert page.locator("#lv-dl").is_visible()
            with page.expect_download() as d:
                tap("#lv-dl")
            assert d.value.suggested_filename == "edits.csv"
            # close: the host's panel as it was, and the picked roads' colour cleared
            page.evaluate("window.colorCalls = []; const o = window.rsColor; window.rsColor = (...a) => { colorCalls.push(a); return o(...a); }")
            page.evaluate("window.editor.destroy()")
            assert page.evaluate("colorCalls.some(a => a[0] === null)"), "destroy clears rsColor"
            assert page.evaluate("document.querySelector('#sb .sb-body').style.display") == "flex" and not page.locator("#sb .lv-title").count()
            assert page.locator("#sb .sb-top h2").is_visible() and (phone or page.locator("#sb-hide").is_visible())
            assert not [e for e in errors if e != "boom"], errors
            b.close()
    finally:
        server.shutdown()
