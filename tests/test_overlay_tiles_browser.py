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
            own = page.evaluate("O.overlay_layers.sources.ov1")         # hidden: out of the starting style, in the page's options
            assert own["source"]["tiles"] == ["pmtiles://ov1/{z}/{x}/{y}"] and "url" not in own["source"], own["source"]
            assert page.evaluate("window.__rs_tiles.archives") == ["roads", "ov1"] and "ov0" not in src and "ov1" not in src
            assert [l["source"] for l in own["layers"]] == ["ov1", "ov1"] and all(l["source-layer"] == "ov1" for l in own["layers"])
            assert page.evaluate("map.querySourceFeatures('roads', {sourceLayer: 'ov0'}).length") > 0
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


def test_a_hidden_overlay_shows_each_time_that_it_is_switched_on(tmp_path):
    """A hidden overlay's layers leave the map when it hides and come back when it shows. A layer with no filter came back with `filter: undefined`,
    which addLayer refuses, so the overlay showed only the first time (noise-map: hour 08 -> 09 -> 08, wall height 4 m -> 10 m -> 4 m)."""
    import geopandas as gpd
    from shapely.geometry import Point
    walls = gpd.GeoDataFrame({"h": [4, 4]}, geometry=[Point(18.0005, 59.302), Point(18.0045, 59.302)], crs=4326)
    path = tmp_path / "t.html"
    rs.render_dashboard(_edges(), basemap="blank", overlays=[
        rs.Overlay(_zones(), label="hour 08", popup=[], visible=False), rs.Overlay(_zones(), label="hour 09", popup=[], visible=False),
        rs.Overlay(walls, label="wall 4 m", popup=[], visible=False), rs.Overlay(walls, label="wall 10 m", popup=[], visible=False)]).save(path)
    shown = """l => { const ov = OVERLAYS.find(o => o.label === l);
        return ov.layers.every(id => map.getLayer(id)) && map.queryRenderedFeatures({layers: ov.layers}).length > 0; }"""
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        try:
            page.wait_for_function("map.areTilesLoaded()", timeout=20_000)
            for a, b in (("hour 08", "hour 09"), ("wall 4 m", "wall 10 m")):
                for on, off in ((a, None), (b, a), (a, b), (b, a), (a, b)):           # each one on and off twice
                    page.evaluate("([on, off]) => { if(off) rsSetOverlay(off, false); rsSetOverlay(on, true); }", [on, off])
                    page.wait_for_function(f"({shown})({on!r})", timeout=20_000)
                page.evaluate("l => rsSetOverlay(l, false)", a)
        finally:
            browser.close()
    assert errors == []


def _serve(page, folder, asked, ranges):
    """The page and its files at an http address that answers range requests, as a file host does."""
    def serve(route):
        name = route.request.url.split("//rs.test/", 1)[1]
        asked.append(name)
        body, r = (folder / name).read_bytes(), route.request.headers.get("range")
        if r:
            ranges.append(name)
            a, b = map(int, r.removeprefix("bytes=").split("-"))
            part = body[a:b + 1]
            route.fulfill(status=206, body=part, headers={"Content-Range": f"bytes {a}-{a + len(part) - 1}/{len(body)}",
                                                          "Content-Length": str(len(part)), "Content-Type": "application/octet-stream"})
        else:
            route.fulfill(body=body, content_type="text/html" if name.endswith(".html") else "application/gzip")
    page.route("http://rs.test/**", serve)


