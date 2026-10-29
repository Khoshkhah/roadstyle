"""The layers of the Google 3D window (docs/design/dashboard_templates.md, step D8): the typed keyword `google_3d_layers`, and the window that draws them.

Google's script is a stub (a route that answers the script request), so the checks run in headless Chromium without a Google key or a network.
Skipped when playwright is not installed.
"""
import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
_URL = "http://rs.test/p.html"
# what the window needs of Google's "maps3d" library: three elements that keep what they are given
_STUB = """
class E extends HTMLElement { constructor(o){ super(); Object.assign(this, o||{}); } }
for (const [n, c] of [["gmp-map-3d", "Map3DElement"], ["gmp-polyline-3d", "Polyline3DElement"], ["gmp-polygon-3d", "Polygon3DElement"]]) {
  window[c] = class extends E {}; customElements.define(n, window[c]); }
window.google = {maps: {importLibrary: async () => ({Map3DElement, Polyline3DElement, Polygon3DElement})}};
window.__rsGmReady();
"""
_ZONES = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"zone": "a"}, "geometry": {"type": "Polygon", "coordinates": [[[18.0, 59.30], [18.001, 59.30], [18.001, 59.305], [18.0, 59.30]]]}},
    {"type": "Feature", "properties": {"zone": "b"}, "geometry": {"type": "Polygon", "coordinates": [[[18.002, 59.30], [18.003, 59.30], [18.003, 59.305], [18.002, 59.30]]]}}]}
_SPOTS = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [18.001, 59.302]}},
                                                    {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [18.002, 59.303]}}]}
_LAYER = {"id": "zones", "label": "Zones", "kind": "polygon", "source": "zones", "scope": "view", "style": {"fill": "rgba(255,0,0,0.3)", "outline_width": 3}}


def _edges(n=6):
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary"] * n, "name": [f"Street {i}" for i in range(n)], "edge_id": list(range(1, n + 1))},
                            geometry=[LineString([(18.0 + i * 1e-3, 59.30), (18.0 + i * 1e-3, 59.31)]) for i in range(n)], crs=4326)


def _options(**kw):
    html = rs.render_dashboard(_edges(), basemap="blank", google_3d=True, street_view_key="AIzaTEST", **kw).html
    at = html.index("const RS_OPTIONS = ") + len("const RS_OPTIONS = ")
    return html, json.JSONDecoder().raw_decode(html, at)[0]


def test_the_layers_go_to_the_page_as_typed_options():
    _, o = _options(google_3d_layers=[_LAYER])
    (layer,) = o["dashboard"]["google_3d"]["layers"]
    assert (layer["kind"], layer["scope"], layer["max"], layer["on"], layer["arrows"]) == ("polygon", "view", 500, True, False)
    assert layer["style"] == {"fill": "rgba(255,0,0,0.3)", "outline_width": 3.0}
    assert _options()[1]["dashboard"]["google_3d"]["layers"] == []


@pytest.mark.parametrize("layer, message", [
    ({**_LAYER, "kind": "tube"}, "tube"),
    ({**_LAYER, "colour": "red"}, "colour"),
    ({**_LAYER, "style": {"outlineWidth": 2}}, "outlineWidth"),
    ({**{k: v for k, v in _LAYER.items() if k != "scope"}}, "needs `match`"),
])
def test_a_wrong_layer_is_an_error(layer, message):
    with pytest.raises(ValueError, match=message):
        _options(google_3d_layers=[layer])


def test_a_layer_id_is_used_once():
    with pytest.raises(ValueError, match="used twice"):
        _options(google_3d_layers=[_LAYER, _LAYER])


def test_the_window_draws_the_layers_and_the_show_menu_hides_one(tmp_path):
    """Two layers of the page: the window draws the polygons of the view; the "Show" menu has a checkbox for each; clearing one removes its polygons."""
    html, _ = _options(google_3d_layers=[_LAYER, {"id": "pts", "label": "Points", "kind": "points", "source": "spots", "scope": "view", "on": False,
                                                  "style": {"radius": 4}}])
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("https://maps.googleapis.com/**", lambda r: r.fulfill(content_type="text/javascript", body=_STUB))
        page.route(_URL, lambda r: r.fulfill(content_type="text/html", body=html))
        page.goto(_URL)
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        page.evaluate("""([z, s]) => { map.addSource('zones', {type: 'geojson', data: z}); map.addSource('spots', {type: 'geojson', data: s});
                          map.jumpTo({center: [18.0015, 59.302], zoom: 15}); }""", [_ZONES, _SPOTS])
        page.click("button[title='Google 3D']")
        page.wait_for_selector("gmp-map-3d", state="attached")
        page.wait_for_function("document.querySelectorAll('gmp-polygon-3d').length === 2")
        labels = page.eval_on_selector_all(".rs-g3d-menu label", "l => l.map(x => [x.textContent.trim(), x.querySelector('input').checked])")
        page.evaluate("rsG3dLayers.setOn('zones', false)")
        page.wait_for_function("document.querySelectorAll('gmp-polygon-3d').length === 0")
        page.evaluate("rsG3dLayers.setOn('pts', true)")
        page.wait_for_function("document.querySelectorAll('gmp-polygon-3d').length === 2")
        browser.close()

    assert errors == []
    assert labels == [["Selected road", True], ["Zones", True], ["Points", False]]
