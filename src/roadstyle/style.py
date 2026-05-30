"""Resolve an OSM ``highway`` tag (+ tunnel/bridge flags + theme) to a concrete line style."""
from __future__ import annotations

from dataclasses import dataclass

from .config import DEFAULT, StyleConfig
from .palettes import FALLBACK, PALETTES, SELECTION, RoadStyle
from .themes import Theme, get_theme

# Kept for backward-compatible imports (e.g. interactive.py) — mirror StyleConfig defaults.
LINK_SCALE = DEFAULT.link_scale       # *_link variants render narrower than their parent class
FILL_OPACITY = DEFAULT.fill_opacity   # softer than fully opaque (matches the web renderer)
CASING_OPACITY = DEFAULT.casing_opacity


@dataclass
class ResolvedStyle:
    fill: str
    width: float
    casing: str | None
    casing_width: float
    dash: tuple[int, int] | None
    opacity: float              # fill opacity
    casing_opacity: float = CASING_OPACITY

    def dash_str(self) -> str | None:
        return ",".join(map(str, self.dash)) if self.dash else None


def normalize_highway(highway) -> tuple[str, bool]:
    """Return (base_class, is_link). Unknown tags fall back to ``unclassified``."""
    h = (str(highway) if highway is not None else "").strip().lower()
    is_link = h.endswith("_link")
    if is_link:
        h = h[: -len("_link")]
    return h, is_link


def base_style(highway, palette: str = "highsat") -> RoadStyle:
    table = PALETTES.get(palette)
    if table is None:
        raise ValueError(f"unknown palette {palette!r}; choose from {list(PALETTES)}")
    base, _ = normalize_highway(highway)
    return table.get(base, table[FALLBACK])


@dataclass
class ResolvedPair:
    """Like :class:`ResolvedStyle`, but keeps *both* casing colours (pre theme-selection).

    This is the shared, theme-agnostic result: a renderer that swaps casing on base-map change
    needs both ``casing_light`` and ``casing_dark`` for each edge, so the per-edge maths is done
    once here and the theme just *picks* one of the two later.
    """
    fill: str
    width: float
    casing_light: str | None
    casing_dark: str | None
    casing_width: float
    dash: tuple[int, int] | None
    opacity: float
    casing_opacity: float


def _apply(
    rs: RoadStyle,
    is_link: bool,
    tunnel: bool = False,
    bridge: bool = False,
    config: StyleConfig = DEFAULT,
) -> ResolvedPair:
    """Apply link/tunnel/bridge adjustments to a base :class:`RoadStyle` → :class:`ResolvedPair`.

    The single source of truth for the per-edge styling maths. ``resolve()`` and the
    ``ClassStyler`` both go through here, so OSM styling stays identical everywhere.
    """
    scale = config.link_scale if is_link else 1.0
    width = rs.width * scale
    casing_width = rs.casing_width * scale
    casing_light, casing_dark = rs.casing_light, rs.casing_dark
    dash = rs.dash
    opacity = config.fill_opacity * rs.opacity
    casing_opacity = config.casing_opacity

    if tunnel:                       # tunnels: faded + dashed
        opacity *= config.tunnel_opacity_scale
        casing_opacity *= config.tunnel_opacity_scale
        dash = dash or (4, 4)
    if bridge:                       # bridges: solid black casing, a touch wider
        casing_light = casing_dark = "#000000"
        casing_width = (casing_width or width) + config.bridge_casing_extra

    return ResolvedPair(rs.fill, width, casing_light, casing_dark, casing_width,
                        dash, opacity, casing_opacity)


def resolve(
    highway,
    palette: str = "highsat",
    theme: str | Theme = "dark",
    tunnel: bool = False,
    bridge: bool = False,
) -> ResolvedStyle:
    """Resolve the full line style for one edge (casing chosen for the given theme)."""
    th = get_theme(theme)
    rs = base_style(highway, palette)
    _, is_link = normalize_highway(highway)
    p = _apply(rs, is_link, tunnel, bridge)
    casing = p.casing_light if th.casing == "light" else p.casing_dark
    return ResolvedStyle(p.fill, p.width, casing, p.casing_width, p.dash,
                         p.opacity, p.casing_opacity)


def selection_style(theme: str | Theme = "dark", base_width: float = 4.0) -> dict:
    """Neon-violet selected-edge style (3 stacked layers: glow, casing, core)."""
    th = get_theme(theme)
    casing = SELECTION["casing_light"] if th.casing == "light" else SELECTION["casing_dark"]
    return {
        "glow":   {"color": SELECTION["glow"], "width": base_width * 3.0,
                   "opacity": SELECTION["glow_opacity"]},
        "casing": {"color": casing, "width": base_width * 1.8, "opacity": 1.0},
        "core":   {"color": SELECTION["core"], "width": base_width * 1.5, "opacity": 1.0},
    }
