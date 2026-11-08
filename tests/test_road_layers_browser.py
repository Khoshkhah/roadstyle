"""roadLayers (dashboard/roadlayers.js, docs/design/level_part.md, step d): the roads of a page on its map and the swap of their style, with a stub of
MapLibre's map (the calls that the helper makes), in a real browser for `Image`. The design editor page uses it too (test_design_edit_browser.py)."""
import contextlib
import functools
import http.server
import threading
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "rust/roadstyle-assets/files/static"

_PAGE = """<!doctype html><html><body><script type="module">
import {roadLayers} from "/dashboard/roadlayers.js";
// a stub of the map: the layers, the sources, the images and the global state that the helper reads and writes, in order
const log = [];
const map = {
  _layers: [{id: "area-fill", type: "fill", source: "base"}, {id: "rs-low-fill", type: "fill", source: "rs-low"}], _sources: {base: {type: "vector"}, "rs-low": {type: "vector", tiles: ["t://low/{z}"]}},
  _images: new Set(), _state: {rs_theme: "dark"}, _listeners: [],
  getStyle() { return {layers: [...this._layers], sources: {...this._sources}}; },
  getLayer(id) { return this._layers.find(l => l.id === id); },
  getSource(id) { return this._sources[id] && {setTiles: (t) => log.push(["setTiles", id, t])}; },
  addLayer(l, before) { log.push(["addLayer", l.id, before ?? null]); const i = before ? this._layers.findIndex(x => x.id === before) : -1; i >= 0 ? this._layers.splice(i, 0, l) : this._layers.push(l); },
  removeLayer(id) { log.push(["removeLayer", id]); this._layers = this._layers.filter(l => l.id !== id); },
  addSource(id, s) { log.push(["addSource", id]); this._sources[id] = s; },
  removeSource(id) { log.push(["removeSource", id]); delete this._sources[id]; },
  hasImage(id) { return this._images.has(id); }, addImage(id) { log.push(["addImage", id]); this._images.add(id); }, removeImage(id) { log.push(["removeImage", id]); this._images.delete(id); },
  getGlobalState() { return this._state; }, setGlobalStateProperty(k, v) { log.push(["state", k, v]); this._state[k] = v; },
  once(ev, f) { if(ev === "idle") setTimeout(f, 0); },
};
const dash = {styles: [], setStyle(s) { this.styles.push(s.layers.length); }};
const png = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='4' height='4'/>";
const style = (n) => ({sources: {roads: {type: "vector", tiles: ["t://roads/{z}"]}}, state: {rs_theme: {default: "light"}, rs_mode: {default: 7}},
  metadata: {"roadstyle:images": {arrow: {url: png, sdf: true, pixelRatio: 2}}},
  layers: Array.from({length: n}, (_, i) => ({id: "r" + i, type: "line", source: "roads", layout: {"icon-image": "arrow"}}))});
window.run = async () => {
  const out = {};
  const roads = roadLayers({map, dashboard: dash, prefix: "rs-", before: "area-fill", also: ["rs-low-"]});
  out.first = await roads.show(style(2));
  out.layersAfterFirst = map._layers.map(l => l.id);
  out.sources = Object.keys(map._sources);
  out.images = roads.images;
  out.state = map._state;                                          // a name that the map has keeps its value; a new name gets its start value
  out.iconName = map.getLayer("rs-r0").layout["icon-image"];       // the image name has the prefix
  out.before = log.find(e => e[0] === "addLayer" && e[1] === "rs-r0")[2];
  await roads.show(style(3), {after: async (st) => { log.push(["after", st.layers.length]); }});
  out.layersAfterSecond = map._layers.map(l => l.id);               // the old road layers went, and the page's own copy (also) went with them
  out.dashStyles = dash.styles;
  out.afterCalled = log.some(e => e[0] === "after" && e[1] === 3);
  log.length = 0;
  await roads.reloadTiles({timeout: 50});
  out.reload = log.filter(e => e[0] === "setTiles").map(e => e[1]);
  roads.remove();
  out.removed = [map._layers.map(l => l.id), Object.keys(map._sources), roads.layers, roads.sources];
  return out;
};
window.ready = true;
</script></body></html>"""


class _H(http.server.SimpleHTTPRequestHandler):
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
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_H, directory=str(STATIC)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}/t.html"
    finally:
        srv.shutdown()


def test_road_layers_show_swap_reload_and_remove_the_roads_of_a_page():
    with served() as url, pw.sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.wait_for_function("window.ready", timeout=30000)
        got = page.evaluate("window.run()")
        assert got["first"] == {"layers": ["rs-r0", "rs-r1"], "sources": ["rs-roads"]}, got
        # the road layers are under "area-fill", the page's own copy "rs-low-fill" (also) went at the first show too
        assert got["layersAfterFirst"] == ["rs-r0", "rs-r1", "area-fill"] and got["before"] == "area-fill", got
        assert got["sources"] == ["base", "rs-roads"] and got["images"] == ["rs-arrow"] and got["iconName"] == "rs-arrow", got
        assert got["state"] == {"rs_theme": "dark", "rs_mode": 7}, got
        assert got["layersAfterSecond"] == ["rs-r0", "rs-r1", "rs-r2", "area-fill"] and got["dashStyles"] == [2, 3] and got["afterCalled"], got
        assert got["reload"] == ["rs-roads"], got
        assert got["removed"] == [["area-fill"], ["base"], [], []], got
        assert not errors, errors
        b.close()
