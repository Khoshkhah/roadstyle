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
def load_edges(path: str, blob: bytes | None, blob_name: str | None, mode: str = "driving"):
    if blob is not None:
        with tempfile.NamedTemporaryFile(suffix=Path(blob_name).suffix, delete=False) as t:
            t.write(blob)
            path = t.name
    if str(path).endswith(".duckdb"):
        return rs.from_duckosm(path, schema=mode).gdf   # the GeoDataFrame inside RoadEdges
    import geopandas as gpd
    return gpd.read_file(path)


def data_section():
    """The sidebar "Data" block. Returns ``(edges, loader)`` — the GeoDataFrame and the code
    line that loads it."""
    st.subheader("Data")
    up = st.file_uploader("Road file (.gpkg / .geojson)", type=["gpkg", "geojson", "json"])
    path = st.text_input("…or a path (.duckdb / .gpkg)", value=DEFAULT_DB,
                         disabled=up is not None)
    is_db = str(path).endswith(".duckdb") and up is None
    mode = st.selectbox("Mode (duckOSM network)", ["driving", "walking", "cycling"]) \
        if is_db else "driving"
    try:
        edges = load_edges(path, up.getvalue() if up else None,
                           up.name if up else None, mode)
    except Exception as e:
        st.error(f"Could not load edges: {e}")
        st.stop()
    st.caption(f"{len(edges):,} edges loaded")
    marg = "" if mode == "driving" else f", schema={mode!r}"
    loader = (f'edges = rs.from_duckosm("{path}"{marg})' if is_db
              else f'edges = gpd.read_file("{up.name if up else path}")')
    return edges, loader


@st.cache_data(show_spinner="Loading overlay…")
def load_overlay(blob: bytes, name: str):
    with tempfile.NamedTemporaryFile(suffix=Path(name).suffix, delete=False) as t:
        t.write(blob)
    import geopandas as gpd
    return gpd.read_file(t.name)


SAMPLES_DIR = Path(__file__).resolve().parent / "samples"


def overlay_section():
    """The sidebar "Overlays" block: each uploaded (or sample) file becomes one
    :class:`rs.Overlay`. Returns ``(overlays, code_lines)`` — the objects and the
    ``ovN = rs.Overlay(...)`` lines."""
    st.subheader("Overlays")
    ups = st.file_uploader("Zones / POIs / lines (.gpkg / .geojson)",
                           type=["gpkg", "geojson", "json"],
                           accept_multiple_files=True, key="ov_files")
    samples = {p.stem: p for p in sorted(SAMPLES_DIR.glob("*.geojson"))}
    picks = st.multiselect("…or sample overlays", list(samples), key="ov_samples")
    # (display name, bytes, the path the generated code should read)
    files = ([(u.name, u.getvalue(), u.name) for u in (ups or [])]
             + [(samples[k].name, samples[k].read_bytes(), f"ui/studio/samples/{k}.geojson")
                for k in picks])
    overlays, lines = [], []
    for i, (fname, blob, code_path) in enumerate(files):
        gdf = load_overlay(blob, fname)
        with st.expander(fname, expanded=True):
            c1, c2 = st.columns([3, 1])
            label = c1.text_input("Label", value=Path(fname).stem, key=f"ov_l{i}")
            color = c2.color_picker("Colour", value=OV_COLORS[i % len(OV_COLORS)],
                                    key=f"ov_c{i}")
            under = st.checkbox("Under the roads", key=f"ov_u{i}",
                                value=bool(len(gdf)) and "Polygon" in gdf.geom_type.iloc[0],
                                help="zones go under, POIs go over")
            click = st.checkbox("Clickable (popup of its fields)", value=True, key=f"ov_p{i}")
        popup = [c for c in gdf.columns if c != gdf.geometry.name] if click else []
        place = "under" if under else "over"
        overlays.append(rs.Overlay(gdf, label=label, color=color, placement=place, popup=popup))
        lines.append(f'ov{i} = rs.Overlay(gpd.read_file("{code_path}"), label={label!r}, '
                     f'color={color!r}, placement={place!r}, popup={popup!r})')
    return overlays, lines
