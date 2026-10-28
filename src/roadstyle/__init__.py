"""roadstyle — OSM-style road/edge map styling; self-contained MapLibre maps.

    import geopandas as gpd
    from roadstyle import render_edges

    edges = gpd.read_file(...)                       # needs a `highway` column
    render_edges(edges).save("map.html")             # web backend, Voyager base (settings default)
    render_edges(edges, basemap="dark_matter",
                 include=["motorway", "trunk", "primary"]).save("major.html")
"""
from .basemaps import (
    BASEMAPS,
    Basemap,
    get_api_key,
    get_basemap,
    register_basemap,
    set_api_key,
)
from .config import StyleConfig
from .edges import (
    RoadEdges,
    as_edges,
    from_arrow,
    from_duckdb,
    from_geojson,
    is_directed,
    load_edges,
    normalize_edges,
)
from .export import export_geojson, export_inline, export_look, export_style, tile_geojson
from .filters import filter_edges, highway_types, normalize_highway
from .levels import auto_ends, casing_parts, compute_levels, level_input, solve_levels
from .levels_store import (
    load_area_levels,
    load_levels,
    restore_area_inputs,
    save_area_levels,
    save_levels,
)
from .overlays import Overlay
from .pages import render_dashboard, render_report, render_street_view, sidebar_html
from .render import render_edges
from .snapshot import snapshot


def use_settings(*sources) -> None:
    """Apply settings overrides from code — the in-process equivalent of a ``roadstyle.json``.

    Each source is a path to a JSON or YAML file (``.yaml`` / ``.yml``) or a dict, in the same
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
    """
    from . import _settings, config, render_web

    _settings.set_extra(*sources)
    config.DEFAULT = config._default_config()
    render_web.CONFIG = config.DEFAULT
    render_web._load_road_model()


def _source_version():
    """The version in the ``pyproject.toml`` next to ``src/`` when roadstyle is imported from a source checkout (PYTHONPATH=.../src), else ``None``:
    the metadata of another, older installed copy must not win there (it said 0.17.1 for a 0.22.1 tree)."""
    import re
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8")
    if not re.search(r'^name\s*=\s*"roadstyle"', text, re.M):
        return None
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    return m.group(1) if m else None


# Single source of truth is [project] version in pyproject.toml: read from the source tree, else from the install metadata.
try:
    __version__ = _source_version()
    if __version__ is None:
        from importlib.metadata import version as _pkg_version
        __version__ = _pkg_version("roadstyle")
except Exception:                                    # running from a bare source tree
    __version__ = "0+unknown"

__all__ = [
    "export_inline",
    "export_look",
    "export_style",
    "export_geojson",
    "tile_geojson",
    "compute_levels",
    "level_input",
    "solve_levels",
    "casing_parts",
    "auto_ends",
    "load_area_levels",
    "load_levels",
    "restore_area_inputs",
    "save_area_levels",
    "save_levels",
    "render_edges", "render_dashboard", "render_report", "render_street_view", "sidebar_html",
    "filter_edges", "highway_types", "use_settings", "snapshot",
    "normalize_highway",
    "BASEMAPS", "Basemap", "get_basemap", "set_api_key", "get_api_key",
    "StyleConfig", "register_basemap",
    # canonical input (Phase 3a)
    "RoadEdges", "normalize_edges", "load_edges", "as_edges",
    "from_geojson", "from_arrow", "from_duckdb", "is_directed",
    # extra overlay layers (zones / POIs / any geometry)
    "Overlay",
]
