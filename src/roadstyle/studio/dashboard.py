"""Dashboard builder — the packaged ``render_dashboard`` page, behind knobs.

Same idea as the map page, but the product is a *dashboard*: :func:`roadstyle.render_dashboard`
renders the map with every built-in control off and injects the bundled dashboard sidebar (query
box, colour-by, class filter + legend, table) — wired through the public ``window.rs*`` API.
Download ``dashboard.html`` or copy the code (it mirrors ``ui/dashboard/build.py``).
"""
from __future__ import annotations

import streamlit as st
from common import colour_by_section, data_section, overlay_section, tiles_available

import roadstyle as rs

with st.sidebar:
    st.title("dashboard builder")

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
        title = st.text_input("Title", value="Roads dashboard")

    color_options = colour_by_section(edges, default=("maxspeed_kmh", "lanes"))

    with st.expander("Hover tooltip", expanded=False):
        hover = st.multiselect("Columns shown on hover",
                               [c for c in edges.columns if c != edges.geometry.name],
                               help="A tooltip that follows the mouse over a road. Empty = off.")

    with st.expander("Decorations", expanded=False):
        labels = st.checkbox("Street names", value=True)
        arrows = st.checkbox("One-way arrows", value=True)

    overlays, ov_lines = overlay_section()

# render_dashboard turns the built-in controls off and injects the bundled sidebar; the studio just
# passes the look/data knobs through.
kw = {"basemap": basemap, "view_3d": view_3d, "basemaps": bms or None,
      "color_options": color_options, "name": title}
if tiles:
    kw["tiles"] = True
if minzoom:
    kw["minzoom"] = True
if hover:
    kw["tooltip"] = hover
if not labels:
    kw["labels"] = False
if not arrows:
    kw["arrows"] = False
if overlays:
    kw["overlays"] = overlays

ovs = "[" + ", ".join(f"ov{i}" for i in range(len(overlays))) + "]"


def _fmt(k, v):
    return ovs if k == "overlays" else repr(v)


args = "".join(f",\n                        {k}={_fmt(k, v)}" for k, v in kw.items())
loader = loader if not overlays else (
    "import geopandas as gpd\n\n" + loader + "\n" + "\n".join(ov_lines))
code = (f"import roadstyle as rs\n\n{loader}\n"
        f"m = rs.render_dashboard(edges{args})\n"
        f'm.save("dashboard.html")')

m = rs.render_dashboard(edges, compress=True, **kw)

# always the CDN-v3 preview variant: vendored MapLibre v4 stalls any roads source in
# sandboxed iframes; pmtiles' Protocol is v3-compatible so tiled previews work under v3
st.components.v1.html(m._repr_html_(), height=660)
if tiles:
    st.caption(f"✓ roads served from **embedded vector tiles** — {len(m.html) // 1024:,} KB "
               "self-contained page (the download carries the same tileset)")

left, right = st.columns([3, 1])
with left:
    st.code(code, language="python")
with right:
    st.download_button("⬇ download dashboard.html", m.html, file_name="dashboard.html",
                       mime="text/html", use_container_width=True)
    st.caption("Self-contained — opens anywhere, no server. The sidebar ships with roadstyle "
               "(`rs.sidebar_html('dashboard')`) — copy it and reshape the plain HTML/`window.rs*` code.")
