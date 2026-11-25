"""boundary_limit in a browser, on a GeoJSON page, a tiled page and duckosm.page: the map shows nothing outside the area's box grown by
limit_pad (map.setMaxBounds), and the lowest zoom is zoom_out levels under the zoom that fits the box, again after a resize. The area is an
input: True takes boundary=, else boundary_limit is the area (a box, a shapely geometry, a GeoDataFrame, GeoJSON); the page writer gives
its box (dashboard.boundary.bounds). Skipped without playwright or the Rust extension."""
import pytest

pw = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not __import__("roadstyle._engine", fromlist=["available"]).available(), reason="no roadstyle._rust")

W, S, E, N = 7.40, 43.72, 7.41, 43.73
RULES = {"panel": None, "boundary": {"limit_pad": 0.5, "zoom_out": 1}}


def _page(kind, tmp_path):
    import geopandas as gpd
    from shapely.geometry import LineString, box

    import roadstyle as rs
    bd = box(W, S, E, N)
    path = tmp_path / f"{kind}.html"
    if kind == "duckosm":
        from test_duckosm import _tiny

        from roadstyle import duckosm
        duckosm.page(_tiny(tmp_path / "t.duckdb"), "driving", levels="tags", tiles=True, boundary_limit=bd, dashboard=RULES).save(str(path))
        return path
    edges = gpd.GeoDataFrame({"highway": ["residential"] * 4},
                             geometry=[LineString([(W + i * 2e-3, S), (W + i * 2e-3, N)]) for i in range(4)], crs=4326)
    if kind == "geojson":                                                  # True: the box of boundary=
        rs.render_edges(edges, basemap="blank", boundary=bd, boundary_limit=True, dashboard=RULES).save(path)
    elif kind == "tiles":                                                  # a box, and no boundary=
        rs.render_edges(edges, basemap="blank", tiles=True, boundary_limit=(W, S, E, N), dashboard=RULES).save(path)
    else:                                                                  # a GeoDataFrame in metres
        area = gpd.GeoDataFrame(geometry=[bd], crs=4326).to_crs(3857)
        rs.render_edges(edges, basemap="blank", tiles=True, boundary_limit=area, dashboard=RULES).save(path)
    return path


_STATE = """() => { const b = map.getMaxBounds(), c = map.getCenter(), v = map.getBounds();
  return {max: b && [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], min: map.getMinZoom(), zoom: map.getZoom(), center: [c.lng, c.lat],
          view: [v.getWest(), v.getSouth(), v.getEast(), v.getNorth()], fit: map.cameraForBounds([[%r, %r], [%r, %r]], {padding: 0}).zoom}; }""" % (W, S, E, N)


def test_true_with_no_boundary_says_so():
    import geopandas as gpd
    from shapely.geometry import LineString

    import roadstyle as rs
    edges = gpd.GeoDataFrame({"highway": ["residential"]}, geometry=[LineString([(W, S), (E, N)])], crs=4326)
    with pytest.raises(Exception, match="boundary_limit"):
        rs.render_edges(edges, basemap="blank", boundary_limit=True)
    with pytest.raises(Exception, match="west < east"):
        rs.render_edges(edges, basemap="blank", boundary_limit=(E, S, W, N))


@pytest.mark.parametrize("kind", ["geojson", "tiles", "gdf", "duckosm"])
def test_the_map_stops_at_the_boundary(kind, tmp_path):
    path = _page(kind, tmp_path)
    px, py = (E - W) * 0.5, (N - S) * 0.5
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded() && window.rsReady", timeout=60_000)
        start = page.evaluate(_STATE)
        page.mouse.move(700, 450)
        for _ in range(30):                                                # zoom out far, with the wheel
            page.mouse.wheel(0, 600)
            page.wait_for_timeout(30)
        page.wait_for_timeout(600)
        out = page.evaluate(_STATE)
        for _ in range(4):                                                 # pan far to the east and the north
            page.mouse.move(1200, 200)
            page.mouse.down()
            page.mouse.move(100, 800, steps=10)
            page.mouse.up()
        page.wait_for_timeout(600)
        pan = page.evaluate(_STATE)
        page.set_viewport_size({"width": 390, "height": 844})             # a phone: the lowest zoom again, for the new window
        page.wait_for_timeout(600)
        phone = page.evaluate(_STATE)
        browser.close()
    assert errors == []
    assert start["max"] == pytest.approx([W - px, S - py, E + px, N + py]), start
    assert start["min"] == pytest.approx(start["fit"] - 1, abs=1e-6), start
    for s in (out, pan):
        assert s["zoom"] >= start["min"] - 1e-6, s
        lo, hi = s["view"][:2], s["view"][2:]
        assert lo[0] >= W - px - 1e-6 and lo[1] >= S - py - 1e-6 and hi[0] <= E + px + 1e-6 and hi[1] <= N + py + 1e-6, s   # the view stays in the box
    assert phone["min"] == pytest.approx(phone["fit"] - 1, abs=1e-6) and phone["min"] < start["min"], (phone, start)
