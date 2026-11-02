"""The two directions of a two-way road (a twin pair: two edges on one line, one each way) are two halves of the road that lie side by side, so
a colour on one direction (`rsColor`) shows as a half and never hides the other. Before offset_zoom the halves are the road's width in all; from
there they widen to the lanes of the profile (docs/design/twin_ends.md). A road that is not painted looks as it did when the pair was drawn as
one line on one line (the pictures in tests/data/twin_halves; ROADSTYLE_BLESS=1 makes them again). Skipped without playwright and PIL."""
import io
import os
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
Image = pytest.importorskip("PIL.Image")

import geopandas as gpd  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

import roadstyle as rs  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
_DATA = Path(__file__).parent / "data" / "twin_halves"
_LINE = [(18.07, 59.30), (18.07, 59.33)]
_PURPLE = (124, 77, 255)           # #7c4dff
_SCALE = 4                         # device pixels for a CSS pixel: a width in quarters of a pixel
_ZOOMS = [10, 12, 14, 16]
_CLASSES = ["primary", "secondary"]


def _pair(highway):
    return gpd.GeoDataFrame({"highway": [highway] * 2, "edge_id": [1, 2]}, geometry=[LineString(_LINE), LineString(_LINE[::-1])], crs=4326)


def _shoot(p, path, zoom, theme, paint):
    """The map around the road's middle (a crop of 3 x 40 CSS pixels over the road's line) after `paint` of one twin."""
    browser = p.chromium.launch(args=_ARGS)
    try:
        page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=_SCALE)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        page.evaluate("t => rsSetTheme(t)", theme)
        page.evaluate("z => map.jumpTo({center: [18.07, 59.315], zoom: z})", zoom)
        if paint:
            page.evaluate("rsColor([0], '#7c4dff')")
        page.wait_for_function("map.loaded()")
        page.wait_for_timeout(800)
        x, y = page.evaluate("(() => { const q = map.project([18.07, 59.315]); return [q.x, q.y]; })()")
        png = page.screenshot(clip={"x": x - 20, "y": y - 2, "width": 40, "height": 4})
        assert errors == []
        return Image.open(io.BytesIO(png)).convert("RGB")
    finally:
        browser.close()


def _dist(a, b):
    return sum(abs(i - j) for i, j in zip(a, b))


def _widths(im, fill):
    """The visible width in CSS pixels of the purple twin and of the other one, along the middle row of `im`: the road's two outer edges are
    the first and the last pixel that is not the map's background, and the two twins meet where the row turns from purple to the road's colour
    (a pixel between the two has its share of each)."""
    row = [im.getpixel((x, im.size[1] // 2)) for x in range(im.size[0])]
    bg = row[0]
    road = [x for x, c in enumerate(row) if _dist(c, bg) > 12]
    left, right = road[0], road[-1] + 1
    purple = [x for x, c in enumerate(row) if _dist(c, _PURPLE) < 24]
    plain = [x for x, c in enumerate(row) if _dist(c, fill) < 24]
    if not purple or not plain:
        return (len(purple) / _SCALE, len(plain) / _SCALE)
    left_is_purple = max(purple) < min(plain)
    a, z = (max(purple), min(plain)) if left_is_purple else (max(plain), min(purple))
    share = sum(min(1.0, _dist(row[x], fill) / _dist(_PURPLE, fill)) for x in range(a + 1, z))      # the purple part of the pixels between
    meet = a + 1 + (share if left_is_purple else (z - a - 1) - share)
    first, second = (meet - left, right - meet) if left_is_purple else (right - meet, meet - left)
    return first / _SCALE, second / _SCALE


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("highway", _CLASSES)
def test_a_painted_direction_shows_as_wide_as_its_twin(tmp_path, highway, theme):
    path = tmp_path / "p.html"
    rs.render_dashboard(_pair(highway), basemap="blank").save(path)
    with pw.sync_playwright() as p:
        for zoom in _ZOOMS:
            fill = _shoot(p, path, zoom, theme, False).getpixel((20 * _SCALE, 2 * _SCALE))      # the road's own colour, at its middle
            purple, other = _widths(_shoot(p, path, zoom, theme, True), fill)
            assert purple > 0 and other > 0, (zoom, purple, other)
            assert abs(purple - other) <= 0.5, f"{highway} {theme} zoom {zoom}: the painted direction shows {purple} px, its twin {other} px"


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("zoom", _ZOOMS)
def test_a_road_that_is_not_painted_looks_as_it_did(tmp_path, zoom, theme):
    path = tmp_path / "p.html"
    rs.render_dashboard(_pair("primary"), basemap="blank").save(path)
    with pw.sync_playwright() as p:
        got = _shoot(p, path, zoom, theme, False)
    gold = _DATA / f"unpainted_{theme}_z{zoom}.png"
    if os.environ.get("ROADSTYLE_BLESS"):
        got.save(gold)
    want = Image.open(gold).convert("RGB")
    assert got.size == want.size
    worst = max(_dist(a, b) for a, b in zip(got.getdata(), want.getdata()))
    assert worst <= 90, f"zoom {zoom} {theme}: a pixel differs by {worst} (sum of the three channels) from {gold.name}"