def test_lazy_overlays_keep_the_data_of_a_hidden_overlay_in_files_that_load_when_it_shows(tmp_path):
    """lazy_overlays=True: the archive and the rows of each hidden overlay are files next to the page (docs/design/tiling.md, "Overlays in files").
    While the overlay shows, the page reads tiles of the archive with range requests, and the rows the first time; a click and rsQuery read the rows."""
    path = tmp_path / "l.html"
    m = rs.render_dashboard(_edges(), basemap="blank", lazy_overlays=True,
                            overlays=[rs.Overlay(_zones(), kind="fill", label="zones", popup=["zone"]),
                                      rs.Overlay(_zones(), kind="fill", label="hidden", popup=["zone"], visible=False)])
    assert sorted(f.rsplit("-", 1)[0] for f in m.files) == ["rs-files/ov1", "rs-files/ov1", "rs-files/roads"], m.files
    assert "__RS_PMTILES__" not in m.html and m.html.count("rs-files/") == 3          # the page's own tiles are a file too: the HTML has no archive
    m.save(path)
    assert sorted(p.name.split(".", 1)[1] for p in (tmp_path / "rs-files").iterdir()) == ["json.gz", "pmtiles", "pmtiles"]
    asked, ranges = [], []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        _serve(page, tmp_path, asked, ranges)
        # the cache of each range read: Chrome locks its HTTP cache for each URL, so with the cache on, the reads of one file go one after the other
        page.add_init_script("""const f0 = fetch; window.__caches = [];
            window.fetch = (u, o) => { if(String(u).endsWith('.pmtiles')) __caches.push(o && o.cache); return f0(u, o); };""")
        try:
            page.goto("http://rs.test/l.html")
            page.wait_for_function("window.map && window.map.loaded() && map.areTilesLoaded()", timeout=60_000)
            assert page.evaluate("rsQuery(() => true, 'zones').length") == 3                  # the shown overlay: its rows are in the page
            assert not [a for a in asked if "/ov1-" in a] and any("/roads-" in a for a in asked)   # the roads' tiles, no file of the hidden overlay yet
            page.evaluate("document.addEventListener('rs:select', e => { window.__sel = e.detail; })")
            page.evaluate("rsSetOverlay('zones', false); rsSetOverlay('hidden', true)")
            page.wait_for_function("map.querySourceFeatures('ov1', {sourceLayer: 'ov1'}).length > 0", timeout=20_000)
            page.wait_for_function("rsQuery(() => true, 'hidden').length === 3", timeout=20_000)
            assert sorted({a.split(".", 1)[1] for a in asked if "/ov1-" in a}) == ["json.gz", "pmtiles"]
            assert ranges and all(r.endswith(".pmtiles") for r in ranges)                     # the archive: range requests only
            assert set(page.evaluate("__caches")) == {"no-store"}, page.evaluate("__caches")  # on every OS, not only Windows
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


def test_an_overlay_with_no_popup_loads_its_rows_only_when_a_call_asks(tmp_path):
    """lazy_overlays=True: an overlay with no popup, click or tooltip (a noise surface of one hour) reads no rows file when it shows. The first
    rsGetProps on it answers from the rows that it has (none), fetches them, and "rs:overlayrows" tells when they are in."""
    path = tmp_path / "s.html"
    m = rs.render_dashboard(_edges(), basemap="blank", lazy_overlays=True,
                            overlays=[rs.Overlay(_zones(), kind="fill", label="surface", popup=[], visible=False)])
    m.save(path)
    asked, ranges = [], []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        _serve(page, tmp_path, asked, ranges)
        try:
            page.goto("http://rs.test/s.html")
            page.wait_for_function("window.map && window.map.loaded() && map.areTilesLoaded()", timeout=60_000)
            page.evaluate("rsSetOverlay('surface', true)")
            page.wait_for_function("map.querySourceFeatures('ov0', {sourceLayer: 'ov0'}).length > 0", timeout=20_000)
            page.wait_for_function("map.areTilesLoaded()", timeout=20_000)
            assert any(a.endswith(".pmtiles") and "/ov0-" in a for a in asked)
            assert not [a for a in asked if a.endswith(".json.gz")], asked                    # shown, and no rows file
            page.evaluate("document.addEventListener('rs:overlayrows', e => { window.__rows = e.detail; })")
            assert page.evaluate("rsGetProps([0], 'surface')") == [{}]                        # the rows that it has: none yet
            page.wait_for_function("window.__rows", timeout=20_000)
            assert page.evaluate("window.__rows") == {"overlay": "surface"}
            assert [a for a in asked if a.endswith(".json.gz")]
            assert page.evaluate("rsGetProps([0, 2], 'surface')") == [{"zone": "a", "owner": "x"}, {"zone": "a", "owner": "z"}]
        finally:
            browser.close()
    assert errors == []


def test_lazy_overlays_need_tiles():
    with pytest.raises(ValueError, match="needs tiles=True"):
        rs.render_dashboard(_edges(), basemap="blank", lazy_overlays=True, tiles=False,
                            overlays=[rs.Overlay(_zones(), kind="fill", label="hidden", visible=False)])


