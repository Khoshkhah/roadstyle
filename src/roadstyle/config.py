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

# default OSM classes that carry no casing (fill only) — matches the web renderer. Used as the
# in-code fallback when the data file omits the key.
_MINOR_NO_CASING = frozenset(
    {"service", "living_street", "pedestrian", "track", "cycleway", "footway", "path"}
)


@dataclass(frozen=True)
class StyleConfig:
    """Knobs shared by every styler. Defaults == the original calibrated values."""

    fill_opacity: float = 0.9          # softer than fully opaque (matches the web renderer)
    casing_opacity: float = 0.75
    casing_extra: float = 2.0          # casing width = fill width + casing_extra (web renderer)
    link_scale: float = 0.7            # ``*_link`` variants render narrower than their parent
    tunnel_opacity_scale: float = 0.45  # tunnels fade to 45 % and gain a dash
    bridge_casing_extra: float = 1.5   # bridges: solid black casing, a touch wider
    minor_no_casing: frozenset[str] = field(default_factory=lambda: _MINOR_NO_CASING)
    #: class -> zoom below which it is hidden. Consulted only when the caller opts in.
    minzoom: dict = field(default_factory=dict)
    #: street-name label paint (web backend): color, halo_color, halo_width (0/None = no halo)
    labels: dict = field(default_factory=lambda: {"color": "#5b5b5b", "halo_color": None,
                                                 "halo_width": 0})
    #: oneway-arrow chevrons (web backend): color, spacing (px along the line), opacity
    arrows: dict = field(default_factory=lambda: {"color": "#5b5b5b", "spacing": 120,
                                                  "opacity": 0.7})


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
