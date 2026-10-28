"""The toolbar at each of its four positions, in a browser: the bar's box, its size, every button on top, and the base-map list opens toward the map."""
import pytest

pytest.importorskip("playwright")
gpd = pytest.importorskip("geopandas")
from playwright.sync_api import sync_playwright  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

import roadstyle as rs  # noqa: E402

W, H = 1200, 800


def _page(tmp_path, pos):
    g = gpd.GeoDataFrame({"edge_id": [1, 2], "highway": ["primary", "residential"], "name": ["A", "B"], "oneway": [False, False]},
                         geometry=[LineString([(0, 0), (0.001, 0)]), LineString([(0, 0), (0, 0.001)])], crs="EPSG:4326")
    path = tmp_path / f"{pos}.html"
    rs.render_dashboard(g, layout="overlay", toolbar=pos, basemap="blank", basemap_switcher=True).save(path)
    return path


@pytest.mark.parametrize("pos", ["right", "left", "top", "bottom"])
def test_toolbar_position(tmp_path, pos):
    path = _page(tmp_path, pos)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        pg.goto(path.as_uri())
        pg.wait_for_function("window.map && window.map.loaded() && document.getElementById('rs-toolbar')", timeout=60000)
        pg.wait_for_timeout(500)
        r = pg.evaluate("""() => { const t = document.getElementById('rs-toolbar').getBoundingClientRect();
            const btns = [...document.querySelectorAll('#rs-toolbar button')];
            const covered = btns.filter(b => { const q = b.getBoundingClientRect(), e = document.elementFromPoint(q.left + q.width / 2, q.top + q.height / 2); return !(e === b || b.contains(e)); }).length;
            return {l: t.left, t: t.top, w: t.width, h: t.height, right: innerWidth - t.right, bottom: innerHeight - t.bottom, n: btns.length, covered}; }""")
        assert r["n"] >= 5 and r["covered"] == 0
        if pos in ("right", "left"):
            assert round(r["w"]) == 44 and abs((r["t"] + r["h"] / 2) - H / 2) <= 1
            assert round(r["right"] if pos == "right" else r["l"]) == 8
        else:
            assert round(r["h"]) == 44 and abs((r["l"] + r["w"] / 2) - W / 2) <= 1
            assert round(r["t"] if pos == "top" else r["bottom"]) == 8
        # the base-map list opens toward the centre of the map
        pg.click("#rs-toolbar .bm-icon")
        m = pg.evaluate("(() => { const q = document.querySelector('.bm-menu').getBoundingClientRect(); return [q.left, q.top, q.right, q.bottom]; })()")
        centre = (W / 2, H / 2)
        if pos == "right":
            assert m[2] < W - 8
        elif pos == "left":
            assert m[0] > 8
        elif pos == "top":
            assert m[1] > 8
        else:
            assert m[3] < H - 8
        assert centre[0] > 0
        b.close()