def test_a_road_with_its_fill_off_is_two_borders_with_an_empty_middle(tmp_path):
    """rsSetRoadFill(false): the casing of a road is drawn as its two borders around a gap of the fill's width, so what is under the road shows in
    the middle (before, the casing was one wide solid line). rsSetRoadFill(true) gives the road its fill and its own widths back."""
    import io

    from PIL import Image
    path = tmp_path / "f.html"
    rs.render_dashboard(_edges(), basemap="blank").save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            page.evaluate("map.jumpTo({center: [18.0, 59.305], zoom: 17})")
            page.wait_for_function("map.areTilesLoaded() && map.loaded()", timeout=20_000)

            def row():                          # the pixels across the road 18.0 at its middle: [background far left, ..., the road's centre, ...]
                page.wait_for_timeout(300)
                x, y = page.evaluate("(() => { const q = map.project([18.0, 59.305]); return [q.x, q.y]; })()")
                img = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
                return [img.getpixel((round(x) + d, round(y))) for d in range(-40, 41)]

            on = row()
            bg, mid = on[0], on[40]
            assert mid != bg, "the fill is drawn"
            page.evaluate("rsSetRoadFill(false)")
            assert page.evaluate("map.getPaintProperty('roads-simple', 'line-gap-width')") is not None
            off = row()
            assert off[40] == bg, ("the middle shows what is under the road", off[40], bg)
            edges = [d for d in range(-40, 41) if off[d + 40] != bg]
            assert edges and min(edges) < 0 < max(edges), "a border at each side"
            page.evaluate("rsSetRoadFill(true)")
            assert row()[40] == mid and page.evaluate("map.getPaintProperty('roads-simple', 'line-gap-width')") is None
        finally:
            browser.close()
    assert errors == []


def test_a_page_makes_the_hover_tooltip_of_an_overlay(tmp_path):
    """rs.tooltip(label, fn): fn(properties) gives {title, rows}; the tooltip has the title in bold and one field on each line. null: no tooltip."""
    import geopandas as gpd
    from shapely.geometry import Point
    pts = gpd.GeoDataFrame({"PK": [7]}, geometry=[Point(18.0025, 59.305)], crs=4326)
    path = tmp_path / "t.html"
    rs.render_dashboard(_edges(), basemap="blank", overlays=[rs.Overlay(pts, kind="circle", label="Walls", radius=8, popup_window=False)]).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            page.evaluate("""rs.tooltip('Walls', p => p.PK === 7 ? {title: 'Noise at the wall', rows: [['Wall', 'faces a street'], ['This hour', 63 + ' dB']]} : null);
                             map.jumpTo({center: [18.0025, 59.305], zoom: 17})""")
            page.wait_for_function("map.areTilesLoaded() && map.loaded()", timeout=20_000)
            x, y = page.evaluate("(() => { const q = map.project([18.0025, 59.305]); return [q.x, q.y]; })()")
            page.mouse.move(x - 30, y)
            page.mouse.move(x, y)
            page.wait_for_selector(".rs-tip .maplibregl-popup-content", timeout=5_000)
            html = page.inner_html(".rs-tip .maplibregl-popup-content")
            assert html.startswith("<b>Noise at the wall</b><br><b>Wall</b>: faces a street<br><b>This hour</b>: 63 dB"), html
            page.mouse.move(x - 200, y)
            page.evaluate("rs.tooltip('Walls', p => null)")
            page.mouse.move(x, y)
            page.wait_for_timeout(800)
            assert page.locator(".rs-tip").count() == 0                     # null: no tooltip
        finally:
            browser.close()
    assert errors == []

def test_the_text_of_an_overlay_is_its_geojson():
    """overlays.fc_text (the overlay's GeoJSON made as text, with no Python dict of a feature) gives the FeatureCollection of to_fc."""
    import json

    from roadstyle.overlays import fc_text, to_fc
    z = _zones().to_crs(3006)
    assert json.loads(fc_text(z)) == to_fc(z)
    assert json.loads(fc_text({"type": "Point", "coordinates": [18.0, 59.3]})) == to_fc({"type": "Point", "coordinates": [18.0, 59.3]})


def test_the_boundary_limits_the_camera_on_a_tiled_page(tmp_path):
    """boundary_limit=True on a tiled page: the boundary is a tile layer there, with no GeoJSON source, so the page gives its shape (O.boundary_shape).
    The camera's lowest zoom comes from the boundary, and a move far out comes back. Before, a tiled page had no limit."""
    from shapely.geometry import box
    path = tmp_path / "b.html"
    rs.render_dashboard(_edges(), basemap="blank", boundary=box(17.999, 59.299, 18.006, 59.311), boundary_limit=True).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            assert page.evaluate("map.getSource('roads').type") == "vector"
            page.wait_for_function("map.getMinZoom() > 5", timeout=10_000)
            page.evaluate("map.jumpTo({center: [18.5, 59.0]})")
            page.wait_for_function("Math.abs(map.getCenter().lng - 18.0) < 0.05", timeout=10_000)     # back inside the boundary's bounds and margin
        finally:
            browser.close()
    assert errors == []


