"""LiveMap.setLook in a browser (docs/design/restyle_without_retile.md, D6): a map draws the tiles of a LiveMap (the wasm package), the roads
get live colours (the feature state rs_c, as rs.setData and rsColor write it), and a theme-like change of colours goes through setLook and
MapLibre's setStyle with diff. The map then requests no tile again, keeps its sources, keeps the live colours, shows the new colours, and gives
no error. A change of structure gives no style (undefined): the host makes a new map. Needs Playwright and the web package
(rust/roadstyle-wasm/build_editor.sh), as test_binding's wasm test."""
import functools
import http.server
import json
import os
import shutil
import threading
from pathlib import Path

import pytest

from roadstyle import _engine
from roadstyle.render_web import _asset

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "rust/roadstyle-rs/tests/data"
PKG = Path(os.environ.get("CARGO_TARGET_DIR") or ROOT / "rust" / "target") / "editor-pkg"


def _look_json():
    """The saved look of the theme liberty with the duckOSM page's options (a colour option by class, the access column, the live state)."""
    o = {"args": {"color_options": {"Road class": {}}, "access_col": "access", "arrows": True, "labels": True, "state": "live"},
         "base_map": {"mode": "all", "theme": "liberty", "paths": "google"}}
    return json.loads(_engine.rust().resolve_look(json.dumps(o)).json())


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def _recolour(v, f):
    """Each colour #rrggbb in v changed by f."""
    if isinstance(v, str) and len(v) == 7 and v.startswith("#"):
        try:
            r, g, b = (int(v[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            return v
        return "#%02x%02x%02x" % f(r, g, b)
    if isinstance(v, list):
        return [_recolour(x, f) for x in v]
    if isinstance(v, dict):
        return {k: _recolour(x, f) for k, x in v.items()}
    return v


PAGE = """<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="maplibre-gl.css"><script src="maplibre-gl.js"></script>
<div id="m" style="width:900px;height:700px"></div>
<script type="module">
import init, { Look, styleSources, LiveMap } from "./pkg/roadstyle_wasm.js";
const errors = [];
const step = (s) => { window.step = s; console.log("step: " + s); };
const idle = (map) => new Promise((ok) => { map.once("idle", ok); setTimeout(ok, 15000); });
try {
  step("init");
  await init();
  const roads = new Uint8Array(await (await fetch("roads.parquet")).arrayBuffer());
  const [a, b, c] = await Promise.all(["a.json", "b.json", "c.json"].map((u) => fetch(u).then((r) => r.text())));
  const la = Look.fromJson(a);
  // a name: a style with none has "name": null, which MapLibre's style check refuses (the duckOSM page gives the area's name)
  const live = new LiveMap(styleSources(roads, la, undefined, undefined, "Monaco"), la, "rs://1/", []);
  let requests = 0;
  maplibregl.addProtocol("rs", async (p) => {
    requests++;
    const [src, z, x, y] = p.url.slice("rs://1/".length).split("?")[0].split("/");
    return { data: live.tile(src, +z, +x, +y, undefined) };
  });
  step("map");
  const map = new maplibregl.Map({ container: "m", style: JSON.parse(live.style(undefined)) });
  map.on("error", (e) => { errors.push(String(e.error && e.error.message)); console.log("map error: " + errors[errors.length - 1]); });
  await new Promise((ok) => { map.once("load", ok); setTimeout(ok, 30000); });
  step("loaded: " + map.loaded());
  await idle(map);
  const feats = map.querySourceFeatures("roads", { sourceLayer: "simple" }).filter((f) => f.id != null);
  const ids = [...new Set(feats.map((f) => f.id))].slice(0, 20);
  for (const id of ids) map.setFeatureState({ source: "roads", sourceLayer: "simple", id }, { rs_c: "#ff00ff" });
  await idle(map);
  const sourcesBefore = Object.keys(map.getStyle().sources);
  const before = requests;
  step("setLook");
  const style = live.setLook(Look.fromJson(b), undefined);
  if (style !== undefined) map.setStyle(JSON.parse(style), { diff: true });
  await idle(map);
  const structure = live.setLook(Look.fromJson(c), undefined);
  window.result = {
    kept: style !== undefined, tiles: ids.length, newRequests: requests - before,
    sourcesBefore, sourcesAfter: Object.keys(map.getStyle().sources),
    state: ids.map((id) => (map.getFeatureState({ source: "roads", sourceLayer: "simple", id }) || {}).rs_c),
    colour: JSON.stringify(map.getPaintProperty("roads-simple", "line-color")),
    structureKept: structure !== undefined, errors,
  };
} catch (e) {
  window.result = { failed: String(e && e.stack || e), errors };
}
</script>"""


def test_set_look_keeps_the_tiles_the_sources_and_the_live_colours(tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    if not (PKG / "roadstyle_wasm.js").exists():
        pytest.skip("no web package (rust/roadstyle-wasm/build_editor.sh)")
    a = _look_json()
    b = dict(a)      # every colour of the look as a theme has them: not the user's data colours (map, data, overlays)
    for k, v in a.items():
        if k not in ("map", "data", "overlays"):
            b[k] = _recolour(v, lambda r, g, bl: (bl, r, g))
    c = json.loads(json.dumps(a))      # structure: the first zoom of every class 2 later
    for e in c["roads"]["classes"].values():
        e["minzoom"] = (e.get("minzoom") or 0) + 2
    shutil.copytree(PKG, tmp_path / "pkg")
    shutil.copyfile(DATA / "monaco_part/roads.parquet", tmp_path / "roads.parquet")
    for name, look in (("a", a), ("b", b), ("c", c)):
        (tmp_path / f"{name}.json").write_text(json.dumps(look))
    (tmp_path / "maplibre-gl.js").write_text(_asset("maplibre-gl.js"))
    (tmp_path / "maplibre-gl.css").write_text(_asset("maplibre-gl.css"))
    (tmp_path / "index.html").write_text(PAGE)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html")
            page.wait_for_function("window.result", timeout=120_000)
            r = page.evaluate("window.result")
            browser.close()
    finally:
        server.shutdown()
    assert "failed" not in r, r.get("failed")
    new_colour = _recolour(_look_json()["settings"]["palettes"][a["palette"]]["primary"]["fill"], lambda r_, g, bl: (bl, r_, g))
    assert r["kept"], "a change of colours keeps the tiles"
    assert r["tiles"] > 0 and r["newRequests"] == 0, f"no tile is requested again ({r['newRequests']} requests)"
    assert r["sourcesAfter"] == r["sourcesBefore"], "no source is removed or added"
    assert r["state"] == ["#ff00ff"] * r["tiles"], "the live colours stay"
    assert new_colour in r["colour"], "the road layer has the new class colours"
    assert not r["structureKept"], "a change of structure needs a new map"
    assert not r["errors"], r["errors"]
