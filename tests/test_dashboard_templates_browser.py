"""The phone form of each layout of the dashboard template (docs/design/dashboard_templates.md, section 5): a phone of 390 x 844 px with touch.

Each test saves a page, opens it in headless Chromium and reads the DOM. Skipped when playwright is not installed.
"""
import pytest

pw = pytest.importorskip("playwright.sync_api")

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
PHONE = {"viewport": {"width": 390, "height": 844}, "has_touch": True, "is_mobile": True}


def _edges(n=12):
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame(
        {"highway": ["primary"] * n, "name": [f"Street {i}" for i in range(n)], "edge_id": list(range(1, n + 1))},
        geometry=[LineString([(18.0 + i * 1e-3, 59.30), (18.0 + i * 1e-3, 59.31)]) for i in range(n)], crs=4326)


def _open(p, tmp_path, template, **ctx):
    import roadstyle as rs
    path = tmp_path / f"{template}.html"
    kw = {"dock": {"layout": "dock"}}.get(template, {})                    # the two layouts of the one template
    rs.render_dashboard(_edges(), basemap="blank", **kw).save(path)
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_context(**ctx).new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(path.resolve().as_uri())
    page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
    return browser, page, errors


def _box(page, sel):
    return page.evaluate("s=>{const r=document.querySelector(s).getBoundingClientRect();return {t:r.top,b:r.bottom,l:r.left,r:r.right,w:r.width,h:r.height}}", sel)


@pytest.mark.parametrize("template", ["dashboard", "dock"])
def test_a_phone_has_no_horizontal_scroll(tmp_path, template):
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, tmp_path, template, **PHONE)
        wide = page.evaluate("document.documentElement.scrollWidth > innerWidth")
        phone = page.evaluate("document.documentElement.classList.contains('rs-phone')")
        map_box = _box(page, "#map")
        browser.close()
    assert phone and not wide and not errors and map_box["w"] == 390


@pytest.mark.parametrize("template", ["dashboard", "dock"])
def test_the_sidebar_is_a_sheet_of_three_heights(tmp_path, template):
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, tmp_path, template, **PHONE)
        heights = {}
        for state in (2, 0, 1):                            # from 40 %, a tap of the grip goes to full, then closed, then 40 % again
            page.touchscreen.tap(195, _box(page, ".rs-grip")["t"] + 14)
            page.wait_for_timeout(300)
            hidden = page.evaluate("getComputedStyle(document.getElementById('sb')).display") == "none"
            heights[state] = 0 if hidden else _box(page, "#sb")
        browser.close()
    assert not errors
    assert heights[2]["t"] >= 52 and heights[2]["b"] == 844                  # full: the bar's 52 px stay free
    assert heights[0] == 0                                                   # closed
    assert abs(heights[1]["h"] - 0.4 * 844) < 2                              # 40 % again: the map has 60 %