def test_an_overlay_whose_data_is_a_function_is_read_while_its_files_are_written(tmp_path):
    """lazy_overlays=True and rs.Overlay(data=<a function>, visible=False): the page has a stand-in of the overlay; roadstyle calls the function
    while it writes that overlay's files, one overlay at a time. The files are the overlay's: the same tiles and rows as with the data itself."""
    import gzip
    import json
    calls = []

    def zones():
        calls.append(1)
        return _zones()
    lazy = rs.render_dashboard(_edges(), basemap="blank", lazy_overlays=True,
                               overlays=[rs.Overlay(zones, kind="fill", label="hidden", popup=["zone"], visible=False)])
    assert calls == [1]                                                  # read once, for its files
    given = rs.render_dashboard(_edges(), basemap="blank", lazy_overlays=True,
                                overlays=[rs.Overlay(_zones(), kind="fill", label="hidden", popup=["zone"], visible=False)])
    rows = lambda m: json.loads(gzip.decompress(next(v for k, v in m.files.items() if k.endswith(".json.gz"))))  # noqa: E731
    def tiles(m):                       # the archive's tiles by z/x/y (its header has the bounds of the overlay alone, and no roads' generation)
        reader = pytest.importorskip("pmtiles.reader")
        MemorySource, Reader, all_tiles = reader.MemorySource, reader.Reader, reader.all_tiles
        return dict(all_tiles(Reader(MemorySource(next(v for k, v in m.files.items() if k.endswith(".pmtiles")))).get_bytes))
    assert rows(lazy) == rows(given) and len(rows(lazy)) == 3
    assert tiles(lazy) == tiles(given) and len(tiles(lazy)) > 5
    path = tmp_path / "f.html"
    lazy.save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        def serve(route):
            name = route.request.url.split("//rs.test/", 1)[1]
            body, r = (tmp_path / name).read_bytes(), route.request.headers.get("range")
            if r:
                a, b = map(int, r.removeprefix("bytes=").split("-"))
                part = body[a:b + 1]
                route.fulfill(status=206, body=part, headers={"Content-Range": f"bytes {a}-{a + len(part) - 1}/{len(body)}", "Content-Length": str(len(part))})
            else:
                route.fulfill(body=body, content_type="text/html" if name.endswith(".html") else "application/gzip")
        page.route("http://rs.test/**", serve)
        try:
            page.goto("http://rs.test/f.html")
            page.wait_for_function("window.map && window.map.loaded() && map.areTilesLoaded()", timeout=60_000)
            page.evaluate("rsSetOverlay('hidden', true)")
            page.wait_for_function("(s => map.querySourceFeatures(s, {sourceLayer: s}).length >= 3)(RS_OVERLAYS.find(o => o.label === 'hidden').source)", timeout=20_000)
            page.wait_for_function("rsQuery(() => true, 'hidden').length === 3", timeout=20_000)
        finally:
            browser.close()
    assert errors == []


def test_data_as_a_function_needs_lazy_overlays_and_a_kind():
    with pytest.raises(ValueError, match="needs lazy_overlays=True"):
        rs.render_dashboard(_edges(), basemap="blank", overlays=[rs.Overlay(_zones, kind="fill", visible=False)])
    with pytest.raises(ValueError, match="needs kind="):
        rs.render_dashboard(_edges(), basemap="blank", lazy_overlays=True, overlays=[rs.Overlay(_zones, visible=False)])


