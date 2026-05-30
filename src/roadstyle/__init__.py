"""roadstyle — OSM-theme road/edge map styling for folium & lonboard.

    import geopandas as gpd
    from roadstyle import render_edges

    edges = gpd.read_file(...)                       # needs a `highway` column
    render_edges(edges, theme="dark").save("map.html")
    render_edges(edges, palette="carto", theme="light",
                 include=["motorway", "trunk", "primary"]).save("major.html")
"""
from .basemaps import BASEMAPS, Basemap, get_basemap, register_basemap
from .config import StyleConfig
from .controls import BaseLayerSwitcher
from .filters import filter_edges, highway_types
from .palettes import (
    CARTO,
    HIGHSAT,
    PALETTES,
    SELECTION,
    RoadStyle,
    load_palette,
    palette_from_dict,
    palette_to_dict,
    register_palette,
    save_palette,
)
from .render import render_edges
from .style import base_style, normalize_highway, resolve, selection_style
from .stylers import (
    CategoricalStyler,
    ClassStyler,
    NumericStyler,
    ResolvedFrame,
    Styler,
    build_styler,
    color_by,
    color_by_class,
    color_by_value,
)
from .themes import THEMES, Theme, get_theme, register_theme

__version__ = "0.2.0.dev0"

__all__ = [
    "render_edges", "filter_edges", "highway_types",
    "resolve", "base_style", "selection_style", "normalize_highway",
    "PALETTES", "HIGHSAT", "CARTO", "SELECTION", "RoadStyle",
    "THEMES", "Theme", "get_theme",
    "BASEMAPS", "Basemap", "get_basemap", "BaseLayerSwitcher",
    # generalization additions (Phase 0)
    "StyleConfig", "register_palette", "register_theme", "register_basemap",
    # styler abstraction (Phase 1)
    "Styler", "ClassStyler", "ResolvedFrame",
    # palette JSON I/O (Phase 2a)
    "load_palette", "save_palette", "palette_to_dict", "palette_from_dict",
    # data-driven styling (Phase 2)
    "CategoricalStyler", "NumericStyler", "build_styler",
    "color_by", "color_by_value", "color_by_class",
]
