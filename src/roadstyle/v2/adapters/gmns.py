"""GMNS (General Modeling Network Specification) Adapter for roadstyle v2.

Translates standard GMNS transport network specifications (link, lane, segment, movement)
directly into decoupled roadstyle v2 primitives (Corridor, Channel, Demarcation, Patch, Glyph).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from shapely import from_wkt
from shapely.geometry import LineString, Point, shape

from ..engine.compiler import WebMap, compile_map
from ..engine.primitives import Channel, Corridor, Demarcation, Glyph, Patch, ViewPreset


def _parse_geometry(val: Any) -> Any:
    """Parse geometry from WKT string or Shapely object."""
    if val is None or pd.isna(val):
        return None
    if hasattr(val, "geom_type"):
        return val
    if isinstance(val, str):
        val = val.strip()
        if val.startswith("{"):
            import json
            return shape(json.loads(val))
        return from_wkt(val)
    return None


def _is_truthy(val: Any) -> bool:
    if val is None or pd.isna(val):
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("1", "true", "yes", "t", "y")


@dataclass(slots=True)
class GMNSNetwork:
    """A parsed GMNS network mapped to roadstyle v2 primitives."""

    corridors: list[Corridor] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=list)
    demarcations: list[Demarcation] = field(default_factory=list)
    patches: list[Patch] = field(default_factory=list)
    glyphs: list[Glyph] = field(default_factory=list)
    presets: list[ViewPreset] = field(default_factory=list)

    def add_preset(self, preset: ViewPreset | str, **kwargs: Any) -> GMNSNetwork:
        """Add a dynamic client-side ViewPreset."""
        if isinstance(preset, str):
            p = ViewPreset(name=preset, **kwargs)
        else:
            p = preset
        self.presets.append(p)
        return self

    def compile(self, **kwargs: Any) -> WebMap:
        """Compile the network into an interactive MapLibre WebMap."""
        return compile_map(
            corridors=self.corridors,
            channels=self.channels,
            demarcations=self.demarcations,
            patches=self.patches,
            glyphs=self.glyphs,
            presets=self.presets,
            **kwargs,
        )


class GMNSAdapter:
    """Converter for GMNS link, lane, segment, and movement tables."""

    @classmethod
    def from_csv(
        cls,
        directory: str | Path | None = None,
        *,
        link_file: str | Path | None = None,
        lane_file: str | Path | None = None,
        segment_file: str | Path | None = None,
        movement_file: str | Path | None = None,
    ) -> GMNSNetwork:
        """Load GMNS network from CSV files."""
        dir_p = Path(directory) if directory else None

        def resolve_file(explicit: str | Path | None, default_name: str) -> Path | None:
            if explicit:
                p = Path(explicit)
                return p if p.exists() else None
            if dir_p:
                candidates = [dir_p / default_name, dir_p / f"{default_name}.csv", dir_p / default_name.lower()]
                for c in candidates:
                    if c.exists():
                        return c
            return None

        f_link = resolve_file(link_file, "link.csv")
        f_lane = resolve_file(lane_file, "lane.csv")
        f_seg = resolve_file(segment_file, "segment.csv")
        f_mov = resolve_file(movement_file, "movement.csv")

        links_df = pd.read_csv(f_link) if f_link else None
        lanes_df = pd.read_csv(f_lane) if f_lane else None
        segs_df = pd.read_csv(f_seg) if f_seg else None
        movs_df = pd.read_csv(f_mov) if f_mov else None

        return cls.from_dataframes(links=links_df, lanes=lanes_df, segments=segs_df, movements=movs_df)

    @classmethod
    def from_dataframes(
        cls,
        links: Any = None,
        lanes: Any = None,
        segments: Any = None,
        movements: Any = None,
    ) -> GMNSNetwork:
        """Convert in-memory DataFrames or GeoDataFrames into roadstyle v2 primitives."""
        corridors: list[Corridor] = []
        channels: list[Channel] = []
        demarcations: list[Demarcation] = []
        patches: list[Patch] = []
        glyphs: list[Glyph] = []

        # 1. Parse Lanes if available
        lanes_by_link: dict[Any, list[dict[str, Any]]] = {}
        if lanes is not None:
            lane_records = lanes.to_dict("records") if hasattr(lanes, "to_dict") else lanes
            for r in lane_records:
                geom = _parse_geometry(r.get("geometry"))
                if geom is None:
                    continue

                link_ref = r.get("link_id")
                lanes_by_link.setdefault(link_ref, []).append(r)

                w = float(r.get("width") or r.get("width_m") or 3.5)
                is_conn = _is_truthy(r.get("connector"))
                priority = 5.0 if is_conn else 0.0

                # Determine lane color by mode
                mode = str(r.get("mode") or r.get("modes") or "").lower()
                if "bus" in mode or "transit" in mode:
                    col = "#0284c7"  # Bus lane cyan-blue
                elif "bike" in mode or "cycle" in mode:
                    col = "#16a34a"  # Cycle track green
                elif "walk" in mode or "foot" in mode:
                    col = "#ea580c"  # Pedestrian brick
                else:
                    col = "#1e293b"  # Asphalt dark

                channels.append(
                    Channel(
                        geometry=geom,
                        id=r.get("lane_id"),
                        corridor_id=link_ref,
                        width_m=w,
                        fill_color=col,
                        priority=priority,
                        interactive=True,
                        properties={k: v for k, v in r.items() if k != "geometry" and not pd.isna(v)},
                    )
                )

        # 2. Parse Links into Parent Corridors
        if links is not None:
            link_records = links.to_dict("records") if hasattr(links, "to_dict") else links
            for r in link_records:
                geom = _parse_geometry(r.get("geometry"))
                if geom is None or not isinstance(geom, LineString):
                    continue

                link_id = r.get("link_id")
                child_lanes = lanes_by_link.get(link_id, [])

                # If child lanes exist, corridor is hollow container envelope (fill_visible=False)
                has_child_lanes = len(child_lanes) > 0

                if has_child_lanes:
                    total_lane_width = sum(float(l.get("width") or l.get("width_m") or 3.5) for l in child_lanes)
                    w_m = total_lane_width
                    fill_vis = False
                else:
                    n_lanes = float(r.get("lanes") or r.get("lane_count") or 2)
                    w_m = n_lanes * 3.5
                    fill_vis = True

                # Grade Band
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

                # Junction Priority (Roundabout ring dominance)
                p_val = 0.0
                j_tag = str(r.get("junction") or "").lower()
                if j_tag in ("roundabout", "circular") or _is_truthy(r.get("roundabout")):
                    p_val = 100.0

                # Setbacks
                s1 = float(r.get("split_start") or 6.0)
                s2 = float(r.get("split_end") or 6.0)

                corridors.append(
                    Corridor(
                        geometry=geom,
                        id=link_id,
                        width_m=w_m,
                        casing_left_m=0.30,
                        casing_right_m=0.30,
                        split_start=s1,
                        split_end=s2,
                        band=band,
                        junction_priority=p_val,
                        fill_visible=fill_vis,
                        fill_color="#334155",
                        casing_color="#18181b",
                        interactive=not has_child_lanes,
                        properties={k: v for k, v in r.items() if k != "geometry" and not pd.isna(v)},
                    )
                )

        # 3. Parse Movements into Directional Glyphs
        if movements is not None:
            mov_records = movements.to_dict("records") if hasattr(movements, "to_dict") else movements
            for r in mov_records:
                geom = _parse_geometry(r.get("geometry"))
                m_type = str(r.get("movement_type") or r.get("turn_type") or "").lower()

                # Map movement type to icon name
                icon = None
                if "left" in m_type:
                    icon = "turn-left"
                elif "right" in m_type:
                    icon = "turn-right"
                elif "through" in m_type or "thru" in m_type:
                    icon = "through"
                elif "u" in m_type:
                    icon = "u-turn"

                if geom is not None and icon:
                    glyphs.append(
                        Glyph(
                            geometry=geom,
                            id=r.get("movement_id"),
                            symbol=icon,
                            interactive=False,
                            properties={k: v for k, v in r.items() if k != "geometry" and not pd.isna(v)},
                        )
                    )

        return GMNSNetwork(
            corridors=corridors,
            channels=channels,
            demarcations=demarcations,
            patches=patches,
            glyphs=glyphs,
        )
