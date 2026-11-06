"""The chart part (dashboard/chart.js, docs/guides/dashboard-parts.md, "A chart"): each kind in both themes and at 390 px, with no mark outside its box; at
most 40 bars and a "more" line; a pie of 12 rows has 8 slices with "Other"; a histogram counts the numbers it gets (all the rows, not the table's); the
pointer on a mark shows its values and a click gives its row; a kind with no fitting columns shows a line in place of the chart. In the data dock: Table |
Chart, the first chart of a result, and Kind. Skipped without playwright."""
import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _ARGS, _edges  # noqa: E402
from test_data_dock_browser import served  # noqa: E402

import roadstyle as rs  # noqa: E402

_COLS = [{"name": "highway", "type": "VARCHAR"}, {"name": "km", "type": "DOUBLE"}, {"name": "edges", "type": "BIGINT"}, {"name": "day", "type": "DATE"}]
_ROWS = [["primary", 12.5, 40, "2026-06-01"], ["secondary", 8.25, 31, "2026-06-02"], ["tertiary", 6.0, 22, "2026-06-03"], ["residential", 30.5, 220, "2026-06-04"]]
_DRAW = """([kind, x, y, cols, rows, w]) => { const el = document.createElement('div'); el.id = 'c'; el.style.cssText = `width:${w}px;height:260px`;
  document.getElementById('sb').querySelector('.sb-body').prepend(el);
  window.picked = []; window.C = rs.chart(el, {kind, x, y, columns: cols, rows, onPick: i => picked.push(i)}); }"""
_INSIDE = """() => { const el = document.getElementById('c'), b = el.getBoundingClientRect(), s = el.querySelector('svg');
  const marks = s ? [...s.querySelectorAll('path, circle, polyline, rect')] : [];
  return {marks: marks.length, out: marks.filter(m => { const r = m.getBoundingClientRect(); return r.left < b.left - 1 || r.right > b.right + 1 || r.top < b.top - 1 || r.bottom > b.bottom + 1; }).length,
          none: (el.querySelector('.rs-chart-none') || {}).textContent || null, foot: (el.querySelector('.rs-chart-foot') || {}).textContent || ''}; }"""


def _page(p, tmp_path, phone=False):
    path = tmp_path / "chart.html"
    rs.render_dashboard(_edges(), basemap="blank").save(path)
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_page(viewport={"width": 390, "height": 844} if phone else {"width": 1280, "height": 800}, has_touch=phone, is_mobile=phone)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(path.resolve().as_uri())
    page.wait_for_function("window.map && map.loaded() && window.rsReady", timeout=60_000)
    if phone:
        page.evaluate("rs.sheet(2)")
    return browser, page, errors


@pytest.mark.parametrize("theme,phone", [("light", False), ("dark", False), ("light", True)])
def test_each_kind_draws_inside_its_box(tmp_path, theme, phone):
    with pw.sync_playwright() as p:
        browser, page, errors = _page(p, tmp_path, phone)
        try:
            page.evaluate(f"rsSetTheme('{theme}')")
            w = 340 if phone else 360
            for kind, x, y, marks in [("bar", "highway", "km", 4), ("bar", "highway", ["km", "edges"], 8), ("line", "day", "km", 5), ("histogram", "km", None, 4),
                                      ("scatter", "km", "edges", 4), ("pie", "highway", "edges", 4)]:
                page.evaluate("document.getElementById('c') && document.getElementById('c').remove()")
                page.evaluate(_DRAW, [kind, x, y, _COLS, _ROWS, w])
                page.wait_for_timeout(80)
                m = page.evaluate(_INSIDE)
                assert m["none"] is None and m["marks"] >= marks and m["out"] == 0, (kind, y, m)
            # two series and a pie have a legend; one series has none
            assert page.locator("#c .rs-chart-legend span").count() == 4
            page.evaluate("C.set({kind: 'bar', y: 'km'})")
            assert page.locator("#c .rs-chart-legend").count() == 0
        finally:
            browser.close()
    assert errors == [], errors


