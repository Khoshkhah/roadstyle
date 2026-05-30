"""roadstyle — OSM-theme road/edge map styling for folium & lonboard.

    import geopandas as gpd
    from roadstyle import render_edges

    edges = gpd.read_file(...)                       # needs a `highway` column
    render_edges(edges, theme="dark").save("map.html")
    render_edges(edges, palette="carto", theme="light",
                 include=["motorway", "trunk", "primary"]).save("major.html")
"""
from .basemaps import BASEMAPS, Basemap, get_basemap
from .controls import BaseLayerSwitcher
from .filters import filter_edges, highway_types
from .palettes import CARTO, HIGHSAT, PALETTES, SELECTION, RoadStyle
from .render import render_edges
from .style import base_style, normalize_highway, resolve, selection_style
from .themes import THEMES, Theme, get_theme

__version__ = "0.1.0"

__all__ = [
    "render_edges", "filter_edges", "highway_types",
    "resolve", "base_style", "selection_style", "normalize_highway",
    "PALETTES", "HIGHSAT", "CARTO", "SELECTION", "RoadStyle",
    "THEMES", "Theme", "get_theme",
    "BASEMAPS", "Basemap", "get_basemap", "BaseLayerSwitcher",
]
