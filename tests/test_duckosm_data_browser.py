"""duckosmLevelsData (rust/roadstyle-wasm/js/levels_sql.js, docs/design/level_part.md, step f): the adapter of the level-edit part for a duckOSM file, on a
real duckdb-wasm connection (loaded from the CDN: the test is skipped without the network). The tables are made as duckOSM makes them."""
import contextlib
import functools
import http.server
import os
import threading
import urllib.request
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "rust/roadstyle-wasm/js"
PKG = Path(os.environ.get("CARGO_TARGET_DIR") or ROOT / "rust" / "target") / "editor-pkg"          # rust/roadstyle-wasm/build_editor.sh
CDN = "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.33.1-dev57.0/+esm"

try:
    urllib.request.urlopen(CDN, timeout=10).close()
    _NET = True
except Exception:
    _NET = False

_PAGE = """<!doctype html><html><body><script type="module">
import * as duckdb from "%CDN%";
import {duckosmLevelsData} from "/js/levels_sql.js";
import init, * as pkg from "/pkg/roadstyle_wasm.js";
await init();
const bundle = await duckdb.selectBundle(duckdb.getJsDelivrBundles());
const url = URL.createObjectURL(new Blob([`importScripts("${bundle.mainWorker}");`], {type: "text/javascript"}));
const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), new Worker(url));
await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
const conn = await db.connect();
const q = async (sql) => (await conn.query(sql)).toArray().map((r) => r.toJSON());
window.run = async () => {
  const out = {};
  const none = duckosmLevelsData({db, conn, pkg: null, schema: "nothing_here"});
  out.none = await none.storedLevels();                                   // no meta table: null
  await conn.query(`CREATE SCHEMA visualization;
    CREATE TABLE visualization.edge_levels (edge_id BIGINT, casing_start INTEGER, casing_level INTEGER, casing_end INTEGER, fill_level INTEGER,
      head_start_m DOUBLE, head_end_m DOUBLE, cap_start VARCHAR, cap_end VARCHAR);
    INSERT INTO visualization.edge_levels VALUES (11, 0, 0, 0, 0, 5, 5, NULL, NULL), (12, 0, 0, 0, 0, 5, 5, NULL, NULL), (13, 1, 1, 1, 1, 5, 5, NULL, NULL);
    CREATE TABLE visualization.edge_levels_meta (source VARCHAR, area VARCHAR, n_edges BIGINT, edge_hash VARCHAR, created VARCHAR);
    INSERT INTO visualization.edge_levels_meta VALUES ('solve', NULL, 3, 'abc123', '2026-01-01T00:00:00+00:00');`);
  let hooks = [];
  const data = duckosmLevelsData({db, conn, pkg: null, before: () => hooks.push("before"), after: async ({tables, toParquet}) => {
    hooks.push("after:" + tables.join(","));
    out.parquetBytes = (await toParquet("edge_levels")).byteLength;
  }});
  const s = await data.storedLevels();
  out.stored = [s.edge_hash, s.csv.trim().split("\\n")];
  const files = {
    "levels.csv": "edge,casing_start,casing_level,casing_end,fill_level,head_start_m,head_end_m,cap_start,cap_end\\n11,0,0,0,0,5,5,,\\n12,0,2,0,2,5,5,flat,\\n13,1,1,1,1,7.5,5,,\\n",
    "edits.csv": "relation,a,b,a_end,b_end,enabled,time\\norder,11,12,,,true,2026-11-08 10:00\\n",
    "heads.csv": "road,start_m,end_m,time\\n13,7.5,,2026-11-08 10:00\\n",
    "caps.csv": "road,start,end,time\\n12,flat,,2026-11-08 10:00\\n",
  };
  await data.saveLevels(files, {name: "this browser: test"});
  out.hooks = [...hooks];
  out.levels = (await q("SELECT edge_id, casing_level, fill_level, head_start_m, cap_start FROM visualization.edge_levels ORDER BY edge_id")).map(r => [Number(r.edge_id), r.casing_level, r.fill_level, r.head_start_m, r.cap_start]);
  const [meta] = await q("SELECT source, area, edge_hash, n_edges FROM visualization.edge_levels_meta");
  out.meta = [meta.source, meta.area, meta.edge_hash, Number(meta.n_edges)];
  const [edit] = await q("SELECT a, b, relation FROM visualization.level_edits");
  out.edit = [Number(edit.a), Number(edit.b), edit.relation];
  out.counts = [(await q("SELECT count(*) AS n FROM visualization.level_heads"))[0].n, (await q("SELECT count(*) AS n FROM visualization.level_caps"))[0].n].map(Number);
  // the build has 3 edges: a levels.csv with 2 is refused, and nothing changes
  try { await data.saveLevels({...files, "levels.csv": "edge,casing_start,casing_level,casing_end,fill_level\\n11,0,0,0,0\\n12,0,0,0,0\\n"}); out.refused = "saved"; }
  catch(e){ out.refused = e.message; }
  // edges(): duckosmPlan's level_edges SQL on a small <mode>.edges table (needs duckdb's spatial extension: ST_AsWKB)
  try {
    await conn.query("INSTALL spatial; LOAD spatial;");
    await conn.query(`CREATE SCHEMA driving; CREATE TABLE driving.edges (edge_id BIGINT, highway VARCHAR, layer INTEGER, bridge VARCHAR, tunnel VARCHAR, oneway BOOLEAN, geometry GEOMETRY);
      INSERT INTO driving.edges VALUES (11, 'primary', 0, NULL, NULL, false, ST_GeomFromText('LINESTRING(7.42 43.73, 7.43 43.73)')),
        (12, 'primary', 1, 'yes', NULL, true, ST_GeomFromText('LINESTRING(7.42 43.731, 7.43 43.731)'));`);
    const e = await duckosmLevelsData({db, conn, pkg}).edges();
    out.edges = [e.byteLength > 100, new TextDecoder().decode(e.slice(0, 4)), new TextDecoder().decode(e.slice(-4))];      // a Parquet file: PAR1 ... PAR1
  } catch(err){ out.edges = "no spatial: " + err.message; }
  return out;
};
window.ready = true;
</script></body></html>""".replace("%CDN%", CDN)


