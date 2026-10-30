"""The toolbar's default place is the right edge on a desktop (the panel stays at the left); on a phone the bar stays at the top. The boxes of the bar
open to its left and stay inside the window, and the corner box (the credits) does not lie on the bar. A page that sets the position keeps it.
Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
_BOX = """s => { const e = document.querySelector(s); if(!e || getComputedStyle(e).display === 'none' || e.hidden) return null; const r = e.getBoundingClientRect(); return {l: r.left, t: r.top, r: r.right, b: r.bottom}; }"""


def _edges():
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary"], "edge_id": [1]}, crs=4326, geometry=[LineString([(18.0, 59.3), (18.001, 59.301)])])


def _open(browser, html, w, h, **ctx):
    errors = []
    page = browser.new_context(viewport={"width": w, "height": h}, **ctx).new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("http://rs.test/p.html", lambda r: r.fulfill(content_type="text/html", body=html))
    page.goto("http://rs.test/p.html")
    page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
    page.wait_for_timeout(1200)
    return page, errors


def test_on_a_desktop_the_bar_is_at_the_right_edge_the_panel_at_the_left_and_the_boxes_open_inside():
    html = rs.render_dashboard(_edges(), basemap="blank").html
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page, errors = _open(browser, html, 1400, 900)
        bar, sb = page.evaluate(_BOX, "#rs-toolbar"), page.evaluate(_BOX, "#sb")
        assert page.evaluate("document.documentElement.classList.contains('rs-tb-right')")
        assert bar["r"] > 1400 - 16 and bar["l"] > 1400 - 70 and abs((bar["t"] + bar["b"]) / 2 - 450) < 40, bar       # a column at the right edge, in the middle
        assert sb["l"] < 20 and sb["r"] < 700, sb                                                                      # the panel stays at the left
        scale = page.evaluate(_BOX, "#rs-scalebox")
        if scale:                                                                                                       # the corner box is under the bar's end, not on it
            assert scale["t"] >= bar["b"] or scale["r"] <= bar["l"] or scale["b"] <= bar["t"] or scale["l"] >= bar["r"], (scale, bar)
        for button, box in ((".bm-ctrl > button", ".bm-menu.open"), (".rs-set-ctrl > button", "#rs-settings-box")):     # the base-map box and the settings box
            page.locator(button).first.click()
            page.wait_for_timeout(300)
            b = page.evaluate(_BOX, box)
            assert b and b["r"] <= bar["l"] and b["l"] >= 0 and b["t"] >= 0 and b["b"] <= 900, (box, b, bar)         # to the left of the bar, inside the window
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
        browser.close()
    assert not errors, errors


def test_a_page_that_sets_the_position_keeps_it():
    html = rs.render_dashboard(_edges(), basemap="blank", dashboard={"toolbar": {"position": "left"}}).html
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page, errors = _open(browser, html, 1400, 900)
        bar, sb = page.evaluate(_BOX, "#rs-toolbar"), page.evaluate(_BOX, "#sb")
        assert page.evaluate("document.documentElement.classList.contains('rs-tb-left')") and bar["l"] < sb["r"] + 80, (bar, sb)
        browser.close()
    assert not errors, errors


def test_on_a_phone_the_bar_stays_at_the_top():
    html = rs.render_dashboard(_edges(), basemap="blank").html
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page, errors = _open(browser, html, 390, 844, is_mobile=True, has_touch=True)
        bar = page.evaluate(_BOX, "#rs-toolbar")
        assert page.evaluate("document.querySelector('#rs-toolbar').dataset.edge") == "top" and bar["t"] < 16 and bar["r"] - bar["l"] > 300, bar
        browser.close()
    assert not errors, errors
