"""Lane-level rendering for roadstyle v2.

Turns a lane table (one row per lane centreline, e.g. ``monaco_lanes.parquet``)
into v2 primitives and compiles them into a single-source WebMap:

* ``Channel``      - every lane surface, coloured by its ``use`` (auto / bus / bike / walk)
* ``Demarcation``  - painted lines: dashed lane dividers, solid centre lines, road edges
* direction arrows - a symbol layer along every one-way, non-connector lane
* street names     - one line-placed label per named road
* bridges/tunnels  - bridges get a dark deck outline, tunnels are faded with a dashed outline

All look-and-feel lives in :data:`LANE_STYLE` (modelled on lanestyle v1's
``lanestyle.json``); pass ``style=`` overrides to change it.
"""

from __future__ import annotations

import copy
import math
from typing import Any

import shapely
from shapely.geometry import LineString, MultiLineString
from shapely.strtree import STRtree

from .engine.compiler import WebMap, compile_map
from .engine.primitives import Channel, Demarcation


LANE_STYLE: dict[str, Any] = {
    "colors": {
        "auto": "#a3a3a3",
        "bus": "#d6336c",
        "bike": "#1c7ed6",
        "walk": "#f0cb8c",
        "connector": "#8f8f8f",
        "_default": "#a3a3a3",
    },
    "lines": {
        "divider": {"color": "#f4f4f4", "width_m": 0.15, "pattern": "dashed"},
        "centre": {"color": "#f4f4f4", "width_m": 0.15, "pattern": "solid"},
        "edge": {"color": "#f4f4f4", "width_m": 0.12, "pattern": "solid"},
    },
    "default_width_m": 3.25,
    "width_m_by_use": {"walk": 2.0, "bike": 1.5},
    # Two lane edges closer than this (metres) are treated as one shared line.
    "edge_match_m": 0.8,
}


def _merge(base: dict[str, Any], over: dict[str, Any] | None) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _isna(v: Any) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _truthy(v: Any) -> bool:
    if _isna(v):
        return False
    return str(v).strip().lower() not in ("", "no", "false", "0", "none")


def _level(row: dict[str, Any]) -> int:
    lay = row.get("layer")
    if not _isna(lay):
        try:
            return int(float(lay))
        except (TypeError, ValueError):
            pass
    if _truthy(row.get("bridge")):
        return 1
    if _truthy(row.get("tunnel")):
        return -1
    return 0


def _lines(g: Any) -> list[LineString]:
    if isinstance(g, LineString):
        return [g]
    if isinstance(g, MultiLineString):
        return list(g.geoms)
    return []


