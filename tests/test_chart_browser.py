"""The chart part (dashboard/chart.js, docs/guides/dashboard-parts.md, "A chart"): each kind in both themes and at 390 px, with no mark outside its box; at
most 40 bars and a "more" line; a pie of 12 rows has 8 slices with "Other"; a histogram counts the numbers it gets (all the rows, not the table's); the
pointer on a mark shows its values and a click gives its row; a kind with no fitting columns shows a line in place of the chart. The chart fits its box:
the bars get thinner, and only past their minimum the box scrolls; a pie is the largest circle beside or above its legend; the axis titles of a scatter
are outside the plot; a line has value labels only when all of them fit. In the data dock: Table | Chart, the first chart of a result, and Kind; the
Chart view takes the width of an empty side column. Skipped without playwright."""
import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _ARGS, _edges  # noqa: E402
from test_data_dock_browser import served  # noqa: E402

import roadstyle as rs  # noqa: E402

_COLS = [{"name": "highway", "type": "VARCHAR"}, {"name": "km", "type": "DOUBLE"}, {"name": "edges", "type": "BIGINT"}, {"name": "day", "type": "DATE"}]
_ROWS = [["primary", 12.5, 40, "2026-06-01"], ["secondary", 8.25, 31, "2026-06-02"], ["tertiary", 6.0, 22, "2026-06-03"], ["residential", 30.5, 220, "2026-06-04"]]
_DRAW = """([kind, x, y, cols, rows, w, h = 260]) => { const el = document.createElement('div'); el.id = 'c'; el.style.cssText = `width:${w}px;height:${h}px`;
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
            assert page.locator("#c svg path").count() == 6 and "Other (7)" in page.inner_text("#c .rs-chart-legend")
            page.evaluate("C.set({kind: 'histogram', x: 'km', values: Array.from({length: 2765}, (_, i) => i % 97)})")
            page.evaluate("C.set({values: Array.from({length: 50}, (_, i) => i * 1.8e17)})")
            ticks = page.evaluate("[...document.querySelectorAll('#c svg text')].map(x => x.textContent).join(' ')")
            assert "2e18" in ticks and "000000" not in ticks, ticks                                        # a huge number: a short tick
            page.evaluate("C.set({values: Array.from({length: 2765}, (_, i) => i % 97)})")
            assert "2 765 values" in page.inner_text("#c .rs-chart-hd")
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


_STREETS = [{"name": "name", "type": "VARCHAR"}, {"name": "length_m", "type": "DOUBLE"}, {"name": "maxspeed_kmh", "type": "DOUBLE"}]
_LONG = [[f"Street number {i}", 40.0 + (i * 37) % 300, 30.0 + (i * 13) % 60] for i in range(40)]
# the bars of the chart, and which of them are not in the visible part of its box
_BARS = """() => { const el = document.getElementById('c'), b = el.getBoundingClientRect(), bars = [...el.querySelectorAll('svg path.rs-mk')];
  return {bars: bars.length, cut: bars.filter(m => { const r = m.getBoundingClientRect(); return r.top < b.top - 1 || r.bottom > b.bottom + 1; }).length,
          scrolls: el.scrollHeight > el.clientHeight + 1, more: el.hasAttribute('data-more'), overflow: getComputedStyle(el).overflowY,
          bar: [getComputedStyle(el).scrollbarWidth, getComputedStyle(el).scrollbarColor]}; }"""


@pytest.mark.parametrize("phone", [False, True])
def test_the_bars_fit_the_box_and_scroll_only_past_their_minimum(tmp_path, phone):
    """Reviewer: "Bar, two series" with 8 rows showed 4 groups; a bar chart of 15 rows on a phone showed 3 bars."""
    with pw.sync_playwright() as p:
        browser, page, errors = _page(p, tmp_path, phone)
        try:
            w = 340 if phone else 600
            for y, n, h in [(["length_m", "maxspeed_kmh"], 8, 220), ("length_m", 15, 260)]:
                page.evaluate("document.getElementById('c') && document.getElementById('c').remove()")
                page.evaluate(_DRAW, ["bar", "name", y, _STREETS, _LONG[:n], w, h])
                page.wait_for_timeout(80)
                m = page.evaluate(_BARS)
                assert m["bars"] == n * (len(y) if isinstance(y, list) else 1) and m["cut"] == 0 and not m["scrolls"], (y, n, m)
            # 40 bars do not fit at their minimum: the box scrolls (a phone: a fade at the bottom), and it scrolls to each bar. The scrollbar is thin and
            # has a colour (the headless browser hides every scrollbar, so the test reads the style)
            page.evaluate("C.set({rows: " + json.dumps(_LONG) + "})")
            page.wait_for_timeout(80)
            m = page.evaluate(_BARS)
            assert m["scrolls"] and m["cut"] > 0 and m["overflow"] == "auto" and m["more"], m
            assert m["bar"][0] == "thin" and not m["bar"][1].startswith(("auto", "rgba(0, 0, 0, 0)")), m
            reach = page.evaluate("""() => { const el = document.getElementById('c'), b = el.getBoundingClientRect();
              return [...el.querySelectorAll('svg path.rs-mk')].filter(m => { m.scrollIntoView({block: 'nearest'}); const r = m.getBoundingClientRect(), b = el.getBoundingClientRect();
                return r.top >= b.top - 1 && r.bottom <= b.bottom + 1; }).length; }""")
            assert reach == 40, reach
        finally:
            browser.close()
    assert errors == [], errors


@pytest.mark.parametrize("w,h", [(900, 200), (340, 340)])
def test_a_pie_takes_the_room_it_has(tmp_path, w, h):
    """Reviewer: a pie of about 90 px in a large chart area. The free area is the box without the title line; the pie and its legend share it."""
    with pw.sync_playwright() as p:
        browser, page, errors = _page(p, tmp_path)
        try:
            page.evaluate(_DRAW, ["pie", "name", "length_m", _STREETS, _LONG[:6], w, h])
            page.wait_for_timeout(80)
            m = page.evaluate("""() => { const el = document.getElementById('c'), b = el.getBoundingClientRect(), hd = el.querySelector('.rs-chart-hd').getBoundingClientRect();
              const ps = [...el.querySelectorAll('svg path')].map(p => p.getBoundingClientRect()), lg = el.querySelector('.rs-chart-legend').getBoundingClientRect();
              const l = Math.min(...ps.map(r => r.left)), r = Math.max(...ps.map(r => r.right)), t = Math.min(...ps.map(r => r.top)), bt = Math.max(...ps.map(r => r.bottom));
              return {d: Math.min(r - l, bt - t), free: Math.min(b.width, b.bottom - hd.bottom), inside: t >= b.top && bt <= b.bottom && l >= b.left && r <= b.right,
                      apart: r <= lg.left || bt <= lg.top || t >= lg.bottom || l >= lg.right, scrolls: el.scrollHeight > el.clientHeight + 1}; }""")
            assert m["d"] >= 0.7 * m["free"] and m["inside"] and m["apart"] and not m["scrolls"], m
        finally:
            browser.close()
    assert errors == [], errors



def test_a_small_pie_keeps_its_legend(tmp_path):
    """Kaveh: "legend is not there" (the pie in Ask's card, a small copy). A small copy has no labels, but a pie keeps its legend: the pie at
    the left at its full height, the legend at its right ("just need to shift left and add legend there"). The other small kinds still have no legend."""
    with pw.sync_playwright() as p:
        browser, page, errors = _page(p, tmp_path)
        try:
            page.evaluate(_DRAW, ["pie", "name", "length_m", _STREETS, _LONG[:6], 320, 140])
            page.evaluate("C.set({small: true})")
            page.wait_for_timeout(80)
            m = page.evaluate("""() => { const el = document.getElementById('c'), b = el.getBoundingClientRect(), lg = el.querySelector('.rs-chart-legend');
              const ps = [...el.querySelectorAll('svg path')].map(p => p.getBoundingClientRect()), g = lg && lg.getBoundingClientRect();
              const l = Math.min(...ps.map(r => r.left)), r = Math.max(...ps.map(r => r.right)), t = Math.min(...ps.map(r => r.top)), bt = Math.max(...ps.map(r => r.bottom));
              return {names: lg ? lg.children.length : 0, d: Math.min(r - l, bt - t), left: l - b.left, legendIn: !!g && g.top >= b.top - 1 && g.bottom <= b.bottom + 1 && g.right <= b.right + 1,
                      apart: !!g && (r <= g.left || bt <= g.top), title: !!el.querySelector('.rs-chart-hd')}; }""")
            assert m["names"] == 6 and m["legendIn"] and m["apart"] and not m["title"], m
            assert m["d"] >= 120 and m["left"] <= 24, m                         # the full height of the box (140 px), at its left (its padding and 6 px)
            page.evaluate("C.set({kind: 'bar'})")
            assert page.evaluate("!document.querySelector('#c .rs-chart-legend')")
        finally:
            browser.close()
    assert errors == [], errors

@pytest.mark.parametrize("theme,phone", [("light", False), ("dark", True)])
def test_the_axis_titles_of_a_scatter_are_outside_the_plot(tmp_path, theme, phone):
    """Reviewer: "maxspeed_kmh" at the top left and "length_m" at the bottom right lay on the tick numbers and the grid."""
    with pw.sync_playwright() as p:
        browser, page, errors = _page(p, tmp_path, phone)
        try:
            page.evaluate(f"rsSetTheme('{theme}')")
            page.evaluate(_DRAW, ["scatter", "length_m", "maxspeed_kmh", _STREETS, _LONG[:15], 340 if phone else 600, 300])
            page.wait_for_timeout(80)
            m = page.evaluate("""() => { const s = document.querySelector('#c svg'), box = e => e.getBoundingClientRect(), texts = [...s.querySelectorAll('text')];
              const titles = texts.filter(t => ['length_m', 'maxspeed_kmh'].includes(t.textContent)), ticks = texts.filter(t => !titles.includes(t)), grid = [...s.querySelectorAll('line')].map(box);
              const plot = {left: Math.min(...grid.map(r => r.left)), right: Math.max(...grid.map(r => r.right)), top: Math.min(...grid.map(r => r.top)), bottom: Math.max(...grid.map(r => r.bottom))};
              const hit = (a, b) => a.left < b.right - 0.5 && b.left < a.right - 0.5 && a.top < b.bottom - 0.5 && b.top < a.bottom - 0.5;
              return {titles: titles.length, ticks: ticks.length, hits: titles.flatMap(t => [plot, ...ticks.map(box)].filter(b => hit(box(t), b)).map(() => t.textContent))}; }""")
            assert m["titles"] == 2 and m["ticks"] >= 6 and m["hits"] == [], m
        finally:
            browser.close()
    assert errors == [], errors


def test_a_line_has_value_labels_only_when_all_fit(tmp_path):
    """Reviewer: only the last point had a value label. The rule: one line of at most 15 points, each label narrower than the space to the next point:
    a label over each point; else none, and the hover shows the value."""
    days = [{"name": "day", "type": "DATE"}, {"name": "cars", "type": "DOUBLE"}, {"name": "vans", "type": "DOUBLE"}]
    rows = [[f"2026-06-{i + 1:02d}", 100.0 + (i * 37) % 90, 20.0 + i] for i in range(30)]
    vals = "() => [...document.querySelectorAll('#c svg .rs-chart-val')].map(t => t.textContent)"
    with pw.sync_playwright() as p:
        browser, page, errors = _page(p, tmp_path)
        try:
            page.evaluate(_DRAW, ["line", "day", "cars", days, rows[:5], 600])
            page.wait_for_timeout(80)
            assert page.evaluate(vals) == ["100", "137", "174", "121", "158"]
            page.evaluate("C.set({rows: " + json.dumps(rows) + "})")                      # 30 points: no label; the hover shows the value
            assert page.evaluate(vals) == []
            page.locator("#c svg circle").nth(3).hover()
            page.wait_for_timeout(100)
            assert "121" in page.inner_text("#rs-hover")
            page.evaluate("C.set({rows: " + json.dumps(rows[:5]) + ", y: ['cars', 'vans']})")   # two lines: no label
            assert page.evaluate(vals) == []
            page.evaluate("document.getElementById('c').style.width = '300px'")              # 15 points in 300 px: the labels do not fit, none
            page.evaluate("C.set({y: 'cars', rows: " + json.dumps(rows[:15]) + "})")
            page.wait_for_timeout(150)
            assert page.evaluate(vals) == []
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
        assert page.is_hidden("#rs-dock .rs-dock-table") and page.is_visible("#rs-dock .rs-dd-chartel svg")
        # reviewer: the side column kept 300 px with only its hint. In the Chart view the chart takes that width while no card and no list show.
        widths = "() => ['.rs-dd-chart', '.rs-dd-split'].map(c => Math.round(document.querySelector('#rs-dock ' + c).getBoundingClientRect().width))"
        chart_w, split_w = page.evaluate(widths)
        assert chart_w == split_w and page.is_hidden("#rs-dock .rs-dd-side"), (chart_w, split_w)
        page.evaluate("rs.select('2')")                                                   # a road card: the side column comes back
        page.wait_for_timeout(200)
        assert page.is_visible("#rs-dock .rs-dd-card") and page.evaluate(widths)[0] < split_w - 250
        page.evaluate("rs.select(null)")
        page.wait_for_timeout(200)
        assert page.evaluate(widths)[0] == split_w
        # the first chart of a result with one number column is a histogram over all its 2765 rows (not the table's 1000)
        assert page.evaluate("document.querySelector('#rs-dock .rs-dd-kind.on').dataset.kind") == "histogram"
        # the controls: Kind is five icon buttons, X and Y are roadstyle's select boxes (not the browser's list)
        assert page.locator("#rs-dock .rs-dd-kind").count() == 5 and page.locator("#rs-dock .rs-dd-chartrow .rs-sel-btn").count() == 2
        assert "2 765 values" in page.inner_text("#rs-dock .rs-chart-hd")
        # a result of a text and a number: a bar chart in the open view
        page.evaluate("data.run('SELECT edge_id, name, highway FROM edges')")
        page.wait_for_timeout(300)
        # no measure (edge_id is an id): the rows for each value of the text column with the fewest values, highway
        assert page.evaluate("JSON.stringify(data.result().chart)") == '{"kind":"bar","x":"highway","y":"(count of rows)"}'
        assert page.locator("#rs-dock .rs-dd-chartel svg path").count() == 3
        page.evaluate("data.run('SELECT edge_id, length_m FROM big')")
        page.click("#rs-dock .rs-dd-kind[data-kind=scatter]")
        assert "edge_id" not in page.evaluate("[...document.querySelectorAll('#rs-dock .rs-dd-chartrow select')[0].options].map(o => o.value)")   # no chart over road ids
        page.wait_for_timeout(300)
        assert page.locator("#rs-dock .rs-dd-chartel svg circle").count() >= 6
        # data.chart(spec), as Ask's draw_chart: a spec that does not fit is an error
        assert page.evaluate("(() => { try { data.chart({kind: 'pie', x: 'nope', y: 'length_m'}); return 'no error'; } catch(e) { return e.message; } })()").startswith("The column")
        # Kaveh's case: a pie of a number X with many values (the 2765 lengths) has the rows in ranges, about 6 slices; a change of the kind drops the title
        page.evaluate("data.chart({kind: 'bar', x: 'length_m', title: 'Histogram of lengths'})")
        page.wait_for_timeout(300)
        page.click("#rs-dock .rs-dd-kind[data-kind=pie]")
        page.wait_for_timeout(500)
        slices = page.evaluate("[...document.querySelectorAll('#rs-dock .rs-chart-legend span')].map(s => s.textContent)")
        assert 3 <= len(slices) <= 6 and all("\u2013" in s for s in slices if not s.startswith("Other")), slices
        assert "in ranges" in page.inner_text("#rs-dock .rs-dd-chint") and "Histogram of lengths" not in page.inner_text("#rs-dock .rs-chart-hd")
        # Kaveh's case: a kind that needs a number X never takes the road ids; the hint says how to use the kind
        page.click("#rs-dock .rs-dd-kind[data-kind=bar]")
        page.click("#rs-dock .rs-dd-kind[data-kind=histogram]")
        assert page.evaluate("data.result().chart.x") == "length_m" and "20 equal ranges" in page.inner_text("#rs-dock .rs-dd-chint")
        page.click("#rs-dock .rs-dd-view button:has-text('Table')")
        assert page.is_visible("#rs-dock .rs-dock-table")
        browser.close()
    assert errors == [], errors
