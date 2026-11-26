"""Measure what MapLibre's main thread unpacks for each tile, on a page with many hidden overlays (tiles=True, lazy_overlays=True).

MapLibre's worker sends each tile to the main thread as a tree of objects, which the main thread walks again (`deserialize`) before the
tile shows. This script counts those objects for each tile of the `roads` source during zooms and a pan, and sums the main thread's long
tasks (> 50 ms). Run it with the roadstyle that you want to measure (the installed one, or PYTHONPATH=<checkout>/src):

    python scripts/measure_tile_messages.py                 # 300 hidden overlays
    python scripts/measure_tile_messages.py --overlays 1200

Needs playwright and its Chromium. Headless Chromium draws with SwiftShader: read the objects and the long tasks, not the frame times.
"""
import argparse
import statistics
import tempfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, box

import roadstyle as rs

# count the objects of each tile result that a worker sends (what MapLibre's deserialize walks), by the source of the tile
INIT = r"""
window.__tiles = [];
const W = window.Worker;
window.Worker = function(...a){
  const w = new W(...a), asked = {}, post = w.postMessage.bind(w);
  w.postMessage = (m, ...r) => { if(m && m.id && m.data && m.data.source) asked[m.id] = m.type + ":" + m.data.source; return post(m, ...r); };
  w.addEventListener("message", ev => {
    const m = ev.data, what = m && asked[m.id]; if(!what) return; delete asked[m.id];
    let n = 0;
    const walk = v => { if(v === null || typeof v !== "object" || ArrayBuffer.isView(v) || v instanceof ArrayBuffer || v instanceof ImageBitmap) return;
      n++; if(Array.isArray(v)) v.forEach(walk); else for(const k in v) walk(v[k]); };
    walk(m.data);
    if(m.data && m.data.buckets) __tiles.push([what, n]);
  });
  return w;
};
window.Worker.prototype = W.prototype;
window.__lt = [];
new PerformanceObserver(l => { for(const e of l.getEntries()) __lt.push(e.duration); }).observe({entryTypes: ["longtask"]});
"""


def _roads(n=30):
    """A grid of n x n named streets, about 2 km wide."""
    lines, names = [], []
    for i in range(n):
        x, y = 18.04 + i * 1.2e-3, 59.30 + i * 6e-4
        lines += [LineString([(x, 59.30), (x, 59.30 + n * 6e-4)]), LineString([(18.04, y), (18.04 + n * 1.2e-3, y)])]
        names += [f"Street {i}", f"Road {i}"]
    return gpd.GeoDataFrame({"highway": ["residential"] * len(lines), "name": names}, geometry=lines, crs=4326)


def _zones(k=40):
    return gpd.GeoDataFrame({"v": list(range(k))}, geometry=[box(18.04 + i * 9e-4, 59.305, 18.0405 + i * 9e-4, 59.3055) for i in range(k)], crs=4326)


def _serve(page, folder):
    """The page and its files at an http address that answers range requests (the overlays' archives need them)."""
    def serve(route):
        body, r = (folder / route.request.url.split("//rs.test/", 1)[1]).read_bytes(), route.request.headers.get("range")
        if r:
            a, b = map(int, r.removeprefix("bytes=").split("-"))
            part = body[a:b + 1]
            route.fulfill(status=206, body=part, headers={"Content-Range": f"bytes {a}-{a + len(part) - 1}/{len(body)}",
                                                          "Content-Length": str(len(part)), "Content-Type": "application/octet-stream"})
        else:
            route.fulfill(body=body, content_type="text/html" if route.request.url.endswith(".html") else "application/octet-stream")
    page.route("http://rs.test/**", serve)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--overlays", type=int, default=300, help="hidden overlays on the page")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    folder = Path(tempfile.mkdtemp())
    overlays = [rs.Overlay(_zones(), kind="fill", label="shown")]
    overlays += [rs.Overlay(_zones(), kind="fill", label=f"hidden {i}", visible=False) for i in range(args.overlays)]
    rs.render_dashboard(_roads(), basemap="blank", lazy_overlays=True, overlays=overlays).save(folder / "m.html")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(INIT)
        _serve(page, folder)
        page.goto("http://rs.test/m.html")
        page.wait_for_function("window.map && map.loaded() && map.areTilesLoaded()", timeout=120_000)
        keys = page.evaluate("Object.keys(map.getGlobalState()).length")
        page.evaluate("map.jumpTo({zoom: 17}); __tiles = []; __lt = []")
        for move in ["map.zoomTo(15, {duration: 800})", "map.zoomTo(13, {duration: 800})", "map.panBy([500, 0], {duration: 800})",
                     "map.zoomTo(16, {duration: 800})"]:
            page.evaluate(f"new Promise(r => {{ {move}; map.once('moveend', () => r()); }})")  # not r: Playwright would copy the event and its map
            page.wait_for_function("map.loaded() && map.areTilesLoaded() && !map.isMoving()", polling=50, timeout=60_000)
        tiles, lt = page.evaluate("__tiles"), page.evaluate("__lt")
        browser.close()
    roads = [n for what, n in tiles if what.endswith(":roads")]
    print(f"roadstyle {rs.__version__} from {Path(rs.__file__).parent}")
    print(f"hidden overlays {args.overlays}, global state keys {keys}")
    print(f"roads tiles {len(roads)}, objects per tile: median {statistics.median(roads):,.0f}, sum {sum(roads):,}")
    print(f"main-thread long tasks: {len(lt)}, sum {sum(lt):.0f} ms")


if __name__ == "__main__":
    main()
