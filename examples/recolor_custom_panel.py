"""Sample: embed roadstyle in your own page and INJECT A CUSTOM PANEL that recolours the map.

Run it::

    python examples/recolor_custom_panel.py        # writes examples/custom_panel_sample.html

It shows the canonical embedding path (Leaflet + roadstyle.js + a spec), then uses the public
client-side API to build a *custom* UI instead of the built-in "Colour by" dropdown:

  * ``addPanel(...)``      — your own DOM in a styled, auto-stacking panel;
  * ``setColorField(...)`` — recolour the roads to a baked "colour by" option, no server round-trip;
  * the event bus          — ``colorchange`` keeps the buttons in sync; ``select`` / ``deselect``
                             feed a live readout panel.

The colour options are baked in Python by ``to_spec(color_options=...)`` over a neutral ``mono``
base so the data ramps stand out.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import geopandas as gpd

import roadstyle as rs
from roadstyle.emit import _asset  # reads the bundled roadstyle.js / roadstyle.css

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# 1. data — the repo's example edges + seeded AADT/speed so the ramps look real
g = gpd.read_file(REPO / "notebooks" / "data" / "sundbyberg_edges.gpkg")
random.seed(7)
g["aadt"] = [random.randint(200, 24000) for _ in range(len(g))]
g["speed_kph"] = [random.choice([30, 40, 50, 60, 70]) for _ in range(len(g))]

# 2. spec — mono base so the data ramps stand out; three "colour by" options
spec = rs.to_spec(
    g, basemap="dark_matter", palette="mono",
    color_options={
        "Class": {},
        "AADT": {"color_by": "aadt", "cmap": "viridis"},
        "Speed": {"color_by": "speed_kph", "cmap": "magma"},
    },
    tooltip=["highway", "aadt", "speed_kph"],
)

# 3. assemble a self-contained page; inline roadstyle's own JS/CSS, Leaflet from CDN
RS_JS = _asset("roadstyle.js").replace("</script", "<\\/script")
RS_CSS = _asset("roadstyle.css")
SPEC_JSON = json.dumps(spec).replace("</script", "<\\/script")

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>roadstyle — custom panel sample</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
<style>__RS_CSS__</style>
<style>
  html,body{margin:0;height:100%} #map{position:absolute;inset:0}
  /* a little styling for OUR custom panel's segmented control */
  .seg{display:flex;gap:4px}
  .seg button{flex:1;background:rgba(255,255,255,.06);color:#cfd6dd;border:1px solid rgba(255,255,255,.14);
    border-radius:7px;padding:4px 8px;font:600 11px system-ui;cursor:pointer}
  .seg button.on{background:#38bdf8;border-color:#38bdf8;color:#04121a}
  .muted{color:#8a97a3}
  .kv b{color:#9fb0bf;font-weight:600}
</style></head><body>
<div id="map"></div>
<script>__RS_JS__</script>
<script>
  const SPEC = __SPEC__;
  // create the map WITHOUT the built-in colour picker — we'll inject our own panel instead
  const m = new RoadStyleMap("map", { widgets: { colors: false, legend: true, basemap: true } });

  m.load(SPEC).then(function () {
    // ── custom panel #1: a segmented "Colour by" control wired to setColorField ──
    m.addPanel({
      title: "Colour by", position: "topright",
      render: function (body, map) {
        const seg = document.createElement("div"); seg.className = "seg";
        map.getColorOptions().forEach(function (o, i) {
          const b = document.createElement("button");
          b.textContent = o.name; b.dataset.i = i;
          if (i === map.getColorField()) b.classList.add("on");
          b.onclick = function () { map.setColorField(i); };
          seg.appendChild(b);
        });
        body.appendChild(seg);
        // keep the buttons in sync with the active option (event bus)
        map.on("colorchange", function (opt, idx) {
          seg.querySelectorAll("button").forEach(function (b) {
            b.classList.toggle("on", Number(b.dataset.i) === idx);
          });
        });
      }
    });

    // ── custom panel #2: a live selection readout, fed by the select/deselect events ──
    const idle = '<div class="muted">click a road…</div>';
    const info = m.addPanel({ title: "Selection", position: "topright",
      render: function (body) { body.innerHTML = idle; } });
    m.on("select", function (f) {
      const p = f.properties || {};
      info.body.innerHTML =
        '<div class="kv"><b>type</b> ' + (p.highway || "road") + '</div>' +
        '<div class="kv"><b>AADT</b> ' + p.aadt + '</div>' +
        '<div class="kv"><b>speed</b> ' + p.speed_kph + ' km/h</div>';
    });
    m.on("deselect", function () { info.body.innerHTML = idle; });
  });
</script></body></html>"""

html = (PAGE.replace("__RS_CSS__", RS_CSS)
            .replace("__SPEC__", SPEC_JSON)
            .replace("__RS_JS__", RS_JS))   # JS last: its blob isn't scanned for other markers
out = HERE / "custom_panel_sample.html"
out.write_text(html, encoding="utf-8")
print("wrote", out, "(%d KB)" % (len(html) // 1024))
