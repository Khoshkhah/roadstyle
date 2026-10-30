"""The dashboard on a phone: the bar folds to one button and the page keeps that choice, the sheet has a visible button that lowers and raises it, and
the first view fits into the free part of the window (below the bar, above the sheet; beside the panel on a desktop). Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_URL = "http://rs.test/page.html"
_BOXES = """() => { const box = s => { const e = document.querySelector(s); if(!e || getComputedStyle(e).display === "none") return null;
  const r = e.getBoundingClientRect(); return {l: r.left, t: r.top, r: r.right, b: r.bottom}; };
  return {bar: box("#rs-toolbar"), sb: box("#sb"), grip: box(".rs-grip")}; }"""
# the roads' box on the screen: the corners of the bounds of the data
_ROADS = """() => { const m = window.map, b = m.getBounds(), cs = [[18.0, 59.3], [18.003, 59.301]].map(c => m.project(c));
  return {l: Math.min(...cs.map(c => c.x)), r: Math.max(...cs.map(c => c.x)), t: Math.min(...cs.map(c => c.y)), b: Math.max(...cs.map(c => c.y))}; }"""


def _edges():
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary", "residential"], "edge_id": [1, 2]}, crs=4326,
                            geometry=[LineString([(18.0, 59.3), (18.001, 59.301)]), LineString([(18.002, 59.3), (18.003, 59.301)])])


def _open(browser, html, errors, **ctx):
    page = browser.new_context(**ctx).new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route(_URL, lambda r: r.fulfill(content_type="text/html", body=html))
    page.goto(_URL)
    page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
    page.wait_for_timeout(1500)
    return page


def test_the_bar_folds_to_one_button_and_the_page_keeps_it():
    html, errors = rs.render_dashboard(_edges(), basemap="blank").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = _open(browser, html, errors, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        shown = lambda: page.evaluate("[...document.querySelectorAll('#rs-toolbar > .maplibregl-ctrl')].filter(e => e.offsetParent).length")  # noqa: E731
        full = shown()
        assert full > 5 and page.locator(".rs-tb-fold button").count() == 1
        page.locator(".rs-tb-fold button").tap()
        assert shown() == 1 and page.evaluate("document.documentElement.classList.contains('rs-tb-folded')")
        page.reload()
        page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
        assert shown() == 1, "the folded bar is kept"
        page.locator(".rs-tb-fold button").tap()
        assert shown() == full
        browser.close()
    assert not errors, errors


def test_the_sheet_has_a_button_and_the_first_view_is_in_the_free_part_of_the_phone():
    html, errors = rs.render_dashboard(_edges(), basemap="blank").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = _open(browser, html, errors, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        b, road = page.evaluate(_BOXES), page.evaluate(_ROADS)
        assert b["grip"]["b"] - b["grip"]["t"] >= 44, "the grip is a touch target"
        assert road["t"] >= b["bar"]["b"] - 1 and road["b"] <= b["sb"]["t"] + 1, (road, b)       # in the free part: below the bar, above the sheet
        btn = page.locator(".rs-grip-btn")
        heights = lambda: page.evaluate("[0, 1, 2].find(i => document.documentElement.classList.contains('rs-sheet-' + i))")  # noqa: E731
        assert heights() == 1
        btn.tap()
        assert heights() == 0
        btn.tap()
        assert heights() == 1
        browser.close()
    assert not errors, errors


def test_the_first_view_on_a_desktop_is_beside_the_panel():
    html, errors = rs.render_dashboard(_edges(), basemap="blank").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = _open(browser, html, errors, viewport={"width": 1280, "height": 800})
        b, road = page.evaluate(_BOXES), page.evaluate(_ROADS)
        assert road["l"] >= b["sb"]["r"] - 1, (road, b)         # the panel is at the left: the roads start at its edge or beyond
        browser.close()
    assert not errors, errors


def test_the_google_3d_window_bar_wraps_on_a_phone():
    html, errors = rs.render_dashboard(_edges(), basemap="blank", google_3d=True).html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = _open(browser, html, errors, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        r = page.evaluate("""() => { const w = document.querySelector('.rs-g3d'); w.hidden = false;
          const n = w.querySelector('.rs-g3d-note'); n.hidden = false;
          const box = e => e.getBoundingClientRect(), bar = w.querySelector('.rs-svw-bar');
          return {bar: box(bar).width, note: box(n).width, noteTop: box(n).top, line: parseFloat(getComputedStyle(n).lineHeight),
                  noteH: box(n).height, btnBottom: Math.max(...[...bar.querySelectorAll('button')].map(b => box(b).bottom))}; }""")
        assert r["note"] > r["bar"] * 0.8, r                       # the note has the width of the bar, not a narrow column
        assert r["noteH"] < r["line"] * 3, r                       # it has one or two lines, not one word on a line
        browser.close()
    assert not errors, errors
