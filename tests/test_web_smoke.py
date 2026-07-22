"""Browser smoke test — the saved page actually boots MapLibre and draws roads.

The rest of the suite inspects the generated HTML as text; this is the one test that runs it,
catching the class of bug a string assertion can't (a JS syntax error, the template failing to
wire the data). Needs ``playwright`` + ``playwright install chromium`` (dev-only, optional) —
skipped when absent.
"""
import pytest

pw = pytest.importorskip("playwright.sync_api")


def _edges(n=40):
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame(
        {"highway": ["primary"] * n, "name": [f"Street {i}" for i in range(n)],
         "oneway": [True] * n},
        geometry=[LineString([(18.0 + i * 1e-3, 59.3), (18.0 + i * 1e-3, 59.301)])
                  for i in range(n)],
        crs=4326)


def test_saved_map_boots_and_draws_roads(tmp_path):
    from roadstyle.render_web import render

    path = tmp_path / "smoke.html"
    render(_edges(), basemap="blank").save(path)   # blank basemap: zero network requests

    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function(
            "window.map && typeof window.map.loaded === 'function' && window.map.loaded()",
            timeout=30_000)
        n_source = page.evaluate("window.map.querySourceFeatures('roads').length")
        n_query = page.evaluate("rsQuery(p => p.highway === 'primary').length")
        browser.close()

    assert errors == []
    assert n_source > 0          # the road data reached the map
    assert n_query == len(_edges())   # the JS API sees every edge
