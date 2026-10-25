"""A road is picked by the real mouse (page.mouse, not window.rsSelect): the hover (the cursor and the tooltip) and a click's rs:select,
on a page whose style has the interaction contract (render_edges, engine="rust") and on a host page whose style has none (a style of
make_style, as a host's makeStyle or the level editor's): there the dashboard picks on the road layer of simple mode, because the
style gives no `pick` (roadstyle:controls)."""
import functools
import http.server
import json
import pathlib
import threading

import pytest

pw = pytest.importorskip("playwright.sync_api")
ROOT = pathlib.Path(__file__).parents[1]
DATA = ROOT / "rust" / "roadstyle-rs" / "tests" / "data" / "monaco_part" / "roads.parquet"

# the middle of a road's fill piece in the window, in pixels, from the road layer of simple mode
ROAD_PIXEL = """() => {
  const f = map.queryRenderedFeatures({layers: ["roads-simple"]}).find(f => f.properties.__rs_k === 1 && f.geometry.type === "LineString"
                                                                          && f.geometry.coordinates.length > 1);
  const c = f.geometry.coordinates, p = map.project(c[Math.floor(c.length / 2)]);
  return [p.x, p.y];
}"""
HOST = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/rust/roadstyle-assets/files/vendor/maplibre-gl.css">
<link rel="stylesheet" href="/rust/roadstyle-assets/files/static/dashboard/dashboard.css"><link rel="stylesheet" href="/rust/roadstyle-assets/files/static/popup.css">
<script src="/rust/roadstyle-assets/files/vendor/maplibre-gl.js"></script>
<style>html,body,#map{margin:0;height:100%}</style></head><body><div id="map"></div>
<script type="module">
import {rsDashboard} from "/rust/roadstyle-assets/files/static/dashboard/index.js";
const style = await (await fetch("/style.json")).json();
window.map = new maplibregl.Map({container: "map", style, bounds: BOUNDS, fitBoundsOptions: {padding: 20}});
window.rs = rsDashboard(map, {style, road_tooltip: true, hover_delay_ms: 50});
</script></body></html>"""


def _roads():
    import geopandas as gpd
    import pyarrow.parquet as pq
    import shapely
    df = pq.read_table(DATA).to_pandas(integer_object_nulls=True)
    return gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")


def _mouse(pg):
    """Hover a road and click it with the real mouse: the cursor, the tooltip and the rs:select's id."""
    pg.wait_for_function("window.map && map.loaded() && map.queryRenderedFeatures({layers: ['roads-simple']}).length", timeout=60000)
    pg.evaluate("window.__sel = null; document.addEventListener('rs:select', e => { window.__sel = e.detail.id; })")
    x, y = pg.evaluate(ROAD_PIXEL)
    pg.mouse.move(x - 30, y - 30)
    pg.mouse.move(x, y, steps=5)
    pg.wait_for_function("map.getCanvas().style.cursor === 'pointer'", timeout=5000)
    pg.wait_for_selector(".rs-tip", timeout=5000)
    pg.mouse.click(x, y)
    pg.wait_for_function("window.__sel !== null", timeout=5000)
    return pg.evaluate("window.__sel")


def test_a_road_is_picked_on_a_page_with_the_contract(tmp_path):
    import roadstyle as rs
    if not __import__("roadstyle._engine", fromlist=["available"]).available():
        pytest.skip("no roadstyle._rust")
    page = tmp_path / "contract.html"
    rs.render_edges(_roads(), engine="rust", basemap="blank", tooltip=["name"]).save(str(page))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 900, "height": 700})
        pg.goto(page.as_uri())
        assert isinstance(_mouse(pg), int)
        browser.close()


def test_a_road_is_picked_on_a_host_page_with_no_contract(tmp_path):
    from roadstyle import _engine
    if not _engine.available():
        pytest.skip("no roadstyle._rust")
    g = _roads()
    style = json.loads(_engine.rust().make_style(_engine._arrow(g), _engine._look_of({}), None, None, "roads"))
    style["layers"] = [lyr for lyr in style["layers"] if lyr["type"] != "symbol"]    # the arrows and names need a sprite and glyphs
    assert not (style.get("metadata") or {}).get("roadstyle:controls", {}).get("pick"), "the style has no pick: the case of this test"
    (tmp_path / "style.json").write_text(json.dumps(style))
    (tmp_path / "host.html").write_text(HOST.replace("BOUNDS", json.dumps([list(g.total_bounds[:2]), list(g.total_bounds[2:])])))

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
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{server.server_address[1]}/host.html")
            assert isinstance(_mouse(pg), int), errors
            browser.close()
    finally:
        server.shutdown()
