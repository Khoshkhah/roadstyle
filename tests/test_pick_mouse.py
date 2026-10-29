"""A road is picked by the real mouse (page.mouse, not window.rsSelect): the hover (the cursor and the tooltip) and a click's rs:select,
on a page whose style has the interaction contract (render_edges) and on a host page whose style has none (a style of
inline_style, as a host's inlineStyle or the level editor's): there the dashboard picks on the road layer of simple mode, because the
style gives no `pick` (roadstyle:controls)."""
import contextlib
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
  const f = map.queryRenderedFeatures({layers: map.getStyle().layers.filter(l => l.id.startsWith("roads-simple")).map(l => l.id)}).find(f => f.properties.__rs_k === 1 && f.geometry.type === "LineString"
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


# The waits test that window.map is the MapLibre map: a host page's module script sets it after the page's load, and until then
# window.map is the element <div id="map"> (the browser's named access), on which map.loaded() throws and stops the wait.
def _mouse(pg):
    """Hover a road and click it with the real mouse: the cursor, the tooltip and the rs:select's id."""
    pg.wait_for_function("typeof window.map?.loaded === 'function' && map.loaded() && map.queryRenderedFeatures({layers: map.getStyle().layers.filter(l => l.id.startsWith('roads-simple')).map(l => l.id)}).length", timeout=60000)
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
    rs.render_edges(_roads(), basemap="blank", tooltip=["name"]).save(str(page))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 900, "height": 700})
        pg.goto(page.as_uri())
        assert isinstance(_mouse(pg), int)
        browser.close()


@pytest.mark.parametrize("old", [False, True], ids=["pick", "no pick"])
def test_a_road_is_picked_on_a_host_page_with_no_contract(tmp_path, old):
    """A style with no interaction contract has its pick layers (R7, 2026-10-25: contract::describe for every style); a style made
    before that has none, and the dashboard finds the road layer itself."""
    from roadstyle import _engine
    if not _engine.available():
        pytest.skip("no roadstyle._rust")
    g = _roads()
    style = json.loads(_engine.rust().inline_style(_engine._arrow(g), _engine._look_of({}), None, None, "roads"))
    style["layers"] = [lyr for lyr in style["layers"] if lyr["type"] != "symbol"]    # the arrows and names need a sprite and glyphs
    assert style["metadata"]["roadstyle:controls"]["pick"] == ["roads-simple-dash", "roads-simple", "roads-simple-z14-dash", "roads-simple-z14", "roads-simple-z15-dash", "roads-simple-z15"]
    if old:
        del style["metadata"]["roadstyle:controls"]["pick"]
    with _host(tmp_path, style, g) as (pg, errors):
        assert isinstance(_mouse(pg), int), errors


@contextlib.contextmanager
def _host(tmp_path, style, g):
    """A host page of `style` on its own server (the dashboard's ES modules need http), the map on the roads' bounds; gives the page and
    its errors."""
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
            yield pg, errors
            browser.close()
    finally:
        server.shutdown()


def test_a_3d_deck_is_picked_on_a_host_page_with_no_contract(tmp_path):
    """view_3d with no contract: the style's pick (since b3a8e64) has the decks' tops, not their casing, so the real mouse picks a deck
    (hover, rs:select on the deck layer)."""
    from roadstyle import _engine
    if not _engine.available():
        pytest.skip("no roadstyle._rust")
    g = _roads()
    style = json.loads(_engine.rust().inline_style(_engine._arrow(g), _engine._look_of({"view_3d": True}), None, None, "roads"))
    style["layers"] = [lyr for lyr in style["layers"] if lyr["type"] != "symbol"]
    pick = style["metadata"]["roadstyle:controls"]["pick"]
    assert "roadstyle:contract" not in style["metadata"] and any(i.startswith("roads-bridge-decks") for i in pick)
    assert "roads-deck-casing" not in pick
    deck = next(f for f in style["sources"]["decks"]["data"]["features"] if not f["properties"].get("__rs_casing_slab"))
    ring = deck["geometry"]["coordinates"][0]
    center = [sum(c[0] for c in ring) / len(ring), sum(c[1] for c in ring) / len(ring)]
    with _host(tmp_path, style, g) as (pg, errors):
        pg.wait_for_function("typeof window.map?.loaded === 'function' && map.loaded()", timeout=60000)
        pg.evaluate("c => map.jumpTo({center: c, zoom: 18})", center)
        pg.wait_for_function("map.loaded() && map.queryRenderedFeatures({layers: map.getStyle().layers.map(l => l.id)"
                             ".filter(i => i.startsWith('roads-bridge-decks'))}).length", timeout=30000)
        pg.evaluate("window.__sel = null; document.addEventListener('rs:select', e => { window.__sel = e.detail.layer; })")
        x, y = pg.evaluate("c => { const p = map.project(c); return [p.x, p.y]; }", center)
        pg.mouse.move(x - 40, y - 40)
        pg.mouse.move(x, y, steps=5)
        pg.wait_for_function("map.getCanvas().style.cursor === 'pointer'", timeout=5000)
        pg.mouse.click(x, y)
        pg.wait_for_function("window.__sel !== null", timeout=5000)
        assert pg.evaluate("window.__sel").startswith("roads-bridge-decks"), errors
