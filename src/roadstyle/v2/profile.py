"""Style profiles for roadstyle v2: the widths, casings and colours a visualization uses.

A profile is a JSON file (or a dict) that restates only what it changes; everything else comes
from the bundled ``default`` profile. Pick one per visualization: a bundled name (``default``,
``compact``), a path to your own file, or a dict. Keys:

    name                   free text
    lane_width_m           metres per lane when a way has ``lanes`` but no ``width`` tag
    lane_width_by_class    per-highway override of ``lane_width_m``, e.g. {"service": 3.0}
    width_sources          order tried to size a road: "width" (OSM tag), "lanes", "class"
    class_width_m          road width by highway class when no source above applies
    default_width_m        width of a class missing from ``class_width_m``
    casing_m               {"default": [left, right], "<highway>": [left, right]}
    colors                 fill colour by highway class
    default_color          fill colour of a class missing from ``colors``
    roundabout_priority    junction priority given to roundabout ways
    split_m                length of the casing head at each road end
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

PROFILE_DIR = Path(__file__).with_name("profiles")
_SOURCES = {"width", "lanes", "class"}


def _merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _read(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def bundled_profiles() -> list[str]:
    return sorted(path.stem for path in PROFILE_DIR.glob("*.json"))


class StyleProfile:
    """Resolved style values; build one with :func:`load_profile`."""

    def __init__(self, data: dict[str, Any]) -> None:
        unknown = set(data["width_sources"]) - _SOURCES
        if unknown:
            raise ValueError(f"width_sources has unknown entries {sorted(unknown)}; use {sorted(_SOURCES)}")
        self.data = data
        self.name: str = data.get("name", "")

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def lane_width(self, highway: str) -> float:
        return float(self.data["lane_width_by_class"].get(highway, self.data["lane_width_m"]))

    def class_width(self, highway: str) -> float:
        return float(self.data["class_width_m"].get(highway, self.data["default_width_m"]))

    def casing(self, highway: str) -> tuple[float, float]:
        table = self.data["casing_m"]
        left, right = table.get(highway, table["default"])
        return float(left), float(right)

    def color(self, highway: str) -> str:
        return str(self.data["colors"].get(highway, self.data["default_color"]))


def load_profile(profile: str | Path | dict[str, Any] | StyleProfile | None = None) -> StyleProfile:
    """Resolve ``profile`` (None, bundled name, JSON path or dict) over the bundled default."""
    if isinstance(profile, StyleProfile):
        return profile
    base = _read(PROFILE_DIR / "default.json")
    if profile is None:
        return StyleProfile(base)
    if isinstance(profile, dict):
        return StyleProfile(_merge(base, profile))
    path = Path(profile)
    if not path.suffix and not path.exists():
        path = PROFILE_DIR / f"{profile}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"style profile {str(profile)!r} is neither a file nor one of {bundled_profiles()}"
        )
    return StyleProfile(_merge(base, _read(path)))
