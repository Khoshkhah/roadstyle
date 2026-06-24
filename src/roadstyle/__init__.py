"""roadstyle — OSM-theme road/edge map styling for folium & lonboard.

    import geopandas as gpd
    from roadstyle import render_edges

    edges = gpd.read_file(...)                       # needs a `highway` column
    render_edges(edges).save("map.html")             # default theme: light + the Voyager base
    render_edges(edges, theme="dark",
                 include=["motorway", "trunk", "primary"]).save("major.html")
"""
from .basemaps import BASEMAPS, Basemap, get_basemap, register_basemap
from .config import StyleConfig
from .controls import BaseLayerSwitcher
from .edges import (
    RoadEdges,
    as_edges,
    from_arrow,
    from_duckdb,
    from_geojson,
    load_edges,
    normalize_edges,
)
from .emit import (
    load_spec,
    save,
    save_spec,
    to_geojson,
    to_html,
    to_iframe,
    to_spec,
)
from .filters import filter_edges, highway_types
from .legend import make_legend
from .overlays import Overlay
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
    ColorTableStyler,
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
    "CategoricalStyler", "NumericStyler", "ColorTableStyler", "build_styler",
    "color_by", "color_by_value", "color_by_class",
    # canonical input (Phase 3a)
    "RoadEdges", "normalize_edges", "load_edges", "as_edges",
    "from_geojson", "from_arrow", "from_duckdb",
    # legends (Phase 3)
    "make_legend",
    # extra overlay layers (zones / POIs / any geometry)
    "Overlay",
    # web / JSON output (Phase 4)
    "to_spec", "to_geojson", "to_html", "to_iframe", "save", "save_spec", "load_spec",
]
