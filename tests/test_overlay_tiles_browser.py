"""A page that is one HTML file (way A) keeps no GeoJSON for an overlay: its geometry is in the embedded PMTiles archive, and the dashboard answers
rsQuery, rsGetProps, rsFocus, rsHighlight and the popup from the overlay's rows (docs/design/memory_budget.md, step 1). Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _edges, _open  # noqa: E402

import roadstyle as rs  # noqa: E402


def _zones():
    import geopandas as gpd
    from shapely.geometry import box
    return gpd.GeoDataFrame({"zone": ["a", "b", "a"], "owner": ["x", "y", "z"]},
                            geometry=[box(18.0 + i * 2e-3, 59.301, 18.001 + i * 2e-3, 59.303) for i in range(3)], crs=4326)


def test_an_overlay_is_a_tile_layer_and_the_dashboard_reads_its_rows(tmp_path):
    path = tmp_path / "o.html"
    rs.render_dashboard(_edges(), basemap="blank", overlays=[rs.Overlay(_zones(), kind="fill", label="zones", popup=["zone"])]).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            page.wait_for_function("rsQuery(() => true, 'zones').length === 3", timeout=20_000)
            sources = page.evaluate("Object.fromEntries(Object.entries(map.getStyle().sources).map(([k, s]) => [k, s.type]))")
            assert not [k for k, t in sources.items() if t == "geojson"], sources
            assert page.evaluate("rsQuery(p => p.zone === 'a', 'zones')") == [0, 2]
            assert page.evaluate("rsGetProps([1], 'zones')") == [{"zone": "b", "owner": "y"}]       # a property that no layer reads is in the row, not in the tile
            before = page.evaluate("[map.getCenter().lng, map.getCenter().lat]")
            page.evaluate("rsFocus([2], {duration: 0}, 'zones')")
            after = page.evaluate("[map.getCenter().lng, map.getCenter().lat]")
            assert abs(after[0] - 18.0045) < 2e-3 and after != before                               # the box of the third zone, from its row
            page.evaluate("rsHighlight([1], 'zones')")                                              # the state names the source layer: no error
            assert page.evaluate("map.getFeatureState({source: 'roads', sourceLayer: 'ov0', id: 1})") == {"select": True}
        finally:
            browser.close()
    assert errors == []


def test_a_hidden_overlay_has_its_own_source_and_loads_no_tile_until_it_shows(tmp_path):
    """An overlay that starts hidden is a vector source of its own with its own archive (docs/design/tiling.md): MapLibre asks for a source's tiles
    only while one of its layers shows, so a hidden overlay costs a map move nothing. Shown, it draws, and a click selects it. An overlay that
    shows at the start stays in `roads`."""
    path = tmp_path / "h.html"
    rs.render_dashboard(_edges(), basemap="blank", overlays=[rs.Overlay(_zones(), kind="fill", label="zones", popup=["zone"]),
                                                             rs.Overlay(_zones(), kind="fill", label="hidden", popup=["zone"], visible=False)]).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            page.wait_for_function("map.areTilesLoaded()", timeout=20_000)
            src = page.evaluate("map.getStyle().sources")
            assert src["ov1"]["tiles"] == ["pmtiles://ov1/{z}/{x}/{y}"] and "url" not in src["ov1"], src["ov1"]
            assert page.evaluate("window.__rs_tiles.archives") == ["roads", "ov1"] and "ov0" not in src
            assert page.evaluate("map.getStyle().layers.filter(l => l['source-layer'] === 'ov1').map(l => l.source)") == ["ov1", "ov1"]
            assert page.evaluate("map.querySourceFeatures('roads', {sourceLayer: 'ov0'}).length") > 0
            assert page.evaluate("map.querySourceFeatures('ov1', {sourceLayer: 'ov1'}).length") == 0       # hidden: no tile asked for
            page.evaluate("document.addEventListener('rs:select', e => { window.__sel = e.detail; })")
            page.evaluate("rsSetOverlay('zones', false); rsSetOverlay('hidden', true)")
            page.wait_for_function("map.querySourceFeatures('ov1', {sourceLayer: 'ov1'}).length > 0", timeout=20_000)
            page.wait_for_function("map.areTilesLoaded()", timeout=20_000)
            x, y = page.evaluate("(() => { const q = map.project([18.0045, 59.302]); return [q.x, q.y]; })()")
            page.mouse.click(x, y)
            page.wait_for_function("window.__sel", timeout=5_000)
            assert page.evaluate("window.__sel.properties.zone") == "a"
            assert page.evaluate("map.getFeatureState({source: 'ov1', sourceLayer: 'ov1', id: 2})").get("select") is True
        finally:
            browser.close()
    assert errors == []


def test_lazy_overlays_keep_the_data_of_a_hidden_overlay_in_files_that_load_when_it_shows(tmp_path):
    """lazy_overlays=True: the archive and the rows of each hidden overlay are files next to the page (docs/design/tiling.md, "Overlays in files").
    While the overlay shows, the page reads tiles of the archive with range requests, and the rows the first time; a click and rsQuery read the rows."""
    path = tmp_path / "l.html"
    m = rs.render_dashboard(_edges(), basemap="blank", lazy_overlays=True,
                            overlays=[rs.Overlay(_zones(), kind="fill", label="zones", popup=["zone"]),
                                      rs.Overlay(_zones(), kind="fill", label="hidden", popup=["zone"], visible=False)])
    assert all(f.startswith("rs-files/ov1-") for f in m.files), m.files
    m.save(path)
    assert sorted(p.name.split(".", 1)[1] for p in (tmp_path / "rs-files").iterdir()) == ["json.gz", "pmtiles"]
    asked, ranges = [], []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        def serve(route):                       # the page and its files at an http address that answers range requests, as a file host does
            name = route.request.url.split("//rs.test/", 1)[1]
            asked.append(name)
            body, r = (tmp_path / name).read_bytes(), route.request.headers.get("range")
            if r:
                ranges.append(name)
                a, b = map(int, r.removeprefix("bytes=").split("-"))
                part = body[a:b + 1]
                route.fulfill(status=206, body=part, headers={"Content-Range": f"bytes {a}-{a + len(part) - 1}/{len(body)}",
                                                              "Content-Length": str(len(part)), "Content-Type": "application/octet-stream"})
            else:
                route.fulfill(body=body, content_type="text/html" if name.endswith(".html") else "application/gzip")
        page.route("http://rs.test/**", serve)
        try:
            page.goto("http://rs.test/l.html")
            page.wait_for_function("window.map && window.map.loaded() && map.areTilesLoaded()", timeout=60_000)
            assert page.evaluate("rsQuery(() => true, 'zones').length") == 3                  # the shown overlay: its rows are in the page
            assert asked == ["l.html"]                                                        # no file of the hidden overlay yet
            page.evaluate("document.addEventListener('rs:select', e => { window.__sel = e.detail; })")
            page.evaluate("rsSetOverlay('zones', false); rsSetOverlay('hidden', true)")
            page.wait_for_function("map.querySourceFeatures('ov1', {sourceLayer: 'ov1'}).length > 0", timeout=20_000)
            page.wait_for_function("rsQuery(() => true, 'hidden').length === 3", timeout=20_000)
            assert sorted({a.split(".", 1)[1] for a in asked[1:]}) == ["json.gz", "pmtiles"]
            assert ranges and all(r.endswith(".pmtiles") for r in ranges)                     # the archive: range requests only
            page.wait_for_function("map.areTilesLoaded()", timeout=20_000)
            x, y = page.evaluate("(() => { const q = map.project([18.0045, 59.302]); return [q.x, q.y]; })()")
            page.mouse.click(x, y)
            page.wait_for_function("window.__sel", timeout=5_000)
            assert page.evaluate("window.__sel.properties") == {"zone": "a", "owner": "z"}
        finally:
            browser.close()
    assert errors == []
    assert len(m.html) < len(rs.render_dashboard(_edges(), basemap="blank", overlays=[
        rs.Overlay(_zones(), kind="fill", label="zones", popup=["zone"]), rs.Overlay(_zones(), kind="fill", label="hidden", popup=["zone"], visible=False)]).html)


def test_lazy_overlays_need_tiles():
    with pytest.raises(ValueError, match="needs tiles=True"):
        rs.render_dashboard(_edges(), basemap="blank", lazy_overlays=True, tiles=False,
                            overlays=[rs.Overlay(_zones(), kind="fill", label="hidden", visible=False)])
