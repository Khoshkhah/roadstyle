"""The memory of a roadstyle page by part (docs/design/memory_budget.md, "Step 0: the memory of a page"), in headless Chromium.
    python scripts/measure_memory.py <area.duckdb | page.html> [--probe]
A duckOSM file gives the page of roadstyle.duckosm.page(db, dashboard=True, live_data=True). Linux only (it reads /proc).
The tab: the private memory of the renderer processes that this program started (smaps_rollup). The JS heaps: the page's and each worker's,
by the DevTools protocol. A part: what the tab and the heaps give back when the page lets it go (live data, the overlays, the road table)."""
import functools
import glob
import http.server
import json
import os
import re
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

page_file = sys.argv[1]
if page_file.endswith(".duckdb"):
    import roadstyle.duckosm
    html = os.path.join(tempfile.mkdtemp(), os.path.basename(page_file).removesuffix(".duckdb") + ".html")
    roadstyle.duckosm.page(page_file, dashboard=True, live_data=True).save(html)
    page_file = html
root = os.path.dirname(os.path.abspath(page_file))


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=root))
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}/{os.path.basename(page_file)}"


def mine(pid):
    while pid > 1:
        pid = int(open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[1])
        if pid == os.getpid():
            return True
    return False


def tab_mib():
    tot = 0
    for d in glob.glob("/proc/[0-9]*"):
        try:
            if b"--type=renderer" not in open(d + "/cmdline", "rb").read() or not mine(int(d[6:])):
                continue
            tot += sum(int(x) for x in re.findall(r"Private_(?:Clean|Dirty):\s+(\d+)", open(d + "/smaps_rollup").read()))
        except OSError:
            pass
    return round(tot / 1024)


class Heaps:
    """The JS heap of the page and of each worker, by the DevTools protocol of the browser (Target.sendMessageToTarget)."""
    def __init__(self, browser, page):
        self.cdp, self.page, self.answers, self.n = browser.new_browser_cdp_session(), page, {}, 0
        self.cdp.on("Target.receivedMessageFromTarget", lambda e: self.answers.update({(e["sessionId"], json.loads(e["message"]).get("id")): json.loads(e["message"])}))
        self.sessions = {}

    def call(self, sid, method, params=None):
        self.n += 1
        self.cdp.send("Target.sendMessageToTarget", {"sessionId": sid, "message": json.dumps({"id": self.n, "method": method, "params": params or {}})})
        for _ in range(600):
            if (sid, self.n) in self.answers:
                return self.answers.pop((sid, self.n)).get("result", {})
            self.page.wait_for_timeout(50)
        raise TimeoutError(method)

    def __call__(self):
        out = {"page": 0, "workers": 0, "n_workers": 0}
        for t in self.cdp.send("Target.getTargets")["targetInfos"]:
            if t["type"] not in ("page", "worker"):
                continue
            sid = self.sessions.get(t["targetId"]) or self.sessions.setdefault(t["targetId"], self.cdp.send("Target.attachToTarget", {"targetId": t["targetId"], "flatten": False})["sessionId"])
            self.call(sid, "HeapProfiler.collectGarbage")
            used = self.call(sid, "Runtime.getHeapUsage")["usedSize"]
            if t["type"] == "page":
                out["page"] += used
            else:
                out["workers"] += used
                out["n_workers"] += 1
        for k in ("page", "workers"):
            out[k] = round(out[k] / 2 ** 20)
        return out


def measure(page, label):
    page.wait_for_timeout(1500)
    m = HEAPS()
    m["tab"] = tab_mib()
    print(f"{label:<34} tab {m['tab']:>5} MiB | JS heap: page {m['page']:>4}, workers {m['workers']:>4} ({m['n_workers']})", flush=True)
    return m


with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    page = b.new_page(viewport={"width": 1280, "height": 800})
    page.on("pageerror", lambda e: print("page error:", e))
    page.goto(url)
    HEAPS = Heaps(b, page)
    page.wait_for_function("window.RS_SIDE && window.map && window.map.loaded && window.map.loaded()", timeout=300_000)
    page.wait_for_timeout(5000)
    page.wait_for_function("window.map.loaded()", timeout=300_000)
    if "--probe" in sys.argv:
        print(page.evaluate("""() => ({O: typeof O, OVERLAYS: typeof OVERLAYS, RoadTable: typeof RoadTable, rs: typeof rs, setData: typeof (window.rs && rs.setData),
          table: typeof O !== 'undefined' && !!O.road_table, edge: typeof O !== 'undefined' && O.edge_id_col,
          sources: Object.entries(map.getStyle().sources).map(([k, s]) => [k, s.type])})"""))
        sys.exit()
    facts = page.evaluate("""() => ({roads: RoadTable.rows(), overlays: OVERLAYS.length,
      overlay_features: OVERLAYS.reduce((n, o) => n + _sfeats(o.source).length, 0),
      road_table_json_MiB: +(JSON.stringify(_side()).length / 2 ** 20).toFixed(1),
      overlay_geojson_MiB: +(OVERLAYS.reduce((n, o) => n + JSON.stringify(_sdata(map.getSource(o.source)) || {}).length, 0) / 2 ** 20).toFixed(1),
      html_MiB: +(document.documentElement.outerHTML.length / 2 ** 20).toFixed(1)})""")
    print(os.path.basename(page_file), facts)
    base = measure(page, "loaded")
    # live data: one value for each road (rs.setData), then cleared
    page.evaluate("""async () => { const n = RoadTable.rows(), rows = [];
      for (let i = 0; i < n; i++) { const p = RoadTable.own(i); if (p && p[O.edge_id_col] != null) rows.push({[O.edge_id_col]: String(p[O.edge_id_col]), v: Math.random() * 100}); }
      await rs.setData(rows, {colorBy: "v"}); }""")
    live = measure(page, "+ live data, 1 value each road")
    page.evaluate("() => rs.clearData()")
    measure(page, "live data cleared")
    # the overlays: their layers and GeoJSON sources go
    page.evaluate("""() => { const st = map.getStyle(), srcs = new Set(OVERLAYS.map(o => o.source));
      for (const l of st.layers) if (srcs.has(l.source)) map.removeLayer(l.id);
      for (const s of srcs) if (map.getSource(s)) map.removeSource(s); }""")
    page.wait_for_timeout(3000)
    no_ov = measure(page, "- overlays (layers and sources)")
    # the road table: the page lets it go
    page.evaluate("() => { O.road_table = null; window.RS_SIDE = null; }")
    no_tab = measure(page, "- road table")
    print("parts (MiB):", json.dumps({"live data": {"page": live["page"] - base["page"], "workers": live["workers"] - base["workers"], "tab": live["tab"] - base["tab"]},
          "overlays": {"page": base["page"] - no_ov["page"], "workers": base["workers"] - no_ov["workers"], "tab": base["tab"] - no_ov["tab"]},
          "road table": {"page": no_ov["page"] - no_tab["page"], "tab": no_ov["tab"] - no_tab["tab"]}}))
    b.close()
