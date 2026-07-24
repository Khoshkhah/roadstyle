"""Shared pieces of the studio pages: data loading and the sidebar Data section."""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

import roadstyle as rs
from roadstyle.colors import ColorRamp

CMAPS = ["viridis", "plasma", "magma", "cividis", "coolwarm", "RdYlGn_r"]


def _colour_opt(edges, num_cols, col, cmap):
    """One ``color_options`` entry for ``col``: a continuous ramp for a many-valued numeric column,
    else discrete ``min(5, #values)`` stepped colours (categorical legend). ``None`` if all-NaN.

    ``missing="self"``: unmapped / NaN edges (e.g. non-bridges when colouring by ``bridge``) keep
    the styler's own neutral grey instead of inheriting the loud "Class" base fill (see
    ``bake_color_options``' base-fallback)."""
    vals = sorted(edges[col].dropna().unique().tolist())   # native ints/floats/strs
    n = len(vals)
    if col in num_cols and n > 12:
        # continuous numeric: robust range — clip vmin/vmax to p2–p98 so one outlier edge can't
        # stretch the ramp and flatten every other road (the ramp clamps out-of-range to its ends).
        vlo, vhi = edges[col].quantile([0.02, 0.98])
        return {"color_by": col, "cmap": cmap, "vmin": float(vlo), "vmax": float(vhi),
                "missing": "self"}
    if n:
        # discrete — few numeric values (lanes) OR a categorical (bridge/oneway/layer). min(5, n)
        # stepped colours → a categorical legend, one swatch per value; >5 values split into 5 even
        # groups so the top values share the top colour.
        k = min(5, n)
        stops = ColorRamp(cmap).stops(k)
        groups = [vals[i * n // k:(i + 1) * n // k] for i in range(k)]
        return {"color_by": col, "missing": "self",
                "colors": {v: stops[i] for i, g in enumerate(groups) for v in g}}
    return None


def colour_by_section(edges, *, default=()):
    """Shared sidebar "Colour by data" block for all three studio pages.

    Renders a multiselect of colourable columns — numeric plus low-cardinality categoricals
    (bridge, tunnel, oneway, layer…); id/key columns and high-cardinality text (street ``name``)
    are dropped — each with its own colormap. Returns the ``color_options`` mapping
    (``{"Class": {}, col: {...}, …}``); every picked column becomes an entry in the in-map
    "Colour by" dropdown, routed to a discrete or continuous scale by its data."""
    with st.expander("Colour by data", expanded=False):
        cols = [c for c in edges.columns if c != edges.geometry.name]
        # id/key columns (edge_id, osm_id…) are meaningless to colour by
        ids = {c for c in cols if c.lower() in {"id", "fid", "gid", "uid", "objectid"}
               or c.lower().endswith("_id")}
        num_cols = [c for c in edges.select_dtypes("number").columns if c not in ids]
        # low-cardinality categoricals colour via the discrete branch; skip text like `name`
        cat_cols = [c for c in cols if c not in num_cols and c not in ids
                    and 0 < edges[c].nunique() <= 12]
        avail = num_cols + cat_cols
        pick = st.multiselect("Columns (besides road class)", avail,
                              default=[c for c in default if c in avail])
        cmaps = {c: st.selectbox(f"↳ colormap for {c}", CMAPS, index=(i + 1) % len(CMAPS),
                                 key=f"cm_{c}")
                 for i, c in enumerate(pick)}
    co = {"Class": {}}                       # Class first = the neutral base / toggle-back option
    for c in pick:
        o = _colour_opt(edges, num_cols, c, cmaps[c])
        if o:
            co[c] = o
    return co


def tiles_available() -> bool:
    """Whether the `tiles` extra (mapbox-vector-tile + pmtiles) is installed."""
    try:
        import mapbox_vector_tile  # noqa: F401
        import pmtiles  # noqa: F401
        return True
    except ImportError:
        return False
OV_COLORS = ["#7c4dff", "#00bcd4", "#ff9800", "#e91e63"]

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"
# Bundled road networks (Södermalm, Stockholm — exported with `duckosm export-gis`), one file
# per network. Any road file with a highway-class column works the same way.
ROAD_SAMPLES = {f"Södermalm {m}": SAMPLES_DIR / f"sodermalm_{m}.geojson"
                for m in ("driving", "walking", "cycling")}


@st.cache_data(show_spinner="Loading edges…")
def load_edges(path: str, blob: bytes | None, blob_name: str | None):
    if blob is not None:
        with tempfile.NamedTemporaryFile(suffix=Path(blob_name).suffix, delete=False) as t:
            t.write(blob)
            path = t.name
    import geopandas as gpd
    return gpd.read_file(path)


def data_section():
    """The sidebar "Data" block (collapsible). Returns ``(edges, loader)`` — the GeoDataFrame
    and the code line that loads it."""
    with st.expander("Data", expanded=True):
        up = st.file_uploader("Road file (.gpkg / .geojson)", type=["gpkg", "geojson", "json"])
        pick = st.selectbox("…or a sample network", list(ROAD_SAMPLES),
                            disabled=up is not None,
                            help="Södermalm (Stockholm), exported with `duckosm export-gis`")
        path = str(ROAD_SAMPLES[pick])
        try:
            edges = load_edges(path, up.getvalue() if up else None,
                               up.name if up else None)
        except Exception as e:
            st.error(f"Could not load edges: {e}")
            st.stop()
        st.caption(f"{len(edges):,} edges loaded")
    loader = (f'edges = gpd.read_file("{up.name}")' if up
              else f'edges = gpd.read_file("ui/studio/samples/{Path(path).name}")')
    return edges, loader


@st.cache_data(show_spinner="Loading overlay…")
def load_overlay(blob: bytes, name: str):
    with tempfile.NamedTemporaryFile(suffix=Path(name).suffix, delete=False) as t:
        t.write(blob)
    import geopandas as gpd
    return gpd.read_file(t.name)


def overlay_section():
    """The sidebar "Overlays" block: each uploaded (or sample) file becomes one
    :class:`rs.Overlay`. Returns ``(overlays, code_lines)`` — the objects and the
    ``ovN = rs.Overlay(...)`` lines."""
    exp = st.expander("Overlays", expanded=False)
    with exp:
        ups = st.file_uploader("Zones / POIs / lines (.gpkg / .geojson)",
                               type=["gpkg", "geojson", "json"],
                               accept_multiple_files=True, key="ov_files")
        samples = {p.stem: p for p in sorted(SAMPLES_DIR.glob("*.geojson"))
                   if p not in ROAD_SAMPLES.values()}
        picks = st.multiselect("…or sample overlays", list(samples), key="ov_samples")
    # (display name, bytes, the path the generated code should read)
    files = ([(u.name, u.getvalue(), u.name) for u in (ups or [])]
             + [(samples[k].name, samples[k].read_bytes(), f"ui/studio/samples/{k}.geojson")
                for k in picks])
    overlays, lines = [], []
    for i, (fname, blob, code_path) in enumerate(files):
        gdf = load_overlay(blob, fname)
        with exp:                       # expanders can't nest: flat group per file, with a rule
            st.markdown(("---\n" if i else "") + f"**{fname}**")
            c1, c2 = st.columns([3, 1])
            label = c1.text_input("Label", value=Path(fname).stem, key=f"ov_l{i}")
            color = c2.color_picker("Colour", value=OV_COLORS[i % len(OV_COLORS)],
                                    key=f"ov_c{i}")
            under = st.checkbox("Under the roads", key=f"ov_u{i}",
                                value=bool(len(gdf)) and "Polygon" in gdf.geom_type.iloc[0],
                                help="zones go under, POIs go over")
            cols = [c for c in gdf.columns if c != gdf.geometry.name]
            # same split the road layer has: click popup fields vs hover tooltip fields
            popup = st.multiselect("Click popup columns", cols, default=cols, key=f"ov_p{i}",
                                   help="Shown on click (popup + the dashboard sidebar). "
                                        "Empty = not clickable.")
            tooltip = st.multiselect("Hover tooltip columns", cols, default=[], key=f"ov_t{i}",
                                     help="Follows the mouse. Empty = hover only highlights.")
        place = "under" if under else "over"
        kw = dict(label=label, color=color, placement=place, popup=popup)
        arg = (f'label={label!r}, color={color!r}, placement={place!r}, popup={popup!r}')
        if tooltip:
            kw["tooltip"] = tooltip
            arg += f", tooltip={tooltip!r}"
        overlays.append(rs.Overlay(gdf, **kw))
        lines.append(f'ov{i} = rs.Overlay(gpd.read_file("{code_path}"), {arg})')
    return overlays, lines
