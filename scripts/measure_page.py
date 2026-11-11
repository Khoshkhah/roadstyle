"""The memory of the tab of any roadstyle page, and a picture of it with every overlay layer on (docs/design/memory_budget.md, "Step 1").
    python scripts/measure_page.py <page.html> <picture prefix> [--zoom 16] [--center LON,LAT]
Same method as measure_memory.py: the private memory of the renderer processes that this program started (smaller view: 640 x 400, so that
two runs are the same size). The picture is `<prefix>-z<zoom>.png`; compare two pictures of the same view with a pixel diff.
Prints one JSON line: the tab after the load (the overlays still as the page has them), the tab after the view with every overlay layer on.
Linux only (it reads /proc)."""
import functools
import glob
import http.server
import json
import os
import re
import sys
import threading

from playwright.sync_api import sync_playwright

args = [a for a in sys.argv[1:] if not a.startswith("--")]
opt = {a.split("=")[0]: a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
page_file, prefix = args[0], args[1]
zoom = float(opt.get("--zoom", 16))
root = os.path.dirname(os.path.abspath(page_file))


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=root))
threading.Thread(target=srv.serve_forever, daemon=True).start()


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


with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    page = b.new_page(viewport={"width": 640, "height": 400})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"http://127.0.0.1:{srv.server_address[1]}/{os.path.basename(page_file)}")
    page.wait_for_function("window.map && window.map.loaded && window.map.loaded()", timeout=900_000)
    page.wait_for_timeout(4000)
    out: dict = {"tab_loaded_MiB": tab_mib()}
    center = [float(v) for v in opt["--center"].split(",")] if "--center" in opt else page.evaluate("() => { const c = map.getCenter(); return [c.lng, c.lat]; }")
    page.evaluate("""() => { for(const o of OVERLAYS){ o.visible = true; for(const id of o.layers) if(map.getLayer(id)) map.setLayoutProperty(id, 'visibility', 'visible'); } }""")
    page.evaluate(f"() => map.jumpTo({{center: {json.dumps(center)}, zoom: {zoom}, pitch: 0, bearing: 0}})")
    page.wait_for_timeout(4000)
    try:
        page.wait_for_function("map.loaded()", timeout=60_000)
    except Exception:
        print("the map was still loading at the picture", file=sys.stderr)
    page.wait_for_timeout(1500)
    page.screenshot(path=f"{prefix}-z{zoom:g}.png")
    out[f"tab_z{zoom:g}_MiB"] = tab_mib()
    out["errors"] = errors[:5]
    print(json.dumps(out))
    b.close()
