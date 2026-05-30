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


def _keystr(v) -> str:
    """Normalise a categorical value to a lookup key (str, stripped, lower-cased)."""
    return ("" if v is None else str(v)).strip().lower()


def _as_float(v):
    """Best-effort float conversion; return None for missing/NaN/non-numeric."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _clamp01(t: float) -> float:
    return 0.0 if t < 0 else 1.0 if t > 1 else t


@dataclass
class CategoricalStyler:
    """Colour each edge by a discrete value in any column, via a ``{value: colour}`` map.

    Serves data like traffic congestion levels (``low``/``moderate``/``heavy``/``severe``).
    Unmapped values (and missing data) get ``fallback_color``. Casing is off by default (these
    overlays usually sit on top of a base map without road borders), but a constant casing colour
    can be set. ``width`` is a constant, or the name of a numeric column to read per edge.
    """
    column: str = ""
    colors: Mapping[str, str] = field(default_factory=dict)
    fallback_color: str = "#cccccc"
    width: float | str = 2.0           # constant px, or a column name to read width from
    casing: str | None = None          # constant casing colour, or None for no casing
    casing_width: float = 0.0
    opacity: float = 0.9
    casing_opacity: float = 0.75
    dash: tuple[int, int] | None = None
    theme_aware_casing: bool = False

    def resolve_frame(self, gdf, theme: str | Theme = "dark") -> ResolvedFrame:
        get_theme(theme)
        values = gdf[self.column].tolist()
        widths_col = (gdf[self.width].tolist()
                      if isinstance(self.width, str) and self.width in gdf.columns else None)
        dash = _dash_str(self.dash)
        n = len(values)

        fill = [self.colors.get(_keystr(v), self.fallback_color) for v in values]
        if widths_col is not None:
            width = [float(w) if w is not None and w == w else 0.0 for w in widths_col]
        else:
            const_w = float(self.width) if not isinstance(self.width, str) else 2.0
            width = [const_w] * n
        casing_light = [self.casing] * n
        casing_dark = [self.casing] * n
        casing_width = [self.casing_width if self.casing else 0.0] * n
        klass = [_keystr(v) for v in values]

        rf = ResolvedFrame(
            fill, width, casing_light, casing_dark, casing_width,
            [dash] * n, [self.opacity] * n, [self.casing_opacity] * n, klass,
            theme_aware_casing=self.theme_aware_casing,
        )
        # legend = the value->colour entries actually present in the data, in mapping order
        present = {k for k in klass}
        entries = [(label, hexc) for label, hexc in self.colors.items()
                   if _keystr(label) in present]
        rf.legend = {"kind": "categorical", "title": self.column, "entries": entries}
        return rf


@dataclass
class NumericStyler:
    """Colour each edge by a *numeric* column via a continuous colour ramp.

    Serves data like traffic volume (``aadt``) or speed (``maxspeed_kmh``). ``vmin``/``vmax``
    default to the data's min/max. Optionally vary line width with the same (or another) numeric
    column via ``width_by=(min_px, max_px)``. Backed by :class:`roadstyle.colors.ColorRamp`.
    """
    column: str = ""
    cmap: object = "viridis"           # branca scheme name, matplotlib name, or list of hex stops
    vmin: float | None = None
    vmax: float | None = None
    width: float = 2.0                 # constant width unless width_by is given
    width_by: tuple[float, float] | None = None   # (min_px, max_px) ramp over [vmin, vmax]
    width_column: str | None = None    # column driving the width ramp (defaults to `column`)
    opacity: float = 0.9
    casing: str | None = None
    casing_width: float = 0.0
    casing_opacity: float = 0.75
    nan_color: str = "#cccccc"
    theme_aware_casing: bool = False

    def resolve_frame(self, gdf, theme: str | Theme = "dark") -> ResolvedFrame:
        from .colors import ColorRamp

        get_theme(theme)
        raw = gdf[self.column].tolist()
        nums = [_as_float(v) for v in raw]
        present = [v for v in nums if v is not None]
        vmin = self.vmin if self.vmin is not None else (min(present) if present else 0.0)
        vmax = self.vmax if self.vmax is not None else (max(present) if present else 1.0)

        ramp = ColorRamp(self.cmap, vmin=vmin, vmax=vmax)
        fill = [ramp(v, nan_color=self.nan_color) for v in nums]
        n = len(nums)

        if self.width_by is not None:
            wcol = self.width_column or self.column
            wraw = [_as_float(v) for v in gdf[wcol].tolist()] if wcol in gdf.columns else nums
            wpresent = [v for v in wraw if v is not None]
            wmin, wmax = (min(wpresent), max(wpresent)) if wpresent else (0.0, 1.0)
            lo, hi = self.width_by
            span = (wmax - wmin) or 1.0
            width = [lo + (hi - lo) * _clamp01((v - wmin) / span) if v is not None else lo
                     for v in wraw]
        else:
            width = [float(self.width)] * n

        casing_light = [self.casing] * n
        casing_dark = [self.casing] * n
        casing_width = [self.casing_width if self.casing else 0.0] * n
        klass = [None] * n   # continuous — no discrete class

        rf = ResolvedFrame(
            fill, width, casing_light, casing_dark, casing_width,
            [None] * n, [self.opacity] * n, [self.casing_opacity] * n, klass,
            theme_aware_casing=self.theme_aware_casing,
        )
        # stash ramp metadata so a legend (Phase 3) can draw the gradient
        rf.legend = {"kind": "continuous", "title": self.column,
                     "vmin": vmin, "vmax": vmax, "ramp": ramp.stops(9)}
        return rf


# ── convenience constructors (so users build a styler without importing the classes) ──────────

def color_by_class(column: str = "highway", palette="highsat", **kw) -> ClassStyler:
    """Style by a road-class column through a palette (OSM by default)."""
    return ClassStyler(column=column, palette=palette, **kw)


def color_by(column: str, colors: Mapping[str, str], **kw) -> CategoricalStyler:
    """Style by a discrete column using an explicit ``{value: colour}`` map."""
    return CategoricalStyler(column=column, colors=colors, **kw)


def color_by_value(column: str, cmap="viridis", **kw) -> NumericStyler:
    """Style by a numeric column using a continuous colour ramp."""
    return NumericStyler(column=column, cmap=cmap, **kw)


def build_styler(
    *,
    style=None,
    palette="highsat",
    highway_col: str = "highway",
    color_by: str | None = None,        # noqa: F811 - shadow is intentional (kwarg name)
    colors: Mapping[str, str] | None = None,
    cmap=None,
    vmin: float | None = None,
    vmax: float | None = None,
    width_by: tuple[float, float] | None = None,
    tunnel_col: str | None = None,
    bridge_col: str | None = None,
    config=None,
) -> "Styler":
    """Pick the right styler from ``render_edges`` keyword arguments.

    Resolution order (keeps the legacy OSM call byte-identical when no new args are given):
    1. explicit ``style=`` (a Styler) wins;
    2. ``color_by`` + ``colors`` → :class:`CategoricalStyler`;
    3. ``color_by`` + (``cmap`` or numeric intent) → :class:`NumericStyler`;
    4. otherwise → :class:`ClassStyler` (the original behaviour).
    """
    if style is not None:
        return style
    if color_by is not None:
        if colors is not None:
            return CategoricalStyler(column=color_by, colors=colors)
        return NumericStyler(column=color_by, cmap=cmap or "viridis",
                             vmin=vmin, vmax=vmax, width_by=width_by)
    extra = {}
    if config is not None:
        extra["config"] = config
    return ClassStyler(column=highway_col, palette=palette,
                       tunnel_col=tunnel_col, bridge_col=bridge_col, **extra)
