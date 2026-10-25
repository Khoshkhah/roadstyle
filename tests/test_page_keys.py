"""filter_control and legend are page keys (N32 step 2): the dashboard reads them from the page's options (RS_OPTIONS, a host's), with
render's defaults (true). The style has the facts: the filter (roadstyle:controls.filter, with no `on`) and the legend data
(roadstyle:color_options). A style made before has its own controls.filter.on, which stays when the page gives no filter_control."""
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
<link rel="stylesheet" href="/rust/roadstyle-assets/files/static/dashboard/dashboard.css">
<script src="/rust/roadstyle-assets/files/vendor/maplibre-gl.js"></script>
<style>html,body,#map{margin:0;height:100%}</style></head><body><div id="map"></div>
<script type="module">
import {rsDashboard} from "/rust/roadstyle-assets/files/static/dashboard/index.js";
const style = await (await fetch("/style.json")).json();
window.map = new maplibregl.Map({container: "map", style, bounds: BOUNDS});
window.rs = rsDashboard(map, {style, ...OPTIONS});
map.once("idle", () => { window.done = true; });
</script></body></html>"""


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
    look = _engine._look_of({"state": "live", "color_by": "lanes", "cmap": "YlOrRd", "vmin": 1, "vmax": 4})
    style = json.loads(_engine.rust().make_style(_engine._arrow(g), look, None, None, "roads"))
    style["layers"] = [lyr for lyr in style["layers"] if lyr["type"] != "symbol"]    # the arrows and names need a sprite and glyphs
    assert style["metadata"]["roadstyle:controls"]["filter"]["classes"] and any(o.get("legend") for o in style["metadata"]["roadstyle:color_options"])
    return style, [list(g.total_bounds[:2]), list(g.total_bounds[2:])]


def _boxes(tmp_path, style, bounds, options):
    """The Roads box and the legend box that the dashboard shows on a host page of `style` with `options`."""
    (tmp_path / "style.json").write_text(json.dumps(style))
    (tmp_path / "host.html").write_text(HOST.replace("BOUNDS", json.dumps(bounds)).replace("OPTIONS", json.dumps(options)))

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
            pg.wait_for_function("window.done === true", timeout=60000)
            out = pg.evaluate("[!!document.querySelector('.flt-ctrl'), !!document.querySelector('.co-lg')]")
            browser.close()
    finally:
        server.shutdown()
    assert not errors, errors
    return out


@pytest.mark.parametrize("on, options, want", [
    (None, {}, [True, True]),                                       # a new style, render's defaults
    (None, {"filter_control": False, "legend": False}, [False, False]),
    (False, {}, [False, True]),                                     # a style made before: its own controls.filter.on
    (False, {"filter_control": True}, [True, True]),                # the page's option first
], ids=["defaults", "page off", "old style off", "page over old style"])
def test_filter_control_and_legend_are_page_keys(tmp_path, live_style, on, options, want):
    style, bounds = live_style
    style = json.loads(json.dumps(style))
    style["metadata"]["roadstyle:controls"]["filter"].pop("on", None)          # a new style: the engine writes no `on`
    if on is not None:
        style["metadata"]["roadstyle:controls"]["filter"]["on"] = on
    assert _boxes(tmp_path, style, bounds, options) == want