def test_limits_hover_click_and_the_line_for_no_data(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _page(p, tmp_path)
        try:
            many = [[f"Street {i}", (i * 37) % 101 + 1.0, i, "2026-06-01"] for i in range(55)]
            page.evaluate(_DRAW, ["bar", "highway", "km", _COLS, many, 600])
            m = page.evaluate(_INSIDE)
            assert m["marks"] == 40 and "15 more" in m["foot"], m
            page.evaluate("C.set({kind: 'pie', y: 'km', rows: " + json.dumps(many[:12]) + "})")
            assert page.locator("#c svg path").count() == 8 and "Other (5)" in page.inner_text("#c .rs-chart-legend")
            page.evaluate("C.set({kind: 'histogram', x: 'km', values: Array.from({length: 2765}, (_, i) => i % 97)})")
            assert "2 765 values" in page.inner_text("#c .rs-chart-foot")
            # the pointer on a bar shows its values; a click gives its row
            page.evaluate("C.set({kind: 'bar', x: 'highway', y: 'km', rows: " + json.dumps(_ROWS) + ", values: null})")
            bar = page.locator("#c svg path").nth(3)
            bar.hover()
            page.wait_for_timeout(100)
            assert "residential" in page.inner_text("#rs-hover") and "30.5" in page.inner_text("#rs-hover")
            bar.click()
            assert page.evaluate("window.picked") == [3]
            # a kind with no fitting columns: a clear line, no chart
            page.evaluate("C.set({kind: 'pie', y: 'highway'})")
            assert "number" in page.evaluate(_INSIDE)["none"]
            page.evaluate("C.set({kind: 'scatter', x: 'highway', y: 'km'})")
            assert "two number columns" in page.evaluate(_INSIDE)["none"]
        finally:
            browser.close()
    assert errors == [], errors


def test_the_data_dock_has_table_and_chart(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.wait_for_function("window.map && map.loaded() && window.rsReady && window.hostReady", timeout=60_000)
        page.evaluate("releaseLoad(); data.open()")
        page.evaluate("data.run('SELECT edge_id, length_m FROM big')")
        page.click("#rs-dock .rs-dd-view button:has-text('Chart')")
        page.wait_for_timeout(300)
        assert page.is_hidden("#rs-dock .rs-dock-table") and page.is_visible("#rs-dock .rs-dd-chart svg")
        # the first chart of a result with one number column is a histogram over all its 2765 rows (not the table's 1000)
        assert page.input_value("#rs-dock .rs-dd-chartrow select >> nth=0") == "histogram"
        assert "2 765 values" in page.inner_text("#rs-dock .rs-chart-foot")
        # a result of a text and a number: a bar chart in the open view
        page.evaluate("data.run('SELECT edge_id, name, highway FROM edges')")
        page.wait_for_timeout(300)
        # no measure (edge_id is an id): the rows for each value of the text column with the fewest values, highway
        assert page.evaluate("JSON.stringify(data.result().chart)") == '{"kind":"bar","x":"highway","y":"(count of rows)"}'
        assert page.locator("#rs-dock .rs-dd-chart svg path").count() == 3
        page.evaluate("data.run('SELECT edge_id, length_m FROM big')")
        page.select_option("#rs-dock .rs-dd-chartrow select >> nth=0", "scatter")
        assert "edge_id" not in page.evaluate("[...document.querySelectorAll('#rs-dock .rs-dd-chartrow select')[1].options].map(o => o.value)")   # no chart over road ids
        page.wait_for_timeout(300)
        assert page.locator("#rs-dock .rs-dd-chart svg circle").count() >= 6
        # data.chart(spec), as Ask's draw_chart: a spec that does not fit is an error
        assert page.evaluate("(() => { try { data.chart({kind: 'pie', x: 'nope', y: 'length_m'}); return 'no error'; } catch(e) { return e.message; } })()").startswith("The column")
        page.click("#rs-dock .rs-dd-view button:has-text('Table')")
        assert page.is_visible("#rs-dock .rs-dock-table")
        browser.close()
    assert errors == [], errors
