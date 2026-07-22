"""roadstyle — OSM-style road/edge map styling; self-contained MapLibre maps (plus folium & lonboard).

    import geopandas as gpd
    from roadstyle import render_edges

    edges = gpd.read_file(...)                       # needs a `highway` column
    render_edges(edges).save("map.html")             # web backend, Voyager base (settings default)
    render_edges(edges, basemap="dark_matter",
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
from .snapshot import snapshot
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


def use_settings(*sources) -> None:
    """Apply settings overrides from code — the in-process equivalent of a ``roadstyle.json``.

    Each source is a path to a JSON file or a dict, in the same
    ``{"palettes", "config", "selection", "roads"}`` layout as an override file (state only what
    changes; everything else keeps the bundled defaults + any discovered override files, which
    these sources outrank; later sources outrank earlier ones). Call with no arguments to drop
    the programmatic overrides again. For a single render, prefer
    ``render_edges(..., settings=...)`` — it applies and restores automatically.

    Safe to call at any point before rendering — already-imported styling tables (palettes,
    ``StyleConfig``, the web renderer's road model) are rebuilt in place::

        import roadstyle as rs
        rs.use_settings("styles/dark-flow.json")     # or a dict
        rs.render_edges(edges, backend="web").save("map.html")

    Two setting sets in one process = call it again between renders. Note the handful of legacy
    class-level defaults (:class:`roadstyle.style.RoadStyle` field defaults) resolve at import and
    are unaffected — palette entries always restate them, so rendering is unaffected too.
    """
    from . import _settings, config, palettes, render_web, style, stylers

    _settings.set_extra(*sources)
    config.DEFAULT = config._default_config()
    style.DEFAULT = stylers.DEFAULT = render_web.CONFIG = config.DEFAULT
    palettes._reload()
    render_web._load_road_model()


__version__ = "0.2.0.dev0"

__all__ = [
    "render_edges", "filter_edges", "highway_types", "use_settings", "snapshot",
    "resolve", "base_style", "selection_style", "normalize_highway",
    "PALETTES", "HIGHSAT", "CARTO", "SELECTION", "RoadStyle",
    "BASEMAPS", "Basemap", "get_basemap", "BaseLayerSwitcher",
    # generalization additions (Phase 0)
    "StyleConfig", "register_palette", "register_basemap",
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
