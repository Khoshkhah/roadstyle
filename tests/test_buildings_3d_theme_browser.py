"""The 3D buildings of a vector base map, in the light and in the dark theme. The flat buildings of the dark OpenFreeMap styles are as dark as
their ground, so the 3D layer takes the color that the base map names (`building_3d` in data/basemaps.json). The styles are stubs with the colors of
the real ones (measured 2026-11-02), so the checks need no network. Skipped without playwright."""
import colorsys
import json
import re

import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _ARGS, _edges  # noqa: E402

import roadstyle as rs  # noqa: E402

STEP = 0.15         # the least lightness step (HSL, 0 to 1) of a dark 3D building above the dark ground


def _stub(ground, building):
    return {"version": 8, "sources": {"openmaptiles": {"type": "vector", "tiles": ["https://tiles.invalid/{z}/{x}/{y}.pbf"]}},
            "layers": [{"id": "background", "type": "background", "paint": {"background-color": ground}},
                       {"id": "building", "type": "fill", "source": "openmaptiles", "source-layer": "building", "paint": {"fill-color": building}}]}


def _lightness(color):
    r, g, b = (int(v) for v in re.findall(r"\d+", color)[:3]) if color.startswith("rgb") else (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r / 255, g / 255, b / 255)[1]


def _colors(tmp_path, basemap, ground, building, theme):
    path = tmp_path / "b.html"
    rs.render_dashboard(_edges(), basemap=basemap, color_options={"Road class": {}}).save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("https://tiles.openfreemap.org/styles/*", lambda r: r.fulfill(content_type="application/json", body=json.dumps(_stub(ground, building))))
        page.route("https://tiles.invalid/**", lambda r: r.abort())
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        page.evaluate(f"rsSetTheme('{theme}')")
        page.wait_for_function("window.map.getLayer('vbm-building-3d')", timeout=30_000)
        got = page.evaluate("[map.getPaintProperty('vbm-building-3d', 'fill-extrusion-color'), map.getPaintProperty('vbm-background', 'background-color')]")
        browser.close()
    assert errors == []
    return got


@pytest.mark.parametrize("basemap, ground, flat", [("ofm_positron", "rgb(12,12,12)", "rgb(10,10,10)"), ("ofm_fiord", "#45516E", "hsla(232,47%,18%,0.65)")])
def test_dark_3d_buildings_are_lighter_than_the_ground(tmp_path, basemap, ground, flat):
    building, back = _colors(tmp_path, basemap, ground, flat, "dark")
    assert _lightness(building) - _lightness(back) >= STEP, (building, back)


def test_light_3d_buildings_keep_the_color_of_the_flat_layer(tmp_path):
    building, _ = _colors(tmp_path, "ofm_positron", "rgb(242,243,240)", "rgb(234, 234, 229)", "light")
    assert building == "rgb(234, 234, 229)"
