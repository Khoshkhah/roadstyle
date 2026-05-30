"""Base-map (tile) providers + thumbnail metadata for the switcher control."""
from __future__ import annotations

from dataclasses import dataclass, field

_CARTO_ATTR = "© OpenStreetMap contributors © CARTO"
_OSM_ATTR = "© OpenStreetMap contributors"
_ESRI_ATTR = "Tiles © Esri"


@dataclass(frozen=True)
class Basemap:
    key: str
    label: str
    url: str                       # leaflet tile URL template ({s}{z}{x}{y}{r})
    attr: str
    is_dark: bool = False          # dark canvas?
    satellite: bool = False        # apply the saturate/brightness tile filter
    lonboard: str | None = None    # CartoBasemap name (lonboard backend)
    bg: str = "#444"               # thumbnail background (CSS)
    preview: tuple[str, str, str] = ("#888", "#bbb", "#888")  # 3 preview road colours
    subdomains: str = "abc"


BASEMAPS: dict[str, Basemap] = {
    "voyager": Basemap(
        "voyager", "Voyager",
        "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", _CARTO_ATTR,
        lonboard="Voyager", bg="linear-gradient(180deg,#e8eef0,#d8e0e5)",
        preview=("#ff9933", "#e8ecef", "#9ec5fe")),
    "positron": Basemap(
        "positron", "Positron",
        "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", _CARTO_ATTR,
        lonboard="Positron", bg="linear-gradient(180deg,#f3f5f7,#e3e8ed)",
        preview=("#888", "#bbb", "#888")),
    "dark_matter": Basemap(
        "dark_matter", "Dark Matter",
        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", _CARTO_ATTR,
        is_dark=True, lonboard="DarkMatter", bg="radial-gradient(circle,#18222e,#0b1014)",
        preview=("#22d3a3", "#9ec5fe", "#5b6573")),
    "osm": Basemap(
        "osm", "OpenStreetMap",
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", _OSM_ATTR,
        bg="linear-gradient(180deg,#f2efe9,#e8e4db)", preview=("#e07020", "#dcdcdc", "#888")),
    "esri_gray": Basemap(
        "esri_gray", "Light Gray",
        "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        _ESRI_ATTR, bg="linear-gradient(180deg,#eceff1,#d8dde1)", preview=("#9aa", "#ccc", "#9aa")),
    "satellite": Basemap(
        "satellite", "Satellite",
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        _ESRI_ATTR, is_dark=True, satellite=True,
        bg="linear-gradient(140deg,#2d3823,#4a3a2a,#2a2820)",
        preview=("#ffe8a0", "#ffd84d", "#fffdf2")),
}

# default set offered by the switcher when the caller doesn't specify one
DEFAULT_SWITCHER = ["voyager", "positron", "dark_matter", "osm", "satellite"]


def get_basemap(key: str | Basemap) -> Basemap:
    if isinstance(key, Basemap):
        return key
    try:
        return BASEMAPS[key]
    except KeyError:
        raise ValueError(f"unknown basemap {key!r}; choose from {list(BASEMAPS)}")
