"""OpenStreetMap (OSM) Adapter for roadstyle v2.

Translates OSM road ways, tags, and spatial attributes directly into
roadstyle v2 primitives (Corridor, Channel, Demarcation).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from shapely.geometry import LineString, shape

from ..engine.compiler import WebMap, compile_map
from ..engine.primitives import Channel, Corridor, Demarcation, ViewPreset


# Default physical roadway widths by OSM highway tag
OSM_HIGHWAY_WIDTHS: dict[str, float] = {
    "motorway": 14.0,
    "motorway_link": 7.0,
    "trunk": 12.0,
    "trunk_link": 7.0,
    "primary": 10.5,
    "primary_link": 6.5,
    "secondary": 8.0,
    "secondary_link": 6.0,
    "tertiary": 7.0,
    "tertiary_link": 5.5,
    "residential": 6.5,
    "living_street": 5.5,
    "unclassified": 6.0,
    "service": 4.5,
    "cycleway": 2.5,
    "footway": 2.0,
    "pedestrian": 4.0,
    "path": 2.0,
}

OSM_HIGHWAY_COLORS: dict[str, str] = {
    "motorway": "#e11d48",
    "motorway_link": "#e11d48",
    "trunk": "#f97316",
    "trunk_link": "#f97316",
    "primary": "#f59e0b",
    "primary_link": "#f59e0b",
    "secondary": "#10b981",
    "secondary_link": "#10b981",
    "tertiary": "#06b6d4",
    "tertiary_link": "#06b6d4",
    "residential": "#64748b",
    "living_street": "#94a3b8",
    "unclassified": "#64748b",
    "service": "#475569",
    "cycleway": "#16a34a",
    "footway": "#ea580c",
    "pedestrian": "#d97706",
    "path": "#78716c",
}


def _is_truthy(val: Any) -> bool:
    if val is None or pd.isna(val):
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("1", "true", "yes", "t", "y")


class OSMAdapter:
    """Converter for OpenStreetMap road tables and GeoDataFrames."""

    @classmethod
    def from_dataframe(
        cls,
        df: Any,
        *,
        include_bike_lanes: bool = True,
        theme: str = "dark",
    ) -> list[Corridor]:
        """Convert OSM GeoDataFrame into roadstyle v2 Corridors."""
        corridors: list[Corridor] = []
        records = df.to_dict("records") if hasattr(df, "to_dict") else df

        for r in records:
            geom = r.get("geometry")
            if geom is None:
                continue
            if not hasattr(geom, "geom_type"):
                geom = shape(geom)
            if not isinstance(geom, LineString):
                continue

            hw = str(r.get("highway") or "unclassified").lower()

            # Physical Width
            w_m = OSM_HIGHWAY_WIDTHS.get(hw, 6.5)
            if r.get("width") is not None and not pd.isna(r.get("width")):
                try:
                    w_m = float(str(r["width"]).replace("m", "").strip())
                except Exception:
                    pass
            elif r.get("lanes") is not None and not pd.isna(r.get("lanes")):
                try:
                    w_m = float(r["lanes"]) * 3.5
                except Exception:
                    pass

            # Casing
            c_left, c_right = 0.20, 0.20
            if hw in ("motorway", "trunk"):
                c_left, c_right = 0.40, 0.20  # Jersey barrier median + shoulder

            # Vertical Elevation Band
            band = 0
            if _is_truthy(r.get("bridge")):
                band = 1
            elif _is_truthy(r.get("tunnel")):
                band = -1
            elif r.get("layer") is not None and not pd.isna(r.get("layer")):
                try:
                    band = int(r["layer"])
                except Exception:
                    band = 0

            # Roundabout Dominance
            p_val = 0.0
            j_tag = str(r.get("junction") or "").lower()
            if j_tag in ("roundabout", "circular"):
                p_val = 100.0

            color = OSM_HIGHWAY_COLORS.get(hw, "#64748b")

            is_bridge = _is_truthy(r.get("bridge")) or band > 0
            is_tunnel = _is_truthy(r.get("tunnel")) or band < 0

            corridors.append(
                Corridor(
                    geometry=geom,
                    id=r.get("osm_id") or r.get("id"),
                    width_m=w_m,
                    casing_left_m=c_left,
                    casing_right_m=c_right,
                    split_start=6.0,
                    split_end=6.0,
                    band=band,
                    junction_priority=p_val,
                    fill_color=color,
                    bridge_deck=is_bridge,
                    tunnel=is_tunnel,
                    interactive=True,
                    properties={k: v for k, v in r.items() if k != "geometry" and not pd.isna(v)},
                )
            )

        return corridors
