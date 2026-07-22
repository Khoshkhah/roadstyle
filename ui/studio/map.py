"""Map studio — the whole library behind a few knobs.

Point it at a road file, click through the looks, and it renders the real map next to the exact
``render_edges`` code for the current state — copy the code out (or download the self-contained
HTML) when you outgrow the knobs.
"""
from __future__ import annotations

import streamlit as st
from common import CMAPS, data_section, overlay_section, tiles_available

import roadstyle as rs
from roadstyle.render_web import DEFAULT_ROAD_POPUP

# ---------------------------------------------------------------- sidebar: the knobs
with st.sidebar:
    st.title("roadstyle studio")

    edges, loader = data_section()

    st.subheader("Look")
    palette = st.selectbox("Palette", ["highsat", "carto", "mono"])
    basemap = st.selectbox("Base map", list(rs.BASEMAPS), index=0)
    view_3d = st.checkbox("3D bridges (tilted view)", value=False)
    tiles = st.checkbox("Vector tiles (big networks)", value=False,
                        disabled=not tiles_available(),
                        help="Embedded-PMTiles tileset in the same single file — ~10⁵-edge maps "
                             "stay responsive. Needs `pip install \"roadstyle[tiles]\"`.")
    kw = {"palette": palette, "basemap": basemap}
    if view_3d:
        kw["view_3d"] = True
    if tiles:
        kw["tiles"] = True

    st.subheader("Colour by data")
    cols = [c for c in edges.columns if c != edges.geometry.name]
    color_by = st.selectbox("Column", ["(road class)"] + cols)
    cmap = st.selectbox("Colormap", CMAPS) if color_by != "(road class)" else None
    if cmap:
        kw.update({"color_by": color_by, "cmap": cmap, "legend": True})

    st.subheader("Filter")
    classes = sorted(rs.highway_types(edges))
    keep = st.multiselect("Road classes", classes, default=classes)
    if set(keep) != set(classes):
        kw["include"] = keep

    st.subheader("Decorations")
    labels = st.checkbox("Street names", value=True)
    arrows = st.checkbox("One-way arrows", value=True)
    if not labels:
        kw["labels"] = False
    if not arrows:
        kw["arrows"] = False

    st.subheader("Popup & hover")
    popup_mode = st.selectbox("Click popup", ["curated fields", "choose columns", "side panel",
                                              "all columns", "off"])
    if popup_mode == "choose columns":
        kw["road_popup"] = st.multiselect("Popup columns", cols,
                                          default=[c for c in DEFAULT_ROAD_POPUP if c in cols])
    elif popup_mode != "curated fields":
        kw["road_popup"] = {"side panel": "panel", "all columns": "all", "off": False}[popup_mode]
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

# embed the notebook-preview variant (CDN MapLibre 3.x): the full vendored-4.x page stalls its
# GeoJSON source inside sandboxed iframes — same class of bug as the Notebook 7 stall
st.components.v1.html(wm._repr_html_(), height=640)

left, right = st.columns([3, 1])
with left:
    st.code(code, language="python")
with right:
    st.download_button("⬇ download map.html", wm.html, file_name="map.html",
                       mime="text/html", use_container_width=True)
    st.caption("Self-contained — opens anywhere, no server. "
               "The code on the left recreates this exact map; "
               "[docs](https://github.com/Khoshkhah/roadstyle#readme) when you outgrow the knobs.")
