"""The "One-way arrows" row of the base map box (basemapbox.js): it hides and shows the road style's arrow layers, the choice is kept in this
browser, and a page without arrows has no row. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
_VIS = """[...map.getStyle().layers].filter(l => l.type === "symbol" && JSON.stringify((l.layout || {})["icon-image"] || "").includes("rs-oneway"))
           .map(l => map.getLayoutProperty(l.id, "visibility") || "visible")"""


def _save(tmp_path, **kw):
    import geopandas as gpd
    from shapely.geometry import LineString
    edges = gpd.GeoDataFrame({"highway": ["primary", "residential"], "oneway": [True, True]},
                             geometry=[LineString([(18.0, 59.30), (18.0, 59.31)]), LineString([(18.01, 59.30), (18.01, 59.31)])], crs=4326)
    path = tmp_path / "arrows.html"
    rs.render_dashboard(edges, basemap="blank", **kw).save(path)
    return path


def _open(page, path):
    page.goto(path.resolve().as_uri())
    page.wait_for_function("window.map && map.loaded() && window.rsReady", timeout=60_000)
    page.evaluate("rs.tools.open('basemap')")
    page.wait_for_selector(".rs-bm-box")


def test_the_one_way_arrows_row_hides_the_arrows_and_is_kept(tmp_path):
    path = _save(tmp_path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            _open(page, path)
            row = page.locator("label:has(#rs-top-arrows)")
            assert row.is_visible() and row.inner_text() == "One-way arrows"
            assert page.is_checked("#rs-top-arrows") and set(page.evaluate(_VIS)) == {"visible"}
            page.click("#rs-top-arrows")
            assert set(page.evaluate(_VIS)) == {"none"}
            assert page.evaluate("localStorage.getItem('rs-top:arrows')") == "0"
            _open(page, path)                                                    # kept in this browser
            assert not page.is_checked("#rs-top-arrows") and set(page.evaluate(_VIS)) == {"none"}
            page.click("#rs-top-arrows")
            assert set(page.evaluate(_VIS)) == {"visible"}
        finally:
            browser.close()
    assert errors == []


def test_rs_set_arrows_and_the_row_show_one_state(tmp_path):
    """The page's API (rsSetArrows, rsArrowsOn, rsHasArrows, rs:arrowschange) and the box's row show and set one state: the duckOSM page's
    Design panel uses it."""
    path = _save(tmp_path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            _open(page, path)
            assert page.evaluate("rsHasArrows() && rsArrowsOn()")
            page.evaluate("window.heard = []; document.addEventListener('rs:arrowschange', e => heard.push(e.detail.on))")
            page.evaluate("rsSetArrows(false)")
            assert set(page.evaluate(_VIS)) == {"none"} and not page.is_checked("#rs-top-arrows") and not page.evaluate("rsArrowsOn()")
            page.click("#rs-top-arrows")
            assert set(page.evaluate(_VIS)) == {"visible"} and page.evaluate("rsArrowsOn()")
            assert page.evaluate("heard") == [False, True]
        finally:
            browser.close()
    assert errors == []


def test_a_page_without_arrows_has_no_row(tmp_path):
    path = _save(tmp_path, arrows=False)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        try:
            _open(page, path)
            assert page.evaluate(_VIS) == []
            assert page.locator("label:has(#rs-top-arrows)").is_hidden()
        finally:
            browser.close()
