"""The buildings of a duckOSM base map on a tiled page, as noise-map's page uses them: a hover shows the page's tooltip (rs.tooltip) and lights the
building in the hover colour, a click sends rs:select with its osm_id. On a building that one tile holds and on one that the tiles cut into pieces,
flat and in 3D, in the light and the dark theme, with and without a theme's colours by kind (the kind `match` goes inside the hover `case`).
A tiny duckOSM file made here. Skipped without playwright or the Rust extension."""
import io

import pytest

pw = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not __import__("roadstyle._engine", fromlist=["available"]).available(), reason="no roadstyle._rust")

_KINDS = """extends: grey
features:
  areas:
    buildings:
      fill: "#d6d3ce"
      kinds: {apartments: "#8fb0d8", office: "#cfc8bd"}
"""
# a small building, and a long one (1.3 km) that the tiles cut into pieces
_SMALL, _LONG = (7.4040, 43.7350), (7.4040, 43.7322)


def _db(path):
    import duckdb
    from test_duckosm import _tiny
    _tiny(path)
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE features.buildings (osm_id BIGINT, kind VARCHAR, name VARCHAR, tags MAP(VARCHAR, VARCHAR), geom GEOMETRY)")
    con.execute("""INSERT INTO features.buildings VALUES
        (101, 'apartments', 'Small', MAP {}, 'POLYGON((7.4035 43.7347, 7.4045 43.7347, 7.4045 43.7353, 7.4035 43.7353, 7.4035 43.7347))'::GEOMETRY),
        (102, 'office', 'Long', MAP {}, 'POLYGON((7.3975 43.7320, 7.4105 43.7320, 7.4105 43.7324, 7.3975 43.7324, 7.3975 43.7320))'::GEOMETRY)""")
    con.close()
    return path


def _purple(c):
    return c[2] - c[1] > 60 and c[0] - c[1] > 15                          # the hover colour (#b388ff): blue and red over green


@pytest.mark.parametrize("theme", [None, "kinds"])
def test_a_building_has_its_hover_tooltip_colour_and_click(theme, tmp_path, monkeypatch):
    from PIL import Image

    from roadstyle import duckosm
    kw = {}
    if theme:
        (tmp_path / "themes").mkdir()
        (tmp_path / "themes" / "kinds.yaml").write_text(_KINDS)
        monkeypatch.chdir(tmp_path)
        kw["theme"] = "kinds"
    path = tmp_path / "h.html"
    duckosm.page(_db(tmp_path / "h.duckdb"), "driving", levels="tags", tiles=True, dashboard={"panel": None}, **kw).save(str(path))
    out = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 700})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded() && window.rsReady", timeout=60_000)
        page.evaluate("""rsSetInteraction('buildings', {popup: false}); rs.tooltip('buildings', p => ({title: 'B ' + p.osm_id, rows: []}));
          window.sel = []; document.addEventListener('rs:select', e => sel.push(e.detail.overlay + ':' + (e.detail.properties || {}).osm_id))""")
        for dark in (False, True):
            for b3d in (False, True):
                page.evaluate(f"rsSetTheme('{'dark' if dark else 'light'}'); rsSetBuildings3D({str(b3d).lower()})")
                for (lng, lat), want in ((_SMALL, "101"), (_LONG, "102")):
                    page.evaluate(f"map.jumpTo({{center: [{lng}, {lat}], zoom: 17.5, pitch: 0}})")
                    page.mouse.move(5, 690)
                    page.wait_for_function("map.areTilesLoaded() && map.loaded()", timeout=20_000)
                    page.wait_for_timeout(300)
                    x, y, pieces = page.evaluate(f"""() => {{ const r = map.getContainer().getBoundingClientRect(), q = map.project([{lng}, {lat}]);
                      const ov = RS_OVERLAYS.find(o => o.label === 'buildings'), fill = ov.layers.find(i => i.endsWith('-fill'));
                      return [r.left + q.x, r.top + q.y, map.queryRenderedFeatures({{layers: [fill]}}).filter(f => String(f.properties.osm_id) === '{want}').length]; }}""")
                    before = Image.open(io.BytesIO(page.screenshot())).convert("RGB").getpixel((round(x), round(y)))
                    page.mouse.move(x - 4, y)
                    page.mouse.move(x, y, steps=2)
                    page.wait_for_selector(".rs-tip .maplibregl-popup-content", timeout=5_000)
                    page.wait_for_timeout(300)
                    tip = page.inner_text(".rs-tip .maplibregl-popup-content")
                    # the colour under the mouse, a little beside it (the tooltip is above the point)
                    lit = Image.open(io.BytesIO(page.screenshot())).convert("RGB").getpixel((round(x), round(y) + 6))
                    page.evaluate("sel.length = 0")
                    page.mouse.click(x, y)
                    page.wait_for_timeout(300)
                    out.append(((dark, b3d, want), pieces, tip, before, lit, page.evaluate("sel.slice()")))
        browser.close()
    assert errors == []
    assert any(o[1] > 1 for o in out if o[0][2] == "102"), out              # the long building is cut into pieces
    for case, _, tip, before, lit, sel in out:
        assert tip == f"B {case[2]}", (case, tip)                          # the hover tooltip
        assert _purple(lit) and not _purple(before), (case, before, lit)  # the hover colour, flat and in 3D, light and dark
        assert sel == [f"buildings:{case[2]}"], (case, sel)                # the click
