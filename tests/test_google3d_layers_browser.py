"""The layers of the Google 3D window, with a stub of Google's elements (the real ones do not draw in a headless browser)."""
import functools
import http.server
import threading

import pytest

pytest.importorskip("playwright")
gpd = pytest.importorskip("geopandas")
from playwright.sync_api import sync_playwright  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

import roadstyle as rs  # noqa: E402

STUB = """
class El extends HTMLElement { constructor(o) { super(); Object.assign(this, o); } }
class Map3D extends El { flyCameraTo() {} }
class Pl extends El {}
class Pg extends El {}
for (const [n, c] of [['gmp-map-3d', Map3D], ['gmp-polyline-3d', Pl], ['gmp-polygon-3d', Pg]]) customElements.define(n, c);
window.google = {maps: {importLibrary: async () => ({Map3DElement: Map3D, Polyline3DElement: customElements.get('gmp-polyline-3d'), Polygon3DElement: customElements.get('gmp-polygon-3d'),
  MapMode: {HYBRID: 'HYBRID', SATELLITE: 'SATELLITE'}, AltitudeMode: {RELATIVE_TO_MESH: 'RELATIVE_TO_MESH'}})}};
window.__rsGmReady();
"""
LINE = [[7.4200, 43.7300], [7.4205, 43.7301], [7.4210, 43.7300]]
GEO = "LINE"


def _page(tmp_path, **kw):
    g = gpd.GeoDataFrame({"edge_id": [1], "highway": ["primary"], "name": ["A"], "oneway": [False]},
                         geometry=[LineString([(7.4195, 43.7299), (7.4215, 43.7301)])], crs="EPSG:4326")
    path = tmp_path / "l3d.html"
    rs.render_dashboard(g, layout="overlay", toolbar="right", google_3d=True, street_view_key="TESTKEY", basemap="blank", **kw).save(path)
    return path


def _serve(path):
    """Google 3D wants a served page, not a file: a local server on a free port."""
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(path.parent))
    h.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _open(p, path):
    srv = _serve(path)
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1300, "height": 800})
    pg.route("**/maps.googleapis.com/**", lambda r: r.fulfill(status=200, content_type="text/javascript", body=STUB))
    pg.goto(f"http://localhost:{srv.server_address[1]}/{path.name}")
    pg.wait_for_function("window.map && window.map.loaded() && window.rsG3dLayers", timeout=60000)
    pg.evaluate("rsSetGoogle3D(true)")
    pg.wait_for_function("document.querySelector('gmp-map-3d')", timeout=15000)
    pg.wait_for_timeout(500)
    return b, pg


def test_default_is_the_selected_road_and_no_menu(tmp_path):
    with sync_playwright() as p:
        b, pg = _open(p, _page(tmp_path))
        pg.evaluate("(l) => rsG3dDraw(l, 'A', 0, {key: 'k', props: {}})", LINE)
        n = pg.evaluate("[document.querySelectorAll('gmp-map-3d gmp-polyline-3d').length, document.querySelector('.rs-g3d-showwrap').hidden]")
        assert n == [1, True], n
        b.close()


