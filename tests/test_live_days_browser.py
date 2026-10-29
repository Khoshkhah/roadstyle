"""Live data for a new day (docs/guides/live-data.md): a day picker in the panel, added with `dashboard={"panel": {"sections": ...}}` and `page_script=`, loads the
file of a day and gives it to `rs.setData`; the next day replaces the values of the day before. The files are routes of a fake address, so the page can fetch them.
Skipped without playwright."""
import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_URL = "http://rs.test/flow.html"
_DAYS = ["2026-10-27", "2026-10-28"]
_ROWS = {"2026-10-27": [100, 400, 900, 200, 600, 50], "2026-10-28": [800, 100, 300, 950, 20, 500]}
_SCRIPT = """
  function start() {
    const pick = document.getElementById("day");
    const show = day => rs.setData(`flow-${day}.json`, {colorBy: "flow", legend: {title: "Flow, " + day}});
    pick.onchange = () => show(pick.value);
    show(pick.value);
  }
  window.rsReady ? start() : document.addEventListener("rs:ready", start, {once: true});
"""


def _edges(n=6):
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary"] * n, "name": [f"Street {i}" for i in range(n)], "edge_id": list(range(1, n + 1))},
                            geometry=[LineString([(18.0 + i * 1e-3, 59.30), (18.0 + i * 1e-3, 59.31)]) for i in range(n)], crs=4326)


def _page():
    picker = "<select id='day'>" + "".join(f"<option>{d}</option>" for d in _DAYS) + "</select>"
    return rs.render_dashboard(_edges(), basemap="blank", live_data=True, name="Flow by day",
                               dashboard={"panel": {"sections": [{"id": "day", "label": "Day", "html": picker, "before": "query"}]}},
                               page_script=_SCRIPT).html


def test_page_script_and_page_style_are_the_last_things_of_the_body():
    h = rs.render_edges(_edges(), backend="web", page_script="window.X = 1; // </script> inside", page_style="body{--x:1}").html
    assert "<style>body{--x:1}</style><script>window.X = 1;" in h and h.index("window.X = 1;") > h.index("rsDashboard")
    assert "// </script> inside" not in h and "<\\/script> inside" in h and h.count("</body>") == 1
    assert h.rstrip().endswith("</script></body></html>")


def test_a_day_picker_gives_each_day_its_numbers_and_the_next_day_replaces_them(tmp_path):
    html, errors, legends = _page(), [], []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(_URL, lambda r: r.fulfill(content_type="text/html", body=html))
        for day in _DAYS:
            page.route(f"http://rs.test/flow-{day}.json", lambda route, request, d=day: route.fulfill(content_type="application/json", body=json.dumps(
                [{"edge_id": str(i + 1), "flow": v} for i, v in enumerate(_ROWS[d])])))
        page.goto(_URL)
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        legend = """() => { rs.tools.open('legend'); const t = document.querySelector('.rs-cb-lg').textContent.replace(/\\\\s+/g, ' ').trim(); rs.tools.close('legend'); return t; }"""
        page.wait_for_function("document.querySelector('#day') && rs.legend", timeout=30_000)
        page.wait_for_timeout(800)
        legends.append(page.evaluate(legend))
        page.evaluate("const s = document.getElementById('day'); s.value = '2026-10-28'; s.dispatchEvent(new Event('change', {bubbles: true}))")
        page.wait_for_timeout(800)
        legends.append(page.evaluate(legend))
        sections = page.evaluate("rs.sections.list()")
        browser.close()
    assert not errors
    assert "Flow, 2026-10-27" in legends[0] and "50" in legends[0] and "900" in legends[0]
    assert "Flow, 2026-10-28" in legends[1] and "20" in legends[1] and "950" in legends[1]
    assert sections.index("day") == sections.index("query") - 1
    assert "day" in sections


def test_the_picker_select_is_the_themed_list_and_ids_must_be_text(tmp_path):
    """A select that a page adds to the panel gets the dashboard's own list, not the system's; a 64-bit edge id matches only as text."""
    import geopandas as gpd
    edges = _edges()
    edges["edge_id"] = [2 ** 60 + i for i in range(6)]
    picker = "<select id='day'><option>a</option><option>b</option></select>"
    html = rs.render_dashboard(edges, basemap="blank", live_data=True, dashboard={"panel": {"sections": [{"id": "day", "label": "Day", "html": picker}]}}).html
    assert isinstance(edges, gpd.GeoDataFrame)
    rows_text = json.dumps([{"edge_id": str(2 ** 60 + i), "flow": 10 * (i + 1)} for i in range(6)])
    rows_number = json.dumps([{"edge_id": 2 ** 60 + i, "flow": 10 * (i + 1)} for i in range(6)])
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.route(_URL, lambda route, request: route.fulfill(content_type="text/html", body=html))
        page.goto(_URL)
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        page.wait_for_function("window.rsReady === true", timeout=30_000)
        themed = page.evaluate("!!document.querySelector('#day').closest('.rs-sel') || !!document.querySelector('[data-rs-section=day] .rs-sel-btn')")
        text = page.evaluate("rows => rs.setData(JSON.parse(rows), {colorBy: 'flow'}).then(r => r.matched)", rows_text)
        number = page.evaluate("rows => rs.setData(JSON.parse(rows), {colorBy: 'flow'}).then(r => r.matched)", rows_number)
        browser.close()
    assert themed and text == 6 and number < 6


def test_a_number_goes_in_one_of_n_sets_by_natural_breaks_and_the_legend_counts_the_members(tmp_path):
    rows = [{"edge_id": str(i + 1), "flow": v} for i, v in enumerate([100, 120, 130, 400, 420, 5000])]
    html, errors = rs.render_dashboard(_edges(), basemap="blank", live_data=True).html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(_URL, lambda r: r.fulfill(content_type="text/html", body=html))
        page.goto(_URL)
        page.wait_for_function("window.map && window.map.loaded() && !!(window.rs && rs.setData)", timeout=60_000)
        legend = """async (o) => { await rs.setData(ROWS, Object.assign({colorBy: "flow"}, o)); rs.tools.open('legend');
          const t = document.querySelector('.rs-cb-lg').textContent.replace(/\\s+/g, ' ').trim(); rs.tools.close('legend'); return t; }""".replace("ROWS", json.dumps(rows))
        three = page.evaluate(legend, {"classes": 3})
        assert "100 – 130 (3)" in three and "400 – 420 (2)" in three and "5000 (1)" in three
        fixed = page.evaluate(legend, {"breaks": [200]})
        assert "100 – 130 (3)" in fixed and "400 – 5000 (3)" in fixed and "5000 (1)" not in fixed
        assert "(" not in page.evaluate(legend, {"classes": 0}) and errors == []
        assert page.evaluate("rs.naturalBreaks([1, 2, 3, 100, 110, 120], 2)") == [100] and page.evaluate("rs.naturalBreaks([5, 5, 5], 4)") == []
        browser.close()
