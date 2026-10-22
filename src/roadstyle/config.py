"""Tunable styling constants, gathered into one place.

Historically these lived as module-level constants in :mod:`roadstyle.style`
(``FILL_OPACITY``, ``CASING_OPACITY``, ``LINK_SCALE``), then as a hardcoded
:class:`StyleConfig`. The values now live in a JSON data file shipped with the package
(``roadstyle/data/defaults.json`` → ``"config"``) and are loaded at import via
:mod:`roadstyle._settings`, which also applies user overrides — so a caller can adjust the
look without editing the library, while the defaults reproduce the original,
web-renderer-calibrated values exactly.

``minor_no_casing`` lists the OSM classes that intentionally render *fill only* (no casing),
matching the website: service / living_street / pedestrian / track / cycleway / footway / path.

``minzoom`` maps a road class to the zoom below which it is not drawn — the standard basemap
behaviour (zoom out far enough and residential streets disappear, motorways stay). It is a
**performance** knob as much as a cartographic one: at city scale most minor roads land on a
sub-pixel of screen, and skipping them removes work you cannot see the result of. Opt-in — pass
``minzoom=True`` to the web renderer to apply this table, or a dict to override parts of it.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields

from . import _settings


@dataclass(frozen=True)
class StyleConfig:
    """Knobs shared by every styler. Defaults == the original calibrated values."""

    fill_opacity: float = field(default_factory=lambda: _settings.theme_value("roads.fill_opacity"))   # softer than fully opaque (matches the web renderer)
    casing_opacity: float = field(default_factory=lambda: _settings.theme_value("casing.opacity"))
    casing_extra: float = field(default_factory=lambda: _settings.theme_value("casing.extra"))   # casing width = fill width + casing_extra (web renderer)
    link_scale: float = field(default_factory=lambda: _settings.theme_value("roads.links.width"))   # ``*_link`` variants render narrower than their parent
    tunnel_opacity_scale: float = field(default_factory=lambda: _settings.theme_value("tunnels.opacity_scale"))   # tunnels fade to 45 % and gain a dash
    bridge_casing_extra: float = field(default_factory=lambda: _settings.theme_value("bridges.casing_extra"))   # bridges: casing a touch wider (the deck "wings")
    bridge_casing_m: float = field(default_factory=lambda: _settings.theme_value("bridges.casing_m"))   # metre widths: a bridge casing is at least this wide each side, whatever casing_m is
    bridge_casing_px: float = field(default_factory=lambda: _settings.theme_value("bridges.casing_px"))   # ... and never thinner than this many pixels each side at any zoom (metres are sub-pixel zoomed out)
    bridge_casing_color: str = field(default_factory=lambda: _settings.theme_value("bridges.casing_color"))   # bridge deck casing colour: slate, as tunnels fade to (2026-10-06; black, then dark grey, too dark)
    bridge_shadow: bool = field(default_factory=lambda: _settings.theme_value("bridges.shadow.show"))   # a soft shadow under a bridge's main part, on what it crosses (2026-10-06)
    bridge_shadow_color: str = field(default_factory=lambda: _settings.theme_value("bridges.shadow.color"))
    bridge_shadow_blur: float = field(default_factory=lambda: _settings.theme_value("bridges.shadow.blur"))   # px (line-blur)
    bridge_shadow_offset: list = field(default_factory=lambda: _settings.theme_value("bridges.shadow.offset"))   # px right, down (line-translate): lit from the top left
    bridge_shadow_trim_m: float = field(default_factory=lambda: _settings.theme_value("bridges.shadow.trim_m"))   # metres of no shadow where a bridge comes down to the road (2026-10-06: the head length cut short bridges too much)
    single_line_classes: list = field(default_factory=lambda: _settings.style()["config"]["single_line_classes"])   # a two-way pair of these is one full-width line, not two lanes
    twin_end_caps: bool = field(default_factory=lambda: _settings.theme_value("roads.twin_end_caps"))   # one road-wide round end under a two-way road's two lanes
    twin_casing: str = field(default_factory=lambda: _settings.theme_value("roads.twin_casing"))   # a two-way road given as two directed edges: "one" casing around both directions (full width, drawn once), or "each" direction its own
    tunnel_casing_dash: list = field(default_factory=lambda: _settings.theme_value("tunnels.casing_dash"))   # the tunnel casing: dash and gap, in line widths (1:1, 2026-10-06)
    tunnel_fill_dash: list = field(default_factory=lambda: _settings.theme_value("tunnels.fill_dash"))   # light dashes on the tunnel fill, e.g. [1.2, 1.2]; none by default (v2's look, 2026-10-06)
    tunnel_fill_dash_color: str = field(default_factory=lambda: _settings.theme_value("tunnels.fill_dash_color"))   # their colour, over any road colour
    tunnel_strength: float = field(default_factory=lambda: _settings.theme_value("tunnels.strength"))   # the tunnel look (docs/design/tunnel_look.md), v2's slider: 0 = normal colours, 100 = the full tunnel colours
    tunnel_toward: str = field(default_factory=lambda: _settings.theme_value("tunnels.toward"))   # the colour a tunnel moves toward: a name in tunnel_towards, or "#rrggbb" (2026-10-08)
    tunnel_towards: dict = field(default_factory=lambda: _settings.theme_value("tunnels.towards"))
    tunnel_palette: str = field(default_factory=lambda: _settings.theme_value("tunnels.palette"))   # the casing of a tunnel, a name in tunnel_palettes (two colours by default, 2026-10-06)
    tunnel_palettes: dict = field(default_factory=lambda: _settings.theme_value("tunnels.palettes"))
    # name -> [dash, gap] (v2's two-colour pattern), or None: slate dashes with empty gaps
    minor_no_casing: frozenset[str] = field(default_factory=lambda: frozenset(_settings.style()["config"]["minor_no_casing"]))
    #: class -> zoom below which it is hidden. Consulted only when the caller opts in.
    minzoom: dict = field(default_factory=lambda: _settings.style()["config"]["minzoom"])
    #: the primary base map layer (a key in basemaps.BASEMAPS); per-call `basemap=` overrides
    basemap: str = "voyager"
    #: street-name label paint (web backend): color, halo_color, halo_width (0/None = no halo); size: [[zoom, px], ...] for every class
    #: (absent: each class's size from its fill width)
    labels: dict = field(default_factory=lambda: _settings.theme_value("labels"))
    #: oneway-arrow chevrons (web backend): color, opacity
    arrows: dict = field(default_factory=lambda: _settings.theme_value("arrows"))
    #: camera (web backend): starting pitch (deg tilt, capped by max_pitch — 70 by default:
    #: up to 60 deg MapLibre loads every tile at one zoom, so a road has one width on the whole screen;
    #: above it the tiles get different zooms and a road's width can step where two zooms meet, and past ~72
    #: the horizon tile cover explodes on large GeoJSON sources and roads stop rendering. `max_pitch=60`
    #: on a render call, or camera.max_pitch, keeps the tilt where the width is exact) and bearing (deg clockwise from N),
    #: plus pitch_3d — the tilt `view_3d=True` and the on-map 2D/3D toggle ease to.
    #: Per-call `pitch=` / `bearing=` override; tilt/rotate stay interactive either way.
    camera: dict = field(default_factory=lambda: {"pitch": 0, "bearing": 0, "pitch_3d": 55,
                                                  "max_pitch": 70})
    #: 3D bridge decks (web backend, view_3d): extruded ribbon height above ground, deck
    #: thickness, and metres per lane for the ribbon width
    #: ribbon width comes from the same class width table as the roads, converted to metres at
    #: match_zoom — decks and flat roads render equally wide at that zoom
    bridge_decks: dict = field(default_factory=lambda: _settings.theme_value("bridges.decks"))
    #: overlay layer defaults (web backend): colour, circle radius, line/outline width, the
    #: per-kind opacities, and the circle stroke. A per-Overlay value always wins.
    overlays: dict = field(default_factory=lambda: _settings.theme_value("overlays"))
    #: annotation slots (web backend): each road chain is divided into equal slot_m-metre pieces;
    #: names take even slots, oneway arrows odd ones — alternating, never stacked. Text/icon zoom
    #: ramps and collision culling handle density automatically; unnamed name-slots stay empty.
    annotations: dict = field(default_factory=lambda: {"slot_m": 100})
    #: vector tiling (web backend, `tiles=True`): tileset zoom range, MVT grid extent, and the
    #: clip buffer in extent units (bleed for strokes crossing tile edges)
    tiles: dict = field(default_factory=lambda: {"minzoom": 6, "maxzoom": 15,
                                                 "extent": 4096, "buffer_px": 80})
    #: default API key / access token for basemaps (e.g. Mapbox, Stadia, MapTiler)
    api_key: str | None = None
    #: provider-specific API keys: {"mapbox": "...", "stadia": "...", ...}
    api_keys: dict = field(default_factory=dict)


def _default_config() -> StyleConfig:
    """Build the default :class:`StyleConfig` from ``data/defaults.json`` (+ user overrides).

    Unknown keys are ignored (so a stray override field can't crash import) and the JSON list
    ``minor_no_casing`` is coerced back to a frozenset. Any field the data omits keeps the
    dataclass default.
    """
    raw = dict(_settings.style()["config"])
    if raw.get("minor_no_casing") is not None:
        raw["minor_no_casing"] = frozenset(raw["minor_no_casing"])
    known = {f.name for f in fields(StyleConfig)}
    return StyleConfig(**{k: v for k, v in raw.items() if k in known})


#: The default configuration (bundled calibrated values + any user override).
DEFAULT = _default_config()
