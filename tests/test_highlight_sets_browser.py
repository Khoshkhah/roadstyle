"""The highlight sets of the dashboard (core.js, rsHighlight(ids, {set, color, opacity})): each named set lights its roads in its own colour,
at the road's own width, through the feature states rs_hl and rs_hlo that the road layer reads. The set that was set last wins on a shared
road, and the other set's colour comes back when it clears. rsHighlight(ids) without a set works as before. Skipped without playwright."""
import io

import pytest

pw = pytest.importorskip("playwright.sync_api")
Image = pytest.importorskip("PIL.Image")

import roadstyle as rs  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
_LONS = [18.000, 18.002, 18.004, 18.006]          # the roads A, B, S (in both sets) and R (in no set), all of one class
_LAT = 59.302
BLUE, GREEN = (37, 99, 235), (22, 163, 74)
_HEX = {BLUE: "#2563eb", GREEN: "#16a34a"}

# the feature state of each road, by its row (the source of the road layer)
_STATE = """[0, 1, 2, 3].map(id => { const l = map.getLayer("roads-simple");
  return map.getFeatureState({source: l.source, sourceLayer: l.sourceLayer, id}); })"""


def _save(tmp_path):
    import geopandas as gpd
    from shapely.geometry import LineString
    lines = [LineString([(x, 59.300), (x, 59.304)]) for x in _LONS]
    edges = gpd.GeoDataFrame({"highway": ["primary"] * 4}, geometry=lines, crs=4326)
    path = tmp_path / "sets.html"
    rs.render_dashboard(edges, basemap="blank", arrows=False, labels=False).save(path)
    return path


def _view(page, lon, zoom):
    """The map at `lon`, moved right of the side panel."""
    page.evaluate(f"map.jumpTo({{center: [{lon}, {_LAT}], zoom: {zoom}}}); map.panBy([-160, 0], {{duration: 0}})")


def _idle(page):
    page.evaluate("new Promise(ok => { map.once('idle', ok); map.triggerRepaint(); })")


def _shot(page):
    return Image.open(io.BytesIO(page.screenshot())).convert("RGB")


def _px(page, img, lon):
    """The colour at the middle of the road at `lon`, and the row of pixels across it (x, colour)."""
    x, y = page.evaluate(f"""(() => {{ const r = map.getCanvas().getBoundingClientRect(), p = map.project([{lon}, {_LAT}]);
                                      return [Math.round(r.left + p.x), Math.round(r.top + p.y)]; }})()""")
    return img.getpixel((x, y)), [(i, img.getpixel((i, y))) for i in range(x - 40, x + 41)]


def _near(c, d, tol=6):
    return all(abs(a - b) <= tol for a, b in zip(c, d, strict=True))


def _run(row, colour):
    """The number of pixels of the row across a road that have this colour (the width of the fill as drawn)."""
    return sum(1 for _, c in row if _near(c, colour, 24))


def test_two_highlight_sets_in_two_colours(tmp_path):
    path = _save(tmp_path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            page.goto(path.resolve().as_uri())
            page.wait_for_function("window.map && map.loaded() && window.rsReady", timeout=60_000)
            _view(page, sum(_LONS) / 4, 16)
            page.evaluate("window.heard = []; document.addEventListener('rs:highlightchange', e => heard.push(e.detail))")
            _idle(page)
            fill = _px(page, _shot(page), _LONS[3])[0]                   # the road's own fill, in no set
            assert not _near(fill, BLUE) and not _near(fill, GREEN)

            page.evaluate(f"rsHighlight([0, 2], {{set: 'edit', color: '{_HEX[BLUE]}', opacity: 1}})")
            page.evaluate(f"rsHighlight([1, 2], {{set: 'turn', color: '{_HEX[GREEN]}', opacity: 1}})")
            states = page.evaluate(_STATE)
            assert [s.get("rs_hl") for s in states] == [_HEX[BLUE], _HEX[GREEN], _HEX[GREEN], None]
            assert [s.get("rs_hlo") for s in states][:3] == [1, 1, 1]
            assert "rs_hl" in str(page.evaluate("JSON.stringify(map.getPaintProperty('roads-simple', 'line-color'))"))
            _idle(page)
            img = _shot(page)
            a, b, s, r = (_px(page, img, x)[0] for x in _LONS)
            assert _near(a, BLUE) and _near(b, GREEN) and _near(s, GREEN), (a, b, s)   # S: the set that was set last wins
            assert _near(r, fill)

            page.evaluate("rsHighlight([], {set: 'turn'})")                # clears only that set
            states = page.evaluate(_STATE)
            assert [s.get("rs_hl") for s in states] == [_HEX[BLUE], None, _HEX[BLUE], None]
            _idle(page)
            img = _shot(page)
            a, b, s, r = (_px(page, img, x)[0] for x in _LONS)
            assert _near(a, BLUE) and _near(s, BLUE) and _near(b, fill) and _near(r, fill), (a, b, s, r)
            assert page.evaluate("heard") == [{"set": "edit", "ids": [0, 2]}, {"set": "turn", "ids": [1, 2]}, {"set": "turn", "ids": []}]

            # without a set, rsHighlight is the selection glow as before; it does not touch the sets
            page.evaluate("rsHighlight([3])")
            assert page.evaluate(_STATE)[3].get("select") is True
            _idle(page)
            img = _shot(page)
            assert not _near(_px(page, img, _LONS[3])[0], fill) and _near(_px(page, img, _LONS[0])[0], BLUE)
            assert page.evaluate("heard.at(-1)") == {"ids": [3]}
            page.evaluate("rsHighlight([])")
            assert page.evaluate(_STATE)[3].get("select") is False
            page.evaluate("rsHighlight([], {set: 'edit'})")
            assert [s.get("rs_hl") for s in page.evaluate(_STATE)] == [None] * 4
        finally:
            browser.close()
    assert errors == []


def test_a_highlight_is_as_wide_as_the_road(tmp_path):
    """At two zooms, the lit road's colour covers as many pixels across it as the fill of a road of the same class in no set."""
    path = _save(tmp_path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            page.goto(path.resolve().as_uri())
            page.wait_for_function("window.map && map.loaded() && window.rsReady", timeout=60_000)
            page.evaluate(f"rsHighlight([0], {{set: 'edit', color: '{_HEX[BLUE]}', opacity: 1}})")
            widths = []
            for z in (15, 17):
                _view(page, (_LONS[0] + _LONS[1]) / 2, z)
                _idle(page)
                img = _shot(page)
                fill, ref = _px(page, img, _LONS[1])
                lit = _run(_px(page, img, _LONS[0])[1], BLUE)
                widths.append(lit)
                assert abs(lit - _run(ref, fill)) <= 1, (z, lit, _run(ref, fill))
            assert widths[1] > widths[0] + 2                               # the width follows the zoom (not a fixed width)
        finally:
            browser.close()
    assert errors == []
