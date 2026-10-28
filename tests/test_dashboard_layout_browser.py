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
            const sb = document.getElementById('sb'), sr = sb ? sb.getBoundingClientRect() : null; const sbOpen = !!sr && getComputedStyle(sb).display !== 'none' && sr.width > 0;
            const onSide = (s) => sbOpen && ((sr.left + sr.width / 2 < innerWidth / 2) === (s === 'left'));
            return {side_open_right: onSide('right') ? sr.width : 0, side_open_left: onSide('left') ? sr.width : 0, l: t.left, t: t.top, w: t.width, h: t.height, right: innerWidth - t.right, bottom: innerHeight - t.bottom, n: btns.length, covered}; }""")
        assert r["n"] >= 5 and r["covered"] == 0
        if pos in ("right", "left"):
            assert round(r["w"]) == 44 and abs((r["t"] + r["h"] / 2) - H / 2) <= 1
            # the bar sits 8 px from the edge, or 8 px beside an open panel on its side
            assert round(r["right"] if pos == "right" else r["l"]) == 8 + (r["side_open_right"] if pos == "right" else r["side_open_left"])
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


def test_old_control_column_never_shows(tmp_path):
    """With a toolbar, no frame shows roadstyle's own control column; the bar is in the page from the first frame."""
    path = _page(tmp_path, "right")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        pg.add_init_script("""window.__seen = {column: 0, noBar: 0, frames: 0};
            (function poll() { const c = document.querySelector('.maplibregl-ctrl-top-right'), t = document.getElementById('rs-toolbar');
              if (document.body) { window.__seen.frames++;
                if (c && getComputedStyle(c).display !== 'none') window.__seen.column++;
                if (c && !t) window.__seen.noBar++; }
              requestAnimationFrame(poll); })();""")
        pg.goto(path.as_uri())
        pg.wait_for_function("window.map && window.map.loaded() && document.querySelectorAll('#rs-toolbar button').length > 3", timeout=60000)
        pg.wait_for_timeout(1000)
        seen = pg.evaluate("window.__seen")
        assert seen["frames"] > 5 and seen["column"] == 0 and seen["noBar"] == 0, seen
        b.close()


def test_attribution_is_the_last_button(tmp_path):
    path = _page(tmp_path, "right")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        pg.goto(path.as_uri())
        pg.wait_for_function("window.map && window.map.loaded() && document.getElementById('rs-attr-btn')", timeout=60000)
        last = pg.evaluate("(() => { const bs = [...document.querySelectorAll('#rs-toolbar button')]; return bs[bs.length - 1].id; })()")
        assert last == "rs-attr-btn"
        pg.click("#rs-attr-btn")
        assert pg.evaluate("!document.getElementById('rs-attr-box').hidden")
        pg.mouse.click(300, 300)
        assert pg.evaluate("document.getElementById('rs-attr-box').hidden")
        pg.click("#rs-attr-btn")
        pg.keyboard.press("Escape")
        assert pg.evaluate("document.getElementById('rs-attr-box').hidden")
        # the corner is empty: roadstyle's own attribution does not show
        assert pg.evaluate("(() => { const a = document.querySelector('.maplibregl-ctrl-attrib'); return !a || a.getBoundingClientRect().width === 0; })()")
        b.close()


def test_no_empty_bar_flashes(tmp_path):
    """In every frame of the load, the bar is either invisible or complete (all its buttons)."""
    path = _page(tmp_path, "right")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        pg.add_init_script("""window.__f = []; (function poll() { const t = document.getElementById('rs-toolbar');
            if (t) { const r = t.getBoundingClientRect(); window.__f.push([getComputedStyle(t).visibility === 'visible' && r.width > 0, t.querySelectorAll('button').length]); }
            requestAnimationFrame(poll); })();""")
        pg.goto(path.as_uri())
        pg.wait_for_function("window.map && window.map.loaded() && document.getElementById('rs-toolbar').classList.contains('rs-ready')", timeout=60000)
        pg.wait_for_timeout(500)
        frames = pg.evaluate("window.__f")
        final = frames[-1][1]
        shown = [f for f in frames if f[0]]
        assert final > 5 and shown and all(n == final for _, n in shown), (final, shown[:3])
        b.close()


