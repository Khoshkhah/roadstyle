"""Shared pieces of the studio pages: data loading and the sidebar Data section."""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

import roadstyle as rs

DEFAULT_DB = "/home/kaveh/projects/duckOSM/data/db/sodermalm.duckdb"
CMAPS = ["viridis", "plasma", "magma", "cividis", "coolwarm", "RdYlGn_r"]
OV_COLORS = ["#7c4dff", "#00bcd4", "#ff9800", "#e91e63"]


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


def data_section():
    """The sidebar "Data" block. Returns ``(edges, loader)`` — the GeoDataFrame and the code
    line that loads it."""
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
    loader = (f'edges = rs.from_duckosm("{path}")'
              if str(path).endswith(".duckdb") and up is None
              else f'edges = gpd.read_file("{up.name if up else path}")')
    return edges, loader


@st.cache_data(show_spinner="Loading overlay…")
def load_overlay(blob: bytes, name: str):
    with tempfile.NamedTemporaryFile(suffix=Path(name).suffix, delete=False) as t:
        t.write(blob)
    import geopandas as gpd
    return gpd.read_file(t.name)


def overlay_section():
    """The sidebar "Overlays" block: each uploaded file becomes one :class:`rs.Overlay`.
    Returns ``(overlays, code_lines)`` — the objects and the ``ovN = rs.Overlay(...)`` lines."""
    st.subheader("Overlays")
    ups = st.file_uploader("Zones / POIs / lines (.gpkg / .geojson)",
                           type=["gpkg", "geojson", "json"],
                           accept_multiple_files=True, key="ov_files")
    overlays, lines = [], []
    for i, u in enumerate(ups or []):
        gdf = load_overlay(u.getvalue(), u.name)
        with st.expander(u.name, expanded=True):
            c1, c2 = st.columns([3, 1])
            label = c1.text_input("Label", value=Path(u.name).stem, key=f"ov_l{i}")
            color = c2.color_picker("Colour", value=OV_COLORS[i % len(OV_COLORS)],
                                    key=f"ov_c{i}")
            under = st.checkbox("Under the roads", key=f"ov_u{i}",
                                value=bool(len(gdf)) and "Polygon" in gdf.geom_type.iloc[0],
                                help="zones go under, POIs go over")
            click = st.checkbox("Clickable (popup of its fields)", value=True, key=f"ov_p{i}")
        popup = [c for c in gdf.columns if c != gdf.geometry.name] if click else []
        place = "under" if under else "over"
        overlays.append(rs.Overlay(gdf, label=label, color=color, placement=place, popup=popup))
        lines.append(f'ov{i} = rs.Overlay(gpd.read_file("{u.name}"), label={label!r}, '
                     f'color={color!r}, placement={place!r}, popup={popup!r})')
    return overlays, lines
