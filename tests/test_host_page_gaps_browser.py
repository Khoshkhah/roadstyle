"""A JavaScript host page that starts with `rsDashboard(map, {style: null, prefix: "rs-", ...})` and gets its roads style later with `rs.setStyle` (the
duckOSM page). The standard dashboard gives it, with no adapter of the page's:
- the style's own base-map layers (`ov<i>`): one switch in the base-map box, their list with the colours in the legend box, no floating Layers box, and the 3D
  tool; each for every style that comes, and they go with a style that has none (gap 3);
- a raster base map under the roads, whose layers have the page's prefix (gap 4);
- the dark twin of a base map in the dark theme, whoever asks (gap 6), and the sprite of a vector base map (gap 7);
- the panel's shell, with no copy of its rules in the page (gap 8);
- a tool that is found by `data-rs-tool` after its title went to the tooltip (gap 11);
- boxes that stay inside a phone's screen sideways (gap 1), and the sheet's height and the free part of the map (gap 10).
Skipped without playwright."""
import functools
import http.server
import json
import pathlib
import threading

import pytest

pw = pytest.importorskip("playwright.sync_api")
ROOT = pathlib.Path(__file__).parents[1]
FILES = "/rust/roadstyle-assets/files"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d605a60000000049454e44ae426082")
SQUARE = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "a"}, "geometry": {
    "type": "Polygon", "coordinates": [[[18.0, 59.3], [18.01, 59.3], [18.01, 59.31], [18.0, 59.31], [18.0, 59.3]]]}}]}
