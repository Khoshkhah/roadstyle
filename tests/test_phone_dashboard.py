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
        shown = lambda: page.evaluate("[...document.querySelectorAll('#rs-toolbar .maplibregl-ctrl')].filter(e => e.offsetParent).length")  # noqa: E731
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


_PHONES = [(390, 844), (360, 740)]
_TOUCH = dict(is_mobile=True, has_touch=True)


def _bar(page):
    return page.evaluate("""() => { const q = s => document.querySelector(s), r = e => { const b = e.getBoundingClientRect(); return {l: b.left, t: b.top, r: b.right, b: b.bottom, w: b.width, h: b.height}; };
      const sc = q('.rs-tb-scroll'), tools = [...sc.children].filter(e => e.offsetParent);
      return {bar: r(q('#rs-toolbar')), scroll: {left: sc.scrollLeft, sw: sc.scrollWidth, cw: sc.clientWidth}, tops: [...new Set(tools.map(e => Math.round(r(e).t)))],
              rowCls: q('.rs-tb-row').className, fold: r(q('.rs-tb-fold button'))}; }""")


@pytest.mark.parametrize("w,h", [(320, 568)])        # a tool shrinks from 32 to 26 px before the row scrolls: the bar of 390 and 360 px shows every tool at once, this one scrolls
def test_the_bar_is_one_row_that_a_finger_moves_sideways(w, h):
    html, errors = rs.render_dashboard(_edges(), basemap="blank").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = _open(browser, html, errors, viewport={"width": w, "height": h}, **_TOUCH)
        b = _bar(page)
        assert len(b["tops"]) == 1 and b["bar"]["h"] < 60, b                      # one row, not two
        assert b["scroll"]["sw"] > b["scroll"]["cw"] and "rs-more-r" in b["rowCls"] and "rs-more-l" not in b["rowCls"], b   # more tools to the right: the fade says so
        cdp = page.context.new_cdp_session(page)                                    # a finger swipe to the left on the tools (touch events, one move every frame)
        y = (b["bar"]["t"] + b["bar"]["b"]) / 2
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": w * 0.8, "y": y}]})
        for k in range(1, 13):
            cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": w * 0.8 - 20 * k, "y": y}]})
            page.wait_for_timeout(16)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        page.wait_for_timeout(500)
        b2 = _bar(page)
        assert b2["scroll"]["left"] > 20 and "rs-more-l" in b2["rowCls"], b2        # it moved, and the left fade shows
        assert b2["bar"]["h"] == b["bar"]["h"] and len(b2["tops"]) == 1
        browser.close()
    assert not errors, errors


@pytest.mark.parametrize("w,h", _PHONES)
def test_a_box_of_the_bar_opens_under_it_and_is_not_clipped(w, h):
    html, errors = rs.render_dashboard(_edges(), basemap="blank").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = _open(browser, html, errors, viewport={"width": w, "height": h}, **_TOUCH)
        page.evaluate("document.querySelector('.rs-tb-scroll').scrollLeft = 9999")   # the credits button is the last one
        page.wait_for_timeout(200)
        page.locator(".rs-attr-ctrl > button").tap()
        page.wait_for_timeout(300)
        r = page.evaluate("""() => { const e = document.getElementById('rs-attr-box'), b = e.getBoundingClientRect(), bar = document.getElementById('rs-toolbar').getBoundingClientRect(),
          at = document.elementFromPoint((b.left + b.right) / 2, (b.top + b.bottom) / 2);
          return {shown: !e.hidden, l: b.left, r: b.right, t: b.top, b: b.bottom, barB: bar.bottom, hit: !!(at && at.closest('#rs-attr-box')), W: innerWidth, H: innerHeight}; }""")
        assert r["shown"] and r["hit"], r                                           # visible, and it is what a finger meets there
        assert r["t"] >= r["barB"] and r["l"] >= 0 and r["r"] <= r["W"] and r["b"] <= r["H"], r
        browser.close()
    assert not errors, errors


