"""The dashboard adds the style's images (roadstyle:images, a page's O.images: a base map's patterns and icons) that the map does not have
yet, and never replaces a host's image of the same name; a layer that asks for one before it has loaded gets an empty one at once (no
"image not found" warning), which the real one replaces."""
import base64
import functools
import http.server
import json
import pathlib
import threading

import pytest

pw = pytest.importorskip("playwright.sync_api")
ROOT = pathlib.Path(__file__).parents[1]
HOST = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/rust/roadstyle-assets/files/vendor/maplibre-gl.css">
<script src="/rust/roadstyle-assets/files/vendor/maplibre-gl.js"></script>
<style>html,body,#map{margin:0;height:100%}</style></head><body><div id="map"></div>
<script type="module">
import {rsDashboard} from "/rust/roadstyle-assets/files/static/dashboard/index.js";
const style = await (await fetch("/style.json")).json();
window.map = new maplibregl.Map({container: "map", style, center: [18.0, 59.3], zoom: 14});
// the host's own image of a name that the style has too: it stays
map.addImage("t-host", {width: 2, height: 2, data: new Uint8Array(16).fill(200)});
window.rs = rsDashboard(map, {style});
map.once("idle", () => setTimeout(() => { window.done = true; }, 300));
</script></body></html>"""


def test_the_dashboard_adds_the_styles_images_and_keeps_the_hosts(tmp_path):
    from roadstyle import _assets
    url = "data:image/png;base64," + base64.b64encode(_assets.data("data/basemap/patterns/waves.png")).decode()
    square = {"type": "Polygon", "coordinates": [[[17.99, 59.29], [18.01, 59.29], [18.01, 59.31], [17.99, 59.31], [17.99, 59.29]]]}
    style = {"version": 8, "sources": {"area": {"type": "geojson", "data": {"type": "Feature", "properties": {}, "geometry": square}}},
             "layers": [{"id": "t-fill", "type": "fill", "source": "area", "paint": {"fill-pattern": "t-waves"}}],
             "metadata": {"roadstyle:images": {"t-waves": url, "t-host": url}}}
    (tmp_path / "style.json").write_text(json.dumps(style))
    (tmp_path / "host.html").write_text(HOST)

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
            pg = browser.new_page(viewport={"width": 600, "height": 500})
            console = []
            pg.on("console", lambda m: console.append((m.type, m.text)))
            pg.goto(f"http://127.0.0.1:{server.server_address[1]}/host.html")
            pg.wait_for_function("window.done === true", timeout=60000)
            sizes = pg.evaluate("['t-waves', 't-host'].map(i => map.getImage(i) && map.getImage(i).data.width)")
            browser.close()
    finally:
        server.shutdown()
    assert sizes[0] > 1, "the style's pattern is in the map, not the empty one"
    assert sizes[1] == 2, "the host's image of the same name stays"
    assert not [t for k, t in console if "could not be loaded" in t or "could not be read" in t], console
