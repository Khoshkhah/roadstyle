"""Browser tests for the sensor-matching requests (docs/notes/requests-from-sensor-matching.md).

Each test saves a page, opens it in headless Chromium and reads the DOM or the map. Skipped when
playwright is not installed.
"""
import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]


def _edges(n=12):
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame(
        {"highway": ["primary"] * n, "name": [f"Street {i}" for i in range(n)],
         "edge_id": list(range(1, n + 1))},
        geometry=[LineString([(18.0 + i * 1e-3, 59.30), (18.0 + i * 1e-3, 59.31)]) for i in range(n)],
        crs=4326)


def _open(p, path, size=(1000, 700)):
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_page(viewport={"width": size[0], "height": size[1]})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(path.resolve().as_uri())
    page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
    return browser, page, errors

def _page(tmp_path, name, edges=None, **kw):
    from roadstyle import render_edges as render

    path = tmp_path / f"{name}.html"
    render(edges if edges is not None else _edges(), basemap="blank", **kw).save(path)
    return path


def test_find_control_and_rsfind(tmp_path):
    """Item 2: rsFind(text) is always there; find_control=True adds the box, a click on a row selects the road."""
    plain, with_box = _page(tmp_path, "plain"), _page(tmp_path, "box", find_control=True)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, plain)
        n_found = page.evaluate("rsFind('Street 3').length")                    # Street 3 only (not Street 30…: 12 edges)
        absent = page.evaluate("[document.querySelectorAll('.rs-find').length, rsFind('x').length, rsFind('zzzz').length]")
        browser.close()
        browser, page, errors2 = _open(p, with_box)
        page.evaluate("document.addEventListener('rs:select', e=>{ window.__sel=e.detail.id; })")
        page.fill(".rs-find input", "Street 7")
        page.wait_for_selector(".rs-find .rs-qrow", timeout=5000)
        page.click(".rs-find .rs-qrow")
        selected = page.evaluate("window.__sel")
        browser.close()
    assert n_found == 1 and absent == [0, 0, 0] and selected is not None and not errors and not errors2


def test_overlay_control_off(tmp_path):
    """Item 3: overlay_control=False hides the Layers box; rsSetOverlay still works."""
    from roadstyle import Overlay

    ov = [Overlay(data={"type": "Point", "coordinates": [18.005, 59.305]}, label="Cams")]
    on, off = _page(tmp_path, "ov_on", overlays=ov), _page(tmp_path, "ov_off", overlays=ov, overlay_control=False)
    with pw.sync_playwright() as p:
        browser, page, _ = _open(p, on)
        has_on = page.evaluate("document.querySelectorAll('.ov-ctrl').length")
        browser.close()
        browser, page, errors = _open(p, off)
        has_off = page.evaluate("document.querySelectorAll('.ov-ctrl').length")
        vis = page.evaluate("rsSetOverlay('Cams', false), map.getLayoutProperty('ov0-circle', 'visibility')")
        browser.close()
    assert (has_on, has_off, vis) == (1, 0, "none") and not errors


def _click_overlay(page, x, y):
    page.mouse.click(x, y)
    page.wait_for_timeout(500)


def test_overlay_popup_window_false(tmp_path):
    """Item 4: popup_window=False (or overlay_popup=False): the overlay is selected and rs:select fires, no popup."""
    from roadstyle import Overlay

    pt = {"type": "Point", "coordinates": [18.0, 59.3]}
    pages = {k: _page(tmp_path, k, edges=_edges(2), overlays=[Overlay(data=pt, label="Cams", radius=14, popup_window=w)], overlay_popup=o,
                      road_popup=False)
             for k, (w, o) in {"win": (True, True), "off1": (False, True), "off2": (True, False)}.items()}
    got = {}
    with pw.sync_playwright() as p:
        for k, path in pages.items():
            browser, page, errors = _open(p, path)
            page.evaluate("map.jumpTo({center:[18.0,59.3], zoom:15, pitch:0, bearing:0})")
            page.wait_for_timeout(1500)
            page.evaluate("window.__sel=null; document.addEventListener('rs:select', e=>{ window.__sel=e.detail.overlay; })")
            xy = page.evaluate("(()=>{const q=map.project([18.0,59.3]); return [q.x,q.y]})()")
            _click_overlay(page, *xy)
            got[k] = page.evaluate("[window.__sel, document.querySelectorAll('.maplibregl-popup:not(.rs-tip)').length]")
            assert not errors
            browser.close()
    assert got == {"win": ["Cams", 1], "off1": ["Cams", 0], "off2": ["Cams", 0]}


def test_circle_overlay_outline_and_width(tmp_path):
    """Item 5: outline and width set a circle's ring."""
    from roadstyle import Overlay

    path = _page(tmp_path, "ring", overlays=[Overlay(data={"type": "Point", "coordinates": [18.005, 59.305]}, outline="#112233", width=3)])
    with pw.sync_playwright() as p:
        browser, page, _ = _open(p, path)
        got = page.evaluate("[map.getPaintProperty('ov0-circle','circle-stroke-color'), map.getPaintProperty('ov0-circle','circle-stroke-width')]")
        browser.close()
    assert got == ["#112233", 3]


