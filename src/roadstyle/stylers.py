"""Stylers: the abstraction that maps a whole GeoDataFrame to per-edge styles.

A :class:`Styler` answers one question — *"for every edge in this table, what fill colour,
width, casing, opacity and dash does it get?"* — and returns a :class:`ResolvedFrame` of
parallel arrays. The renderers (folium / lonboard / JSON) consume that frame and never decide
colours themselves, so all three backends and all styling modes share one code path.

``ClassStyler`` reproduces the original OSM behaviour (and supports custom vocabularies);
``CategoricalStyler`` and ``NumericStyler`` (added in Phase 2) style by an arbitrary column.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable

from .config import DEFAULT, StyleConfig
from .palettes import FALLBACK, PALETTES, RoadStyle
from .style import _apply, normalize_highway
from .themes import Theme, get_theme

_TRUE = {"yes", "true", "1", "y", "t"}


def _truthy(v) -> bool:
    """Loosely interpret a tunnel/bridge column value as a boolean."""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in _TRUE


def _dash_str(dash) -> str | None:
    """Render a (on, off) dash tuple as the ``"4,4"`` string folium/Leaflet expect."""
    if not dash:
        return None
    if isinstance(dash, str):
        return dash
    return ",".join(str(x) for x in dash)


@dataclass
class ResolvedFrame:
    """Per-edge resolved style arrays — the contract every renderer consumes.

    Every list has length ``len(gdf)``. ``casing_light``/``casing_dark`` are both kept so the
    interactive folium layer can swap casing on a light↔dark base-map change. ``klass`` carries
    the per-edge category value (road class / bin label) used for filtering and legends.
    """
    fill: list[str]
    width: list[float]
    casing_light: list[str | None]
    casing_dark: list[str | None]
    casing_width: list[float]
    dash: list[str | None]
    opacity: list[float]
    casing_opacity: list[float]
    klass: list[str | None]
    theme_aware_casing: bool = True   # True only when casing differs by light/dark base map
    legend: object | None = None      # a Legend (Phase 3) describing how to read the colours

    def __len__(self) -> int:
        return len(self.fill)


@runtime_checkable
class Styler(Protocol):
    """Anything with a ``resolve_frame(gdf, theme)`` returning a :class:`ResolvedFrame`."""

    column: str | None

    def resolve_frame(self, gdf, theme: str | Theme) -> ResolvedFrame: ...


@dataclass
class ClassStyler:
    """Style each edge by a *class* column via a palette (the original OSM behaviour).

    With ``normalize_links=True`` (default) this is byte-for-byte the v0.1 OSM styling:
    ``primary_link`` normalises to ``primary`` and renders narrower, unknown tags fall back to
    ``fallback``. Set ``normalize_links=False`` (and register your own ``palette``) to style a
    non-OSM vocabulary where values are matched literally.
    """
    column: str = "highway"
    palette: str | Mapping[str, RoadStyle] = "highsat"
    normalize_links: bool = True
    fallback: str = FALLBACK
    tunnel_col: str | None = None
    bridge_col: str | None = None
    config: StyleConfig = field(default_factory=lambda: DEFAULT)
    theme_aware_casing: bool = True

    def _table(self) -> Mapping[str, RoadStyle]:
        if isinstance(self.palette, str):
            try:
                return PALETTES[self.palette]
            except KeyError:
                raise ValueError(
                    f"unknown palette {self.palette!r}; choose from {list(PALETTES)}"
                )
        return self.palette

    def resolve_frame(self, gdf, theme: str | Theme = "dark") -> ResolvedFrame:
        get_theme(theme)  # validate the theme name early (raises a clear error)
        table = self._table()
        fallback_style = table.get(self.fallback) or next(iter(table.values()))

        values = gdf[self.column].tolist()
        tcol = (gdf[self.tunnel_col].tolist()
                if self.tunnel_col and self.tunnel_col in gdf.columns else None)
        bcol = (gdf[self.bridge_col].tolist()
                if self.bridge_col and self.bridge_col in gdf.columns else None)

        n = len(values)
        fill: list[str] = []
        width: list[float] = []
        casing_light: list[str | None] = []
        casing_dark: list[str | None] = []
        casing_width: list[float] = []
        dash: list[str | None] = []
        opacity: list[float] = []
        casing_opacity: list[float] = []
        klass: list[str | None] = []

        for i in range(n):
            value = values[i]
            if self.normalize_links:
                base, is_link = normalize_highway(value)
            else:
                base = ("" if value is None else str(value)).strip().lower()
                is_link = False
            rs = table.get(base, fallback_style)
            tunnel = _truthy(tcol[i]) if tcol is not None else False
            bridge = _truthy(bcol[i]) if bcol is not None else False
            p = _apply(rs, is_link, tunnel, bridge, self.config)

            fill.append(p.fill)
            width.append(p.width)
            casing_light.append(p.casing_light)
            casing_dark.append(p.casing_dark)
            casing_width.append(p.casing_width)
            dash.append(_dash_str(p.dash))
            opacity.append(p.opacity)
            casing_opacity.append(p.casing_opacity)
            klass.append(base)

        return ResolvedFrame(
            fill, width, casing_light, casing_dark, casing_width, dash,
            opacity, casing_opacity, klass, theme_aware_casing=self.theme_aware_casing,
        )