def test_four_kinds_a_menu_and_the_choice_is_kept(tmp_path):
    with sync_playwright() as p:
        path = _page(tmp_path)
        b, pg = _open(p, path)
        pg.evaluate("""(l) => {
          const fc = f => ({type: 'FeatureCollection', features: f});
          const L = {type: 'LineString', coordinates: l};
          rsG3dLayers.register({id: 'centre', label: 'Centre line', kind: 'line', arrows: true, style: {color: '#1565c0', width: 4}, features: () => fc([{type: 'Feature', geometry: L, properties: {}}])});
          rsG3dLayers.register({id: 'band', label: 'Width band', kind: 'ribbon', style: {widthM: 7, fill: 'rgba(0,0,255,.3)'}, on: false, features: () => fc([{type: 'Feature', geometry: L, properties: {}}])});
          rsG3dLayers.register({id: 'area', label: 'Area', kind: 'polygon', on: false, features: () => fc([{type: 'Feature', geometry: {type: 'Polygon', coordinates: [[[7.4200, 43.7300], [7.4202, 43.7300], [7.4202, 43.7302], [7.4200, 43.7300]]]}, properties: {}}])});
          rsG3dLayers.register({id: 'pts', label: 'Points', kind: 'points', on: false, features: () => fc([{type: 'Feature', geometry: {type: 'MultiPoint', coordinates: [[7.4201, 43.7300], [7.4204, 43.7301]]}, properties: {}}])});
          rsG3dDraw(l, 'A', 0, {key: 'k', props: {}}); }""", LINE)
        pg.wait_for_timeout(300)
        C = "(() => { const m = document.querySelector('gmp-map-3d'); return [m.querySelectorAll('gmp-polyline-3d').length, m.querySelectorAll('gmp-polygon-3d').length]; })()"
        assert pg.evaluate("document.querySelector('.rs-g3d-showwrap').hidden") is False
        assert pg.evaluate("[...document.querySelectorAll('.rs-g3d-menu input')].map(c => c.dataset.id + ':' + c.checked).join()") == "selected:true,centre:true,band:false,area:false,pts:false"
        base = pg.evaluate(C)
        # the centre line has arrows: its polylines are more than one; the selected road adds one
        assert base[0] > 3 and base[1] == 0, base
        for id_, want_poly, want_polygon in (("band", 0, 1), ("area", 0, 1), ("pts", 0, 2)):
            pg.evaluate("(id) => document.querySelector('.rs-g3d-menu input[data-id=' + id + ']').click()", id_)
            c = pg.evaluate(C)
            assert c[1] == want_polygon and c[0] == base[0], (id_, c, base)
            pg.evaluate("(id) => document.querySelector('.rs-g3d-menu input[data-id=' + id + ']').click()", id_)
        # every polyline lies on the mesh
        assert pg.evaluate("[...document.querySelectorAll('gmp-polyline-3d')].every(p => p.altitudeMode === 'RELATIVE_TO_MESH' && p.path.every(q => q.altitude === 0.5))")
        # the choice is kept: switch the selected road off, reload
        pg.evaluate("document.querySelector('.rs-g3d-menu input[data-id=selected]').click()")
        before = pg.evaluate(C)
        assert before[0] < base[0]
        pg.reload()
        pg.wait_for_function("window.map && window.map.loaded() && window.rsG3dLayers", timeout=60000)
        pg.evaluate("rsSetGoogle3D(true)")
        pg.wait_for_function("document.querySelector('gmp-map-3d')", timeout=15000)
        pg.evaluate("""(l) => { rsG3dLayers.register({id: 'centre', label: 'Centre line', kind: 'line', arrows: true, style: {color: '#1565c0'}, features: () => ({type: 'FeatureCollection', features: [{type: 'Feature', geometry: {type: 'LineString', coordinates: l}, properties: {}}]})});
          rsG3dLayers.register({id: 'band', label: 'Width band', kind: 'ribbon', on: false, features: () => ({type: 'FeatureCollection', features: []})}); rsG3dDraw(l, 'A', 0, {key: 'k', props: {}}); }""", LINE)
        assert pg.evaluate("rsG3dLayers.isOn('selected')") is False and pg.evaluate("rsG3dLayers.isOn('centre')") is True
        b.close()


def test_view_scope_is_capped_at_500(tmp_path):
    with sync_playwright() as p:
        b, pg = _open(p, _page(tmp_path))
        pg.evaluate("""() => { const f = []; for (let i = 0; i < 800; i++) { const c = map.getCenter(); f.push({type: 'Feature', geometry: {type: 'Point', coordinates: [c.lng + (i % 20) * 1e-6, c.lat + Math.floor(i / 20) * 1e-6]}, properties: {}}); }
          rsG3dLayers.register({id: 'many', label: 'Many', kind: 'points', scope: 'view', features: () => ({type: 'FeatureCollection', features: f})}); }""")
        pg.wait_for_timeout(300)
        n = pg.evaluate("document.querySelectorAll('gmp-map-3d gmp-polygon-3d').length")
        assert n == 500, n
        b.close()


def test_python_layers_reach_the_page(tmp_path):
    """render_dashboard(google_3d_layers=[...]) puts the layers in the registry (a layer whose source is missing draws nothing and does not break the window)."""
    path = _page(tmp_path, google_3d_layers=[{"id": "x", "label": "X", "kind": "line", "source": "no-such-source", "match": "id"},
                                             {"id": "y", "label": "Y", "kind": "polygon", "source": "no-such-source", "match": "id"}])
    with sync_playwright() as p:
        b, pg = _open(p, path)
        pg.evaluate("(l) => rsG3dDraw(l, 'A', 0, {key: 'k', props: {}})", LINE)
        got = pg.evaluate("[rsG3dLayers.list().map(d => d.id).join(), document.querySelector('.rs-g3d-showwrap').hidden, document.querySelectorAll('gmp-map-3d gmp-polyline-3d').length]")
        assert got == ["selected,x,y", False, 1], got
        b.close()
