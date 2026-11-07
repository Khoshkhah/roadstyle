"""rs.holdHover(key, on) and rs.holdSelectLook(key, on) (select.js): a host tool that works on other objects (duckOSM's fixes editor in its
Building tab) holds the road hover: no road lights up, no tooltip, no pointer over a road, and a lit road goes off at once. A click still
selects the road and sends rs:select. holdSelectLook keeps rs:select but sets no select state, so the host draws its own selection. Each
hold ends when no key holds it. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_LONS = [18.000, 18.002, 18.004]
_LAT = 59.302
# the feature state of road `i`, on the source of the road layer
_FS = """i => { const l = map.getLayer("roads-simple"); return map.getFeatureState({source: l.source, sourceLayer: l.sourceLayer, id: i}); }"""


def _page(p, tmp_path):
    import geopandas as gpd
    from shapely.geometry import LineString
    edges = gpd.GeoDataFrame({"highway": ["primary"] * 3, "name": ["A", "B", "C"]},
                             geometry=[LineString([(x, 59.300), (x, 59.304)]) for x in _LONS], crs=4326)
    path = tmp_path / "hold.html"
    rs.render_dashboard(edges, basemap="blank", arrows=False, labels=False).save(path)
    page = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]).new_page(viewport={"width": 1400, "height": 700})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(path.resolve().as_uri())
    page.wait_for_function("window.map && window.rs && map.loaded() && map.getLayer('roads-simple')", timeout=30_000)
    page.evaluate(f"map.jumpTo({{center: [{_LONS[1]}, {_LAT}], zoom: 16}}); map.panBy([-200, 0], {{duration: 0}})")
    page.evaluate("new Promise(ok => { map.once('idle', ok); map.triggerRepaint(); setTimeout(ok, 3000); })")
    page.evaluate("window.__sel = []; document.addEventListener('rs:select', e => __sel.push(e.detail.id))")
    return page, errors


def _at(page, i):
    return page.evaluate(f"""(() => {{ const r = map.getCanvas().getBoundingClientRect(), q = map.project([{_LONS[i]}, {_LAT}]);
                                      return [r.left + q.x, r.top + q.y]; }})()""")


def _state(page, i, key):
    return bool(page.evaluate(f"({_FS})({i}).{key}"))


def _rest(page, xy):
    page.mouse.move(xy[0] + 1, xy[1])
    page.mouse.move(*xy)
    page.wait_for_timeout(800)                       # past hover_delay_ms


def test_hold_hover_stops_the_road_hover_and_keeps_the_click(tmp_path):
    with pw.sync_playwright() as p:
        page, errors = _page(p, tmp_path)
        b = _at(page, 1)
        _rest(page, b)
        assert _state(page, 1, "hover")                                       # without a hold: the road lights up
        page.evaluate("rs.holdHover('tab', true)")
        assert not _state(page, 1, "hover")                                   # the lit road goes off at once
        assert page.locator(".rs-tip").count() == 0
        _rest(page, _at(page, 2))
        assert not _state(page, 2, "hover") and page.evaluate("map.getCanvas().style.cursor") == ""
        page.mouse.click(*b)
        page.wait_for_timeout(300)
        assert page.evaluate("__sel") == [1] and _state(page, 1, "select")    # a click still selects and sends rs:select
        page.evaluate("rs.holdHover('other', true); rs.holdHover('tab', false)")
        _rest(page, _at(page, 0))
        assert not _state(page, 0, "hover")                                   # one key still holds it
        page.evaluate("rs.holdHover('other', false)")
        _rest(page, _at(page, 2))
        assert _state(page, 2, "hover")                                       # no key: the hover is back
        assert errors == []


def test_hold_select_look_keeps_rs_select_and_draws_no_selection(tmp_path):
    with pw.sync_playwright() as p:
        page, errors = _page(p, tmp_path)
        page.mouse.click(*_at(page, 0))
        page.wait_for_timeout(300)
        assert _state(page, 0, "select")
        page.evaluate("rs.holdSelectLook('editor', true)")
        assert not _state(page, 0, "select")                                  # the look of the selection goes off at once
        page.mouse.click(*_at(page, 1))
        page.wait_for_timeout(300)
        assert page.evaluate("__sel") == [0, 1] and not _state(page, 1, "select")
        page.evaluate("rs.select(2)")
        assert page.evaluate("__sel") == [0, 1, 2] and not _state(page, 2, "select")
        page.evaluate("rs.holdSelectLook('editor', false)")
        page.mouse.click(*_at(page, 0))
        page.wait_for_timeout(300)
        assert _state(page, 0, "select")                                      # no key: roadstyle draws the selection again
        assert errors == []
