"""Sample: dynamic recolouring on the **MapLibre web backend** (`render_edges(backend="web")`).

Run it::

    python examples/recolor_web_backend.py        # writes examples/web_recolor_sample.html

The web backend renders a self-contained MapLibre vector map (per-zoom widths, two-way lanes,
grade separation, one-way **arrows** and **street-name labels**). Passing ``color_options`` bakes
several "colour by" fill sets and adds a *Colour by* dropdown that recolours the roads client-side
with no re-render — each road keeps its width/casing/lanes, only the fill swaps.

It also injects a **custom panel** (a segmented control, top-centre) that drives the same recolour
through the exposed ``window.rsSetColorField(name|index)`` and stays in sync via the
``rs:colorchange`` event — the same hook you'd use to wire your own UI.
"""
from __future__ import annotations

import random
from pathlib import Path

import geopandas as gpd

import roadstyle as rs

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# 1. data — the repo's example edges + seeded AADT/speed so the ramps look real
g = gpd.read_file(REPO / "notebooks" / "data" / "sundbyberg_edges.gpkg")
random.seed(7)
g["aadt"] = [random.randint(200, 24000) for _ in range(len(g))]
g["speed_kph"] = [random.choice([30, 40, 50, 60, 70]) for _ in range(len(g))]

# 2. render on the web (MapLibre) backend — mono base so the data ramps stand out; arrows + labels
#    on (street names) by default; three "colour by" options baked in.
wm = rs.render_edges(
    g, backend="web", theme="dark", palette="mono",
    arrows=True, labels=True,           # one-way arrows + curved street-name labels
    color_options={
        "Class": {},
        "AADT": {"color_by": "aadt", "cmap": "viridis"},
        "Speed": {"color_by": "speed_kph", "cmap": "magma"},
    },
    name="roadstyle — web recolour",
)

# 3. inject a CUSTOM panel that drives the recolour through the exposed globals. This is the
#    web-backend equivalent of addPanel(): the map exposes window.rsSetColorField + the
#    rs:colorchange event, so your own DOM can drive and follow the recolour.
CUSTOM_PANEL = """
<style>
  #mypanel{position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:3;
    background:rgba(20,24,30,.85);color:#cfd6dd;border-radius:10px;padding:7px 9px;
    font:600 11px system-ui;display:flex;gap:5px;box-shadow:0 2px 10px rgba(0,0,0,.4)}
  #mypanel button{background:rgba(255,255,255,.06);color:#cfd6dd;border:1px solid rgba(255,255,255,.16);
    border-radius:7px;padding:4px 10px;cursor:pointer;font:inherit}
  #mypanel button.on{background:#38bdf8;border-color:#38bdf8;color:#04121a}
</style>
<div id="mypanel"></div>
<script>
(function(){
  function build(){
    var opts = window.RS_COLOR_OPTIONS || [], box = document.getElementById("mypanel");
    opts.forEach(function(o,i){
      var b=document.createElement("button"); b.textContent=o.name; b.dataset.i=i;
      if(i===0) b.classList.add("on");
      b.onclick=function(){ window.rsSetColorField(i); };   // recolour, no re-render
      box.appendChild(b);
    });
    document.addEventListener("rs:colorchange", function(e){   // follow changes from any source
      var idx=e.detail.index;
      box.querySelectorAll("button").forEach(function(b){ b.classList.toggle("on", Number(b.dataset.i)===idx); });
    });
  }
  if(window.RS_COLOR_OPTIONS) build(); else window.addEventListener("load", build);
})();
</script>
"""
html = wm.html.replace("</body>", CUSTOM_PANEL + "</body>")

out = HERE / "web_recolor_sample.html"
out.write_text(html, encoding="utf-8")
print("wrote", out, "(%d KB)" % (len(html) // 1024))
