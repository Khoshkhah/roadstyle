"""Resolve an OSM ``highway`` tag (+ tunnel/bridge flags + theme) to a concrete line style."""
from __future__ import annotations

from dataclasses import dataclass

from .palettes import FALLBACK, PALETTES, SELECTION, RoadStyle
from .themes import Theme, get_theme

LINK_SCALE = 0.7      # *_link variants render narrower than their parent class
FILL_OPACITY = 0.9    # softer than fully opaque (matches the web renderer)
CASING_OPACITY = 0.75


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


def resolve(
    highway,
    palette: str = "highsat",
    theme: str | Theme = "dark",
    tunnel: bool = False,
    bridge: bool = False,
) -> ResolvedStyle:
    """Resolve the full line style for one edge."""
    th = get_theme(theme)
    rs = base_style(highway, palette)
    _, is_link = normalize_highway(highway)

    width = rs.width * (LINK_SCALE if is_link else 1.0)
    casing_width = rs.casing_width * (LINK_SCALE if is_link else 1.0)
    casing = rs.casing_light if th.casing == "light" else rs.casing_dark
    dash = rs.dash
    opacity = FILL_OPACITY * rs.opacity
    casing_opacity = CASING_OPACITY

    if tunnel:                       # tunnels: faded + dashed
        opacity *= 0.45
        casing_opacity *= 0.45
        dash = dash or (4, 4)
    if bridge:                       # bridges: solid black casing, a touch wider
        casing = "#000000"
        casing_width = (casing_width or width) + 1.5

    return ResolvedStyle(rs.fill, width, casing, casing_width, dash, opacity, casing_opacity)


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
