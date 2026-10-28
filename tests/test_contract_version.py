"""The dashboard reads the interaction contract's version (roadstyle:contract; docs/design/contract_schema.md, step 4): a newer version
than core.js' CONTRACT is an error on the console and in rsDashboard's result, and the dashboard adds no road interaction for that
style; a style with roadstyle:* metadata and no version was made before every style had it: it is read as version 1, with a note (version 1 is older than the dashboard's: contract 2 has the road's row as the feature id)."""
import functools
import http.server
import json
import pathlib
import threading

import pytest

pw = pytest.importorskip("playwright.sync_api")
ROOT = pathlib.Path(__file__).parents[1]
DATA = ROOT / "rust" / "roadstyle-rs" / "tests" / "data" / "monaco_part" / "roads.parquet"
HOST = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/rust/roadstyle-assets/files/vendor/maplibre-gl.css">
<script src="/rust/roadstyle-assets/files/vendor/maplibre-gl.js"></script>
<style>html,body,#map{margin:0;height:100%}</style></head><body><div id="map"></div>
<script type="module">
import {rsDashboard} from "/rust/roadstyle-assets/files/static/dashboard/index.js";
const style = await (await fetch("/style.json")).json();
window.map = new maplibregl.Map({container: "map", style, bounds: BOUNDS});
window.rs = rsDashboard(map, {style});
map.once("idle", () => { window.done = true; });
</script></body></html>"""
ROAD = """() => { const f = map.queryRenderedFeatures({layers: ["roads-simple"]}).find(f => f.properties.__rs_k === 1 && f.geometry.type ===
  "LineString"); const c = f.geometry.coordinates, p = map.project(c[Math.floor(c.length / 2)]); return [p.x, p.y]; }"""


@pytest.fixture(scope="module")
def live_style():
    from roadstyle import _engine
    if not _engine.available():
        pytest.skip("no roadstyle._rust")
    import geopandas as gpd
    import pyarrow.parquet as pq
    import shapely
    df = pq.read_table(DATA).to_pandas(integer_object_nulls=True)
    g = gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")
    style = json.loads(_engine.rust().inline_style(_engine._arrow(g), _engine._look_of({"state": "live"}), None, None, "roads"))
    style["layers"] = [lyr for lyr in style["layers"] if lyr["type"] != "symbol"]    # the arrows and names need a sprite and glyphs
    return style, [list(g.total_bounds[:2]), list(g.total_bounds[2:])]


@pytest.mark.parametrize("version, picked, error, note", [
    (2, True, False, False),
    (3, False, True, False),
    (None, True, False, True),
], ids=["this version", "a newer version", "no version"])
def test_the_dashboard_reads_the_contracts_version(tmp_path, live_style, version, picked, error, note):
    style, bounds = live_style
    style = json.loads(json.dumps(style))
    if version is None:
        del style["metadata"]["roadstyle:contract"]
    else:
        style["metadata"]["roadstyle:contract"] = version
    (tmp_path / "style.json").write_text(json.dumps(style))
    (tmp_path / "host.html").write_text(HOST.replace("BOUNDS", json.dumps(bounds)))

    class Files(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path):
            name = path.split("?")[0].lstrip("/")
            return str(tmp_path / name) if name in ("host.html", "style.json") else str(ROOT / name)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Files, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            pg = browser.new_page(viewport={"width": 900, "height": 700})
            console = []
            pg.on("console", lambda m: console.append((m.type, m.text)))
            pg.goto(f"http://127.0.0.1:{server.server_address[1]}/host.html")
            pg.wait_for_function("window.done === true", timeout=60000)
            pg.evaluate("window.__sel = null; document.addEventListener('rs:select', e => { window.__sel = e.detail.id; })")
            x, y = pg.evaluate(ROAD)
            pg.mouse.move(x - 30, y - 30)
            pg.mouse.move(x, y, steps=4)
            pg.mouse.click(x, y)
            pg.wait_for_timeout(400)
            got = pg.evaluate("[window.__sel !== null, map.getCanvas().style.cursor === 'pointer', rs.error]")
            browser.close()
    finally:
        server.shutdown()
    assert got[0] == picked and got[1] == picked, got
    errors = [t for k, t in console if k == "error" and "interaction contract is version 3" in t]
    assert (got[2] is not None and "version 3" in got[2]) == error and bool(errors) == error, (got, console)
    assert any(k == "info" and "no roadstyle:contract" in t for k, t in console) == note, console
