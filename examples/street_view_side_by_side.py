"""Sample: the map and **Google Street View side by side**, in one page.

Run it::

    python examples/street_view_side_by_side.py   # writes examples/street_view_sample.html

Click a road: the right-hand panel shows Street View at that point, looking the way the clicked
edge runs (a two-way road's two edges look opposite ways). No new window, no API key.

How: every click fires ``rs:select`` with ``detail.streetView``, a Google Maps URL carrying the
point (``viewpoint``) and the edge's direction (``heading``). Google refuses to show that URL in
an iframe, so the panel turns the same point and heading into Google's embeddable Street View
URL: the ``google.com/maps/embed?pb=...`` form Google's own "Share > Embed a map" produces. It
needs no key, but building it by hand is not documented by Google; with a Google Maps Embed API
key, use the official URL instead (commented next to ``SV_EMBED`` below).
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd

import roadstyle as rs

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# The right-hand panel. The map is inset so the base-map button and menu stay visible.
PANEL = """
<style>
  #map { right: 42% !important; }
  .bm-icon, .bm-menu { right: calc(42% + 10px) !important; }
  #sv { position: fixed; top: 0; right: 0; bottom: 0; width: 42%; display: flex;
        flex-direction: column; background: #fff; border-left: 1px solid #ddd;
        font: 13px/1.4 system-ui, sans-serif; }
  #sv-title { padding: 8px 12px; font-weight: 600; }
  #sv-frame { flex: 1; width: 100%; border: 0; background: #eee; }
</style>
<div id="sv"><div id="sv-title">Click a road</div><iframe id="sv-frame" title="Street View"></iframe></div>
<script>
(function () {
  // keyless, undocumented; official (needs a Maps Embed API key):
  // "https://www.google.com/maps/embed/v1/streetview?key=KEY&location=" + lat + "," + lng + "&heading=" + h
  const SV_EMBED = (lat, lng, h) =>
    "https://www.google.com/maps/embed?pb=!6m7!1m6!2m2!1d" + lat + "!2d" + lng + "!3f" + h + "!4f0!5f1";
  const frame = document.getElementById("sv-frame"), title = document.getElementById("sv-title");

  document.addEventListener("rs:select", function (e) {
    const d = e.detail, p = d.properties || {};
    if (d.layer != null || !d.streetView) return;        // roads only; null if street_view=False
    const u = new URL(d.streetView);
    const [lat, lng] = u.searchParams.get("viewpoint").split(",");
    title.textContent = p.name || p.highway || "road";
    frame.src = SV_EMBED(lat, lng, u.searchParams.get("heading") || 0);
  });

  map.resize();                                           // #map just lost 42% of its width
  // open on a road, zoomed in, so both sides show something
  function start() {
    const ids = rsQuery(p => p.name === "Götgatan");
    if (!ids.length) return;
    const id = ids[Math.floor(ids.length / 2)];
    rsSelect(id); rsFocus(id, { maxZoom: 16 });
  }
  if (map.loaded()) start(); else map.once("load", start);
})();
</script>
"""


def page(edges) -> str:
    """The side-by-side page for ``edges``: the map on the left, Street View on the right."""
    wm = rs.render_edges(edges, road_popup=False,        # the panel replaces the popup
                         name="roadstyle — map and Street View")
    return wm.html.replace("</body>", PANEL + "</body>")


if __name__ == "__main__":
    g = gpd.read_file(REPO / "notebooks" / "data" / "sodermalm_edges.gpkg")
    out = HERE / "street_view_sample.html"
    out.write_text(page(g), encoding="utf-8")
    print("wrote", out)
