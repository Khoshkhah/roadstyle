"""Map studio — the whole library behind a few knobs.

Point it at a road file, click through the looks, and it renders the real map next to the exact
``render_edges`` code for the current state — copy the code out (or download the self-contained
HTML) when you outgrow the knobs.
"""
from __future__ import annotations

import streamlit as st
from common import colour_by_section, data_section, overlay_section, tiles_available

import roadstyle as rs
from roadstyle.render_web import DEFAULT_ROAD_POPUP


# ---------------------------------------------------------------- sidebar: the knobs
with st.sidebar:
    st.title("roadstyle studio")

    edges, loader = data_section()

    with st.expander("Look", expanded=True):
        palette = st.selectbox("Palette", ["highsat", "carto", "mono"])
        basemap = st.selectbox("Base map", list(rs.BASEMAPS), index=0)
        view_3d = st.checkbox("3D bridges (tilted view)", value=False)
        tiles = st.checkbox("Vector tiles (big networks)", value=False,
                            disabled=not tiles_available(),
                            help="Embedded-PMTiles tileset in the same single file — ~10⁵-edge "
                                 "maps stay responsive. Needs `pip install \"roadstyle[tiles]\"`.")
    kw = {"palette": palette, "basemap": basemap}
    if view_3d:
        kw["view_3d"] = True
    if tiles:
        kw["tiles"] = True

    co = colour_by_section(edges)   # shared "Colour by data" block (built-in in-map dropdown + legend)
    if len(co) > 1:
        kw["color_options"] = co

    with st.expander("Filter", expanded=False):
        classes = sorted(rs.highway_types(edges))
        keep = st.multiselect("Road classes", classes, default=classes)
        minzoom = st.checkbox("Hide minor roads when zoomed out", value=False,
                              help="The built-in per-class `minzoom` table — residential/service "
                                   "appear as you zoom in (with Vector tiles on, low-zoom tiles "
                                   "thin out too).")
    if set(keep) != set(classes):
        kw["include"] = keep
    if minzoom:
        kw["minzoom"] = True

    with st.expander("Decorations", expanded=False):
        labels = st.checkbox("Street names", value=True)
        arrows = st.checkbox("One-way arrows", value=True)
    if not labels:
        kw["labels"] = False
    if not arrows:
        kw["arrows"] = False

    with st.expander("Popup & hover", expanded=False):
        cols = [c for c in edges.columns if c != edges.geometry.name]
        popup_mode = st.selectbox("Click popup", ["curated fields", "choose columns",
                                                  "side panel", "all columns", "off"])
        if popup_mode == "choose columns":
            kw["road_popup"] = st.multiselect(
                "Popup columns", cols,
                default=[c for c in DEFAULT_ROAD_POPUP if c in cols])
        elif popup_mode != "curated fields":
            kw["road_popup"] = {"side panel": "panel", "all columns": "all",
                                "off": False}[popup_mode]
        hover = st.multiselect("Hover tooltip columns", cols)
    if hover:
        kw["tooltip"] = hover

    overlays, ov_lines = overlay_section()
    if overlays:
        kw["overlays"] = overlays

# ---------------------------------------------------------------- render + the code, in sync
ovs = "[" + ", ".join(f"ov{i}" for i in range(len(overlays))) + "]"


def _fmt(k, v):
    return ovs if k == "overlays" else repr(v)


args = "".join(f",\n                     {k}={_fmt(k, v)}" for k, v in kw.items())
prelude = loader if not overlays else (
    "import geopandas as gpd\n\n" + loader + "\n" + "\n".join(ov_lines))
code = (f"import roadstyle as rs\n\n{prelude}\n"
        f"wm = rs.render_edges(edges{args})\n"
        f'wm.save("map.html")')

wm = rs.render_edges(edges, backend="web", compress=True, **kw)

# always the notebook-preview variant (CDN MapLibre 3.x): the vendored-4.x page stalls ANY
# roads source (GeoJSON or vector tiles) inside sandboxed iframes; pmtiles' Protocol is
# v3-compatible, so the embedded-tiles pipeline previews fine under v3
st.components.v1.html(wm._repr_html_(), height=640)
if kw.get("tiles"):
    st.caption(f"✓ roads served from **embedded vector tiles** — {len(wm.html) // 1024:,} KB "
               "self-contained page (the download carries the same tileset)")

left, right = st.columns([3, 1])
with left:
    st.code(code, language="python")
with right:
    st.download_button("⬇ download map.html", wm.html, file_name="map.html",
                       mime="text/html", use_container_width=True)
    st.caption("Self-contained — opens anywhere, no server. "
               "The code on the left recreates this exact map; "
               "[docs](https://github.com/Khoshkhah/roadstyle#readme) when you outgrow the knobs.")
