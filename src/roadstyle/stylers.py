"""Stylers: the abstraction that maps a whole GeoDataFrame to per-edge styles.

A :class:`Styler` answers one question — *"for every edge in this table, what fill colour,
width, casing, opacity and dash does it get?"* — and returns a :class:`ResolvedFrame` of
parallel arrays. The renderers (folium / lonboard / JSON) consume that frame and never decide
colours themselves, so all three backends and all styling modes share one code path.

``ClassStyler`` reproduces the original OSM behaviour (and supports custom vocabularies);
``CategoricalStyler`` and ``NumericStyler`` (added in Phase 2) style by an arbitrary column.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

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
    missing: list[bool] | None = None  # True where a data styler had no value for the edge (NaN /
    #                                    unmapped) — lets colour options fall back to the base fill

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
            except KeyError as err:
                raise ValueError(
                    f"unknown palette {self.palette!r}; choose from {list(PALETTES)}"
                ) from err
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

        cmap = {_keystr(k): v for k, v in self.colors.items()}   # normalise keys to match _keystr(v)
        fill = [cmap.get(_keystr(v), self.fallback_color) for v in values]
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
        # flag unmapped / missing values (got fallback_color) so colour options can fall back
        cmap_keys = {_keystr(k) for k in self.colors}
        rf.missing = [_keystr(v) not in cmap_keys for v in values]
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
        rf.missing = [v is None for v in nums]   # NaN / non-numeric — colour options fall back
        return rf


def _color_or(v, fallback: str) -> str:
    """A per-edge literal colour: the value if it's a non-empty colour string (hex or CSS name),
    else ``fallback`` — so missing edges (NaN/None/blank) and non-string values fall back to gray."""
    return v.strip() if isinstance(v, str) and v.strip() else fallback


@dataclass
class ColorTableStyler:
    """Colour each edge by a **per-edge colour** held in ``color_column`` (literal hex / CSS name),
    while keeping the class-based **widths + casing** so roads still read as roads. Edges with no
    (or blank) colour get ``fallback_color`` (gray). This is the styler behind ``color_table=`` and
    ``colors="self"`` — use it to paint a network by your own per-edge data (clusters, paths,
    metrics) rather than by road class. No legend (the colours are arbitrary per edge).
    """
    color_column: str
    highway_col: str = "highway"
    palette: str | Mapping[str, RoadStyle] = "highsat"
    fallback_color: str = "#bbbbbb"
    column: str | None = None        # the class column (Styler protocol / filtering)

    def __post_init__(self):
        self.column = self.highway_col

    def resolve_frame(self, gdf, theme: str | Theme = "dark") -> ResolvedFrame:
        n = len(gdf)
        if self.highway_col in gdf.columns:
            # borrow per-class widths + (theme-aware) casing, then override the fill
            rf = ClassStyler(column=self.highway_col, palette=self.palette).resolve_frame(gdf, theme)
        else:
            rf = ResolvedFrame([self.fallback_color] * n, [2.0] * n, ["#000000"] * n,
                               ["#000000"] * n, [3.0] * n, [None] * n, [0.9] * n, [0.75] * n,
                               [None] * n, theme_aware_casing=False)
        colors = gdf[self.color_column].tolist() if self.color_column in gdf.columns else [None] * n
        rf.fill = [_color_or(c, self.fallback_color) for c in colors]
        rf.legend = None             # arbitrary per-edge colours -> no categorical legend
        rf.missing = [not (isinstance(c, str) and c.strip()) for c in colors]
        return rf


def bake_props(gj: dict, rf: ResolvedFrame, dark: bool) -> dict:
    """Bake the per-edge ``__rs_*`` style props onto a GeoJSON FeatureCollection, in place.

    The single source of truth for the stable per-feature props every renderer reads — the browser
    ``roadstyle.js`` and the folium ``InteractiveRoads`` layer both consume these, so the two can
    never drift. Both casing variants are baked so a light↔dark base-map switch re-picks casing
    client-side; ``__rs_class`` carries the per-edge category used for filtering and legends.
    """
    feats = gj.get("features", [])
    for i, feat in enumerate(feats):
        p = feat.setdefault("properties", {})
        p["__rs_fill"] = rf.fill[i]
        p["__rs_w"] = rf.width[i]
        p["__rs_op"] = rf.opacity[i]
        p["__rs_dash"] = rf.dash[i]
        p["__rs_casing"] = rf.casing_dark[i] if dark else rf.casing_light[i]
        p["__rs_casing_light"] = rf.casing_light[i]
        p["__rs_casing_dark"] = rf.casing_dark[i]
        p["__rs_cw"] = rf.casing_width[i]
        p["__rs_cop"] = rf.casing_opacity[i]
        p["__rs_class"] = rf.klass[i]
    return gj


def bake_fill_variant(gj: dict, rf: ResolvedFrame, prop: str) -> dict:
    """Bake **only** the per-edge fill colour of ``rf`` onto an already-baked FeatureCollection,
    under the property name ``prop`` (e.g. ``"__rs_fill__1"``), in place.

    Used for client-side recolouring: the same geometry carries several pre-resolved fill sets, one
    per "colour by" option, and the browser (``roadstyle.js`` ``setColorField``) swaps which
    ``prop`` the fill style reads — so the map recolours with no server round-trip. Width, casing
    and class stay as baked by :func:`bake_props` from the active option (only the colour changes).
    """
    feats = gj.get("features", [])
    for i, feat in enumerate(feats):
        feat.setdefault("properties", {})[prop] = rf.fill[i]
    return gj


def bake_color_options(gj: dict, frames, dark: bool):
    """Bake a set of "colour by" options onto a GeoJSON FeatureCollection, in place.

    ``frames`` is an ordered list of ``(name, ResolvedFrame)``. Option 0 is the **active/base**: its
    full per-edge style (width/casing/class + ``__rs_fill``) is baked via :func:`bake_props`. Every
    other option bakes *only* its fill, under ``__rs_fill__<i>`` — and where that option has **no
    colour for an edge** (missing/NaN/unmapped data, flagged by :attr:`ResolvedFrame.missing`), the
    edge falls back to the **base option's fill**, so blank edges keep the neutral base look (e.g.
    the ``mono`` palette colour for that road class) instead of a flat grey.

    Returns ``(gj, options_meta)`` where each meta entry is ``{name, prop, legend}`` — the contract
    the browser reads to build the "Colour by" picker and to swap fills client-side.
    """
    base_rf = frames[0][1]
    gj = bake_props(gj, base_rf, dark)
    base_fill = base_rf.fill
    feats = gj.get("features", [])
    meta = []
    for idx, (name, frame) in enumerate(frames):
        prop = "__rs_fill" if idx == 0 else f"__rs_fill__{idx}"
        if idx != 0:
            fills, miss = frame.fill, frame.missing
            for i, feat in enumerate(feats):
                f = base_fill[i] if (miss is not None and miss[i]) else fills[i]
                feat.setdefault("properties", {})[prop] = f
        meta.append({"name": name, "prop": prop, "legend": getattr(frame, "legend", None)})
    return gj, meta


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


def option_styler(highway_col: str, base_palette: str, opts) -> Styler:
    """Build the styler for one ``color_options`` entry (shared by the spec and web backends).

    ``opts`` is the per-option kwargs dict (``color_by`` / ``colors`` / ``cmap`` / ``vmin`` /
    ``vmax`` / ``width_by`` / ``palette`` / ``style``); an empty dict gives the class style on
    ``base_palette`` — use ``palette="mono"`` for a neutral base that lets the data ramps stand out.
    """
    return build_styler(
        style=opts.get("style"),
        palette=opts.get("palette", base_palette),
        highway_col=highway_col,
        color_by=opts.get("color_by"),
        colors=opts.get("colors"),
        cmap=opts.get("cmap"),
        vmin=opts.get("vmin"),
        vmax=opts.get("vmax"),
        width_by=opts.get("width_by"),
    )


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
) -> Styler:
    """Pick the right styler from ``render_edges`` keyword arguments.

    Resolution order (keeps the legacy OSM call byte-identical when no new args are given):
    1. explicit ``style=`` (a Styler) wins;
    2. ``color_by`` + ``colors="self"`` → :class:`ColorTableStyler` (literal per-edge colours);
    3. ``color_by`` + ``colors`` (a map) → :class:`CategoricalStyler`;
    4. ``color_by`` + (``cmap`` or numeric intent) → :class:`NumericStyler`;
    5. otherwise → :class:`ClassStyler` (the original behaviour).
    """
    if style is not None:
        return style
    if color_by is not None:
        if isinstance(colors, str) and colors == "self":
            return ColorTableStyler(color_column=color_by, highway_col=highway_col, palette=palette)
        if colors is not None:
            return CategoricalStyler(column=color_by, colors=colors)
        return NumericStyler(column=color_by, cmap=cmap or "viridis",
                             vmin=vmin, vmax=vmax, width_by=width_by)
    extra = {}
    if config is not None:
        extra["config"] = config
    return ClassStyler(column=highway_col, palette=palette,
                       tunnel_col=tunnel_col, bridge_col=bridge_col, **extra)
