"""roadstyle studio — the whole library behind eight knobs.

A Streamlit workbench: point it at a road file, click through the looks, and it renders the real
map next to the exact ``render_edges`` code for the current state — copy the code out (or
download the self-contained HTML) when you outgrow the knobs. Run::

    streamlit run ui/studio/app.py

Needs ``pip install streamlit`` (the map itself is plain roadstyle).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

import roadstyle as rs

st.set_page_config(page_title="roadstyle studio", page_icon="🛣️", layout="wide")

DEFAULT_DB = "/home/kaveh/projects/duckOSM/data/db/sodermalm.duckdb"
CMAPS = ["viridis", "plasma", "magma", "cividis", "coolwarm", "RdYlGn_r"]


@st.cache_data(show_spinner="Loading edges…")
def load_edges(path: str, blob: bytes | None, blob_name: str | None):
    if blob is not None:
        with tempfile.NamedTemporaryFile(suffix=Path(blob_name).suffix, delete=False) as t:
            t.write(blob)
            path = t.name
    if str(path).endswith(".duckdb"):
        return rs.from_duckosm(path).gdf     # the normalised GeoDataFrame inside RoadEdges
    import geopandas as gpd
    return gpd.read_file(path)


# ---------------------------------------------------------------- sidebar: the eight knobs
with st.sidebar:
    st.title("roadstyle studio")

    st.subheader("Data")
    up = st.file_uploader("Road file (.gpkg / .geojson)", type=["gpkg", "geojson", "json"])
    path = st.text_input("…or a path (.duckdb / .gpkg)", value=DEFAULT_DB,
                         disabled=up is not None)
    try:
        edges = load_edges(path, up.getvalue() if up else None, up.name if up else None)
    except Exception as e:
        st.error(f"Could not load edges: {e}")
        st.stop()
    st.caption(f"{len(edges):,} edges loaded")

    st.subheader("Look")
    palette = st.selectbox("Palette", ["highsat", "carto", "mono"])
    basemap = st.selectbox("Base map", list(rs.BASEMAPS), index=0)
    view_3d = st.checkbox("3D bridges (tilted view)", value=False)

    st.subheader("Colour by data")
    cols = [c for c in edges.columns if c != edges.geometry.name]
    color_by = st.selectbox("Column", ["(road class)"] + cols)
    cmap = st.selectbox("Colormap", CMAPS) if color_by != "(road class)" else None

    st.subheader("Filter")
    classes = sorted(rs.highway_types(edges))
    keep = st.multiselect("Road classes", classes, default=classes)

    st.subheader("Decorations")
    labels = st.checkbox("Street names", value=True)
    arrows = st.checkbox("One-way arrows", value=True)

# ---------------------------------------------------------------- render + the code, in sync
kw = {"palette": palette, "basemap": basemap}
if view_3d:
    kw["view_3d"] = True
if color_by != "(road class)":
    kw["color_by"], kw["cmap"], kw["legend"] = color_by, cmap, True
if set(keep) != set(classes):
    kw["include"] = keep
if not labels:
    kw["labels"] = False
if not arrows:
    kw["arrows"] = False

loader = (f'edges = rs.from_duckosm("{path}")' if str(path).endswith(".duckdb") and up is None
          else f'edges = gpd.read_file("{up.name if up else path}")')
args = "".join(f",\n                     {k}={v!r}" for k, v in kw.items())
code = (f"import roadstyle as rs\n\n{loader}\n"
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
