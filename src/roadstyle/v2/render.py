"""High-level one-line render() facade for roadstyle v2."""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, MultiLineString, shape

from .engine.compiler import WebMap, compile_map
from .engine.primitives import Corridor, ViewPreset


def _to_hex_color(rgba: tuple[float, float, float, float]) -> str:
    """Convert (r, g, b, a) float tuple (0..1) to #rrggbb hex string."""
    r, g, b = rgba[:3]
    return f"#{int(round(r * 255)):02x}{int(round(g * 255)):02x}{int(round(b * 255)):02x}"


def _is_truthy(val: Any) -> bool:
    """Check if value represents a truthy flag (e.g. 'yes', 1, True)."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("1", "true", "yes", "t", "y")


# Cartographic road-class palette (dark-theme friendly): warm, saturated major
# roads fading to cool, muted minor roads so hierarchy reads at a glance.
HIGHWAY_PALETTE: dict[str, str] = {
    "motorway": "#f0835a",
    "trunk": "#f39c5d",
    "primary": "#f5b95f",
    "secondary": "#e9d77a",
    "tertiary": "#d6dde6",
    "residential": "#a3adbb",
    "unclassified": "#a3adbb",
    "living_street": "#8e99a8",
    "service": "#6b7686",
    "_default": "#8a94a3",
}


# Minimum drawn carriageway width (metres) per road class when lane count is unknown.
HIGHWAY_MIN_WIDTH_M: dict[str, float] = {
    "motorway": 10.5,
    "motorway_link": 4.5,
    "trunk": 9.5,
    "trunk_link": 4.5,
    "primary": 7.5,
    "primary_link": 4.0,
    "secondary": 6.5,
    "secondary_link": 4.0,
    "tertiary": 5.5,
    "tertiary_link": 3.5,
    "residential": 5.0,
    "unclassified": 4.5,
    "living_street": 4.0,
    "service": 3.5,
}


def render(
    roads: Any,
    *,
    width: str | float | int = "width_m",
    lane_width_m: float = 3.5,
    casing: str | float | tuple[float, float] = 0.35,
    casing_color: str | None = None,
    color: str | None = None,
    palette: str | dict[str, str] | None = None,
    split_setback: float | tuple[float, float] | str = 5.0,
    band: str | int | None = None,
    priority: str | float | None = None,
    tooltip: list[str] | bool = True,
    basemap: str | None = "carto-dark",
    background: str | None = None,
    presets: list[ViewPreset] | None = None,
    center: tuple[float, float] | None = None,
    zoom: float | None = None,
    auto_solve: bool = True,
    theme: str = "dark",
    interactive: bool = True,
    smooth: int = 2,
) -> WebMap:
    """One-line high-level entry point to render road networks into a 60 FPS WebGL map.

    Accepts GeoPandas GeoDataFrames, pandas DataFrames with geometry, GeoJSON
    FeatureCollections, or lists of Shapely geometries.

    Parameters
    ----------
    roads : GeoDataFrame, DataFrame, GeoJSON dict, or list of geometries
        The road network to visualize.
    width : str, float, or int
        Column name (e.g. "lanes", "width_m") or fixed scalar width in meters (default "width_m").
    lane_width_m : float
        Width in meters to multiply by if the width column indicates lane counts (default 3.5m).
    casing : str, float, or tuple of (c_left, c_right)
        Outer curb/barrier thickness in meters (default 0.25m).
    casing_color : str
        Hex color of the outer casing curb (default "#222222").
    color : str, optional
        Hex color string (e.g. "#38bdf8") or attribute column name for thematic coloring.
    palette : str or dict, optional
        Colormap name (e.g. "viridis", "turbo") or categorical dict mapping values to colors.
    split_setback : float, tuple, or str
        Junction setback in meters to trim at intersections (default 5.0m).
    band : str or int, optional
        Vertical elevation band (-1 tunnel, 0 surface, +1 bridge) or column name.
    priority : str or float, optional
        Junction flow priority (e.g. 100 for roundabout) or column name.
    tooltip : list of str or bool
        List of attribute names to show in hover inspection tooltips, or True for all attributes.
    basemap : str or None
        Basemap tile provider ("carto-dark", "carto-light", "osm", or None).
    presets : list[ViewPreset], optional
        Optional multi-dimensional client-side view presets.
    center : tuple of (lon, lat), optional
        Map center coordinate. Auto-computed from bounding box if None.
    zoom : float, optional
        Initial camera zoom level. Auto-computed from bounding box if None.
    auto_solve : bool
        Automatically run the LP stacking solver for vertical grade separation.
    theme : str
        Theme mode ("dark" or "light").
    interactive : bool
        Enable hover tooltips and interactive selection halos.
    smooth : int
        Display-only Chaikin smoothing passes for road geometry (default 2; 0 disables it).

    Returns
    -------
    WebMap
        An interactive MapLibre WebGL vector map instance.
    """
    # 1. Normalize Input Rows & Geometries
    raw_rows: list[dict[str, Any]] = []

    # GeoDataFrame / DataFrame
    if hasattr(roads, "iterfeatures"):
        for ft in roads.iterfeatures():
            g = shape(ft["geometry"])
            raw_rows.append({"geometry": g, "properties": ft.get("properties") or {}})
    elif hasattr(roads, "iterrows"):
        # Pandas or GeoPandas DataFrame
        geom_col = getattr(roads, "_geometry_column_name", "geometry")
        for _, row in roads.iterrows():
            g = row.get(geom_col)
            props = {k: v for k, v in row.items() if k != geom_col}
            raw_rows.append({"geometry": g, "properties": props})
    elif isinstance(roads, dict) and roads.get("type") == "FeatureCollection":
        for ft in roads.get("features", []):
            g = shape(ft["geometry"])
            raw_rows.append({"geometry": g, "properties": ft.get("properties") or {}})
    elif isinstance(roads, (list, tuple)):
        for item in roads:
            if hasattr(item, "geom_type"):
                raw_rows.append({"geometry": item, "properties": {}})
            elif isinstance(item, dict) and "geometry" in item:
                g = item["geometry"]
                g_geom = g if hasattr(g, "geom_type") else shape(g)
                raw_rows.append({"geometry": g_geom, "properties": item.get("properties") or {}})
    else:
        raise TypeError(f"roads must be a GeoDataFrame, DataFrame, GeoJSON dict, or list of geometries, got {type(roads)}")

    # 2. Setup Color Mapping if color is a column name
    color_map: dict[Any, str] = {}
    is_color_column = False
    numeric_min = float("inf")
    numeric_max = float("-inf")
    is_numeric_color = False

    if color and not (color.startswith("#") or color.startswith("rgb") or color.startswith("hsl")):
        is_color_column = True
        # Check column values
        vals = [r["properties"].get(color) for r in raw_rows if r["properties"].get(color) is not None]
        if vals:
            if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
                is_numeric_color = True
                numeric_min = min(vals)
                numeric_max = max(vals)
            else:
                # Categorical values
                unique_vals = sorted(set(vals), key=str)
                if isinstance(palette, dict):
                    color_map = dict(palette)
                elif palette in (None, "highway") and color == "highway":
                    for uv in unique_vals:
                        key = str(uv).replace("_link", "")
                        color_map[uv] = HIGHWAY_PALETTE.get(key, HIGHWAY_PALETTE["_default"])
                else:
                    # Sample colormap or fallback palette
                    try:
                        import matplotlib.pyplot as plt
                        cmap_name = palette if isinstance(palette, str) else "tab10"
                        cmap = plt.get_cmap(cmap_name)
                        k = len(unique_vals)
                        for i_v, uv in enumerate(unique_vals):
                            t = i_v / max(1, k - 1)
                            color_map[uv] = _to_hex_color(cmap(t))
                    except Exception:
                        cat_colors = ["#38bdf8", "#34d399", "#f59e0b", "#f43f5e", "#a855f7", "#ec4899", "#14b8a6"]
                        for i_v, uv in enumerate(unique_vals):
                            color_map[uv] = cat_colors[i_v % len(cat_colors)]

    # 3. Process Each Road into Corridors
    corridors: list[Corridor] = []

    for r in raw_rows:
        geom = r["geometry"]
        if geom is None:
            continue

        props = dict(r["properties"])

        # Decompose MultiLineString into LineStrings
        if isinstance(geom, MultiLineString):
            sub_geoms = list(geom.geoms)
        elif isinstance(geom, LineString):
            sub_geoms = [geom]
        else:
            continue

        # Physical Width (meters)
        hw = str(props.get("highway") or "").split(";")[0].strip().lower()
        default_w = HIGHWAY_MIN_WIDTH_M.get(hw, 5.0)
        w_m = default_w

        if isinstance(width, (int, float)):
            w_m = float(width)
        elif isinstance(width, str) and width in props and props[width] is not None:
            try:
                raw_w = float(props[width])
                if not math.isnan(raw_w) and raw_w > 0:
                    if "lane" in width.lower():
                        w_m = max(raw_w * lane_width_m, 2.8)
                    else:
                        w_m = max(raw_w, 2.8)
                else:
                    w_m = default_w
            except (ValueError, TypeError):
                w_m = default_w
        else:
            w_m = default_w

        # Casing Thickness (meters)
        c_left, c_right = 0.25, 0.25
        if isinstance(casing, (tuple, list)) and len(casing) >= 2:
            c_left, c_right = float(casing[0]), float(casing[1])
        elif isinstance(casing, (int, float)):
            c_left = c_right = float(casing)
        elif isinstance(casing, str) and casing in props and props[casing] is not None:
            try:
                c_val = float(props[casing])
                c_left = c_right = c_val
            except (ValueError, TypeError):
                pass

        # Split Setbacks (meters)
        s_start, s_end = 5.0, 5.0
        if isinstance(split_setback, (tuple, list)) and len(split_setback) >= 2:
            s_start, s_end = float(split_setback[0]), float(split_setback[1])
        elif isinstance(split_setback, (int, float)):
            s_start = s_end = float(split_setback)
        elif isinstance(split_setback, str) and split_setback in props and props[split_setback] is not None:
            try:
                s_val = float(props[split_setback])
                s_start = s_end = s_val
            except (ValueError, TypeError):
                pass

        # Vertical Grade Band
        b_val = 0
        if isinstance(band, int):
            b_val = band
        elif isinstance(band, str) and band in props and props[band] is not None:
            try:
                b_val = int(props[band])
            except (ValueError, TypeError):
                b_val = 0
        else:
            # Auto-infer from layer, bridge, tunnel tags
            if "band" in props and props["band"] is not None:
                try:
                    b_val = int(props["band"])
                except Exception:
                    pass
            elif "layer" in props and props["layer"] is not None:
                try:
                    b_val = int(props["layer"])
                except Exception:
                    pass
            elif _is_truthy(props.get("bridge")):
                b_val = 1
            elif _is_truthy(props.get("tunnel")):
                b_val = -1

        # Junction Priority
        p_val = 0.0
        if isinstance(priority, (int, float)):
            p_val = float(priority)
        elif isinstance(priority, str) and priority in props and props[priority] is not None:
            try:
                p_val = float(props[priority])
            except (ValueError, TypeError):
                p_val = 0.0
        else:
            # Auto-infer roundabout dominance
            j_tag = str(props.get("junction") or "").lower()
            if j_tag in ("roundabout", "circular") or _is_truthy(props.get("roundabout")):
                p_val = 100.0

        # Pavement Fill Color
        fill_col = "#ffffff" if theme == "dark" else "#334155"
        if color:
            if not is_color_column:
                fill_col = color
            else:
                row_val = props.get(color)
                if row_val is not None:
                    if is_numeric_color:
                        try:
                            import matplotlib.pyplot as plt
                            cmap_name = palette if isinstance(palette, str) else "viridis"
                            cmap = plt.get_cmap(cmap_name)
                            if numeric_max > numeric_min:
                                norm = (float(row_val) - numeric_min) / (numeric_max - numeric_min)
                            else:
                                norm = 0.5
                            fill_col = _to_hex_color(cmap(norm))
                        except Exception:
                            fill_col = "#38bdf8"
                    else:
                        fill_col = color_map.get(row_val, fill_col)

        # Filter Tooltip Properties
        filtered_props: dict[str, Any] = {}
        if isinstance(tooltip, list):
            filtered_props = {k: props[k] for k in tooltip if k in props}
        elif tooltip is True:
            # Keep all serializable scalar properties
            filtered_props = {
                k: v for k, v in props.items()
                if isinstance(v, (str, int, float, bool)) and not (isinstance(v, float) and math.isnan(v))
            }
        if "highway" in props:
            filtered_props["highway"] = props["highway"]
        if "edge_ref" in props and props["edge_ref"] is not None:
            filtered_props["edge_ref"] = str(props["edge_ref"])
        elif "ref" in props and props["ref"] is not None:
            filtered_props["edge_ref"] = str(props["ref"])
        if "edge_id" in props:
            filtered_props["edge_id"] = str(props["edge_id"])
        elif "id" in props:
            filtered_props["edge_id"] = str(props["id"])
        if "name" in props:
            filtered_props["name"] = props["name"]

        is_bridge = _is_truthy(props.get("bridge")) or b_val > 0
        is_tunnel = _is_truthy(props.get("tunnel")) or b_val < 0
        filtered_props["bridge"] = bool(is_bridge)
        filtered_props["tunnel"] = bool(is_tunnel)

        # Pre-computed levels from compute_levels or upstream pipeline
        cs = props.get("casing_start")
        cm = props.get("casing_level")
        ce = props.get("casing_end")
        fl = props.get("fill_level")
        casing_lvls = None
        if cs is not None and cm is not None and ce is not None:
            try:
                casing_lvls = (int(round(float(cs))), int(round(float(cm))), int(round(float(ce))))
            except Exception:
                casing_lvls = None
        fill_lvl = None
        if fl is not None:
            try:
                fill_lvl = int(round(float(fl)))
            except Exception:
                fill_lvl = None

        eid_val = str(props.get("edge_id") or props.get("id") or "")

        for sg in sub_geoms:
            corridors.append(
                Corridor(
                    id=eid_val,
                    geometry=sg,
                    width_m=w_m,
                    casing_left_m=c_left,
                    casing_right_m=c_right,
                    split_start=s_start,
                    split_end=s_end,
                    band=b_val,
                    junction_priority=p_val,
                    casing_levels=casing_lvls,
                    fill_level=fill_lvl,
                    fill_color=fill_col,
                    casing_color=casing_color or ("#1e293b" if theme == "dark" else "#475569"),
                    bridge_deck=is_bridge,
                    tunnel=is_tunnel,
                    interactive=interactive,
                    properties=filtered_props,
                )
            )

    # 4. Compile into WebMap
    return compile_map(
        corridors=corridors,
        presets=presets,
        basemap=basemap,
        background=background,
        center=center,
        zoom=zoom,
        auto_solve=auto_solve,
        theme=theme,
        smooth=smooth,
    )