class _H(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path.startswith("/js/"):
            return str(JS / path.removeprefix("/js/"))
        if path.startswith("/pkg/"):
            return str(PKG / path.removeprefix("/pkg/"))
        return super().translate_path(path)

    def do_GET(self):
        if self.path.split("?")[0] == "/t.html":
            body = _PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *a):
        pass


@contextlib.contextmanager
def served():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_H, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}/t.html"
    finally:
        srv.shutdown()


@pytest.mark.skipif(not _NET, reason="duckdb-wasm comes from the CDN: no network")
@pytest.mark.skipif(not (PKG / "roadstyle_wasm.js").exists(), reason="the editor's wasm package is not built (rust/roadstyle-wasm/build_editor.sh)")
def test_the_levels_adapter_reads_and_writes_a_duckosm_files_levels_tables():
    with served() as url, pw.sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.wait_for_function("window.ready", timeout=120000)
        got = page.evaluate("window.run()")
        assert got["none"] is None, got
        assert got["stored"][0] == "abc123" and got["stored"][1][0] == "edge,casing_start,casing_level,casing_end,fill_level" and len(got["stored"][1]) == 4, got
        assert got["hooks"] == ["before", "after:edge_levels,edge_levels_meta,level_edits,level_heads,level_caps"] and got["parquetBytes"] > 0, got
        assert got["levels"] == [[11, 0, 0, 5.0, None], [12, 2, 2, 5.0, "flat"], [13, 1, 1, 7.5, None]], got
        assert got["meta"] == ["area", "this browser: test", "abc123", 3] and got["edit"] == [11, 12, "order"] and got["counts"] == [1, 1], got
        assert "has 2 edges, the build has 3" in got["refused"], got
        if isinstance(got["edges"], str):
            pytest.skip(got["edges"])                                  # the rest is checked; edges() needs the spatial extension from the network
        assert got["edges"] == [True, "PAR1", "PAR1"], got
        assert not errors, errors
        b.close()