def _access_edges():
    e = _edges(8)
    e["access"] = [None, None, "private", "private", "bus", "pedestrian", "delivery", None]
    e["highway"] = ["primary"] * 5 + ["pedestrian", "service", "service"]
    return e


def test_access_col_rows_colours_and_filter(tmp_path):
    """Item 6: access_col adds a row per kind, the kind's colour, and a switch that hides those roads."""
    path = _page(tmp_path, "access", edges=_access_edges(), access_col="access")
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        rows = page.evaluate("[...document.querySelectorAll('.flt-body label')].map(l=>l.textContent.trim())")
        counts = page.evaluate("RS_ACCESS")
        fills = page.evaluate("map.querySourceFeatures('simple').map(f=>f.properties.__rs_fill)")      # simple mode draws the roads from their pieces; the roads source is cut into no tiles
        shown = page.evaluate("map.getFilter('roads-simple')")
        page.evaluate("rsSetAccess('private', false)")
        hidden = page.evaluate("JSON.stringify(map.getFilter('roads-simple'))")
        state = page.evaluate("rsGetAccess()")
        page.evaluate("document.getElementById('rs-flt-acc-bus').click()")
        bus_off = page.evaluate("rsGetAccess().bus")
        browser.close()
    assert rows[-4:] == ["Private roads", "Bus lanes", "Pedestrian streets", "Delivery only"]
    assert "pedestrian" not in rows[:-4]                       # every pedestrian road has an access kind: no second switch
    assert counts == {"private": 2, "bus": 1, "pedestrian": 1, "delivery": 1}
    assert {'#c8c8c8', '#9db8d9', '#dddde8', '#e8d2b0'} <= set(fills) and "__rs_access" not in json.dumps(shown) and "__rs_access" in hidden
    assert state["private"] is False and state["bus"] is True and bus_off is False and not errors


def test_side_panel_html(tmp_path):
    """Item 7: a host panel with the handle: » hides it and the map takes the width, « shows it, the state is remembered."""
    path = _page(tmp_path, "host", side_panel_html='<div id="mine">hello</div>', host_panel_width=360)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path, size=(1300, 700))
        w_open = page.evaluate("[document.getElementById('map').getBoundingClientRect().width, document.getElementById('mine').offsetWidth > 0]")
        side = page.evaluate("getComputedStyle(document.body).getPropertyValue('--rs-side')")
        page.click(".rs-host .rs-side-min")
        w_shut = page.evaluate("[document.getElementById('map').getBoundingClientRect().width, document.getElementById('mine').offsetWidth]")
        page.click("[title='Show panel']")
        w_back = page.evaluate("document.getElementById('map').getBoundingClientRect().width")
        page.evaluate("rsPanelShow(false)")
        page.reload()
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        kept = page.evaluate("document.body.classList.contains('rs-side-hidden')")
        browser.close()
    assert w_open == [940, True] and side.strip() == "360px" and w_shut == [1300, 0] and w_back == 940 and kept and not errors


def test_side_panel_html_with_docked_panel_is_an_error(tmp_path):
    from roadstyle import render_edges as render

    with pytest.raises(ValueError, match="two panels"):
        render(_edges(), basemap="blank", side_panel_html="x", popup_mode="panel")


def test_rscolorbase_survives_rscolor(tmp_path):
    """Issue (b): rsColorBase's colours stay under rsColor's own, and rsColor(null) does not clear them. Both are the feature state rs_c
    of the road's row (audit N8); only rsColor's rows are in the global state rs_top (the sort key: a painted road on top)."""
    path = _page(tmp_path, "base")
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        ids = page.evaluate("rsQuery(()=>true)")[:3]
        state = ("(() => { const L = map.getLayer('roads-simple'); return JSON.stringify([" + json.dumps(ids) + ".map(id => "
                 "map.getFeatureState({source: L.source, sourceLayer: L.sourceLayer, id}).rs_c || null), map.getGlobalState().rs_top]); })()")
        page.evaluate(f"rsColorBase([[{ids[:2]}, '#00ee00']])")
        page.evaluate(f"rsColor({ids[1:3]}, '#ee0000')")
        both = json.loads(page.evaluate(state))
        page.evaluate("rsColor(null)")
        after = json.loads(page.evaluate(state))
        page.evaluate("rsColorBase(null)")
        cleared = json.loads(page.evaluate(state))
        used = page.evaluate("JSON.stringify(map.getPaintProperty('roads-simple','line-color')).includes('rs_c')")
        browser.close()
    assert both == [["#00ee00", "#ee0000", "#ee0000"], ids[1:3]]
    assert after == [["#00ee00", "#00ee00", None], []] and cleared == [[None, None, None], []] and used and not errors


