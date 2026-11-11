"""A host that has no data yet (duckOSM Studio, `duckosm studio`: cards for the steps, and the roads come after a build) uses the standard dashboard
unchanged. Three things that a page with roads never shows: the banner "0 road features" is not for a page with no roads, the first view is the
world (not 0, 0), and an option row (`label.rs-opt`) is not in the small capitals of `#sb label`. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _edges, _open  # noqa: E402

import roadstyle as rs  # noqa: E402


def _empty_page(path):
    """The page of a table with no roads, as a host with its own data steps makes it (render_dashboard refuses an empty table: for a script that
    passes one by mistake). The same call as `render_page`, without the check."""
    import json

    import geopandas as gpd

    from roadstyle import _engine
    from roadstyle.render_web import WebMap

    kw = {"template": "dashboard", "basemap": "blank", "tiles": False}     # tiles=False: an archive of no roads has no tile
    lk, o = _engine._look_and_options({**kw, "palette": None, "profile": None, "settings": None, "highway_col": "highway", "state": "live"})
    empty = gpd.GeoDataFrame({"highway": []}, geometry=[], crs=4326)
    given = _engine.page_given(kw, None, None, None, lk, o["args"])
    WebMap(_engine.rust().page_from(_engine._arrow(empty), lk, json.dumps(o), json.dumps(given))).save(path)


def test_a_page_with_no_roads_has_no_banner_and_opens_on_the_world(tmp_path):
    path = tmp_path / "e.html"
    _empty_page(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            page.wait_for_timeout(3500)                       # the check of the banner waits 2.5 s after the load
            assert page.locator("#rs-diag").count() == 0
            assert page.evaluate("map.getZoom()") < 3
            assert page.evaluate("map.getCenter().lat") != 0
        finally:
            browser.close()
    assert errors == []


def test_a_page_with_roads_keeps_its_banner_check_and_its_box(tmp_path):
    path = tmp_path / "r.html"
    rs.render_dashboard(_edges(), basemap="blank").save(path)
    html = path.read_text()
    assert '"empty"' not in html.split("const RS_OPTIONS = ", 1)[1].split("cam = ", 1)[0]
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            assert page.evaluate("map.getZoom()") > 10        # the roads' box (Stockholm), not the world
        finally:
            browser.close()
    assert errors == []


def test_an_option_row_is_not_in_capitals(tmp_path):
    path = tmp_path / "o.html"
    rs.render_dashboard(_edges(), basemap="blank").save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            page.evaluate("""rs.sections.add({id: "o", label: "Options", html:
                '<label class="rs-opt"><input type="checkbox"><span><b>Driving</b><small>Cars</small></span></label><label id="plain">Plain</label>'})""")
            def css(sel):
                return page.evaluate("s => { const c = getComputedStyle(document.querySelector(s)); return [c.textTransform, c.letterSpacing]; }", sel)
            row = css("#sb .rs-opt")
            assert row[0] == "none" and row[1] in ("normal", "0px")
            assert css("#sb #plain")[0] == "uppercase"        # a caption label is still a caption
        finally:
            browser.close()
    assert errors == []
