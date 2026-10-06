"""OpenStreetMap (OSM) Adapter for roadstyle v2.

Translates OSM road ways, tags, and spatial attributes directly into
roadstyle v2 primitives (Corridor, Channel, Demarcation).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from shapely.geometry import LineString, shape

from ..engine.compiler import WebMap, compile_map
from ..engine.primitives import Channel, Corridor, Demarcation, ViewPreset
from ..profile import StyleProfile, load_profile


# Widths, casings and colours come from a style profile: see roadstyle.v2.profile.
# These two names keep the default profile's tables importable.
OSM_HIGHWAY_WIDTHS: dict[str, float] = dict(load_profile()["class_width_m"])
OSM_HIGHWAY_COLORS: dict[str, str] = dict(load_profile()["colors"])


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
        profile: str | Path | dict | StyleProfile | None = None,
    ) -> list[Corridor]:
        """Convert OSM GeoDataFrame into roadstyle v2 Corridors.

        ``profile`` picks the widths, casings and colours (see :mod:`roadstyle.v2.profile`).
        """
        style = load_profile(profile)
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

            # Physical Width: the profile's width_sources decide which value wins
            w_m = None
            for source in style["width_sources"]:
                if source == "width":
                    try:
                        w_m = float(str(r["width"]).replace("m", "").strip())
                    except (KeyError, TypeError, ValueError):
                        pass
                elif source == "lanes":
                    try:
                        w_m = float(r["lanes"]) * style.lane_width(hw)
                    except (KeyError, TypeError, ValueError):
                        pass
                else:
                    w_m = style.class_width(hw)
                if w_m is not None and w_m == w_m:
                    break
                w_m = None
            if w_m is None:
                w_m = float(style["default_width_m"])

            c_left, c_right = style.casing(hw)

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
                p_val = float(style["roundabout_priority"])

            color = style.color(hw)

            is_bridge = _is_truthy(r.get("bridge")) or band > 0
            is_tunnel = _is_truthy(r.get("tunnel")) or band < 0

            corridors.append(
                Corridor(
                    geometry=geom,
                    id=r.get("osm_id") or r.get("id"),
                    width_m=w_m,
                    casing_left_m=c_left,
                    casing_right_m=c_right,
                    split_start=float(style["split_m"]),
                    split_end=float(style["split_m"]),
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
