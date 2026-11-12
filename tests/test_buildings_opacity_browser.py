"""The 3D buildings of a vector base map: their opacity (`ontop.buildings.opacity` of data/basemaps.json, the keyword `buildings_opacity=`, the
script API `rsBuildingsOpacity` and the Opacity slider of the base-map box) and the far buildings of a tilted map (the 3D layer starts at the
lowest zoom of the flat building layer, and the flat layer stays on in 3D). The styles are stubs with the zooms of OpenFreeMap's, so the checks
need no network. Skipped without playwright."""
import json
import pathlib

import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _ARGS, _edges  # noqa: E402

import roadstyle as rs  # noqa: E402

_ONTOP = json.loads((pathlib.Path(__file__).parents[1] / "rust/roadstyle-assets/files/data/basemaps.json").read_text())["ontop"]
_SRC = {"openmaptiles": {"type": "vector", "tiles": ["https://tiles.invalid/{z}/{x}/{y}.pbf"]}}
# Liberty: a flat layer from zoom 13 to 14 and its own 3D layer from 14 at 0.8. Positron: a flat layer from zoom 12 and no 3D layer.
_LIBERTY = {"version": 8, "sources": _SRC, "layers": [
    {"id": "building", "type": "fill", "source": "openmaptiles", "source-layer": "building", "minzoom": 13, "maxzoom": 14, "paint": {"fill-color": "#ddd"}},
    {"id": "building-3d", "type": "fill-extrusion", "source": "openmaptiles", "source-layer": "building", "minzoom": 14,
     "paint": {"fill-extrusion-color": "#ccc", "fill-extrusion-height": ["get", "render_height"], "fill-extrusion-opacity": 0.8}}]}
_POSITRON = {"version": 8, "sources": _SRC, "layers": [
    {"id": "building", "type": "fill", "source": "openmaptiles", "source-layer": "building", "minzoom": 12, "paint": {"fill-color": "#eee"}}]}
_STATE = """() => { const l = map.getStyle().layers.find(x => x.type === 'fill-extrusion'), row = document.querySelector('.rs-bm-opacity:not(.rs-bm-tunnels)');
  return {opacity: map.getPaintProperty(l.id, 'fill-extrusion-opacity'), minzoom: l.minzoom, api: rsBuildingsOpacity(),
          slider: +document.getElementById('rs-top-buildings-opacity').value, shown: !row.hidden && row.offsetParent !== null}; }"""


def _open(browser, html, errors, style, **ctx):
    page = browser.new_context(**({"viewport": {"width": 1280, "height": 800}} | ctx)).new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("https://tiles.openfreemap.org/styles/*", lambda r: r.fulfill(content_type="application/json", body=json.dumps(style)))
    page.route("https://tiles.invalid/**", lambda r: r.abort())
    page.route("http://rs.test/p.html", lambda r: r.fulfill(content_type="text/html", body=html))
    page.goto("http://rs.test/p.html")
    page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
    page.wait_for_function("map.getStyle().layers.some(l => l.type === 'fill-extrusion')", timeout=30_000)
    page.evaluate("rs.tools.open('basemap')")
    return page


def test_the_config_is_solid():
    assert _ONTOP["buildings"]["opacity"] == 1


@pytest.mark.parametrize("basemap, style", [("ofm_liberty", _LIBERTY), ("ofm_positron", _POSITRON)])
def test_the_opacity_is_the_config_else_the_keyword_and_3d_starts_at_the_flat_layers_zoom(basemap, style):
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        for kw, want in (({}, 1), ({"buildings_opacity": 0.6}, 0.6)):
            page = _open(browser, rs.render_dashboard(_edges(), basemap=basemap, **kw).html, errors, style)
            s = page.evaluate(_STATE)
            assert (s["opacity"], s["api"], s["slider"]) == (want, want, want), (kw, s)
            assert s["minzoom"] == style["layers"][0]["minzoom"], s
        browser.close()
    assert not errors, errors


def test_the_slider_shows_with_the_3d_buildings_and_the_api_and_the_slider_agree():
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = _open(browser, rs.render_dashboard(_edges(), basemap="ofm_positron").html, errors, _POSITRON)
        assert page.evaluate(_STATE)["shown"]
        page.evaluate("rsBuildings(false)")
        assert not page.evaluate(_STATE)["shown"], "no slider while the 3D buildings are off"
        page.evaluate("rsBuildings(true)")
        page.evaluate("""() => { window._ev = []; document.addEventListener('rs:buildingsopacitychange', e => _ev.push(e.detail.opacity));
                                 const i = document.getElementById('rs-top-buildings-opacity'); i.value = 0.4; i.dispatchEvent(new Event('input')); }""")
        s = page.evaluate(_STATE)
        assert (s["opacity"], s["api"], s["shown"]) == (0.4, 0.4, True) and page.evaluate("_ev") == [0.4], s
        page.evaluate("rsBuildingsOpacity(0.7)")
        s = page.evaluate(_STATE)
        assert (s["opacity"], s["slider"]) == (0.7, 0.7) and page.evaluate("_ev") == [0.4, 0.7], s
        assert page.evaluate("document.querySelector('.rs-bm-opacity:not(.rs-bm-tunnels) b').textContent") == "0.70"
        with pytest.raises(pw.Error, match="from 0 to 1"):
            page.evaluate("rsBuildingsOpacity(2)")
        browser.close()
    assert not errors, errors


def test_the_flat_buildings_stay_on_in_3d():
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = _open(browser, rs.render_dashboard(_edges(), basemap="ofm_positron").html, errors, _POSITRON)
        vis = "[map.getLayoutProperty('vbm-building', 'visibility'), map.getLayoutProperty('vbm-building-3d', 'visibility')]"
        assert page.evaluate(vis) == ["visible", "none"]
        page.evaluate("map.setPitch(60); map.fire('pitchend')")
        assert page.evaluate(vis) == ["visible", "visible"], "the far tiles of a tilted map show their flat buildings"
        page.evaluate("rsBuildings(false)")
        assert page.evaluate(vis) == ["none", "none"]
        browser.close()
    assert not errors, errors


def test_the_slider_fits_a_phone():
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = _open(browser, rs.render_dashboard(_edges(), basemap="ofm_positron").html, errors, _POSITRON,
                     viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        page.evaluate("document.querySelector('.rs-bm-opacity:not(.rs-bm-tunnels)').scrollIntoView()")
        r = page.evaluate("""() => { const s = document.getElementById('rs-top-buildings-opacity').getBoundingClientRect(),
                                     b = document.querySelector('.rs-bm-box').getBoundingClientRect(), v = document.querySelector('.rs-bm-opacity:not(.rs-bm-tunnels) b').getBoundingClientRect();
                                     return {s: [s.left, s.right, s.width, s.height], box: [b.left, b.right], v: [v.left, v.right], w: innerWidth}; }""")
        assert r["box"][0] <= r["s"][0] and r["s"][1] <= r["box"][1] <= r["w"], r       # the slider is inside the box, the box inside the phone
        assert r["s"][2] >= 120 and r["box"][0] <= r["v"][0] and r["v"][1] <= r["box"][1], r
        browser.close()
    assert not errors, errors
