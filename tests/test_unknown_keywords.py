"""A keyword that no part of roadstyle reads (roadstyle::options::unknown, the one rule of the Python binding and the MCP server): before
0.26.0 render_edges ignored it with no message. Now each one gives a warning with the nearest known name; from 0.27.0 it is an error."""
import inspect

import geopandas as gpd
import pytest
from shapely.geometry import LineString

from roadstyle import _engine, render_edges

pytestmark = pytest.mark.skipif(not _engine.available(), reason="no roadstyle._rust")

# the keywords of the Python functions that are not map keywords, each with its reason
PY_ONLY = {
    "gdf": "the roads",
    "backend": "the renderer (web, folium, lonboard)",
    "palette": "the look's palette (resolveLook's own option)",
    "profile": "the look's profile (resolveLook's own option)",
    "settings": "the look's settings (resolveLook's own option)",
    "include": "a filter of the GeoDataFrame before the map",
    "exclude": "a filter of the GeoDataFrame before the map",
    "match_links": "a filter of the GeoDataFrame before the map",
    "color_col": "the colour column of a color_table DataFrame, read in Python",
    "levels_db": "the stored levels of a duckOSM file, read in Python",
}


def _edges():
    return gpd.GeoDataFrame({"highway": ["primary", "residential"]},
                            geometry=[LineString([(18.0, 59.3), (18.001, 59.301)]), LineString([(18.001, 59.301), (18.002, 59.3)])], crs=4326)


def _unknown(**kw):
    try:
        render_edges(_edges(), basemap="blank", **kw)
    except ValueError as e:
        return str(e)
    return None


def test_an_unknown_keyword_is_an_error_with_the_nearest_name():
    assert _unknown(colour_by="x", zzz=1) == "render_edges: unknown keyword 'colour_by' (did you mean 'color_by'?), 'zzz'"


def test_known_keywords_give_no_error():
    assert _unknown(view_3d=True, legend=False, popup_mode="panel", tooltip=["highway"]) is None
    assert "zzz" in _unknown(palette="mono", zzz=1)


def test_every_keyword_of_the_python_functions_is_known_or_python_only():
    """No keyword drifts: each keyword of render_edges and render_web.render is a keyword that roadstyle reads, or one of PY_ONLY.
    A new Python keyword needs its place in the Rust side (MapOptions, PageOptions) or a line in PY_ONLY with its reason."""
    kinds = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    names = sorted({p.name for f in (render_edges,) for p in inspect.signature(f).parameters.values()
                    if p.kind in kinds and not p.name.startswith("_")})
    unknown = [k for k, _ in _engine.rust().unknown_keywords(names)]
    assert sorted(set(unknown) - set(PY_ONLY)) == [], "keywords that roadstyle does not read"
    assert sorted(set(PY_ONLY) - set(names)) == [], "PY_ONLY names that are no keyword any more"
