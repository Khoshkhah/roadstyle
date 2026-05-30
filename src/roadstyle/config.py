"""Tunable styling constants, gathered into one place.

Historically these lived as module-level constants in :mod:`roadstyle.style`
(``FILL_OPACITY``, ``CASING_OPACITY``, ``LINK_SCALE``). Bundling them into a single
:class:`StyleConfig` lets a caller adjust the look without editing the library, while the
defaults reproduce the original, web-renderer-calibrated values exactly.

``minor_no_casing`` lists the OSM classes that intentionally render *fill only* (no casing),
matching the website: service / living_street / pedestrian / track / cycleway / footway / path.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# default OSM classes that carry no casing (fill only) — matches the web renderer
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


#: The default configuration (the calibrated values used everywhere unless overridden).
DEFAULT = StyleConfig()