def test_overlay_hover_lights_one_feature(tmp_path):
    """Issue (a): features of an overlay that share a number (a property ``id``) are not lit together."""
    import geopandas as gpd
    from shapely.geometry import box

    from roadstyle import Overlay

    areas = gpd.GeoDataFrame({"id": [7, 7, 7], "kind": ["b"] * 3}, geometry=[box(18.001 + i * 0.002, 59.30, 18.002 + i * 0.002, 59.301) for i in range(3)], crs=4326)
    path = _page(tmp_path, "same", overlays=[Overlay(data=areas, label="B", popup=["kind"])])
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        page.evaluate("map.jumpTo({center:[18.004,59.3005], zoom:15, pitch:0, bearing:0})")
        page.wait_for_timeout(1500)
        xy = page.evaluate("(()=>{const q=map.project([18.0015,59.3005]); return [q.x,q.y]})()")
        page.mouse.move(xy[0], xy[1])
        page.mouse.move(xy[0] + 2, xy[1] + 1)
        page.wait_for_timeout(1000)
        lit = page.evaluate("[0,1,2].filter(i=>map.getFeatureState({source:'ov0',id:i}).hover)")
        browser.close()
    assert len(lit) == 1 and not errors


def test_simple_mode_cuts_no_tiles_of_the_roads_source(tmp_path):
    """Simple mode (inline data) draws the roads from their pieces: the page has no roads source (no tiles of it, each one cost the page a
    freeze), a road is picked on a fill piece, and its select glow is one feature-state: its row, the id of all its pieces (promoteId)."""
    path = _page(tmp_path, "lean")
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        page.evaluate("map.jumpTo({center: [18.0005, 59.305], zoom: 15, pitch: 0})")
        page.wait_for_function("map.loaded()", timeout=60_000)
        page.wait_for_timeout(1500)
        tiles = page.evaluate("""Object.fromEntries(['roads', 'simple'].map(k => { const t = (map.style.sourceCaches || map.style.tileManagers)[k];
            return [k, Object.keys((t && t._inViewTiles && t._inViewTiles._tiles) || {}).length]; }))""")
        hit = page.evaluate("(() => { const f = pick(map.project([18.0, 59.305])); return f && [f.id, f.layer.id, Object.keys(f.properties).length > 3]; })()")
        ids = page.evaluate("[...new Set(map.querySourceFeatures('simple').filter(f => f.properties.__rs_edge === 0).map(f => f.id))]")
        page.evaluate("rsSelect(0)")
        lit = page.evaluate("!!map.getFeatureState({source: 'simple', id: 0}).select")
        page.evaluate("rsDeselect()")
        off = page.evaluate("!!map.getFeatureState({source: 'simple', id: 0}).select")
        browser.close()
    assert tiles["roads"] == 0 and tiles["simple"] > 0
    assert hit == [0, "roads-fill", True]                      # the road, with its full properties, as when it was picked on its own layer
    assert ids == [0] and lit and not off and not errors                # every piece of road 0 has its row as its id


def test_one_tile_zoom_in_a_tilted_view(tmp_path):
    """A tilted map loads every tile of the road pieces at one zoom: a road has one width on the whole screen (no horizontal line where two tile zooms meet)."""
    path = _page(tmp_path, "tilt")
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        page.evaluate("map.jumpTo({center:[18.005,59.305], zoom:17.6, pitch:70, bearing:-25})")
        page.wait_for_timeout(4000)
        zooms = page.evaluate("""(()=>{const t=map.style.tileManagers.simple; const ts=t._inViewTiles?._tiles||t._tiles;
            return [...new Set(Object.values(ts).map(x=>x.tileID.overscaledZ))]})()""")
        browser.close()
    assert zooms == [17] and not errors


def test_simple_mode_glow_follows_the_pieces_after_an_update_in_place(tmp_path):
    """The level editor replaces the area's pieces (setData: updateData cannot take the pieces' shared id, promoteId "__rs_edge"): the road
    still glows, through its new pieces (the glow is the state of the row, which every piece of the road has as its id)."""
    path = _page(tmp_path, "inplace")
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        page.evaluate("map.jumpTo({center: [18.0005, 59.305], zoom: 15, pitch: 0})")
        page.wait_for_function("map.loaded()", timeout=60_000)
        old = page.evaluate("map.querySourceFeatures('simple').filter(f => f.properties.__rs_edge === 0).length")
        page.evaluate("""map.getSource('simple').setData({type: 'FeatureCollection', features: _sfeats('simple').map(x =>
            x.properties.__rs_edge === 0 ? {...x, properties: {...x.properties, __rs_new: true}} : x)})""")
        page.wait_for_timeout(1500)
        new = page.evaluate("map.querySourceFeatures('simple').filter(f => f.properties.__rs_edge === 0).map(f => !!f.properties.__rs_new)")
        page.evaluate("rsSelect(0)")
        lit = page.evaluate("!!map.getFeatureState({source: 'simple', id: 0}).select")
        browser.close()
    assert old and new and all(new) and lit and not errors
