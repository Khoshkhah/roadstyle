"""The bottom dock (dashboard/dock.js, docs/guides/dashboard-layout.md, "The bottom dock"): a page with no content in the dock has none; a content
shows the dock closed (its title row); open, the map, the panel, the bar and the toolbox's boxes end above it, and the grip sets its height, kept in this
browser. Two contents are tabs. The dock's table: a 64-bit id is exact, a header click sorts, a row click selects the road, and a table of 5000 rows
draws only the rows in view. On a phone the dock is a bottom sheet, one sheet at a time. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _ARGS, _edges  # noqa: E402

import roadstyle as rs  # noqa: E402

_TABLE = """(n) => { window.T = rs.dock.table({idColumn: 'edge_id',
  columns: [{name: 'edge_id', type: 'BIGINT'}, {name: 'name', type: 'VARCHAR', about: 'The street name.'}, {name: 'length_m', type: 'DOUBLE'}],
  rows: Array.from({length: n}, (_, i) => [BigInt(i % 6 + 1), 'Street ' + (i % 6), (i * 37) % 101 + 0.5])});
  rs.dock.add({id: 'roads', label: 'Roads', el: T.el, note: n + ' rows'}); }"""
_BOX = "sel => { const r = document.querySelector(sel).getBoundingClientRect(); return [Math.round(r.top), Math.round(r.bottom), Math.round(r.left), Math.round(r.right)]; }"


def _page(p, tmp_path, phone=False, **kw):
    path = tmp_path / "dock.html"
    rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}}, **kw).save(path)
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_page(viewport={"width": 390, "height": 844} if phone else {"width": 1280, "height": 800}, has_touch=phone, is_mobile=phone)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(path.resolve().as_uri())
    page.wait_for_function("window.map && map.loaded() && window.rsReady", timeout=60_000)
    return browser, page, errors


@pytest.mark.parametrize("look", ["frame", "card"])
def test_the_dock_on_a_desktop(tmp_path, look):
    with pw.sync_playwright() as p:
        browser, page, errors = _page(p, tmp_path, dashboard={"panel": {"look": look}})
        try:
            assert page.locator("#rs-dock").count() == 0 or not page.locator("#rs-dock").is_visible()      # no content: no dock
            page.evaluate(_TABLE, 6)
            page.wait_for_timeout(200)
            assert page.evaluate(_BOX, "#rs-dock")[:2] == [768, 800]                                      # closed: the title row, 32 px
            assert page.locator("#rs-dock .rs-dock-table").is_hidden()
            page.evaluate("rs.dock.open()")
            page.wait_for_timeout(300)
            dock = page.evaluate(_BOX, "#rs-dock")
            assert dock == [500, 800, 0, 1280], dock                                                   # 300 px, edge to edge
            # the map ends at the dock (frame look) or goes on under it (card look); the panel and the bar end above it; the corner box hides
            m = page.evaluate(_BOX, "#map")
            assert m[1] == (500 if look == "frame" else 800), m
            assert page.evaluate(_BOX, "#sb")[1] <= 500 and page.evaluate(_BOX, "#rs-toolbar")[1] <= 500
            assert page.evaluate("getComputedStyle(document.getElementById('rs-scalebox')).display") == "none"
            # a box of the toolbox ends above the dock, and the camera fits above it
            page.evaluate("rs.tools.open('settings')")
            page.wait_for_timeout(300)
            assert page.evaluate(_BOX, "#rs-settings-box")[1] <= 500
            page.keyboard.press("Escape")
            assert page.evaluate("rsFreePad().bottom") >= (300 if look == "card" else 30)        # the card look: the map is under the dock
            # the table: a 64-bit id exactly, numbers at the right, the type under the name, the description in the tooltip
            assert page.evaluate("document.querySelector('#rs-dock th:nth-child(2)').title") == "The street name."
            assert page.evaluate("[...document.querySelectorAll('#rs-dock th small')].map(s => s.textContent)") == ["BIGINT", "VARCHAR", "DOUBLE"]
            assert page.evaluate("getComputedStyle(document.querySelector('#rs-dock td:nth-child(3)')).textAlign") == "right"
            # sort: rising, falling, the order of the rows again
            col = "() => [...document.querySelectorAll('#rs-dock tbody tr')].map(tr => tr.children[2].textContent)"
            first = page.evaluate(col)
            page.click("#rs-dock th:nth-child(3)")
            up = page.evaluate(col)
            assert up == sorted(first, key=float) and page.evaluate("document.querySelector('#rs-dock th:nth-child(3)').dataset.sort") == "asc"
            page.click("#rs-dock th:nth-child(3)")
            assert page.evaluate(col) == sorted(first, key=float, reverse=True)
            page.click("#rs-dock th:nth-child(3)")
            assert page.evaluate(col) == first
            # a row click selects its road
            page.click("#rs-dock tbody tr >> nth=2")
            page.wait_for_timeout(200)
            assert page.evaluate("rs.getState().selection") == "3" and page.locator("#rs-dock tbody tr.on").count() == 1
            # the grip: a drag sets the height, kept in this browser; a double click closes
            g = page.locator("#rs-dock .rs-dock-grip").bounding_box()
            page.mouse.move(g["x"] + 200, g["y"] + 4)
            page.mouse.down()
            page.mouse.move(g["x"] + 200, 350, steps=5)
            page.mouse.up()
            page.wait_for_timeout(200)
            assert abs(page.evaluate("rs.dock.height()") - 450) <= 2
            page.reload()
            page.wait_for_function("window.map && map.loaded() && window.rsReady", timeout=60_000)
            page.evaluate(_TABLE, 6)
            page.evaluate("rs.dock.open()")
            page.wait_for_timeout(200)
            assert abs(page.evaluate("rs.dock.height()") - 450) <= 2
            page.dblclick("#rs-dock .rs-dock-grip", position={"x": 200, "y": 4})
            assert page.evaluate("rs.dock.isOpen()") is False
            # two contents are tabs; remove() of the last one takes the dock away
            page.evaluate("() => { const e = document.createElement('p'); e.textContent = 'Changes'; rs.dock.add({id: 'changes', label: 'Changes', el: e}); rs.dock.open('changes'); }")
            assert page.evaluate("[...document.querySelectorAll('#rs-dock .rs-dock-tabs .rs-tab')].map(b => [b.textContent, b.classList.contains('on')])") \
                == [["Roads", False], ["Changes", True]]
            page.evaluate("rs.dock.remove('roads'); rs.dock.remove('changes')")
            assert page.evaluate("document.documentElement.classList.contains('rs-dock-has')") is False and page.evaluate(_BOX, "#map")[1] == 800
            with pytest.raises(Exception, match="used twice"):
                page.evaluate("() => { const e = document.createElement('p'); rs.dock.add({id: 'x', el: e}); rs.dock.add({id: 'x', el: e}); }")
        finally:
            browser.close()
    assert errors == [] or all("used twice" in e for e in errors), errors


def test_a_long_table_draws_only_the_rows_in_view_and_scrolls(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _page(p, tmp_path)
        try:
            page.evaluate(_TABLE, 5000)
            page.evaluate("rs.dock.open()")
            page.wait_for_timeout(300)
            assert page.evaluate("document.querySelectorAll('#rs-dock tbody tr:not(.rs-dock-pad)').length") < 200
            box = page.locator("#rs-dock .rs-dock-table")
            b = box.bounding_box()
            page.mouse.move(b["x"] + 60, b["y"] + 100)
            for _ in range(10):
                page.mouse.wheel(0, 800)
            page.wait_for_timeout(300)
            s = page.evaluate("(() => { const e = document.querySelector('#rs-dock .rs-dock-table'), th = e.querySelector('th').getBoundingClientRect(); "
                              "return {top: e.scrollTop, head: Math.round(th.top - e.getBoundingClientRect().top), rows: e.querySelectorAll('tbody tr:not(.rs-dock-pad)').length, "
                              "end: e.getBoundingClientRect().bottom <= document.getElementById('rs-dock').getBoundingClientRect().bottom}; })()")
            assert s["top"] > 5000 and s["head"] <= 1 and s["rows"] < 200 and s["end"], s      # it scrolls, the header row stays, the box ends in the dock
            assert page.evaluate("getComputedStyle(document.querySelector('#rs-dock .rs-dock-table')).scrollbarColor").startswith("rgba(0, 0, 0, 0)") is False
        finally:
            browser.close()
    assert errors == []


def test_the_dock_on_a_phone_is_a_sheet_one_at_a_time(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _page(p, tmp_path, phone=True)
        try:
            page.evaluate("rs.sheet(1)")
            page.evaluate(_TABLE, 6)
            page.wait_for_timeout(200)
            assert page.locator("#rs-dock-pill").is_visible() and page.locator("#rs-dock").is_hidden()      # closed: a round button
            assert "Roads" in page.inner_text("#rs-dock-pill")
            page.click("#rs-dock-pill")
            page.wait_for_timeout(300)
            assert page.evaluate("rs.sheet()") == 0 and page.locator("#rs-dock").is_visible()               # one sheet at a time
            d = page.evaluate(_BOX, "#rs-dock")
            assert d[1] == 844 and 300 <= d[1] - d[0] <= 360 and d[2] == 0 and d[3] == 390, d                # 40 %, the whole width
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
            page.tap("#rs-dock .rs-dock-grip")                                                              # a tap: the full height
            page.wait_for_timeout(200)
            assert page.evaluate(_BOX, "#rs-dock")[0] < 120
            page.evaluate("rs.sheet(1)")                                                                     # the panel's sheet opens: the dock closes
            page.wait_for_timeout(200)
            assert page.evaluate("rs.dock.isOpen()") is False and page.locator("#rs-dock-pill").is_visible()
        finally:
            browser.close()
    assert errors == []


def test_a_box_that_keep_inside_makes_shorter_scrolls_to_its_end(tmp_path):
    """keepInside cleared maxHeight at each fit, and each scroll (the class rs-scrolling) ran a fit: a box that it made shorter went back to its top at
    each turn of the wheel (Kaveh: "scroll bug! I can't scroll it"). Now the box keeps its scroll, with or without a dock."""
    path = tmp_path / "short.html"
    rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}}).save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1200, "height": 420})
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded() && window.rsReady", timeout=60_000)
        page.evaluate("rs.tools.open('settings')")
        page.wait_for_timeout(300)
        box = page.locator("#rs-settings-box")
        assert page.evaluate("(() => { const e = document.getElementById('rs-settings-box'); return e.scrollHeight > e.clientHeight + 20; })()")
        b = box.bounding_box()
        page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)
        for _ in range(6):
            page.mouse.wheel(0, 300)
            page.wait_for_timeout(120)
        page.wait_for_timeout(1000)                      # after the class rs-scrolling goes
        assert page.evaluate("(() => { const e = document.getElementById('rs-settings-box'); return e.scrollTop + e.clientHeight >= e.scrollHeight - 2; })()")
        browser.close()
