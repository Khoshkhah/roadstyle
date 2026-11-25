"""The buildings of a duckOSM base map on a tiled page: the tiles hold each building's osm_id (text, exact) and what the look reads, a click
gives the id in rs:select and a hover gives it to rs.tooltip, and a theme's `features.areas.buildings.kinds` colours each kind (the tiles then
hold `kind`). A tiny duckOSM file made here. Skipped without playwright or the Rust extension."""
import pytest

pw = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not __import__("roadstyle._engine", fromlist=["available"]).available(), reason="no roadstyle._rust")

_THEME = """extends: grey
features:
  areas:
    buildings:
      fill: "#d6d3ce"
      kinds: {apartments: "#123456", office: "#654321"}
"""


def _db(path):
    import duckdb
    from test_duckosm import _tiny
    _tiny(path)
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE features.buildings (osm_id BIGINT, kind VARCHAR, name VARCHAR, tags MAP(VARCHAR, VARCHAR), geom GEOMETRY)")
    con.execute("""INSERT INTO features.buildings VALUES
        (9007199254740993, 'apartments', 'Home A', MAP {'building:levels': '5'}, 'POLYGON((7.4010 43.7290, 7.4030 43.7290, 7.4030 43.7298, 7.4010 43.7298, 7.4010 43.7290))'::GEOMETRY),
        (42, 'office', '', MAP {'height': '30'}, 'POLYGON((7.4060 43.7290, 7.4080 43.7290, 7.4080 43.7298, 7.4060 43.7298, 7.4060 43.7290))'::GEOMETRY),
        (43, 'yes', NULL, MAP {}, 'POLYGON((7.4040 43.7302, 7.4050 43.7302, 7.4050 43.7308, 7.4040 43.7308, 7.4040 43.7302))'::GEOMETRY)""")
    con.close()
    return path


def test_a_building_click_gives_its_fields_and_a_theme_colours_its_kind(tmp_path, monkeypatch):
    from roadstyle import duckosm
    (tmp_path / "themes").mkdir()
    (tmp_path / "themes" / "kinds.yaml").write_text(_THEME)
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "b.html"
    duckosm.page(_db(tmp_path / "b.duckdb"), "driving", levels="tags", tiles=True, theme="kinds", dashboard={"panel": None}).save(str(path))
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1000, "height": 700})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded() && window.rsReady", timeout=60_000)
        page.evaluate("map.jumpTo({center: [7.4045, 43.7297], zoom: 17})")
        page.wait_for_function("""() => { const ov = RS_OVERLAYS.find(o => o.label === 'buildings');
          return map.queryRenderedFeatures({layers: ov.layers.filter(id => map.getLayer(id))}).length >= 3; }""", timeout=20_000)
        out = page.evaluate("""() => { const ov = RS_OVERLAYS.find(o => o.label === 'buildings'), ids = ov.layers.filter(id => map.getLayer(id));
          const fs = map.queryRenderedFeatures({layers: ids});
          return {keys: [...new Set(fs.flatMap(f => Object.keys(f.properties)))].sort(), ids: [...new Set(fs.map(f => f.properties.osm_id))].sort(),
                  fill: map.getPaintProperty(ids.find(i => i.endsWith('-fill')), 'fill-color')}; }""")
        page.evaluate("rs.tooltip('buildings', p => ({title: 'Building ' + p.osm_id, rows: []}))")
        pt = page.evaluate("""(() => { const p = map.project([7.4063, 43.7294]), r = map.getContainer().getBoundingClientRect();
          return [r.left + p.x, r.top + p.y]; })()""")                    # the page's coordinates: the map can start right of a bar
        page.mouse.move(pt[0] - 300, pt[1])
        page.mouse.move(pt[0], pt[1])
        page.wait_for_selector(".rs-tip .maplibregl-popup-content", timeout=5_000)
        tip = page.inner_text(".rs-tip .maplibregl-popup-content")
        got = page.evaluate("""() => new Promise(ok => { document.addEventListener('rs:select', e => ok(e.detail), {once: true});
          const pt = map.project([7.4020, 43.7294]); map.fire('click', {point: pt, lngLat: map.unproject(pt), originalEvent: {}}); })""")
        browser.close()
    assert errors == []
    assert "Building 42" in tip, tip                                       # the hover: the id from the tiles
    assert out["keys"] == ["base", "height", "kind", "osm_id"], out        # the look's keys and the id; the rest is in the rows
    assert out["ids"] == ["42", "43", "9007199254740993"], out             # text: above 2**53 too
    fill = str(out["fill"])
    assert "#123456" in fill and "#654321" in fill and "#d6d3ce" in fill, fill
    p = got["properties"]
    assert got["overlay"] == "buildings" and p["osm_id"] == "9007199254740993" and p["name"] == "Home A", got   # above 2**53: exact as text
    assert p["kind"] == "apartments", p
