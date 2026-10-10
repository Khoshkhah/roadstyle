"""The vendored MapLibre must draw a per-feature (data-driven) line-dasharray (MapLibre >= 5.8) and line-cap."""
import pytest

from roadstyle.render_web import _asset


def test_data_driven_line_dasharray_loads_without_error(tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    style = {"version": 8, "sources": {"s": {"type": "geojson", "data": {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"d": True, "sq": True}, "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 0]]}},
        {"type": "Feature", "properties": {"d": False, "sq": False}, "geometry": {"type": "LineString", "coordinates": [[0, 1], [1, 1]]}}]}}},
        "layers": [{"id": "l", "type": "line", "source": "s", "layout": {"line-cap": ["case", ["get", "sq"], "square", "round"]}, "paint": {
            "line-width": 4, "line-dasharray": ["case", ["get", "d"], ["literal", [2, 2]], ["literal", [1, 0]]]}}]}
    import json
    page_html = (f"<style>{_asset('maplibre-gl.css')}</style><script>{_asset('maplibre-gl.js')}</script>"
                 f"<div id=m style='width:400px;height:300px'></div><script>window.errs=[];"
                 f"window.map=new maplibregl.Map({{container:'m',style:{json.dumps(style)},center:[0.5,0.5],zoom:7}});"
                 f"map.on('error',e=>errs.push(String(e.error&&e.error.message)));</script>")
    path = tmp_path / "dash.html"
    path.write_text(page_html)
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        console = []
        pg.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: console.append(str(e)))
        pg.goto(path.resolve().as_uri())
        pg.wait_for_function("map.loaded()", timeout=30_000)
        pg.wait_for_timeout(500)
        errs = pg.evaluate("errs")
        b.close()
    assert errs == [] and console == []