@pytest.mark.parametrize("w,h", _PHONES)
def test_the_fold_button_hides_the_bar_and_the_page_keeps_it_with_the_sheet_open(w, h):
    html, errors = rs.render_dashboard(_edges(), basemap="blank").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = _open(browser, html, errors, viewport={"width": w, "height": h}, **_TOUCH)
        for sheet in (2, 1):                                                         # with the panel sheet full, and at 40 %
            page.evaluate(f"rs.sheet({sheet})")
            page.wait_for_timeout(300)
            page.locator(".rs-tb-fold button").tap()
            page.wait_for_timeout(300)
            b = _bar(page)
            assert b["bar"]["w"] < 70 and b["bar"]["h"] < 70, b                     # one small button, not a bar
            assert not page.evaluate("[...document.querySelectorAll('.rs-tb-scroll > *')].some(e => e.offsetParent)"), "the tools are hidden"
            grip = page.evaluate("(() => { const g = document.querySelector('.rs-grip-btn').getBoundingClientRect(); const e = document.elementFromPoint((g.left + g.right) / 2, (g.top + g.bottom) / 2); return !!(e && e.closest('.rs-grip-btn')); })()")
            assert grip, "the sheet's button is not under the bar"
            page.reload()
            page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
            assert _bar(page)["bar"]["w"] < 70, "the folded bar is kept"
            page.locator(".rs-tb-fold button").tap()                                 # show it again
            page.wait_for_timeout(300)
            assert _bar(page)["bar"]["h"] < 60 and _bar(page)["bar"]["w"] > w * 0.8
        browser.close()
    assert not errors, errors


@pytest.mark.parametrize("w,h", _PHONES)
def test_the_google_3d_header_is_one_row_on_a_phone(w, h):
    html, errors = rs.render_dashboard(_edges(), basemap="blank", google_3d=True).html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = _open(browser, html, errors, viewport={"width": w, "height": h}, **_TOUCH)
        r = page.evaluate("""() => { const win = document.querySelector('.rs-g3d'); win.hidden = false;
          const bar = win.querySelector('.rs-svw-bar'), kids = [...bar.children].filter(e => e.offsetParent), top = e => { const b = e.getBoundingClientRect(); return Math.round((b.top + b.bottom) / 2 / 6); };   // the centres: items of other heights share a row
          return {h: bar.getBoundingClientRect().height, tops: [...new Set(kids.map(top))], n: kids.length, credit: getComputedStyle(win.querySelector('.rs-g3d-src')).display}; }""")
        assert len(r["tops"]) == 1 and r["h"] < 46 and r["credit"] == "none", r      # one row; the credit is in the attribution box
        browser.close()
    assert not errors, errors


def test_a_tap_on_a_phone_shows_no_hover_tooltip_but_a_mouse_on_a_desktop_does():
    html, errors = rs.render_dashboard(_edges(), basemap="blank", road_tooltip=True, hover_delay_ms=100).html, []
    on_road = "(() => { const p = map.project([18.0005, 59.3005]); return [p.x, p.y]; })()"
    tip = "[...document.querySelectorAll('.rs-tip')].filter(e => e.offsetParent).length"
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = _open(browser, html, errors, viewport={"width": 390, "height": 844}, **_TOUCH)
        page.evaluate("rs.sheet(0)")
        page.wait_for_timeout(400)
        x, y = page.evaluate(on_road)
        page.touchscreen.tap(x, y)
        page.wait_for_timeout(900)
        assert page.evaluate(tip) == 0, "a tap on a phone is a click, not a hover"
        desk = _open(browser, html, errors, viewport={"width": 1280, "height": 800})
        x, y = desk.evaluate(on_road)
        desk.mouse.move(x - 3, y - 3)
        desk.mouse.move(x, y)
        desk.wait_for_timeout(900)
        assert desk.evaluate(tip) == 1, "a mouse on a desktop still shows the tooltip"
        browser.close()
    assert not errors, errors
