"""Browser tests for the sensor-matching requests (docs/notes/requests-from-sensor-matching.md).

Each test saves a page, opens it in headless Chromium and reads the DOM or the map. Skipped when
playwright is not installed.
"""
import pytest

pw = pytest.importorskip("playwright.sync_api")

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]


def _edges(n=12):
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame(
        {"highway": ["primary"] * n, "name": [f"Street {i}" for i in range(n)],
         "edge_id": list(range(1, n + 1))},
        geometry=[LineString([(18.0 + i * 1e-3, 59.30), (18.0 + i * 1e-3, 59.31)]) for i in range(n)],
        crs=4326)


def _open(p, path, size=(1000, 700)):
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_page(viewport={"width": size[0], "height": size[1]})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(path.resolve().as_uri())
    page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
    return browser, page, errors


def test_one_tile_zoom_in_a_tilted_view(tmp_path):
    """Item 1: a tilted map loads every tile of the roads at one zoom (no width step)."""
    from roadstyle.render_web import render

    path = tmp_path / "tilt.html"
    render(_edges(), basemap="blank", simple=True).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        page.evaluate("map.jumpTo({center:[18.005,59.305], zoom:17.6, pitch:72, bearing:-25})")
        page.wait_for_timeout(4000)
        zooms = page.evaluate("""(()=>{const t=map.style.tileManagers.roads; const ts=t._inViewTiles?._tiles||t._tiles;
            return [...new Set(Object.values(ts).map(x=>x.tileID.overscaledZ))]})()""")
        browser.close()
    assert zooms == [17] and not errors