def test_the_sheet_starts_at_40_percent_and_the_map_stays_full(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, _ = _open(p, tmp_path, "dashboard", **PHONE)
        sb, grip, mp = _box(page, "#sb"), _box(page, ".rs-grip"), _box(page, "#map")
        browser.close()
    assert abs(sb["h"] - 0.4 * 844) < 2 and sb["b"] == 844 and grip["b"] <= sb["t"] + 1
    assert mp["h"] == 844 and mp["w"] == 390                                 # the sheet floats over the map


def test_a_desktop_keeps_the_docked_sidebar(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, _ = _open(p, tmp_path, "dock", viewport={"width": 1280, "height": 800})
        phone = page.evaluate("document.documentElement.classList.contains('rs-phone')")
        sb, mp = _box(page, "#sb"), _box(page, "#map")
        browser.close()
    assert not phone and sb["w"] == 340 and mp["w"] == 1280 - 340


def test_a_held_toolbar_shows_when_the_page_has_added_its_tools(tmp_path):
    """toolbar.hold: no bar at the load; rs.tools.ready() shows it."""
    import roadstyle as rs
    path = tmp_path / "hold.html"
    rs.render_dashboard(_edges(), basemap="blank", dashboard={"toolbar": {"hold": True}}).save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page()
        page.add_init_script("const st = window.setTimeout; window.setTimeout = (f, t, ...a) => t === 6000 ? 0 : st(f, t, ...a)")    # the 6 s limit does not run
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        vis = lambda: page.evaluate("getComputedStyle(document.getElementById('rs-toolbar')).visibility")   # noqa: E731
        before = vis()
        page.evaluate("rs.tools.add({id: 'mine', title: 'Mine'}); rs.tools.ready()")
        after = vis()
        browser.close()
    assert (before, after) == ("hidden", "visible")


@pytest.mark.parametrize("look", ["card", "frame"])
@pytest.mark.parametrize("bar", ["right", "left"])
def test_a_left_panel_keeps_the_bar_beside_it_and_the_show_marker_at_the_left(tmp_path, bar, look):
    """panel.side "left": the bar is in the window (at the right edge, or beside the panel when it is at the left too), and the marker that brings
    the closed panel back is at the left."""
    import roadstyle as rs
    path = tmp_path / "left.html"
    rs.render_dashboard(_edges(), basemap="blank", dashboard={"panel": {"side": "left", "look": look}, "toolbar": {"position": bar}}).save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        page.wait_for_timeout(500)
        sb, tb, card = _box(page, "#sb"), _box(page, "#rs-toolbar"), _box(page, "#sb .sb-card")
        page.click("#sb-hide")
        page.wait_for_timeout(500)
        show, tb2 = _box(page, "#sb-show"), _box(page, "#rs-toolbar")
        browser.close()
    assert sb["l"] < 20 and 0 <= tb["l"] and tb["r"] <= 1280                    # the panel is at the left, the bar is in the window
    assert abs(tb["l"] - card["r"]) <= 1.01 if bar == "left" else tb["r"] > 1200      # at the left: on the card's edge (no gap, 1 px overlap); at the right: at the edge
    assert show["l"] < 100 and tb2["l"] >= 0 and tb2["r"] <= 1280              # the marker at the left; the bar is still in the window


def test_changing_the_layout_closes_the_open_settings_box(tmp_path):
    """The settings box opens toward the map from the bar's edge: a choice in it that moves the bar or the panel closes it first."""
    pick = """([row, name]) => { const r = [...document.querySelectorAll('.rs-set-row')].find(r => r.querySelector('.rs-set-l').textContent === row);
        [...r.querySelectorAll('button')].find(b => b.textContent.trim() === name).click(); }"""
    is_open = "rs.tools.list().find(t => t.id === 'settings').open"
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, tmp_path, "dashboard", viewport={"width": 1280, "height": 800})
        got = []
        for row, name in [("Toolbar", "Left"), ("Panel", "Left"), ("Panel", "Right")]:
            page.evaluate("rs.tools.open('settings')")
            was = page.evaluate(is_open)
            page.evaluate(pick, [row, name])
            got.append((was, page.evaluate(is_open)))
        edge = page.evaluate("document.getElementById('rs-toolbar').dataset.edge")
        browser.close()
    assert not errors and got == [(True, False)] * 3 and edge == "left"


def test_the_typed_panel_options_work_without_the_settings_button(tmp_path):
    """panel.width_px, panel.side and panel.look are read at the start, also in the dock layout (no toolbar, so no settings button), and a saved choice of
    an earlier visit does not override a page that has no settings button."""
    import roadstyle as rs
    path = tmp_path / "typed.html"
    rs.render_dashboard(_edges(), basemap="blank", layout="dock", dashboard={"panel": {"side": "left", "width_px": 420}}).save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.add_init_script("localStorage.setItem('rs-settings:layout', JSON.stringify({panel: 'right'}))")      # an old choice
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        page.wait_for_timeout(300)
        sb, mp = _box(page, "#sb"), _box(page, "#map")
        left = page.evaluate("document.documentElement.classList.contains('rs-panel-left')")
        browser.close()
    assert left and sb["w"] == 420 and sb["l"] == 0 and mp["l"] == 420 and mp["w"] == 1280 - 420


def test_a_wider_panel_in_the_overlay_layout(tmp_path):
    import roadstyle as rs
    path = tmp_path / "wide.html"
    rs.render_dashboard(_edges(), basemap="blank", dashboard={"panel": {"width_px": 420}}).save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        page.wait_for_timeout(300)
        sb, card, bar = _box(page, "#sb"), _box(page, "#sb .sb-card"), _box(page, "#rs-toolbar")
        browser.close()
    assert sb["w"] == 420 and abs(bar["r"] - card["l"]) <= 1.01
