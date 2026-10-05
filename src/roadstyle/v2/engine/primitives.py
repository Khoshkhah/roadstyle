"""Universal cartographic primitives for roadstyle v2 Core Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shapely.geometry.base import BaseGeometry


@dataclass(slots=True)
class Corridor:
    """A 1D corridor reference polyline representing a physical right-of-way container."""

    geometry: Any
    id: str | int | None = None

    # Physical Dimensions
    width_m: float = 8.0
    casing_left_m: float = 0.20
    casing_right_m: float = 0.20

    # 2-Point Casing Split (Asymmetric Junction Setbacks or Stations)
    # Mode: "setbacks" (h_start, h_end) or "stations" (s_start, s_end)
    split_mode: str = "setbacks"
    split_start: float = 5.0
    split_end: float = 5.0

    # Stacking & Levels
    band: int = 0
    junction_priority: float = 0.0
    casing_levels: tuple[int, int, int] | None = None  # (cs, cm, ce)
    fill_level: int | None = None

    # Visual Properties
    fill_visible: bool = True
    fill_color: str = "#ffffff"
    casing_color: str = "#222222"
    bridge_deck: bool = False
    tunnel: bool = False

    # Interaction
    interactive: bool = True
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def casing_m(self) -> float:
        """Symmetric average casing thickness."""
        return (self.casing_left_m + self.casing_right_m) / 2.0


@dataclass(slots=True)
class Channel:
    """A longitudinal flow channel (lane, cycle track, rail, sidewalk) running inside or across corridors."""

    geometry: Any
    id: str | int | None = None
    corridor_id: str | int | None = None

    width_m: float = 3.50
    offset_m: float = 0.0

    order: int = 0
    band: int = 0
    level: int = 0
    priority: float = 0.0

    fill_color: str = "#444444"
    color: str = "#444444"
    opacity: float = 1.0
    dash_array: list[float] | None = None

    interactive: bool = True
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Demarcation:
    """A zero-area boundary or dividing paint line (lane divider, stop bar, edge line)."""

    geometry: Any
    id: str | int | None = None
    corridor_id: str | int | None = None

    stroke_px: float = 2.0
    stroke_m: float | None = None
    width_m: float = 0.15
    pattern: str = "solid"
    color: str = "#ffffff"
    opacity: float = 0.9
    dash_array: list[float] = field(default_factory=list)
    cap: str = "butt"

    order: int = 1
    band: int = 0
    level: int = 0

    interactive: bool = False
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Patch:
    """A 2D planar polygon surface (junction fillet, painted island, crosswalk zebra, wedge)."""

    geometry: Any
    id: str | int | None = None

    fill_color: str = "#333333"
    color: str = "#333333"
    fill_opacity: float = 1.0
    opacity: float = 1.0
    outline_color: str | None = None
    outline_width_px: float = 0.0

    order: int = -1
    band: int = 0
    level: int = 0

    interactive: bool = False
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Glyph:
    """An oriented symbol, lane arrow, shield, or text annotation."""

    geometry: Any
    id: str | int | None = None

    symbol: str | None = None
    text: str | None = None
    size: float = 1.0
    color: str = "#ffffff"
    alignment: str = "line"

    order: int = 10
    band: int = 0
    level: int = 0

    interactive: bool = False
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ViewPreset:
    """A multi-dimensional client-side visual preset (Color, Width, Labels, Filters)."""

    name: str

    # 1. Color Dimension
    color_by: str | None = None
    palette: str | dict[str, str] | None = None
    cmap: str | None = None
    vmin: float | None = None
    vmax: float | None = None
    legend_title: str | None = None

    # 2. Width Dimension
    width_mode: str = "physical"  # "physical", "flow", "schematic"
    width_by: str | None = None
    width_scale: float = 1.0
    min_width_px: float = 2.0
    max_width_px: float = 30.0

    # 3. Label / Annotation Dimension
    label_by: str | None = None

    # 4. Filter / Sub-Network Isolation
    filter_expr: list[Any] | None = None
    opacity_unselected: float = 0.10

    # 5. Camera View Position
    center: tuple[float, float] | None = None
    zoom: float | None = None

