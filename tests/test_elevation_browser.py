"""Elevation on the map: the Hillshade and 3D terrain rows of the base-map box, drawn from the DEM of `ontop.dem` (Terrain Tiles on AWS). The tiles are
answered here with a synthetic Terrarium PNG (a slope), so the test needs no network. Skipped without playwright."""
import json
import pathlib

import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_DEM = json.loads((pathlib.Path(__file__).parents[1] / "rust/roadstyle-assets/files/data/basemaps.json").read_text())["ontop"]["dem"]
_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]


def _tile():
    """A Terrarium tile: the height rises from 0 m at the left to 255 m at the right (R*256 + G + B/256 - 32768). A PNG from the standard library."""
    import struct
    import zlib
    row = b"\x00" + b"".join(bytes(((32768 + x) >> 8, (32768 + x) & 255, 0)) for x in range(256))      # filter type 0, then 256 RGB pixels
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 256, 256, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(row * 256)) + chunk(b"IEND", b"")


def _edges():
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary"], "edge_id": [1]}, crs=4326, geometry=[LineString([(18.0, 59.3), (18.001, 59.301)])])


def _open(browser, html, errors, tile):
    page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("**/elevation-tiles-prod/**", lambda r: r.fulfill(content_type="image/png", body=tile))
    page.route("http://rs.test/p.html", lambda r: r.fulfill(content_type="text/html", body=html))
    page.goto("http://rs.test/p.html")
    page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
    page.wait_for_timeout(1200)
    return page


def test_the_dem_is_one_rule_in_the_config():
    assert _DEM["encoding"] == "terrarium" and "{z}/{x}/{y}" in _DEM["tiles"][0] and _DEM["maxzoom"] == 15


def test_off_by_default_and_the_rows_draw_the_hillshade_under_the_roads_and_the_terrain():
    tile, errors = _tile(), []
    html = rs.render_dashboard(_edges(), basemap="blank").html
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = _open(browser, html, errors, tile)
        state = lambda: page.evaluate("""({hill: !!map.getLayer('rs-top-hillshade'), terrain: !!map.getTerrain(),
            hillBeforeRoads: (() => { const ls = map.getStyle().layers.map(l => l.id), h = ls.indexOf('rs-top-hillshade'), r = ls.findIndex(i => i.startsWith('rs-') && i !== 'rs-top-hillshade' && map.getLayer(i).type === 'line');
                                      return h < 0 || r < 0 || h < r; })(),
            hillRow: document.getElementById('rs-top-hillshade').checked, terrainRow: document.getElementById('rs-top-terrain').checked})""")  # noqa: E731
        assert state() == {"hill": False, "terrain": False, "hillBeforeRoads": True, "hillRow": False, "terrainRow": False}
        page.evaluate("document.getElementById('rs-top-hillshade').click()")
        page.wait_for_timeout(500)
        s = state()
        assert s["hill"] and s["hillBeforeRoads"] and not s["terrain"], s                       # the hillshade is under the roads
        page.evaluate("document.getElementById('rs-top-terrain').click()")
        page.wait_for_timeout(1000)
        assert state()["terrain"] and page.evaluate("map.getPitch()") > 40, "the switch tilts a flat map"
        page.evaluate("document.getElementById('rs-top-terrain').click()")
        page.wait_for_timeout(1000)
        assert not state()["terrain"] and page.evaluate("map.getPitch()") < 5, "off: no terrain, and the map is flat again"
        page.evaluate("rsHillshade(false)")
        page.wait_for_timeout(300)
        assert not state()["hill"] and page.evaluate("rsHillshade()") is False, "the script API"
        browser.close()
    assert not errors, errors


def test_the_keywords_start_them_on_and_a_saved_choice_wins():
    tile, errors = _tile(), []
    html = rs.render_dashboard(_edges(), basemap="blank", hillshade=True, terrain=True).html
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = _open(browser, html, errors, tile)
        assert page.evaluate("[!!map.getLayer('rs-top-hillshade'), !!map.getTerrain(), map.getPitch()]") == [True, True, 0], "on at the start, the camera is the page's"
        page.evaluate("document.getElementById('rs-top-terrain').click()")                    # the person turns it off: kept in this browser
        page.wait_for_timeout(500)
        page.reload()
        page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
        page.wait_for_timeout(1200)
        assert page.evaluate("[!!map.getLayer('rs-top-hillshade'), !!map.getTerrain()]") == [True, False]
        browser.close()
    assert not errors, errors


def test_terrain_exaggeration_is_the_keyword_else_the_config():
    tile, errors = _tile(), []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        for kw, want in (({}, 1.0), ({"terrain_exaggeration": 2.5}, 2.5)):
            page = _open(browser, rs.render_dashboard(_edges(), basemap="blank", terrain=True, **kw).html, errors, tile)
            assert page.evaluate("map.getTerrain().exaggeration") == want, kw
        browser.close()
    assert not errors, errors
