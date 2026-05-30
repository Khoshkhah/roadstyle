"""Road/edge colour palettes, keyed by OSM ``highway`` tag.

Two palettes (transcribed from the cartographic spec docs):

- ``highsat`` — the custom **high-saturation** theme (cyan motorway, pink trunk, …) with
  theme-dependent casing (light vs dark/satellite). Best legibility over any base map.
- ``carto``   — the classic **OSM Carto** palette (muted warm tones), with its own coloured
  casing constant across themes.

Each entry is a :class:`RoadStyle` (fill colour, line widths, casing colour per theme,
optional dash). ``casing_light``/``casing_dark`` let the renderer swap the casing to suit a
light vs dark/satellite base map (the high-saturation theme uses pure black on dark/sat).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoadStyle:
    fill: str
    width: float
    casing_width: float
    casing_light: str | None = None      # casing colour on a light base map (None = no casing)
    casing_dark: str = "#000000"         # casing colour on a dark/satellite base map
    dash: tuple[int, int] | None = None  # dash pattern (on, off) in px
    opacity: float = 1.0


# Importance order (low -> high). Used for the casing/fill "geometry sandwich" z-order.
ORDER = [
    "path", "footway", "cycleway", "track", "service", "living_street",
    "residential", "unclassified", "tertiary", "secondary", "primary",
    "trunk", "motorway",
]

# --- high-saturation custom theme — matched to the osm-traffic-enrichment web renderer ---
# Casing width = fill + 2; minor roads carry NO casing (casing colours = None).
HIGHSAT: dict[str, RoadStyle] = {
    "motorway":      RoadStyle("#00E5FF", 6.0, 8.0, "#007785", "#000000"),
    "trunk":         RoadStyle("#FF007F", 5.5, 7.5, "#9E004F", "#000000"),
    "primary":       RoadStyle("#FF9100", 4.5, 6.5, "#A86000", "#000000"),
    "secondary":     RoadStyle("#FFEA00", 3.5, 5.5, "#A39600", "#000000"),
    "tertiary":      RoadStyle("#00E676", 2.5, 4.5, "#007A3E", "#000000"),
    "unclassified":  RoadStyle("#FFFFFF", 2.0, 4.0, "#999999", "#000000"),
    "residential":   RoadStyle("#FFFFFF", 2.0, 4.0, "#999999", "#000000"),
    # minor classes: fill only, no casing (matches the website)
    "living_street": RoadStyle("#DDDDDD", 2.0, 0.0, None, None),
    "pedestrian":    RoadStyle("#DDDDDD", 1.5, 0.0, None, None),
    "service":       RoadStyle("#A6A6A6", 1.0, 0.0, None, None),
    "track":         RoadStyle("#9E7B54", 1.5, 0.0, None, None),
    "cycleway":      RoadStyle("#2980B9", 1.5, 0.0, None, None, dash=(6, 4)),
    "footway":       RoadStyle("#C0392B", 1.5, 0.0, None, None, dash=(4, 4)),
    "path":          RoadStyle("#C0392B", 1.5, 0.0, None, None, dash=(4, 4)),
}

# --- classic OSM Carto theme (osm_highway_styles.md); coloured casing, theme-independent ---
def _carto(fill, casing, w, cw, dash=None):
    return RoadStyle(fill, w, cw, casing, casing, dash)

CARTO: dict[str, RoadStyle] = {
    "motorway":      _carto("#e892a2", "#dc2a48", 6.0, 8.0),
    "trunk":         _carto("#f9b29c", "#c84e2f", 5.5, 7.5),
    "primary":       _carto("#fcd6a4", "#a06b00", 4.5, 6.5),
    "secondary":     _carto("#f7fabf", "#707d00", 3.5, 5.5),
    "tertiary":      _carto("#ffffff", "#bcbcbc", 2.5, 4.0),
    "unclassified":  _carto("#ffffff", "#bcbcbc", 2.0, 3.5),
    "residential":   _carto("#ffffff", "#bcbcbc", 2.0, 3.5),
    "living_street": _carto("#ededed", "#cccccc", 1.8, 3.0),
    "service":       _carto("#ffffff", "#bcbcbc", 1.2, 2.2),
    "track":         _carto("#9e7b54", "#9e7b54", 1.5, 1.5, dash=(4, 4)),
    "cycleway":      _carto("#5c7cb6", "#5c7cb6", 1.2, 1.2, dash=(3, 3)),
    "footway":       _carto("#9e5b5b", "#9e5b5b", 1.2, 1.2, dash=(4, 4)),
    "path":          _carto("#9e5b5b", "#9e5b5b", 1.2, 1.2, dash=(2, 5)),
}

PALETTES: dict[str, dict[str, RoadStyle]] = {"highsat": HIGHSAT, "carto": CARTO}
FALLBACK = "unclassified"   # used for unknown highway tags

# Neon-violet selected-edge profile (selected_edge_color.md).
SELECTION = {
    "core": "#EE00FF",
    "casing_light": "#220033",
    "casing_dark": "#000000",
    "glow": "#D000FF",
    "glow_opacity": 0.35,
}