def render_lanes(
    lanes: Any,
    *,
    style: dict[str, Any] | None = None,
    basemap: str | None = "carto-dark",
    theme: str = "dark",
    center: tuple[float, float] | None = None,
    zoom: float | None = None,
) -> WebMap:
    """Render a lane GeoDataFrame as a styled, lane-level interactive map.

    Expected columns (missing ones are tolerated): ``geometry`` (lane centreline,
    in the direction of travel), ``width_m``, ``use``, ``name``, ``link_id``,
    ``lane_num``, ``turn``, ``bridge``, ``tunnel``, ``layer``, ``connector``.
    """
    s = _merge(LANE_STYLE, style)
    colors = s["colors"]

    g4326 = lanes.to_crs(4326) if getattr(lanes, "crs", None) is not None else lanes
    metric = g4326.to_crs(g4326.estimate_utm_crs())
    cols = [c for c in g4326.columns if c != g4326.geometry.name]
    records = g4326[cols].to_dict("records")
    geoms_ll = list(g4326.geometry.values)
    geoms_m = list(metric.geometry.values)

    channels: list[Channel] = []
    # Per-lane metric info for lane-marking detection (non-connector lanes only).
    lane_info: list[dict[str, Any]] = []

    for i, row in enumerate(records):
        g = geoms_ll[i]
        if g is None or g.is_empty:
            continue
        use = str(row.get("use") or "auto")
        is_conn = bool(row.get("connector")) if not _isna(row.get("connector")) else False
        w = row.get("width_m")
        if _isna(w) or not w:
            w = s["width_m_by_use"].get(use, s["default_width_m"])
        w = float(w)
        lvl = _level(row)
        is_bridge = _truthy(row.get("bridge")) or lvl > 0
        is_tunnel = _truthy(row.get("tunnel")) or lvl < 0
        color = colors["connector"] if (is_conn and use == "auto") else colors.get(use, colors["_default"])
        name = row.get("name")
        lane_num = row.get("lane_num")
        props = {
            "name": None if _isna(name) else str(name),
            "highway": None if _isna(row.get("highway")) else str(row.get("highway")),
            "use": use,
            "lane_id": None if _isna(row.get("lane_id")) else str(row.get("lane_id")),
            "lane_num": None if _isna(lane_num) else int(lane_num),
            "lanes": None if _isna(row.get("lanes")) else int(row.get("lanes")),
            "turn": None if _isna(row.get("turn")) else str(row.get("turn")),
            "connector": is_conn,
            "oneway": (not is_conn) and use != "walk",
            "bridge": is_bridge,
            "tunnel": is_tunnel,
        }
        for part in _lines(g):
            channels.append(Channel(geometry=part, width_m=w, level=lvl, color=color, properties=dict(props)))

        if not is_conn:
            for part in _lines(geoms_m[i]):
                lane_info.append({
                    "geom_m": part, "width": w, "link": row.get("link_id"),
                    "level": lvl, "bridge": is_bridge, "tunnel": is_tunnel,
                })

    demarcations = _lane_markings(lane_info, s, metric.crs)

    from .engine.primitives import ViewPreset
    default_presets = [
        ViewPreset(name="Port Hercule", width_mode="physical", center=(7.4205, 43.7348), zoom=18.0),
        ViewPreset(name="Monte Carlo Casino", width_mode="physical", center=(7.4285, 43.7392), zoom=18.0),
        ViewPreset(name="Larvotto Viaduct", width_mode="physical", center=(7.4320, 43.7460), zoom=17.5),
        ViewPreset(name="Monaco Overview", width_mode="physical", center=(7.422, 43.738), zoom=15.0),
    ]

    return compile_map(
        channels=channels,
        demarcations=demarcations,
        presets=default_presets,
        basemap=basemap,
        theme=theme,
        center=center,
        zoom=zoom,
        auto_solve=False,
    )


def _lane_markings(info: list[dict[str, Any]], s: dict[str, Any], crs: Any) -> list[Demarcation]:
    """Classify each lane edge as a divider, centre line or road edge and emit Demarcations."""
    if not info:
        return []
    import geopandas as gpd

    tree = STRtree([d["geom_m"] for d in info])
    match = s["edge_match_m"]
    out_geoms: list[Any] = []
    out_meta: list[tuple[str, dict[str, Any]]] = []

    for i, d in enumerate(info):
        line = d["geom_m"]
        if line.length < 1.0:
            continue
        half = d["width"] / 2.0
        for side in (half, -half):
            try:
                edge = line.offset_curve(side)
            except Exception:
                continue
            if edge is None or edge.is_empty or edge.length < 0.5:
                continue
            mid = edge.interpolate(0.5, normalized=True)
            kind = "edge"
            skip = False
            for j in tree.query(mid.buffer(half + 4.0)):
                if j == i:
                    continue
                o = info[j]
                if o["level"] != d["level"]:
                    continue
                if abs(o["geom_m"].distance(mid) - o["width"] / 2.0) <= match:
                    # Shared edge: emit it once (from the lower index).
                    if j < i:
                        skip = True
                    kind = "divider" if o["link"] == d["link"] else "centre"
                    break
            if skip:
                continue
            out_geoms.append(edge)
            out_meta.append((kind, d))

    if not out_geoms:
        return []
    ll = gpd.GeoSeries(out_geoms, crs=crs).to_crs(4326)
    dems: list[Demarcation] = []
    for g, (kind, d) in zip(ll.values, out_meta):
        st = s["lines"][kind]
        dems.append(Demarcation(
            geometry=g,
            width_m=st["width_m"],
            color=st["color"],
            pattern=st["pattern"],
            level=d["level"],
            properties={"kind": kind, "bridge": d["bridge"], "tunnel": d["tunnel"]},
        ))
    return dems
