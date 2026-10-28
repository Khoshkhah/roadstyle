"""OpenFreeMap vector styles as base maps: registered, offered by the switcher, and handled by the dashboard's basemap.js."""
import pathlib

import roadstyle as rs
from roadstyle.basemaps import DEFAULT_SWITCHER

JS = (pathlib.Path(__file__).resolve().parent.parent / "src/roadstyle/static/dashboard/basemap.js").read_text()


def test_openfreemap_is_registered_and_offered():
    for key, name in (("ofm_liberty", "liberty"), ("ofm_bright", "bright"), ("ofm_positron", "positron")):
        bm = rs.BASEMAPS[key]
        assert bm.style_url == f"https://tiles.openfreemap.org/styles/{name}" and "OpenFreeMap" in bm.attr
        assert key in DEFAULT_SWITCHER


def test_page_options_carry_the_style_url():
    from roadstyle.render_web import _page_basemaps
    _, bms, _ = _page_basemaps("osm", ["osm", "ofm_liberty"], None, True)
    assert [b.get("style_url") for b in bms] == [None, "https://tiles.openfreemap.org/styles/liberty"]


def test_basemap_js_merges_a_vector_style():
    assert "mergeVector" in JS and "fill-extrusion" in JS and "window.rsBuildings" in JS and "rs:basemapready" in JS