def test_a_thousand_hidden_overlays_are_not_in_the_starting_style(tmp_path):
    """The caller's hidden overlays with a source of their own are outside the starting style (O.overlay_layers): MapLibre walks every layer at each
    frame, and a page of 1,215 hidden overlays could not pan. rsSetOverlay(label, true) adds the overlay's source and layers at their place (an
    "under" overlay under the roads), with its click and its tooltip; false takes them away. A paint change made while it is out (a page's script)
    is in the layer when it shows."""
    import geopandas as gpd
    from shapely.geometry import box
    n = 1000
    cells = [gpd.GeoDataFrame({"k": [i]}, geometry=[box(18.0 + (i % 40) * 1.5e-4, 59.3 + (i // 40) * 4e-4, 18.0001 + (i % 40) * 1.5e-4, 59.3003 + (i // 40) * 4e-4)],
                              crs=4326) for i in range(n)]
    ovs = [rs.Overlay(c, kind="fill", label=f"cell {i}", placement="under", visible=False, popup=["k"]) for i, c in enumerate(cells)]
    path = tmp_path / "t.html"
    rs.render_dashboard(_edges(), basemap="blank", overlays=[rs.Overlay(_zones(), kind="fill", label="zones", popup=["zone"])] + ovs).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            st = page.evaluate("(() => { const s = map.getStyle(); return {layers: s.layers.length, sources: Object.keys(s.sources).length, lazy: Object.keys(O.overlay_layers.sources).length}; })()")
            assert st["lazy"] == n and st["layers"] < 60 and st["sources"] < 10, st
            moves = "(map._delegatedListeners.mousemove || []).length"     # MapLibre queries each layer with a handler at each mouse move
            at_load = page.evaluate(moves)
            assert at_load < 20, at_load
            src = page.evaluate("RS_OVERLAYS.find(o => o.label === 'cell 0').source")
            lid = page.evaluate(f"O.overlay_layers.sources['{src}'].layers[0].id")
            page.evaluate(f"map.setPaintProperty('{lid}', 'fill-color', '#ff0000')")              # a page's change while the overlay is out
            page.evaluate("rs.tooltip('cell 0', p => ({title: 'Cell', rows: [['k', p.k]]})); rsSetOverlay('zones', false); rsSetOverlay('cell 0', true)")
            ids = page.evaluate("map.getStyle().layers.map(l => l.id)")
            assert lid in ids and ids.index(lid) < ids.index("roads-simple"), "under the roads"
            assert page.evaluate(f"map.getPaintProperty('{lid}', 'fill-color')") == "#ff0000"
            assert page.evaluate(f"map.getLayoutProperty('{lid}', 'visibility')") == "visible"
            page.evaluate("map.jumpTo({center: [18.00005, 59.30015], zoom: 18})")
            page.wait_for_function("map.areTilesLoaded() && map.loaded()", timeout=20_000)
            page.evaluate("document.addEventListener('rs:select', e => { window.__sel = e.detail; })")
            x, y = page.evaluate("(() => { const q = map.project([18.00005, 59.30015]); return [q.x, q.y]; })()")
            page.mouse.move(x - 40, y)
            page.mouse.move(x, y)
            page.wait_for_selector(".rs-tip .maplibregl-popup-content", timeout=5_000)
            assert page.inner_html(".rs-tip .maplibregl-popup-content").startswith("<b>Cell</b><br><b>k</b>: 0")
            page.mouse.click(x, y)
            page.wait_for_function("window.__sel", timeout=5_000)
            assert page.evaluate("window.__sel.overlay") == "cell 0" and page.evaluate("window.__sel.properties.k") == 0
            assert page.evaluate(moves) <= at_load + 2                          # zones off, cell 0 on
            page.evaluate("rsSetOverlay('cell 0', false)")
            assert page.evaluate(f"[!!map.getSource('{src}'), !!map.getLayer('{lid}')]") == [False, False]
            assert page.evaluate(moves) < at_load                               # hidden: no handler
            page.evaluate("rsSetOverlay('cell 0', true)")                    # again: its definition kept the change
            assert page.evaluate(f"map.getPaintProperty('{lid}', 'fill-color')") == "#ff0000"
        finally:
            browser.close()
    assert errors == []


def test_a_zoom_or_a_jump_during_the_move_back_into_the_boundary_breaks_nothing(tmp_path):
    """boundary_limit: a pan past the edge starts a move back; a zoom and a jump during it stop it. Before, the move back started inside the
    moveend that stop() fires, and MapLibre's render loop threw at each frame (a blank map that did not move again); and a center a rounding outside
    the limits eased for ever. Now: no page error, and the map is still after a second."""
    from shapely.geometry import box
    path = tmp_path / "e.html"
    rs.render_dashboard(_edges(), basemap="blank", boundary=box(17.999, 59.299, 18.006, 59.311), boundary_limit=True).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        try:
            page.wait_for_function("map.getMinZoom() > 5", timeout=10_000)
            for _ in range(3):
                page.evaluate("map.jumpTo({center: [18.2, 59.4]})")                     # past the edge: the move back starts
                page.wait_for_timeout(60)
                page.evaluate("map.zoomTo(map.getZoom() + 0.5, {duration: 80})")       # stops the move back
                page.wait_for_timeout(20)
                page.evaluate("map.jumpTo({center: [18.003, 59.305]})")
                page.wait_for_timeout(40)
            page.evaluate("map.easeTo({center: [18.1, 59.305], duration: 100})")     # to the edge: the center ends at the limit
            page.wait_for_timeout(1500)
            assert page.evaluate("map.isMoving()") is False
            page.evaluate("map.zoomTo(map.getZoom() + 1, {duration: 0})")           # the map still moves
            assert page.evaluate("map.isMoving()") is False
        finally:
            browser.close()
    assert errors == []
