"""Which object a hover and a click take where a building is over a tunnel, and where a tall building stands in front of another one in a
tilted 3D view (noise-map's page, 2026-11-25). A tunnel is drawn under the ground: the building over it takes the hover box and the click, and
the tunnel outside the building is still a road to click. In 3D the pick is on the building that is drawn at the pointer (the 3D layer), not
on the ground outline of the building behind it. Flat and in 3D, in the light and the dark theme. A tiny duckOSM file made here. Skipped
without playwright or the Rust extension."""
import pytest

pw = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not __import__("roadstyle._engine", fromlist=["available"]).available(), reason="no roadstyle._rust")

_ON_TUNNEL, _TUNNEL_ONLY = (7.4040, 43.7350), (7.4040, 43.7342)     # in building 101 over the tunnel; on the tunnel south of it
_BEHIND = (7.4063, 43.7354)                                         # in building 202, which tall building 201 hides in the tilted view


def _db(path):
    import duckdb
    from test_duckosm import _tiny
    _tiny(path)
    con = duckdb.connect(str(path))
    con.execute("INSERT INTO driving.edges VALUES (3, 12, 13, 300, 'residential', 'T', NULL, 'yes', '-1', false, "
                "'LINESTRING(7.4040 43.7338, 7.4040 43.7360)'::GEOMETRY)")
    con.execute("CREATE TABLE features.buildings (osm_id BIGINT, kind VARCHAR, name VARCHAR, tags MAP(VARCHAR, VARCHAR), geom GEOMETRY)")
    con.execute("""INSERT INTO features.buildings VALUES
        (101, 'office', 'Over the tunnel', MAP {'height': '10'}, 'POLYGON((7.4035 43.7347, 7.4045 43.7347, 7.4045 43.7353, 7.4035 43.7353, 7.4035 43.7347))'::GEOMETRY),
        (201, 'office', 'Tall, in front', MAP {'height': '80'}, 'POLYGON((7.4060 43.7345, 7.4066 43.7345, 7.4066 43.7348, 7.4060 43.7348, 7.4060 43.7345))'::GEOMETRY),
        (202, 'office', 'Low, behind', MAP {'height': '10'}, 'POLYGON((7.4060 43.7352, 7.4066 43.7352, 7.4066 43.7356, 7.4060 43.7356, 7.4060 43.7352))'::GEOMETRY)""")
    con.close()
    return path


def test_a_building_wins_over_a_tunnel_and_3d_picks_the_building_in_front(tmp_path):
    from roadstyle import duckosm
    path = tmp_path / "p.html"
    duckosm.page(_db(tmp_path / "p.duckdb"), "driving", levels="tags", tiles=True, dashboard={"panel": None}).save(str(path))
    out = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 700})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded() && window.rsReady", timeout=60_000)
        page.evaluate("""rsSetInteraction('buildings', {popup: false}); rs.tooltip('buildings', p => ({title: 'B ' + p.osm_id, rows: []}));
          window.sel = []; document.addEventListener('rs:select', e => sel.push(e.detail.overlay ? 'buildings:' + e.detail.properties.osm_id : 'road:' + e.detail.properties.edge_id))""")

        def at(case, lng, lat, pitch):
            page.evaluate(f"map.jumpTo({{center: [{lng}, {lat}], zoom: 17.5, pitch: {pitch}, bearing: 0}})")
            page.mouse.move(5, 690)
            page.wait_for_function("map.areTilesLoaded() && map.loaded()", timeout=20_000)
            page.wait_for_timeout(300)
            x, y = page.evaluate(f"""() => {{ const r = map.getContainer().getBoundingClientRect(), q = map.project([{lng}, {lat}]);
              return [r.left + q.x, r.top + q.y]; }}""")
            page.mouse.move(x - 4, y)
            page.mouse.move(x, y, steps=2)
            page.wait_for_selector(".rs-tip .maplibregl-popup-content", timeout=5_000)
            page.wait_for_timeout(600)
            tips = page.evaluate("[...document.querySelectorAll('.rs-tip .maplibregl-popup-content')].map(e => e.innerText.trim())")
            page.evaluate("sel.length = 0")
            page.mouse.click(x, y)
            page.wait_for_timeout(300)
            out.append((case, tips, page.evaluate("sel.slice()")))
            page.keyboard.press("Escape")

        for dark in (False, True):
            for b3d in (False, True):
                page.evaluate(f"rsSetTheme('{'dark' if dark else 'light'}'); rsSetBuildings3D({str(b3d).lower()})")
                at((dark, b3d, "on tunnel"), *_ON_TUNNEL, 0)
                at((dark, b3d, "tunnel only"), *_TUNNEL_ONLY, 0)
                at((dark, b3d, "behind"), *_BEHIND, 60)
        browser.close()
    assert errors == []
    for case, tips, sel in out:
        dark, b3d, where = case
        if where == "on tunnel":                                           # the building over the tunnel, its box alone
            assert tips == ["B 101"] and sel == ["buildings:101"], (case, tips, sel)
        elif where == "tunnel only":                                       # the tunnel outside a building is still a road
            assert sel == ["road:3"], (case, tips, sel)
        else:                                                              # 3D: the tall building in front; flat: the ground outline
            want = "201" if b3d else "202"
            assert tips == [f"B {want}"] and sel == [f"buildings:{want}"], (case, tips, sel)
