"""Shared pieces of the studio pages: data loading and the sidebar Data section."""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

import roadstyle as rs

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
