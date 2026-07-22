"""Dashboard builder — the ``ui/dashboard`` template, behind knobs.

Same idea as the map page, but the product is a *dashboard*: the map rendered with every
built-in control off and the sidebar UI (``ui/dashboard/sidebar.html`` — query box, colour-by,
class filter, table, 2D/3D) injected on top, wired through the public ``window.rs*`` API.
Download ``dashboard.html`` or copy the code (it mirrors ``ui/dashboard/build.py``).
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

import roadstyle as rs

from common import CMAPS, data_section, overlay_section

SIDEBAR = (Path(__file__).resolve().parent.parent / "dashboard" / "sidebar.html").read_text()

with st.sidebar:
    st.title("dashboard builder")

    edges, loader = data_section()

    st.subheader("Look")
    all_bms = list(rs.BASEMAPS)
    bms = st.multiselect("Base maps offered", all_bms,
                         default=[b for b in ("voyager", "positron", "dark_matter", "osm",
                                              "satellite", "blank") if b in all_bms])
    basemap = st.selectbox("Initial base map", bms or all_bms)
    view_3d = st.checkbox("3D bridges", value=True)
    title = st.text_input("Title", value="Roads dashboard")

    st.subheader("Colour-by options")
    num_cols = list(edges.select_dtypes("number").columns)
    co_cols = st.multiselect("Columns (besides road class)", num_cols,
                             default=[c for c in ("maxspeed_kmh", "lanes") if c in num_cols])
    color_options = {"Class": {}}
    for i, c in enumerate(co_cols):
        cm = st.selectbox(f"↳ colormap for {c}", CMAPS, index=(i + 1) % len(CMAPS),
                          key=f"cm_{c}")
        color_options[c] = {"color_by": c, "cmap": cm}

    overlays, ov_lines = overlay_section()

# built-in controls off — the injected sidebar IS the UI (see ui/dashboard/build.py)
kw = {"basemap": basemap, "view_3d": view_3d, "basemaps": bms or None,
      "color_options": color_options, "basemap_switcher": False, "filter_control": False,
      "road_popup": False, "name": title}
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
        f'sidebar = open("ui/dashboard/sidebar.html").read()\n'
        f'open("dashboard.html", "w").write(m.html.replace("</body>", sidebar + "</body>", 1))')

m = rs.render_edges(edges, backend="web", compress=True, **kw)
# inject before the MapLibre placeholders are substituted, so BOTH the iframe-safe preview
# (_repr_html_, CDN MapLibre 3.x) and the download (.html, vendored) carry the sidebar
m._tpl = m._tpl.replace("</body>", SIDEBAR + "</body>", 1)

st.components.v1.html(m._repr_html_(), height=660)

left, right = st.columns([3, 1])
with left:
    st.code(code, language="python")
with right:
    st.download_button("⬇ download dashboard.html", m.html, file_name="dashboard.html",
                       mime="text/html", use_container_width=True)
    st.caption("Self-contained — opens anywhere, no server. The sidebar is plain HTML over "
               "the `window.rs*` API — copy `ui/dashboard/sidebar.html` and reshape it.")
