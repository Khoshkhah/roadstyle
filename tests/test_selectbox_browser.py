"""The select list of the dashboard (selectbox.js): a pointer over a row does not scroll the list, the keys do, the open list follows its button when the
panel scrolls, and it closes when the panel hides the button. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
# a section with a long select, after a tall block: the panel scrolls
_ADD = """() => rs.sections.add({id: 'long', label: 'Long', html: '<div style="height:1500px"></div><select id="longsel">'
    + Array.from({length: 40}, (_, i) => '<option>Row ' + i + '</option>').join('') + '</select><div style="height:1500px"></div>'})"""
_LIST = ".rs-sel-list"


def _edges():
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary"] * 3, "name": ["A", "B", "C"], "edge_id": [1, 2, 3]},
                            geometry=[LineString([(18.0 + i * 1e-3, 59.30), (18.0 + i * 1e-3, 59.31)]) for i in range(3)], crs=4326)


def _open(p, tmp_path):
    path = tmp_path / "s.html"
    rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}}).save(path)
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(path.resolve().as_uri())
    page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
    page.evaluate(_ADD)
    page.wait_for_selector("#longsel ~ .rs-sel-btn, .rs-sel:has(#longsel) .rs-sel-btn", state="attached")
    # bring the button into view, then open its list
    page.evaluate("document.querySelector('.rs-sel:has(#longsel) .rs-sel-btn').scrollIntoView({block: 'center'})")
    page.click(".rs-sel:has(#longsel) .rs-sel-btn")
    page.wait_for_selector(_LIST)
    return browser, page, errors


def test_a_pointer_over_a_row_does_not_scroll_the_list(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, tmp_path)
        box = page.evaluate("(() => { const r = document.querySelector('%s').getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.bottom - 3}; })()" % _LIST)
        page.mouse.move(box["x"], box["y"])             # the row that the list's lower edge cuts
        page.wait_for_timeout(200)
        got = page.evaluate("({top: document.querySelector('%s').scrollTop, on: document.querySelectorAll('%s .on').length})" % (_LIST, _LIST))
        browser.close()
    assert got == {"top": 0, "on": 1}
    assert not errors


def test_the_arrow_keys_scroll_the_list_to_the_marked_row(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, tmp_path)
        for _ in range(25):
            page.keyboard.press("ArrowDown")
        top = page.evaluate("document.querySelector('%s').scrollTop" % _LIST)
        browser.close()
    assert top > 0
    assert not errors


def test_the_open_list_follows_its_button_and_closes_when_the_panel_hides_it(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, tmp_path)
        scroller = """(() => { let e = document.querySelector('.rs-sel:has(#longsel) .rs-sel-btn'); while((e = e.parentElement))
            if(e.scrollHeight > e.clientHeight + 50 && /(auto|scroll)/.test(getComputedStyle(e).overflowY)) return e; })()"""
        def gap():
            return page.evaluate("document.querySelector('%s').getBoundingClientRect().top - document.querySelector('.rs-sel:has(#longsel) .rs-sel-btn').getBoundingClientRect().bottom" % _LIST)
        before = gap()
        page.evaluate("(%s).scrollTop += 20" % scroller)
        page.wait_for_timeout(100)
        after = gap()                                   # the list moved with the button
        # scroll the panel until the button is just above the panel's top edge: out of the panel, still inside the window
        page.evaluate("""(s) => { const b = document.querySelector('.rs-sel:has(#longsel) .rs-sel-btn'); s.scrollTop += b.getBoundingClientRect().bottom - s.getBoundingClientRect().top + 10; }""", page.evaluate_handle(scroller))
        page.wait_for_timeout(100)
        left = page.evaluate("document.querySelectorAll('%s').length" % _LIST)
        browser.close()
    assert abs(before - after) < 1
    assert left == 0
    assert not errors
