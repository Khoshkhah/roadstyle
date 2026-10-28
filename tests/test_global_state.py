"""The dashboard sets the style's global state (roadstyle:state): a host that adds a live style's layers to its own map has none of
its values (they are in the style's own "state"), so the dashboard sets the start value of each name that the map does not have, and
keeps a value that the map has (the host's or the user's)."""
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
window.errors = [];
const style = await (await fetch("/style.json")).json();
// the host's own style, with no global state; the roads come later
window.map = new maplibregl.Map({container: "map", style: {version: 8, sources: {}, layers: []}, bounds: BOUNDS});
map.on("error", e => window.errors.push(String(e.error && e.error.message || e)));
const rs = rsDashboard(map, {style: null, prefix: "rs-"});
await map.once("load");
map.setGlobalStateProperty("rs_fill_on", false);            // a value of the host's own: it stays
for (const [id, src] of Object.entries(style.sources)) map.addSource("rs-" + id, src);
for (const l of style.layers) map.addLayer({...l, id: "rs-" + l.id, source: "rs-" + l.source});
rs.setStyle(style);
map.once("idle", () => { window.done = true; });
</script></body></html>"""


def test_set_style_gives_a_host_map_the_styles_global_state(tmp_path):
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
    start = style["metadata"]["roadstyle:state"]
    assert "rs_fill_on" in start and start["rs_fill_on"] is True
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
            page_errors = []
            pg.on("pageerror", lambda e: page_errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{server.server_address[1]}/host.html")
            pg.wait_for_function("window.done === true", timeout=60000)
            state, errors = pg.evaluate("[map.getGlobalState(), window.errors]")
            browser.close()
    finally:
        server.shutdown()
    assert not errors and not page_errors, (errors, page_errors)
    assert state["rs_fill_on"] is False, "the host's own value stays"
    assert {k: v for k, v in state.items() if k != "rs_fill_on"} == {k: v for k, v in start.items() if k != "rs_fill_on"}
