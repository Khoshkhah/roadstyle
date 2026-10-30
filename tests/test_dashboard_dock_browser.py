"""A dashboard with no panel (`dashboard={"panel": None}`) and Street View docked beside the map (`street_view="dock"`): no panel in the page, the bar at the map's
own edge, the window a side of the page with a divider that the person drags, and the map taking the rest. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _edges, _open  # noqa: E402

import roadstyle as rs  # noqa: E402


def _run(tmp_path, body, **kw):
    path = tmp_path / "d.html"
    rs.render_dashboard(_edges(), basemap="blank", **kw).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            body(page)
        finally:
            browser.close()
    assert [e for e in errors if "accelerometer" not in e] == []


def test_a_dashboard_without_a_panel_is_a_map_with_the_toolbox(tmp_path):
    def body(page):
        assert page.locator("#sb").count() == 0 and page.locator("#rs-toolbar").count() == 1
        assert page.evaluate("document.documentElement.classList.contains('rs-panel-left')") is False
        assert page.evaluate("document.getElementById('map').getBoundingClientRect().width") == 1280
        # the help of a page has no title to sit in: it is a tool of the bar
        page.evaluate("rs.help.set({title: 'How to read this page', terms: [['A', 'b']]})")
        assert "help" in page.evaluate("rs.tools.list().map(t => t.id)")
        page.click("#rs-toolbar button[title='How to read this page']")
        assert page.locator("#rs-help").is_visible()
    _run(tmp_path, body, dashboard={"panel": None})


def test_street_view_dock_shares_the_screen_with_a_divider(tmp_path):
    def body(page):
        assert page.locator("#sb").count() == 0
        assert page.evaluate("document.getElementById('rs-toolbar').dataset.edge") == "left"
        win = page.locator(".rs-svw-dock")
        assert win.is_visible()
        r = win.bounding_box()
        assert r["x"] + r["width"] == pytest.approx(1280, abs=1) and r["height"] == pytest.approx(800, abs=1)
        def mapw():
            return page.evaluate("document.getElementById('map').getBoundingClientRect().width")
        assert mapw() == pytest.approx(1280 - r["width"], abs=1)
        # the divider: dragging it to the left gives Street View more
        d = page.locator(".rs-svw-drag").bounding_box()
        page.mouse.move(d["x"] + 5, 400)
        page.mouse.down()
        page.mouse.move(500, 400, steps=6)
        page.mouse.up()
        r2 = win.bounding_box()
        assert r2["width"] > r["width"] + 100 and mapw() == pytest.approx(1280 - r2["width"], abs=1)
        # the window is still a side of the page while and after the drag: windows.js moves a window that is being dragged, and must not touch this one
        box = win.bounding_box()
        assert box["x"] + box["width"] == pytest.approx(1280, abs=1) and box["y"] == 0 and box["height"] == pytest.approx(800, abs=1)
        assert "left" not in (win.get_attribute("style") or "") and "top" not in (win.get_attribute("style") or "")
        page.mouse.move(d["x"] + 5, 400)
        page.mouse.down()
        page.mouse.move(520, 400, steps=3)
        mid = win.bounding_box()
        page.mouse.up()
        assert mid["y"] == 0 and mid["height"] == pytest.approx(800, abs=1) and "rs-drag " not in (win.get_attribute("class") or "") + " "
        # the share is kept, and bounded: at most 80 %
        page.mouse.move(500 + 5, 400)
        page.mouse.down()
        page.mouse.move(5, 400, steps=6)
        page.mouse.up()
        assert win.bounding_box()["width"] <= 0.8 * 1280 + 1
        # closed: the map has the whole page again, and the divider goes
        page.evaluate("rs.tools.close('street_view')")
        assert mapw() == 1280 and page.locator(".rs-svw-drag").is_hidden()
        page.evaluate("rs.tools.open('street_view')")
        assert win.is_visible() and mapw() < 1280
    _run(tmp_path, body, street_view="dock")


def test_the_window_mode_is_unchanged(tmp_path):
    def body(page):
        assert page.locator(".rs-svw-dock").count() == 0 and page.locator("#sb").count() == 1
        page.evaluate("rs.tools.open('street_view')")
        assert page.evaluate("document.getElementById('map').getBoundingClientRect().width") == 1280      # a floating window takes no room from the map
    _run(tmp_path, body)


def test_street_view_dock_is_the_only_new_value(tmp_path):
    with pytest.raises(Exception) as e:
        rs.render_dashboard(_edges(), basemap="blank", street_view="beside")
    assert "dock" in str(e.value)