HOST = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="FILES/vendor/maplibre-gl.css"><link rel="stylesheet" href="FILES/static/dashboard/dashboard.css">
<script src="FILES/vendor/maplibre-gl.js"></script>
<script>
const OPTS = __OPTS__;
if (location.search.includes("boundary")) { OPTS.dashboard.boundary.dim = true; OPTS.dashboard.boundary.limit = true; }
const d = OPTS.dashboard, c = document.documentElement.classList;
c.add("rs-tpl-dashboard", "rs-overlay", "rs-has-toolbar", "rs-tb-" + d.toolbar.position, "rs-panel-left", "rs-hide-scale");
document.documentElement.style.setProperty("--rs-panel-w", d.panel.width_px + "px");
if (matchMedia("(max-width:" + d.phone.max_width_px + "px)").matches) c.add("rs-phone");
</script>
<style>html,body{margin:0;height:100%}#map{position:fixed;inset:0}</style></head><body>
<div id="map"></div>
<div id="sb" data-theme="light"><div class="sb-card"><div class="sb-top"><h2>Host</h2><button id="sb-hide" title="Hide the panel">x</button></div><div class="sb-body">Hello</div></div></div>
<script type="module">
import {rsDashboard} from "FILES/static/dashboard/index.js";
window.errors = [];
const baseLayers = [{id: "bg", type: "background", paint: {"background-color": "#efede8"}}, {id: "basemap", type: "raster", source: "bm", layout: {visibility: "none"}}];
window.map = new maplibregl.Map({container: "map", center: [18.005, 59.305], zoom: 12, style: {version: 8, sprite: "http://rs.test/own", glyphs: "http://rs.test/fonts/{fontstack}/{range}.pbf", sources: {bm: {type: "raster", tiles: ["http://rs.test/t/{z}/{x}/{y}.png"], tileSize: 256}}, layers: baseLayers}});
map.on("error", e => window.errors.push(String(e.error && e.error.message || e)));
map.addControl(new maplibregl.NavigationControl(), "top-right");
window.rs = rsDashboard(map, {style: null, prefix: "rs-", tiles: true, basemaps: OPTS.basemaps, ontop: OPTS.ontop, basemap_switcher: true, dashboard: OPTS.dashboard});
// a roads style, as the page makes it: the sources and layers are in the map with the prefix first, then rs.setStyle
window.addStyle = (style) => {
  for (const l of map.getStyle().layers.filter(l => l.id.startsWith("rs-"))) map.removeLayer(l.id);
  for (const k of Object.keys(map.getStyle().sources).filter(k => k.startsWith("rs-"))) map.removeSource(k);
  for (const [id, src] of Object.entries(style.sources)) map.addSource("rs-" + id, src);
  for (const l of style.layers) map.addLayer({...l, id: "rs-" + l.id, source: "rs-" + l.source});
  rs.setStyle(style);
};
await map.once("load");
window.ready = true;
</script></body></html>"""


def _style(overlays=True):
    style = {"version": 8, "sources": {"roadsrc": {"type": "geojson", "data": SQUARE}}, "metadata": {},
             "layers": [{"id": "roads", "type": "line", "source": "roadsrc", "paint": {"line-color": "#c33", "line-width": 2}}]}
    if overlays:
        style["sources"]["ov0"] = {"type": "geojson", "data": SQUARE}
        style["layers"] += [{"id": "ov0-fill", "type": "fill", "source": "ov0", "paint": {"fill-color": "#39c", "fill-opacity": 0.5}},
                            {"id": "ov0-3d", "type": "fill-extrusion", "source": "ov0", "layout": {"visibility": "none"}, "paint": {"fill-extrusion-height": 20}}]
        style["metadata"]["roadstyle:controls"] = {"overlays": [{"label": "Water", "source": "ov0", "layers": ["ov0-fill", "ov0-3d"], "extrude": "ov0-3d",
                                                                  "interactive": False, "popup": [], "tooltip": None, "color": "#f4f4f4"}]}
    return style


@pytest.fixture(scope="module")
def host():
    opts = json.loads((ROOT / "rust" / "roadstyle-assets" / "files" / "data" / "host_options.json").read_text())
    opts["basemaps"] = [b for b in opts["basemaps"] if b["key"] in ("blank", "osm", "blank_dark")]
    opts["basemaps"].append({"key": "vec", "label": "Vector", "title": "Vector", "group": "", "swatch": None, "order": 90, "tiles": [], "bg": "#ffffff", "maxzoom": 19,
                             "attr": "", "is_dark": False, "style_url": "http://rs.test/vec.json", "dark": None})
    opts["dashboard"]["panel"]["hide"] = []         # the host has none of roadstyle's own panel sections (the duckOSM page says so in its `dashboard` key)
    page = HOST.replace("FILES", FILES).replace("__OPTS__", json.dumps({k: opts[k] for k in ("dashboard", "basemaps", "ontop")}))
    vec = json.dumps({"version": 8, "sprite": "http://rs.test/vsprite", "sources": {}, "layers": []})

    class Files(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] == "/page.html":
                body = page.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                super().do_GET()

        def translate_path(self, path):
            return str(ROOT / path.split("?")[0].lstrip("/"))

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Files, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", vec
    server.shutdown()


def test_a_later_style_brings_its_base_map_layers_a_raster_map_goes_under_the_roads_and_the_shell_needs_no_copy(host):
    base, vec = host
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1100, "height": 760})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("http://rs.test/**", lambda r: r.fulfill(content_type="application/json", body=vec) if r.request.url.endswith("/vec.json")
                   else r.fulfill(content_type="image/png", body=PNG) if ".png" in r.request.url else r.fulfill(content_type="application/json", body="{}"))
        page.route("**/*.tile.openstreetmap.org/**", lambda r: r.fulfill(content_type="image/png", body=PNG))
        page.goto(base + "/page.html")
        page.wait_for_function("window.ready === true", timeout=60_000)
        # gap 8: the panel's shell is dashboard.css (the host has no rule for #sb)
        shell = page.evaluate("""() => { const s = getComputedStyle(document.getElementById("sb")); return {position: s.position, width: s.width}; }""")
        assert shell["position"] == "fixed" and shell["width"] == "340px", shell
        # gap 3: no overlay at the start; the style that has them brings the switch (base-map box), the list (legend box) and the 3D tool, and no Layers box
        buildings = "() => rs.tools.list().find(t => t.id === 'buildings').title"
        switch = "() => { rs.tools.open('basemap'); const r = document.querySelector('.rs-bm-layers'); const out = {hidden: r.hidden, label: r.textContent.trim(), on: r.querySelector('input').checked}; rs.tools.close('basemap'); return out; }"
        assert page.evaluate("() => !document.querySelector('.ov-ctrl')") and "vector base map" in page.evaluate(buildings)       # the base map's own tool
        assert page.evaluate(switch)["hidden"]
        page.evaluate("(s) => addStyle(s)", _style())
        assert page.evaluate("() => document.querySelectorAll('.ov-ctrl').length + document.querySelectorAll('#rs-b3d').length") == 0
        assert page.evaluate(switch) == {"hidden": False, "label": "Map layers", "on": True}
        assert page.evaluate(buildings) == "Buildings in 3D"
        page.evaluate("() => { rs.tools.open('legend'); }")
        assert page.evaluate("() => document.querySelector('.rs-cb-layers .lg-row').textContent") == "Water"
        assert page.evaluate("() => getComputedStyle(document.querySelector('.rs-cb-layers .lg-sw')).boxShadow") != "none"      # the swatch has its border
        page.evaluate("() => rs.tools.close('legend')")
        # the one switch hides all the layers together; the next style has them hidden too
        page.evaluate("() => rsSetOverlays(false)")
        page.evaluate("(s) => addStyle(s)", _style())
        assert page.evaluate("() => map.getLayoutProperty('rs-ov0-fill', 'visibility')") == "none"
        assert not page.evaluate(switch)["on"]
        page.evaluate("() => rsSetOverlays(true)")
        assert page.evaluate("() => map.getLayoutProperty('rs-ov0-fill', 'visibility')") == "visible"
        page.evaluate("() => rsSetBuildings3D(true)")
        assert page.evaluate("() => map.getLayoutProperty('rs-ov0-3d', 'visibility')") == "visible"
        page.evaluate("(s) => addStyle(s)", _style(overlays=False))
        assert page.evaluate(switch)["hidden"]
        assert "vector base map" in page.evaluate(buildings)           # the base map's own tool again
        # gap 4: a raster base map goes under the roads of the page, which have the prefix
        page.evaluate("() => rsSetBasemap('osm')")
        order = page.evaluate("() => map.getStyle().layers.map(l => l.id)")
        assert order.index("basemap") < order.index("rs-roads"), order
        assert page.evaluate("() => map.getLayoutProperty('basemap', 'visibility')") == "visible"
        # gap 7: a vector base map brings its sprite, and the raster map takes the map's own back
        page.evaluate("() => rsSetBasemap('vec')")
        page.wait_for_function("map.getStyle().sprite === 'http://rs.test/vsprite'")
        page.evaluate("() => rsSetBasemap('osm')")
        page.wait_for_function("map.getStyle().sprite === 'http://rs.test/own'")
        # gap 6: whoever asks, the dark theme gets the dark twin
        page.evaluate("() => rsSetTheme('dark')")
        page.evaluate("() => rsSetBasemap('blank')")
        assert page.evaluate("() => RS_BASEMAPS.find(b => b.key === 'blank_dark') && map.getPaintProperty('bg', 'background-color')") == "#14181d"
        # gap 11: a tool is found by its id, before and after the first hover
        tool = "[data-rs-tool='basemap']"
        assert page.locator(tool).count() == 1
        page.hover(tool + " , " + tool + " button")
        page.wait_for_selector("#rs-tip:not([hidden])", timeout=3000)
        page.mouse.move(5, 5)
        assert page.locator(tool).count() == 1
        browser.close()
    assert not errors, errors


def test_boxes_stay_inside_a_phone_and_the_sheet_and_the_free_part_of_the_map_are_known(host):
    base, vec = host
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 390, "height": 844})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("http://rs.test/**", lambda r: r.fulfill(content_type="image/png", body=PNG) if ".png" in r.request.url else r.fulfill(content_type="application/json", body="{}"))
        page.goto(base + "/page.html")
        page.wait_for_function("window.ready === true", timeout=60_000)
        for tool, box in (("basemap", ".bm-menu"), ("attribution", "#rs-attr-box"), ("settings", "#rs-settings-box"), ("navigate", "#rs-nav-box")):
            page.evaluate("(t) => rs.tools.open(t)", tool)
            page.wait_for_timeout(300)
            r = page.evaluate("(b) => { const r = document.querySelector(b).getBoundingClientRect(); return {left: r.left, right: r.right}; }", box)
            assert r["left"] >= 11 and r["right"] <= 390 - 11, (tool, r)
            page.evaluate("(t) => rs.tools.close(t)", tool)
        # gap 10: the sheet is at the bottom, and the free part of the map ends at its upper edge
        heights = {}
        for n in (0, 1, 2):
            page.evaluate("(n) => rs.sheet(n)", n)
            page.wait_for_timeout(200)
            heights[n] = page.evaluate("() => ({sheet: rs.sheet(), bottom: rs.freeArea().bottom, top: rs.freeArea().top})")
        browser.close()
    assert not errors, errors
    assert [heights[n]["sheet"] for n in (0, 1, 2)] == [0, 1, 2], heights
    assert heights[0]["bottom"] > heights[1]["bottom"] > heights[2]["bottom"], heights
    assert heights[1]["bottom"] < 844 * 0.7 and heights[0]["bottom"] > 844 - 60 and heights[1]["top"] > 40, heights


def _engine_style():
    """The tiled style that a host's map worker makes (roadstyle-wasm's styleSources and tilesOfSources; here the same engine through the Python binding): Monaco's roads
    and base-map rows, a live look with the colour options, the tunnel control and the arrows. Its tiles are served by the test."""
    import pyarrow.parquet as pq

    from roadstyle import _engine
    if not _engine.available():
        pytest.skip("no roadstyle._rust")
    data = ROOT / "rust" / "roadstyle-rs" / "tests" / "data"
    rust = _engine.rust()
    look = rust.Look.from_json((data / "look.json").read_text())
    for key, value in {"state": '"live"', "color_options": '{"Road class": {}}', "tunnel_control": "true", "arrows": "true"}.items():
        look = look.with_arg(key, value)
    sources = rust.style_sources(pq.read_table(data / "monaco" / "roads.parquet"), look, pq.read_table(data / "monaco" / "features.parquet"), None, "monaco")
    style, tiler = sources.tile_stage(None, None, [], json.dumps({"tiles": ["http://rs.test/t/{z}/{x}/{y}"]}))
    return json.loads(style), tiler


# what the page finds with a style of the engine: each box, tool and global that follows the style (rs.setStyle), and goes with a style that has none
_TOOLS = """() => ({
  roads: [...document.querySelectorAll('.flt-ctrl label')].map(l => l.textContent.trim()),
  roadsOff: [...document.querySelectorAll('.flt-ctrl input')].filter(i => !i.checked).length,
  floating: document.querySelectorAll('.ov-ctrl').length, switchShown: !document.querySelector('.rs-bm-layers').hidden,
  layers: (() => { rs.tools.open('legend'); const l = [...document.querySelectorAll('.rs-cb-layers .lg-row')].map(r => r.textContent.trim()); rs.tools.close('legend'); return l; })(),
  tunnel: !!document.querySelector('.tn-ctrl #tn-pre'),
  legend: !rs.tools.list().find(t => t.id === 'legend').disabled,
  classes: window.RS_CLASSES.length, arrowImage: map.hasImage('oneway'), colourOptions: window.RS_COLOR_OPTIONS.length,
})"""


def test_every_control_that_a_style_gives_follows_a_later_style_of_the_engine(host):
    base, vec = host
    style, tiler = _engine_style()
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1100, "height": 760})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        def serve(route):
            url = route.request.url
            if "/t/" in url:
                z, x, y = (int(v) for v in url.rsplit("/t/", 1)[1].split("?")[0].split("/"))
                route.fulfill(content_type="application/x-protobuf", body=bytes(tiler.tile(z, x, y)))
            elif ".png" in url:
                route.fulfill(content_type="image/png", body=PNG)
            else:
                route.fulfill(content_type="application/json", body="{}")
        page.route("http://rs.test/**", serve)
        page.goto(base + "/page.html")
        page.wait_for_function("window.ready === true", timeout=60_000)
        start = page.evaluate(_TOOLS)
        assert not start["roads"] and not start["layers"] and not start["switchShown"] and not start["tunnel"] and not start["legend"] and not start["arrowImage"], start
        page.evaluate("(s) => addStyle(s)", style)
        page.wait_for_selector(".flt-ctrl")
        page.wait_for_function("map.hasImage('oneway')", timeout=20_000)
        first = page.evaluate(_TOOLS)
        assert "primary" in first["roads"] and first["classes"] > 3, first
        assert "buildings" in first["layers"] and len(first["layers"]) == 17 and first["floating"] == 0 and first["switchShown"] and first["tunnel"] and first["legend"] and first["colourOptions"] == 1, first
        # a class that the person switched off stays off with the next style, and the box has it unchecked
        page.evaluate("() => rsSetClasses(RS_CLASSES.filter(c => c !== 'primary'))")
        page.evaluate("(s) => addStyle(s)", style)
        page.wait_for_selector(".flt-ctrl")
        again = page.evaluate(_TOOLS)
        assert again["roadsOff"] == 1 and again["roads"] == first["roads"] and again["layers"] == first["layers"], (first, again)
        # a style with none of the controls takes every one of them away
        page.evaluate("(s) => addStyle(s)", _style(overlays=False))
        gone = page.evaluate(_TOOLS)
        assert not gone["roads"] and not gone["layers"] and not gone["switchShown"] and not gone["tunnel"] and not gone["legend"] and gone["classes"] == 0, gone
        browser.close()
    assert not errors, errors


def test_the_boundary_follows_a_later_style(host):
    base, vec = host
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1100, "height": 760})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("http://rs.test/**", lambda r: r.fulfill(content_type="image/png", body=PNG) if ".png" in r.request.url else r.fulfill(content_type="application/json", body="{}"))
        page.goto(base + "/page.html?boundary=1")
        page.wait_for_function("window.ready === true", timeout=60_000)
        min_zoom = page.evaluate("() => map.getMinZoom()")
        with_boundary = _style(overlays=False)
        with_boundary["sources"]["boundary"] = {"type": "geojson", "data": SQUARE}
        with_boundary["layers"].append({"id": "boundary", "type": "line", "source": "boundary", "paint": {"line-color": "#333"}})
        page.evaluate("(s) => addStyle(s)", with_boundary)
        page.wait_for_function("!!map.getLayer('rs-boundary-dim') && map.getMinZoom() > 0")      # the shade and the limit of the style's boundary
        page.evaluate("(s) => addStyle(s)", _style(overlays=False))
        assert page.evaluate("() => !map.getLayer('rs-boundary-dim') && !map.getSource('rs-boundary-dim')")
        assert page.evaluate("() => map.getMinZoom()") == min_zoom           # a style with no boundary takes the limit away
        browser.close()
    assert not errors, errors


def test_the_boxes_with_the_layers_stay_inside_a_phone(host):
    base, vec = host
    style, tiler = _engine_style()
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 390, "height": 844})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("http://rs.test/**", lambda r: r.fulfill(content_type="application/x-protobuf", body=bytes(tiler.tile(*(int(v) for v in r.request.url.rsplit("/t/", 1)[1].split("?")[0].split("/")))))
                   if "/t/" in r.request.url else r.fulfill(content_type="image/png", body=PNG) if ".png" in r.request.url else r.fulfill(content_type="application/json", body="{}"))
        page.goto(base + "/page.html")
        page.wait_for_function("window.ready === true", timeout=60_000)
        page.evaluate("(s) => addStyle(s)", style)
        page.wait_for_selector(".flt-ctrl")
        seen = {}
        for tool, box in (("basemap", ".bm-menu"), ("legend", "#rs-color-box")):
            page.evaluate("(t) => rs.tools.open(t)", tool)
            page.wait_for_timeout(300)
            seen[tool] = page.evaluate("(b) => { const r = document.querySelector(b).getBoundingClientRect(); return {left: r.left, right: r.right, top: r.top, bottom: r.bottom, scrolls: document.querySelector(b).scrollHeight > document.querySelector(b).clientHeight + 1}; }", box)
            page.evaluate("(t) => rs.tools.close(t)", tool)
        browser.close()
    assert not errors, errors
    for tool, r in seen.items():
        assert r["left"] >= 11 and r["right"] <= 390 - 11 and r["top"] >= 0 and r["bottom"] <= 844 - 11, (tool, r)
