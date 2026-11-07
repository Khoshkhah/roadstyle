"""The chart card (`part: "chart"`, docs/guides/dashboard-parts.md, "A chart"): each kind in the panel from Python, in both themes and at 390 px, with no mark outside its
card; the roads by class equal a count of the road table; `follow` draws again after a filter of the roads; a click on a bar lights its roads (the
highlight set "chart") and a second click ends the light; with `data`, a click sends rs:chartpick. Skipped without playwright."""
import pandas as pd
import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _ARGS  # noqa: E402

import roadstyle as rs  # noqa: E402

_CLASSES = ["primary"] * 4 + ["secondary"] * 7 + ["residential"] * 12 + ["footway"] * 2
_COUNTS = pd.DataFrame({"hour": list(range(24)), "vehicles": [abs(12 - h) * 40 + 100 for h in range(24)]})
_CARDS = [
    {"id": "pie", "label": "Roads by class", "part": "chart", "chart": {"kind": "pie", "x": "highway"}},
    {"id": "bar", "label": "km by class", "part": "chart", "chart": {"kind": "bar", "x": "highway", "y": "length_m", "scale": 0.001, "follow": True}},
    {"id": "line", "label": "Vehicles per hour", "part": "chart", "chart": {"kind": "line", "x": "hour", "y": "vehicles", "data": _COUNTS}},
    {"id": "hist", "label": "Lengths", "part": "chart", "chart": {"kind": "histogram", "x": "length_m"}},
    {"id": "scatter", "label": "Lanes and length", "part": "chart", "chart": {"kind": "scatter", "x": "length_m", "y": "lanes"}},
    {"id": "names", "label": "Busy streets", "part": "chart", "chart": {"kind": "bar", "x": "street", "y": "cars", "height": 160,
                                                                         "data": [{"street": "Boulevard Albert 1er", "cars": 900}, {"street": "Avenue de la Costa", "cars": 650}]}},
]
_INSIDE = """() => [...document.querySelectorAll('.rs-chart-card')].map(el => { const b = el.closest('.sb-sec').getBoundingClientRect();
  const marks = [...el.querySelectorAll('svg .rs-mk, svg polyline')];
  return {id: el.closest('.sb-sec').dataset.rsSection, marks: marks.length, none: (el.querySelector('.rs-chart-none') || {}).textContent || null,
          title: (el.querySelector('.rs-chart-hd b') || {}).textContent || null, count: (el.querySelector('.rs-chart-hd span') || {}).textContent,
          out: marks.filter(m => { const r = m.getBoundingClientRect(); return r.left < b.left - 1 || r.right > b.right + 1; }).length}; })"""


def _edges():
    import geopandas as gpd
    from shapely.geometry import LineString
    n = len(_CLASSES)
    return gpd.GeoDataFrame({"highway": _CLASSES, "name": [f"Street {i}" for i in range(n)], "edge_id": list(range(1, n + 1)),
                             "length_m": [40.0 + 13 * i for i in range(n)], "lanes": [1 + i % 3 for i in range(n)]},
                            geometry=[LineString([(7.42 + i * 4e-4, 43.73), (7.42 + i * 4e-4, 43.731)]) for i in range(n)], crs=4326)


def _open(p, tmp_path, cards=_CARDS, phone=False):
    path = tmp_path / "charts.html"
    rs.render_dashboard(_edges(), basemap="blank", dashboard={"panel": {"sections": cards}}).save(path)
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_page(viewport={"width": 390, "height": 844} if phone else {"width": 1280, "height": 1000}, has_touch=phone, is_mobile=phone)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.goto(path.resolve().as_uri())
    page.wait_for_function("window.map && map.loaded() && window.rsReady", timeout=60_000)
    if phone:
        page.evaluate("rs.sheet(2)")
    page.wait_for_timeout(300)
    return browser, page, errors


@pytest.mark.parametrize("theme,phone", [("light", False), ("dark", False), ("light", True)])
def test_each_kind_is_a_card_of_the_panel(tmp_path, theme, phone):
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, tmp_path, phone=phone)
        try:
            page.evaluate(f"rsSetTheme('{theme}')")
            page.wait_for_timeout(200)
            got = {c["id"]: c for c in page.evaluate(_INSIDE)}
            assert list(got) == [c["id"] for c in _CARDS]
            for c in got.values():
                assert c["none"] is None and c["marks"] > 0 and c["out"] == 0, c
                assert c["title"] is None, c                         # the card's label is the title: no second title
            assert got["pie"]["marks"] == 4 and got["pie"]["count"] == "25 roads" and got["line"]["count"] == "24 rows"
            assert got["names"]["marks"] == 2
        finally:
            browser.close()
    assert errors == [], errors


