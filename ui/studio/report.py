"""Report builder — the ``ui/report`` template, behind knobs.

Same knobs as the Dashboard page, but the product is the **report sidebar**
(``ui/report/sidebar.html`` — headline counts, a by-class breakdown, search, and a
selected-road read-out) injected on top of a controls-off map, wired through the public
``window.rs*`` API. Download ``report.html`` or copy the code (it mirrors ``ui/report/build.py``).

Deliberately parallels ``dashboard.py`` — same rendering path, different injected sidebar.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
from common import CMAPS, data_section, overlay_section, tiles_available

import roadstyle as rs

SIDEBAR = (Path(__file__).resolve().parent.parent / "report" / "sidebar.html").read_text()

with st.sidebar:
    st.title("report builder")

    edges, loader = data_section()

    with st.expander("Look", expanded=True):
        all_bms = list(rs.BASEMAPS)
        bms = st.multiselect("Base maps offered", all_bms,
                             default=[b for b in ("voyager", "positron", "dark_matter", "osm",
                                                  "satellite", "blank") if b in all_bms])
        basemap = st.selectbox("Initial base map", bms or all_bms)
        view_3d = st.checkbox("3D bridges", value=True)
        tiles = st.checkbox("Vector tiles (big networks)", value=False,
                            disabled=not tiles_available(),
                            help="Embedded-PMTiles tileset in the same single file — ~10⁵-edge "
                                 "maps stay responsive. Needs `pip install \"roadstyle[tiles]\"`.")
        minzoom = st.checkbox("Hide minor roads when zoomed out", value=False,
                              help="The built-in per-class `minzoom` table — residential/service "
                                   "appear as you zoom in (thins low-zoom tiles too).")
        title = st.text_input("Title", value="Roads report")

    with st.expander("Colour-by options", expanded=False):
        num_cols = list(edges.select_dtypes("number").columns)
        co_cols = st.multiselect("Columns (besides road class)", num_cols,
                                 default=[c for c in ("maxspeed_kmh", "lanes") if c in num_cols])
        color_options = {"Class": {}}
        for i, c in enumerate(co_cols):
            cm = st.selectbox(f"↳ colormap for {c}", CMAPS, index=(i + 1) % len(CMAPS),
                              key=f"cm_{c}")
            color_options[c] = {"color_by": c, "cmap": cm}

    with st.expander("Hover tooltip", expanded=False):
        hover = st.multiselect("Columns shown on hover",
                               [c for c in edges.columns if c != edges.geometry.name],
                               help="A tooltip that follows the mouse over a road. Empty = off.")

    overlays, ov_lines = overlay_section()

# the sidebar owns colour-by / legend / filter; the base map keeps the map's on-map switcher
# icon (basemap_switcher=True). See ui/report/build.py.
kw = {"basemap": basemap, "view_3d": view_3d, "basemaps": bms or None,
      "color_options": color_options, "basemap_switcher": True, "filter_control": False,
      "road_popup": False, "name": title}
if tiles:
    kw["tiles"] = True
if minzoom:
    kw["minzoom"] = True
if hover:
    kw["tooltip"] = hover
if overlays:
    kw["overlays"] = overlays

ovs = "[" + ", ".join(f"ov{i}" for i in range(len(overlays))) + "]"


def _fmt(k, v):
    return ovs if k == "overlays" else repr(v)


args = "".join(f",\n                    {k}={_fmt(k, v)}" for k, v in kw.items())
loader = loader if not overlays else (
    "import geopandas as gpd\n\n" + loader + "\n" + "\n".join(ov_lines))
code = (f"import roadstyle as rs\n\n{loader}\n"
        f'm = rs.render_edges(edges, backend="web"{args})\n'
        f'sidebar = open("ui/report/sidebar.html").read()\n'
        f'open("report.html", "w").write(m.html.replace("</body>", sidebar + "</body>", 1))')

m = rs.render_edges(edges, backend="web", compress=True, **kw)
# inject before the MapLibre placeholders are substituted, so BOTH the iframe-safe preview
# (_repr_html_, CDN MapLibre 3.x) and the download (.html, vendored) carry the sidebar
m._tpl = m._tpl.replace("</body>", SIDEBAR + "</body>", 1)

# always the CDN-v3 preview variant: vendored MapLibre v4 stalls any roads source in
# sandboxed iframes; pmtiles' Protocol is v3-compatible so tiled previews work under v3
st.components.v1.html(m._repr_html_(), height=660)
if tiles:
    st.caption(f"✓ roads served from **embedded vector tiles** — {len(m.html) // 1024:,} KB "
               "self-contained page (the report's stats read the same tileset)")

left, right = st.columns([3, 1])
with left:
    st.code(code, language="python")
with right:
    st.download_button("⬇ download report.html", m.html, file_name="report.html",
                       mime="text/html", use_container_width=True)
    st.caption("Self-contained — opens anywhere, no server. The sidebar is plain HTML over "
               "the `window.rs*` API — copy `ui/report/sidebar.html` and reshape it.")
