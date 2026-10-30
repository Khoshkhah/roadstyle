"""The page's own buildings (a layer of its area with a 3D layer) win over the buildings of a vector base map: the two are never drawn together, and
the base-map box's "3D buildings" row is off while the page's are on. Skipped without playwright."""
import json
import pathlib

import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_MAPS = json.loads((pathlib.Path(__file__).parents[1] / "rust/roadstyle-assets/files/data/basemaps.json").read_text())["basemaps"]
_LIBERTY = next(b["style_url"] for b in _MAPS if b["key"] == "ofm_liberty")
_STYLE = {"version": 8, "sources": {"s": {"type": "geojson", "data": {"type": "FeatureCollection", "features": []}}},
          "layers": [{"id": "building", "type": "fill", "source": "s", "source-layer": "building", "paint": {"fill-color": "#ccc"}},
                     {"id": "building-3d", "type": "fill-extrusion", "source": "s", "source-layer": "building", "paint": {"fill-extrusion-height": 10}}]}


def _edges():
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary"], "edge_id": [1]}, crs=4326, geometry=[LineString([(18.0, 59.3), (18.001, 59.301)])])


def test_the_pages_own_buildings_hide_the_vector_base_maps_buildings():
    html, errors = rs.render_dashboard(_edges(), basemap="ofm_liberty").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(_LIBERTY, lambda r: r.fulfill(content_type="application/json", body=json.dumps(_STYLE)))
        page.route("http://rs.test/page.html", lambda r: r.fulfill(content_type="text/html", body=html))
        page.goto("http://rs.test/page.html")
        page.wait_for_function("window.map && !!map.getLayer('vbm-building-3d')", timeout=60_000)
        page.evaluate("map.jumpTo({pitch: 50})")
        page.wait_for_timeout(500)
        vis = lambda: page.evaluate("[map.getLayoutProperty('vbm-building-3d', 'visibility'), map.getLayoutProperty('vbm-building', 'visibility')]")  # noqa: E731
        row = lambda: page.evaluate("document.getElementById('rs-top-buildings').disabled")  # noqa: E731
        assert vis()[0] == "visible" and not row(), "no page buildings: the style's 3D buildings show"
        page.evaluate("""RS_OVERLAYS.push({label: 'buildings', extrude: 'rs-x', visible: true, layers: [], source: 'none'});
                         document.dispatchEvent(new CustomEvent('rs:overlayschange'));""")
        page.wait_for_timeout(300)
        assert vis() == ["none", "none"] and row(), "the page's buildings are on: the style's are not drawn, its row is off"
        page.evaluate("RS_OVERLAYS.at(-1).visible = false; document.dispatchEvent(new CustomEvent('rs:overlaychange'));")
        page.wait_for_timeout(300)
        assert vis()[0] == "visible" and not row(), "the page's buildings are switched off: the style's come back"
        browser.close()
    assert not errors, errors
