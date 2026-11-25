"""roadstyle's own keys of an overlay item (`__rs_bbox`, the box of its row) are not data: a click on the item shows its fields only, in the popup and in
rs:select. Skipped without playwright."""
import geopandas as gpd
import pytest
from shapely.geometry import box

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _ARGS, _edges  # noqa: E402

import roadstyle as rs  # noqa: E402


def test_a_click_on_an_overlay_item_shows_no_internal_key(tmp_path):
    edges = _edges()
    x0, y0, x1, y1 = edges.total_bounds
    w = x1 - x0
    zone = gpd.GeoDataFrame({"kind": ["shed"]}, geometry=[box(x1 + w, y0, x1 + 2 * w, y1)], crs=4326)   # beside the roads: the click hits no road
    path = tmp_path / "ov.html"
    rs.render_dashboard(edges, basemap="blank", overlays=[rs.Overlay(zone, kind="fill", label="Sheds", placement="over")]).save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1100, "height": 760})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded() && window.rsReady", timeout=60_000)
        page.evaluate("window.sel = null; document.addEventListener('rs:select', e => { window.sel = e.detail; })")
        xy = page.evaluate(f"""() => {{ map.jumpTo({{center: [{x1 + 1.5 * w}, {(y0 + y1) / 2}], zoom: 15}});
                                       const r = map.getCanvas().getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }}""")
        page.wait_for_function("map.loaded() && map.areTilesLoaded()", timeout=30_000)
        page.wait_for_timeout(500)
        page.mouse.click(*xy)
        page.wait_for_selector(".maplibregl-popup-content", timeout=10_000)
        text = page.inner_text(".maplibregl-popup-content")
        sel = page.evaluate("window.sel")
        browser.close()
    assert "shed" in text and "__rs" not in text, text
    assert sel["overlay"] == "Sheds" and not [k for k in [*sel["properties"], *sel["fields"]] if k.startswith("__rs")], sel
    assert not errors, errors