def test_the_roads_by_class_follow_the_filter_and_a_click_lights_them(tmp_path):
    cards = [{"id": "n", "label": "Roads by class", "part": "chart", "chart": {"kind": "bar", "x": "highway", "follow": True}}]
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, tmp_path, cards)
        try:
            # the bars equal a count of the road table, the largest first
            want = page.evaluate("""() => { const n = {}; rsGetProps(rsQuery(() => true)).forEach(p => n[p.highway] = (n[p.highway] || 0) + 1);
              return Object.entries(n).sort((a, b) => b[1] - a[1]); }""")
            assert want == [["residential", 12], ["secondary", 7], ["primary", 4], ["footway", 2]]
            labels = page.evaluate("[...document.querySelectorAll('.rs-chart-card svg text')].map(t => t.textContent)")
            assert [x for x in labels if x in {"12", "7", "4", "2"}] == ["12", "7", "4", "2"], labels
            assert page.locator(".rs-chart-card svg .rs-mk").count() == 4
            # a click on the first bar lights its 12 roads in the set "chart"; a second click ends the light
            page.evaluate("window.hl = []; document.addEventListener('rs:highlightchange', e => hl.push(e.detail))")
            page.locator(".rs-chart-card svg .rs-mk").first.click()
            page.wait_for_timeout(100)
            first = page.evaluate("hl[hl.length - 1]")
            assert first["set"] == "chart" and len(first["ids"]) == 12
            assert all(p["highway"] == "residential" for p in page.evaluate(f"rsGetProps({first['ids']})"))
            page.locator(".rs-chart-card svg .rs-mk").first.click()
            page.wait_for_timeout(100)
            assert page.evaluate("hl[hl.length - 1]") == {"set": "chart", "ids": []}
            # follow: the roads that the map shows now
            page.evaluate("rsSetClasses(['primary', 'footway'])")
            page.wait_for_timeout(150)
            assert page.locator(".rs-chart-card svg .rs-mk").count() == 2
            assert page.inner_text(".rs-chart-card .rs-chart-hd") == "6 roads"
            page.evaluate("rsSetClasses(RS_CLASSES)")
            page.wait_for_timeout(150)
            assert page.locator(".rs-chart-card svg .rs-mk").count() == 4
        finally:
            browser.close()
    assert errors == [], errors


def test_a_click_on_the_pages_own_rows_sends_chartpick_and_many_numbers_go_in_ranges(tmp_path):
    many = pd.DataFrame({"speed": [float(i) for i in range(100)], "n": [1] * 100})
    cards = [{"id": "own", "label": "Busy streets", "part": "chart", "chart": {"kind": "bar", "x": "street", "y": "cars", "agg": "mean",
                                                                                  "data": [{"street": "A", "cars": 10}, {"street": "B", "cars": 30}, {"street": "A", "cars": 20}]}},
             {"id": "ranges", "label": "Speeds", "part": "chart", "chart": {"kind": "pie", "x": "speed", "y": "n", "data": many}}]
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, tmp_path, cards)
        try:
            page.evaluate("window.picks = []; document.addEventListener('rs:chartpick', e => picks.push(e.detail))")
            page.locator('[data-rs-section="own"] svg .rs-mk').first.click()
            page.wait_for_timeout(100)
            # A has two rows: their mean, and the indices of the two rows
            assert page.evaluate("picks") == [{"id": "own", "row": {"street": "A", "cars": 15}, "rows": [0, 2]}]
            legend = page.inner_text('[data-rs-section="ranges"] .rs-chart-legend')
            assert "–" in legend and page.locator('[data-rs-section="ranges"] svg .rs-mk').count() <= 6, legend
        finally:
            browser.close()
    assert errors == [], errors


def test_rs_sections_add_makes_a_chart_card_from_javascript(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, tmp_path, [])
        try:
            page.evaluate("""rs.sections.add({id: 'js', label: 'From JavaScript', part: 'chart',
                             chart: {kind: 'line', x: 'day', y: 'n', data: [{day: '2026-06-01', n: 3}, {day: '2026-06-02', n: 5}]}})""")
            page.wait_for_timeout(100)
            assert page.locator('[data-rs-section="js"] svg polyline').count() == 1
            err = page.evaluate("() => { try { rs.sections.add({id: 'bad', part: 'chart', chart: {kind: 'donut', x: 'a'}}); } catch(e){ return e.message; } }")
            assert "chart.kind is one of" in err
        finally:
            browser.close()
    assert errors == [], errors
