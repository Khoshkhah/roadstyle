"""Road/edge colour palettes, keyed by OSM ``highway`` tag.

The palette *tables* are no longer hardcoded here — they live as JSON data files shipped inside
the package (``roadstyle/data/palettes/*.json``) and are loaded at import via
:mod:`roadstyle._settings`, which also layers user overrides on top (see that module for the
override-file locations and format). This module owns the palette *machinery*: the
:class:`RoadStyle` value type, JSON (de)serialisation, registration, and the resolved
``PALETTES`` mapping built from the data files.

Built-in palettes:

- ``highsat`` — the custom **high-saturation** palette (cyan motorway, pink trunk, …) with a
  light-grey casing. Best legibility over any base map.
- ``carto``   — the classic **OSM Carto** palette (muted warm tones) with its own per-class
  coloured casing.

Each entry is a :class:`RoadStyle` (fill colour, line widths, one casing colour, optional dash).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import _settings


@dataclass(frozen=True)
class RoadStyle:
    fill: str
    width: float
    casing_width: float
    casing: str | None = "#bcbcbc"       # casing colour (None = no casing); default light grey
    dash: tuple[int, int] | None = None  # dash pattern (on, off) in px
    opacity: float = 1.0

    def to_dict(self) -> dict:
        """Serialise to a plain JSON-ready dict (``dash`` tuple becomes a list)."""
        return {
            "fill": self.fill,
            "width": self.width,
            "casing_width": self.casing_width,
            "casing": self.casing,
            "dash": list(self.dash) if self.dash else None,
            "opacity": self.opacity,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RoadStyle:
        """Build a RoadStyle from a dict (e.g. parsed JSON). Unknown keys are ignored.

        Only ``fill``/``width``/``casing_width`` are required; the rest fall back to the
        dataclass defaults, so a minimal ``{"fill": "#fff", "width": 2, "casing_width": 4}`` works.
        """
        missing = [k for k in ("fill", "width", "casing_width") if k not in d]
        if missing:
            raise ValueError(f"RoadStyle dict is missing required keys: {missing}")
        dash = d.get("dash")
        # legacy palette files carried casing_light/casing_dark; the dark variant (the one every
        # built-in theme actually used) maps onto the single ``casing``
        casing = d.get("casing", d.get("casing_dark", "#bcbcbc"))
        return cls(
            fill=d["fill"],
            width=float(d["width"]),
            casing_width=float(d["casing_width"]),
            casing=casing,
            dash=tuple(dash) if dash else None,
            opacity=float(d.get("opacity", 1.0)),
        )


# Importance order (low -> high). Used for the casing/fill "geometry sandwich" z-order.
ORDER = [
    "path", "footway", "cycleway", "track", "service", "living_street",
    "residential", "unclassified", "tertiary", "secondary", "primary",
    "trunk", "motorway",
]

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


# --- built-in palettes & selection style, loaded from the bundled JSON data files (+ overrides) ---
# Source of truth: roadstyle/data/palettes/*.json and roadstyle/data/style.json. To retint a class,
# edit the data file or drop a user override (see roadstyle._settings) — no code change needed.
PALETTES: dict[str, dict[str, RoadStyle]] = {
    name: palette_from_dict(roads) for name, roads in _settings.palettes().items()
}
HIGHSAT: dict[str, RoadStyle] = PALETTES["highsat"]
CARTO: dict[str, RoadStyle] = PALETTES["carto"]


def _reload() -> None:
    """Rebuild PALETTES / SELECTION **in place** from :mod:`roadstyle._settings` (called by
    :func:`roadstyle.use_settings`). In place, so aliases already imported elsewhere (HIGHSAT,
    CARTO, a ``from roadstyle import PALETTES``) see the new values. Palettes registered at
    runtime via :func:`register_palette` are left alone."""
    fresh = {name: palette_from_dict(roads) for name, roads in _settings.palettes().items()}
    for name, table in fresh.items():
        dst = PALETTES.setdefault(name, {})
        dst.clear()
        dst.update(table)
    SELECTION.clear()
    SELECTION.update(_settings.style()["selection"])

# Neon-violet selected-edge profile (data/style.json → "selection").
SELECTION: dict = dict(_settings.style()["selection"])
