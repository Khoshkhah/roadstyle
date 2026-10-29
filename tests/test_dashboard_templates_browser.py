"""The phone form of each dashboard template (docs/design/dashboard_templates.md, section 5): a phone of 390 x 844 px with touch.

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
    (rs.render_report if template == "report" else rs.render_dashboard)(_edges(), basemap="blank",
                                                                         **({} if template == "report" else {"template": template})).save(path)
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_context(**ctx).new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(path.resolve().as_uri())
    page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
    return browser, page, errors


def _box(page, sel):
    return page.evaluate("s=>{const r=document.querySelector(s).getBoundingClientRect();return {t:r.top,b:r.bottom,l:r.left,r:r.right,w:r.width,h:r.height}}", sel)


@pytest.mark.parametrize("template", ["dashboard", "classic", "report"])
def test_a_phone_has_no_horizontal_scroll(tmp_path, template):
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, tmp_path, template, **PHONE)
        wide = page.evaluate("document.documentElement.scrollWidth > innerWidth")
        phone = page.evaluate("document.documentElement.classList.contains('rs-phone')")
        map_box = _box(page, "#map")
        browser.close()
    assert phone and not wide and not errors and map_box["w"] == 390


@pytest.mark.parametrize("template", ["dashboard", "classic"])
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


def test_the_report_goes_under_the_map(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, _ = _open(p, tmp_path, "report", **PHONE)
        rp, mp = _box(page, "#rp"), _box(page, "#map")
        browser.close()
    assert abs(mp["h"] - 0.55 * 844) < 2 and abs(rp["t"] - mp["b"]) < 2 and rp["b"] == 844 and rp["w"] == 390


def test_a_desktop_keeps_the_docked_sidebar(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, _ = _open(p, tmp_path, "classic", viewport={"width": 1280, "height": 800})
        phone = page.evaluate("document.documentElement.classList.contains('rs-phone')")
        sb, mp = _box(page, "#sb"), _box(page, "#map")
        browser.close()
    assert not phone and sb["w"] == 340 and mp["w"] == 1280 - 340
