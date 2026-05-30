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

    def to_dict(self) -> dict:
        """Serialise to a plain JSON-ready dict (``dash`` tuple becomes a list)."""
        return {
            "fill": self.fill,
            "width": self.width,
            "casing_width": self.casing_width,
            "casing_light": self.casing_light,
            "casing_dark": self.casing_dark,
            "dash": list(self.dash) if self.dash else None,
            "opacity": self.opacity,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RoadStyle":
        """Build a RoadStyle from a dict (e.g. parsed JSON). Unknown keys are ignored.

        Only ``fill``/``width``/``casing_width`` are required; the rest fall back to the
        dataclass defaults, so a minimal ``{"fill": "#fff", "width": 2, "casing_width": 4}`` works.
        """
        missing = [k for k in ("fill", "width", "casing_width") if k not in d]
        if missing:
            raise ValueError(f"RoadStyle dict is missing required keys: {missing}")
        dash = d.get("dash")
        return cls(
            fill=d["fill"],
            width=float(d["width"]),
            casing_width=float(d["casing_width"]),
            casing_light=d.get("casing_light"),
            casing_dark=d.get("casing_dark", "#000000"),
            dash=tuple(dash) if dash else None,
            opacity=float(d.get("opacity", 1.0)),
        )


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


def register_palette(name: str, table: dict[str, RoadStyle]) -> None:
    """Register (or replace) a named palette so ``render_edges(palette=name)`` can use it.

    ``table`` maps a class value (e.g. an OSM ``highway`` tag, or your own road class) to a
    :class:`RoadStyle`. This is how non-OSM vocabularies are supported without forking.
    """
    if not isinstance(name, str) or not name:
        raise ValueError("palette name must be a non-empty string")
    if not table:
        raise ValueError("palette table must be a non-empty mapping of class -> RoadStyle")
    for key, value in table.items():
        if not isinstance(value, RoadStyle):
            raise TypeError(
                f"palette entry {key!r} must be a RoadStyle, got {type(value).__name__}"
            )
    PALETTES[name] = dict(table)


def palette_to_dict(palette: str | dict[str, RoadStyle]) -> dict[str, dict]:
    """Return ``{class: roadstyle_dict}`` for a registered palette name or a palette mapping."""
    table = PALETTES[palette] if isinstance(palette, str) else palette
    return {cls: rs.to_dict() for cls, rs in table.items()}


def palette_from_dict(roads: dict[str, dict]) -> dict[str, RoadStyle]:
    """Build a palette mapping ``{class: RoadStyle}`` from ``{class: roadstyle_dict}``."""
    return {cls: RoadStyle.from_dict(d) for cls, d in roads.items()}


def save_palette(palette: str | dict[str, RoadStyle], path, *, name: str | None = None) -> None:
    """Write a palette to a JSON file as ``{"name": ..., "roads": {class: {...}}}``.

    ``palette`` may be a registered name (e.g. ``"highsat"``) or a ``{class: RoadStyle}`` mapping.
    The JSON is human-editable and can be reloaded with :func:`load_palette` — or read directly by
    a web frontend, so Python and the browser share one source of truth for colours.
    """
    import json

    if name is None:
        name = palette if isinstance(palette, str) else "palette"
    payload = {"name": name, "roads": palette_to_dict(palette)}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def load_palette(path, *, register: bool = True) -> dict[str, RoadStyle]:
    """Load a palette from a JSON file written by :func:`save_palette`.

    Accepts either the full ``{"name", "roads"}`` form or a bare ``{class: {...}}`` mapping.
    If ``register`` is True and a name is present, the palette is added to :data:`PALETTES` so
    ``render_edges(palette=name)`` can use it.
    """
    import json

    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if "roads" in data:                 # full {name, roads} form
        name = data.get("name")
        roads = data["roads"]
    else:                               # bare {class: {...}} mapping
        name = None
        roads = data
    table = palette_from_dict(roads)
    if register and name:
        register_palette(name, table)
    return table


# Neon-violet selected-edge profile (selected_edge_color.md).
SELECTION = {
    "core": "#EE00FF",
    "casing_light": "#220033",
    "casing_dark": "#000000",
    "glow": "#D000FF",
    "glow_opacity": 0.35,
}