def test_basemap_box(tmp_path):
    """The box: eight keyless radio rows (CARTO only with a key) in the default order with a swatch each, the 'On top' checkboxes, a themed pair that
    follows the theme, and the hillshade layer below the roads."""
    g = gpd.GeoDataFrame({"edge_id": [1], "highway": ["primary"], "name": ["A"], "oneway": [False]},
                         geometry=[LineString([(0, 0), (0.001, 0)])], crs="EPSG:4326")
    path = tmp_path / "bm.html"
    rs.render_dashboard(g, layout="overlay", toolbar="right", basemap="osm", basemap_switcher=True).save(path)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        pg.goto(path.as_uri())
        pg.wait_for_function("window.map && window.map.loaded() && document.querySelector('.rs-bm-row') && document.getElementById('rs-toolbar').classList.contains('rs-ready')", timeout=60000)
        pg.click("#rs-toolbar .bm-icon")
        names = pg.evaluate("[...document.querySelectorAll('.rs-bm-row input[type=radio]')].map(e => e.parentElement.querySelector('.rs-bm-n').textContent)")
        assert names == ["OpenFreeMap Liberty", "OpenFreeMap Bright", "OpenFreeMap Positron", "OpenStreetMap", "Esri Gray", "Esri Streets", "Esri Satellite", "Blank"], names
        assert pg.evaluate("[...document.querySelectorAll('.rs-bm-row input[type=radio]')].every(e => { const s = e.parentElement.querySelector('.rs-bm-sw').getBoundingClientRect(); return Math.round(s.width) === 32 && Math.round(s.height) === 20; })")
        tops = pg.evaluate("[...document.querySelectorAll('.rs-bm-row input[type=checkbox]')].map(e => e.parentElement.querySelector('.rs-bm-n').textContent)")
        assert tops == ["Hillshade", "Labels", "3D buildings", "Satellite labels"], tops
        assert pg.evaluate("document.querySelector('input[value=osm]').checked")
        # Blank follows the theme: white on light, the dark blank on dark; a map with no twin stays
        pg.click("label.rs-bm-row[data-key=blank]")
        pg.keyboard.press("Escape")
        assert pg.evaluate("document.querySelector('.rs-bm-row input[value=blank]').checked")
        pg.evaluate("document.getElementById('sb').dataset.theme = 'dark'")
        pg.wait_for_timeout(300)
        assert pg.evaluate("window.map.getPaintProperty('bg', 'background-color')").lower().replace(" ", "") in ("#14181d", "rgb(20,24,29)")
        pg.evaluate("document.getElementById('sb').dataset.theme = 'light'")
        pg.wait_for_timeout(300)
        assert pg.evaluate("window.map.getPaintProperty('bg', 'background-color')").lower() in ("#efede8", "rgb(239,237,232)", "rgb(239, 237, 232)")
        # the hillshade is a raster layer below the roads, and it goes away
        pg.click("#rs-toolbar .bm-icon")
        pg.check("#rs-top-hillshade")
        order = pg.evaluate("(() => { const ids = map.getStyle().layers.map(l => l.id); return [ids.indexOf('rs-top-hillshade'), ids.findIndex(i => i.startsWith('roads'))]; })()")
        assert 0 <= order[0] < order[1], order
        pg.uncheck("#rs-top-hillshade")
        assert pg.evaluate("!map.getLayer('rs-top-hillshade')")
        b.close()


def test_theme_button_on_the_bar(tmp_path):
    path = _page(tmp_path, "right")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        pg.goto(path.as_uri())
        pg.wait_for_function("window.map && document.getElementById('rs-theme-btn') && document.getElementById('rs-toolbar').classList.contains('rs-ready')", timeout=60000)
        order = pg.evaluate("[...document.querySelectorAll('#rs-toolbar button')].map(b => b.id)")
        assert order[0] == "rs-theme-btn" and order[-1] == "rs-attr-btn", order
        assert pg.evaluate("getComputedStyle(document.getElementById('sb-th')).display") == "none"
        assert pg.evaluate("document.getElementById('rs-theme-btn').dataset.theme") == "light"
        pg.click("#rs-theme-btn")
        assert pg.evaluate("[document.getElementById('sb').dataset.theme, document.getElementById('rs-theme-btn').dataset.theme, document.getElementById('rs-theme-btn').innerHTML.includes('<circle')]") == ["dark", "dark", False]
        pg.click("#rs-theme-btn")
        assert pg.evaluate("[document.getElementById('sb').dataset.theme, document.getElementById('rs-theme-btn').innerHTML.includes('<circle')]") == ["light", True]
        b.close()
