"""The road arrow image has a name of its own (`rs-oneway`), never `oneway`: the sprite of a vector base map (OpenFreeMap) has an image `oneway` that points
up, and a line placement turns an up-pointing icon 90 degrees from the road. Python and Rust agree on the name; the layer and the images name it; a base map's
own `oneway` image does not take its place. Skipped without playwright."""
import json
import re

import pytest

import roadstyle as rs
from roadstyle import _engine

pw = pytest.importorskip("playwright.sync_api")

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]


def _edges():
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary", "primary"], "name": ["A", "B"], "oneway": [True, True], "edge_id": [1, 2]},
                            geometry=[LineString([(18.0, 59.30), (18.0, 59.31)]), LineString([(18.001, 59.31), (18.001, 59.30)])], crs=4326)


def _style(html):
    j = html.index("{", html.index("const style = "))
    return json.JSONDecoder().raw_decode(html[j:])[0]


def test_the_page_style_names_the_arrow_image_rs_oneway():
    s = _style(rs.render_dashboard(_edges(), basemap="blank").html)
    arrows = [l for l in s["layers"] if l["id"].startswith("roads-arrows")]
    assert arrows and {l["layout"]["icon-image"] for l in arrows} == {_engine._ARROW_IMAGE} == {"rs-oneway"}


def test_the_script_never_uses_the_plain_name():
    from roadstyle import _assets
    js = _assets.text("static/dashboard/arrows.js")
    assert not re.search(r"""(hasImage|addImage|removeImage)\(\s*["']oneway["']""", js) and "ARROW_IMAGE" in js


def test_a_base_maps_oneway_image_does_not_take_the_place_of_the_arrow(tmp_path):
    path = tmp_path / "a.html"
    rs.render_dashboard(_edges(), basemap="blank").save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1000, "height": 700})
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded() && window.rsReady", timeout=60_000)
        # what a vector base map's sprite does: an up-pointing image named `oneway` (21 x 21, as OpenFreeMap's)
        page.evaluate("""() => { const c = document.createElement('canvas'); c.width = 21; c.height = 21; const x = c.getContext('2d');
            x.fillStyle = '#000'; x.beginPath(); x.moveTo(10, 0); x.lineTo(15, 6); x.lineTo(12, 6); x.lineTo(12, 20); x.lineTo(8, 20); x.lineTo(8, 6); x.lineTo(5, 6); x.fill();
            map.addImage('oneway', x.getImageData(0, 0, 21, 21)); }""")
        page.wait_for_timeout(500)
        got = page.evaluate("""() => { const im = map.getImage('rs-oneway').data; return {layer: map.getLayoutProperty('roads-arrows', 'icon-image'), w: im.width, h: im.height,
                                                          other: map.getImage('oneway').data.height}; }""")
        browser.close()
    assert got["layer"] == "rs-oneway"
    assert got["w"] > got["h"], "the road arrow points along the line (wider than tall), not up"
    assert got["other"] == 21                 # the base map's own image is still its own
