"""Browser smoke test — the saved page actually boots MapLibre and draws roads.

The rest of the suite inspects the generated HTML as text; this is the one test that runs it,
catching the class of bug a string assertion can't (a JS syntax error, the template failing to
wire the data). Needs ``playwright`` + ``playwright install chromium`` (dev-only, optional) —
skipped when absent.
"""
import time

import pytest

pw = pytest.importorskip("playwright.sync_api")


def _edges(n=40):
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame(
        {"highway": ["primary"] * n, "name": [f"Street {i}" for i in range(n)],
         "oneway": [True] * n},
        geometry=[LineString([(18.0 + i * 1e-3, 59.3), (18.0 + i * 1e-3, 59.301)])
                  for i in range(n)],
        crs=4326)


def test_saved_map_boots_and_draws_roads(tmp_path):
    from roadstyle.render_web import render

    path = tmp_path / "smoke.html"
    render(_edges(), basemap="blank").save(path)   # blank basemap: zero network requests

    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function(
            "window.map && typeof window.map.loaded === 'function' && window.map.loaded()",
            timeout=30_000)
        n_source = page.evaluate("window.map.querySourceFeatures('roads').length")
        n_query = page.evaluate("rsQuery(p => p.highway === 'primary').length")
        browser.close()

    assert errors == []
    assert n_source > 0          # the road data reached the map
    assert n_query == len(_edges())   # the JS API sees every edge


def test_compressed_map_inflates_and_attaches(tmp_path):
    """The gzip path (the default for real-size data): blobs inflate and land in the source."""
    from roadstyle.render_web import render

    path = tmp_path / "smoke_gz.html"
    g = _edges(4000)             # clears the 256 KB compression threshold
    render(g, basemap="blank").save(path)
    assert 'id="rs-gz"' in path.read_text()

    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        # __rs_gz.ok flips when setData is called; the source still has to re-tile before
        # querySourceFeatures sees anything, so poll for the features too.
        page.wait_for_function(
            "window.__rs_gz && window.__rs_gz.ok"
            " && window.map.querySourceFeatures('roads').length > 0", timeout=30_000)
        inflated = page.evaluate("window.__rs_gz.features")
        browser.close()

    assert errors == []
    # __rs_gz.features counts across every compressed source (roads + annotation slots)
    assert inflated >= len(g)




def test_tiled_map_boots_draws_and_queries(tmp_path):
    """tiles=True: embedded PMTiles serve the roads, the sidecar serves the JS API."""
    pytest.importorskip("mapbox_vector_tile")
    pytest.importorskip("pmtiles")
    from roadstyle.render_web import render

    path = tmp_path / "smoke_tiles.html"
    g = _edges()
    render(g, basemap="blank", tiles=True, simple=False).save(path)

    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function(
            "window.map && typeof window.map.loaded === 'function' && window.map.loaded()"
            " && window.map.querySourceFeatures('roads',{sourceLayer:'roads'}).length > 0",
            timeout=30_000)
        page.wait_for_function("window.RS_SIDE", timeout=10_000)
        n_query = page.evaluate("rsQuery(p => p.highway === 'primary').length")
        props = page.evaluate("rsGetProps([0])[0]")
        browser.close()

    assert errors == []
    assert n_query == len(g)
    assert props["name"] == "Street 0"      # full attributes come from the sidecar


def test_map_boots_with_street_view_window_left_open(tmp_path):
    """A Street View window left open last time is reopened on load, and the page still draws.
    0.7.0 reopened it mid-script, before the marker state existed: a ReferenceError stopped the
    page before any road was drawn, so every later visit showed a map nothing could be clicked on."""
    from roadstyle.render_web import render

    path = tmp_path / "sv.html"
    render(_edges(), basemap="blank").save(path)
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded()", timeout=30_000)
        page.evaluate("localStorage.setItem('rs-street-view-window:' + location.pathname,"
                      " JSON.stringify({open: true}))")
        page.reload()
        page.wait_for_function("window.map && window.map.loaded()", timeout=30_000)
        page.wait_for_timeout(300)
        n_query = page.evaluate("rsQuery(p => p.highway === 'primary').length")
        reopened = page.evaluate("!document.querySelector('.rs-svw').hidden")
        browser.close()

    assert errors == []
    assert n_query == len(_edges())
    assert reopened


def test_basemap_switch_rebuilds_source_with_its_maxzoom(tmp_path):
    """rsSetBasemap rebuilds the raster source (maxzoom and attribution are fixed at creation) and
    puts the layer back in the same place, under the roads."""
    from roadstyle.render_web import render

    path = tmp_path / "bm.html"
    render(_edges(), basemap="osm", basemaps=["osm", "esri_gray", "blank"]).save(path)
    order = "window.map.getStyle().layers.map(l => l.id).indexOf('basemap')"
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.getSource && window.map.getSource('bm')",
                               timeout=30_000)
        before = page.evaluate(order)
        page.evaluate("rsSetBasemap('esri_gray')")
        # a rebuilt raster source reports MapLibre's default (22) until it has loaded its options
        page.wait_for_function("window.map.getSource('bm').maxzoom === 16", timeout=10_000)
        gray = page.evaluate("[window.map.getSource('bm').maxzoom, window.map.getSource('bm').attribution]")
        gray_at = page.evaluate(order)
        page.wait_for_function("document.querySelector('.maplibregl-ctrl-attrib-inner')"
                               ".textContent.includes('Esri')", timeout=10_000)
        page.evaluate("rsSetBasemap('blank')")
        blank_vis = page.evaluate("window.map.getLayoutProperty('basemap', 'visibility')")
        page.evaluate("rsSetBasemap('osm')")
        page.wait_for_function("window.map.getSource('bm').maxzoom === 19", timeout=10_000)
        osm = page.evaluate("[window.map.getSource('bm').maxzoom, "
                            "window.map.getLayoutProperty('basemap', 'visibility')]")
        browser.close()

    assert errors == []
    assert gray[0] == 16 and "Esri" in gray[1]
    assert gray_at == before                     # still directly above the background
    assert blank_vis == "none" and osm == [19, "visible"]


def test_map_that_starts_late_still_gets_its_roads(tmp_path):
    """MapLibre builds its sources on an animation frame; browsers pause those off screen (a
    notebook output scrolled away). The data loader used to stop looking after 60 s, leaving a map
    with no roads. Fake 61 s of timers with frames withheld, then release them."""
    from roadstyle.render_web import render

    path = tmp_path / "late.html"
    render(_edges(4000), basemap="blank").save(path)   # big enough for the compressed path
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.clock.install()
        page.add_init_script("""
            const later = [], raf = window.requestAnimationFrame.bind(window);
            window.requestAnimationFrame = cb => later.push(cb);
            window.__releaseFrames = () => {
              window.requestAnimationFrame = raf; later.splice(0).forEach(cb => raf(cb)); };""")
        page.goto(path.resolve().as_uri())
        # decompression runs in real time; the loader empties its data element once it is done.
        # (wait_for_function would poll on the faked clock, so poll from here)
        for _ in range(100):
            if page.evaluate("document.getElementById('rs-gz').textContent === ''"):
                break
            time.sleep(0.1)
        page.clock.run_for(61_000)
        waiting = page.evaluate("window.__rs_gz")
        page.evaluate("window.__releaseFrames()")
        page.clock.run_for(5_000)
        attached = page.evaluate("window.__rs_gz")
        banner = page.evaluate("!!document.getElementById('rs-diag')")
        browser.close()

    assert waiting["stage"] == "attach" and waiting["waiting"]
    assert attached["ok"] and attached["features"] >= 4000
    assert not banner



def test_edge_overlay_page_boots_and_rsfilter_keeps_position_and_order(tmp_path):
    """docs/design/edge_overlays.md: an overlay attached to edges draws in the browser; rsFilter on it combines with the position and order of each layer and rsFilter(null) restores them."""
    import geopandas as gpd
    from shapely.geometry import Point

    from roadstyle import Overlay
    from roadstyle.render_web import render

    g = _edges().assign(edge_id=range(100, 140))
    pts = gpd.GeoDataFrame({"edge_id": [100, 101, 102]}, geometry=[Point(18.0 + i * 1e-3, 59.3005) for i in range(3)], crs=4326)
    path = tmp_path / "edge_overlay.html"
    render(g, basemap="blank", overlays=[Overlay(pts, edge_col="edge_id", kind="circle", label="signs", radius=8)]).save(path)
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded() && window.map.querySourceFeatures('roads').length > 0", timeout=30_000)
        ids = page.evaluate("RS_OVERLAYS[0].layers")
        assert ids and all("-lv" in i and "-o" in i for i in ids)
        base = page.evaluate("id => map.getFilter(id)", ids[0])
        page.evaluate("rsFilter([0, 1], 'signs')")
        narrowed = page.evaluate("id => map.getFilter(id)", ids[0])
        page.evaluate("rsFilter(null, 'signs')")
        restored = page.evaluate("id => map.getFilter(id)", ids[0])
        drawn = page.evaluate("map.queryRenderedFeatures({layers: RS_OVERLAYS[0].layers}).length")
        browser.close()
    assert errors == []
    assert narrowed[0] == "all" and base in narrowed and narrowed != base      # the position and order stay, the ids are added
    assert restored == base
    assert drawn > 0


def test_rsfilter_reaches_the_arrows_and_street_names(tmp_path):
    """docs/design/edge_overlays.md: after rsFilter(ids) on the roads, the arrow and name layers show only the slots of those edges (their __rs_edge / __rs_edge2)."""
    from roadstyle.render_web import render

    path = tmp_path / "slots.html"
    render(_edges(), basemap="blank", arrows=True, labels=True).save(path)
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded() && window.map.querySourceFeatures('roads').length > 0", timeout=30_000)
        layers = page.evaluate("map.getStyle().layers.map(l => l.id).filter(i => i.startsWith('roads-arrows') || i.startsWith('roads-labels'))")
        assert layers
        before = page.evaluate("ids => ids.map(i => JSON.stringify(map.getFilter(i)))", layers)
        page.evaluate("rsFilter([0, 1])")
        after = page.evaluate("ids => ids.map(i => JSON.stringify(map.getFilter(i)))", layers)
        page.evaluate("rsFilter(null)")
        reset = page.evaluate("ids => ids.map(i => JSON.stringify(map.getFilter(i)))", layers)
        browser.close()
    assert errors == []
    assert not any("__rs_edge" in f for f in before) and all("__rs_edge" in f for f in after)
    assert reset == before


def test_a_road_without_its_fill_is_still_found_by_a_click(tmp_path):
    """road_fill=False: the fill layers are invisible but still query the road, so a click and a hover find it (docs/design/edge_overlays.md)."""
    from roadstyle.render_web import render

    path = tmp_path / "nofill.html"
    render(_edges(), basemap="blank", road_fill=False).save(path)
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded() && window.map.querySourceFeatures('roads').length > 0", timeout=30_000)
        found = page.evaluate("map.queryRenderedFeatures({layers: PICK_LAYERS.filter(id => map.getLayer(id))}).length")
        browser.close()
    assert errors == [] and found > 0


def test_a_page_with_overlay_styles_boots(tmp_path):
    """docs/design/overlay_styles.md: a metre-wide line, a dashed line and a text overlay, from a theme passed in settings=, boot without errors and are in the style."""
    import geopandas as gpd
    from shapely.geometry import LineString

    from roadstyle import Overlay, render_edges

    g = _edges().assign(edge_id=range(100, 140))
    over = gpd.GeoDataFrame({"edge_id": [100, 101], "label": ["A", "B"]}, geometry=[LineString([(18.0, 59.3), (18.0, 59.3008)]), LineString([(18.001, 59.3), (18.001, 59.3008)])], crs=4326)
    theme = {"config": {"overlays": {"styles": {
        "divider": {"kind": "line", "color": "#ffffff", "width_m": 0.5, "min_zoom": 12},
        "dashed": {"kind": "line", "color": "#222222", "width_m": 0.5, "dash": [3, 3], "min_zoom": 12},
        "name": {"kind": "text", "text_col": "label", "text_size": 12}}}}}
    path = tmp_path / "styles.html"
    render_edges(g, backend="web", basemap="blank", settings=theme, road_fill=False,
           overlays=[Overlay(over, edge_col="edge_id", style=s, label=s, popup=[]) for s in ("divider", "dashed", "name")]).save(path)
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && window.map.querySourceFeatures('roads').length > 0", timeout=30_000)
        have = page.evaluate("RS_OVERLAYS.map(o => o.layers.filter(id => map.getLayer(id)).length)")
        browser.close()
    assert errors == [] and all(n > 0 for n in have)


def test_an_item_attached_to_a_road_follows_its_road(tmp_path):
    """docs/design/edge_items.md step 2: rsFilter, rsSetClasses and rsSetTunnels(false) hide the items attached to a hidden road
    (Overlay(edge_col=...)) and leave an overlay that belongs to no road alone; hovering an item highlights its road and clicking it
    selects the road (rs:select with the road's id and properties)."""
    import geopandas as gpd
    from shapely.geometry import LineString, Point

    from roadstyle import Overlay
    from roadstyle.render_web import render

    ys = [59.300, 59.3015, 59.303]
    g = gpd.GeoDataFrame({"highway": ["primary", "primary", "residential"], "tunnel": [None, "yes", None], "edge_id": [100, 101, 102]},
                         geometry=[LineString([(18.000, y), (18.004, y)]) for y in ys], crs=4326)
    items = gpd.GeoDataFrame({"edge_id": [100, 101, 102], "kind": ["sign"] * 3},          # 30 m north of the middle of each road
                             geometry=[Point(18.002, y + 0.00027) for y in ys], crs=4326)
    free = gpd.GeoDataFrame({"n": [1, 2]}, geometry=[Point(18.001, 59.301), Point(18.003, 59.303)], crs=4326)
    path = tmp_path / "items.html"
    render(g, basemap="blank", tunnel_col="tunnel", overlays=[Overlay(items, edge_col="edge_id", kind="circle", radius=8, label="signs", popup=["kind"]),
                                                             Overlay(free, kind="circle", radius=8, label="free")]).save(path)
    shown = """async ([call, label]) => { eval(call); await new Promise(r => { map.once('idle', r); map.triggerRepaint(); setTimeout(r, 3000); });
      const ov = RS_OVERLAYS.find(o => o.label === label);
      return [...new Set(map.queryRenderedFeatures({layers: ov.layers}).map(f => label === 'signs' ? f.properties.edge_id : f.properties.n))].sort(); }"""
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 700})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded()", timeout=30_000)
        page.evaluate("map.jumpTo({center: [18.002, 59.3015], zoom: 16}); 0")
        page.wait_for_function("map.loaded()", timeout=30_000)
        steps = {c: (page.evaluate(shown, [c, "signs"]), page.evaluate(shown, [c, "free"])) for c in
                 ("0", "rsFilter([0, 2])", "rsFilter(null)", "rsSetClasses(['primary'])", "rsSetClasses(RS_CLASSES)",
                  "rsSetTunnels(false)", "rsSetTunnels(true)")}
        page.evaluate("window.__sel = []; document.addEventListener('rs:select', e => __sel.push([e.detail.id, e.detail.properties.edge_id,"
                      " (e.detail.overlays || []).map(o => o.label)]))")
        x, y = page.evaluate("(() => { const p = map.project([18.002, 59.3015 + 0.00027]); return [p.x, p.y]; })()")
        page.mouse.move(x, y)
        page.wait_for_timeout(700)                                           # past hover_delay_ms (300)
        hover = page.evaluate("[0, 1, 2].map(i => !!map.getFeatureState({source: 'roads', id: i}).hover)")
        page.mouse.click(x, y)
        page.wait_for_timeout(300)
        sel = page.evaluate("__sel")
        selected = page.evaluate("[0, 1, 2].map(i => !!map.getFeatureState({source: 'roads', id: i}).select)")
        browser.close()
    assert errors == []
    assert steps["0"] == ([100, 101, 102], [1, 2])
    assert steps["rsFilter([0, 2])"] == ([100, 102], [1, 2])                 # the items of a filtered road go with it; the free overlay stays
    assert steps["rsSetClasses(['primary'])"] == ([100, 101], [1, 2])         # a hidden class: its items too
    assert steps["rsSetTunnels(false)"] == ([100, 102], [1, 2])               # a hidden tunnel: its items too
    assert steps["rsFilter(null)"][0] == steps["rsSetClasses(RS_CLASSES)"][0] == steps["rsSetTunnels(true)"][0] == [100, 101, 102]
    assert hover == [False, True, False]                                       # hovering the item of road 1 highlights road 1
    assert sel == [[1, 101, ["signs"]]] and selected == [False, True, False]   # clicking it selects road 1; its own fields come along


def _open(page, path, center, zoom):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(path.resolve().as_uri())
    page.wait_for_function("window.map && map.loaded()", timeout=30_000)
    page.evaluate(f"map.jumpTo({{center: {list(center)}, zoom: {zoom}}}); 0")
    page.wait_for_function("map.loaded()", timeout=30_000)
    page.evaluate("new Promise(r => { map.once('idle', r); map.triggerRepaint(); setTimeout(r, 3000); })")
    return errors


def test_each_direction_and_each_item_selects_its_own_edge_or_itself(tmp_path):
    """A two-way road's two directions are two edges side by side: a click on either selects that edge (even near the middle, where the
    tolerance box reaches both), and an item attached to either selects its own edge. An item of Overlay(select="item") is selected itself:
    its own highlight and popup, rs:select with the item and its road; hover highlights the item, not the road; a click elsewhere clears it."""
    import geopandas as gpd
    from shapely.geometry import LineString, Point

    from roadstyle import Overlay
    from roadstyle.render_web import render

    y0, y1 = 59.300, 59.3003
    g = gpd.GeoDataFrame({"highway": ["primary", "primary", "residential"], "oneway": [False, False, True], "edge_id": [10, 11, 12]},
                         geometry=[LineString([(18.000, y0), (18.004, y0)]), LineString([(18.004, y0), (18.000, y0)]),     # the two directions
                                   LineString([(18.000, y1), (18.004, y1)])], crs=4326)
    signs = gpd.GeoDataFrame({"edge_id": [10, 11], "kind": ["fwd", "back"]},          # 20 m off: south of the eastbound, north of the westbound
                             geometry=[Point(18.0012, y0 - 0.00018), Point(18.0028, y0 + 0.00018)], crs=4326)
    lanes = gpd.GeoDataFrame({"edge_id": [12], "lane": ["L1"]}, geometry=[LineString([(18.0005, y1), (18.0035, y1)])], crs=4326)
    path = tmp_path / "select.html"
    render(g, basemap="blank", overlays=[Overlay(signs, edge_col="edge_id", kind="circle", radius=8, label="signs", popup=["kind"]),
                                         Overlay(lanes, edge_col="edge_id", kind="line", width=6, label="lanes", popup=["lane"], select="item")]).save(path)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 600})
        errors = _open(page, path, (18.002, y0 + 0.00015), 18)
        page.evaluate("window.__sel = []; document.addEventListener('rs:select', e => __sel.push([e.detail.id, e.detail.properties.edge_id,"
                      " e.detail.item ? [e.detail.item.overlay, e.detail.item.properties.lane] : null]))")
        at = lambda lng, lat, dy=0: page.evaluate(f"(() => {{ const q = map.project([{lng}, {lat}]); return [q.x, q.y + {dy}]; }})()")  # noqa: E731
        fs = lambda src, i: page.evaluate(f"map.getFeatureState({{source: '{src}', id: {i}}})")                                                        # noqa: E731
        got = {}
        for name, xy in (("south lane", at(18.0015, y0, 7)), ("north lane", at(18.0015, y0, -7)), ("south of the middle", at(18.0015, y0, 2)),
                         ("north of the middle", at(18.0015, y0, -2)), ("sign fwd", at(18.0012, y0 - 0.00018)), ("sign back", at(18.0028, y0 + 0.00018))):
            page.evaluate("document.querySelectorAll('.maplibregl-popup').forEach(e => e.remove())")    # the last popup would take the click
            page.mouse.click(*xy)
            page.wait_for_timeout(150)
            got[name] = page.evaluate("__sel[__sel.length - 1]")
        lane = at(18.0015, y1)
        page.mouse.move(*lane)
        page.wait_for_timeout(700)
        hover = (fs("ov1", 0).get("hover"), fs("roads", 2).get("hover"))
        page.mouse.click(*lane)
        page.wait_for_timeout(300)
        got["lane"] = page.evaluate("__sel[__sel.length - 1]")
        selected = (fs("ov1", 0).get("select"), fs("roads", 2).get("select"))
        popup = page.evaluate("[...document.querySelectorAll('.maplibregl-popup-content')].map(e => e.textContent).join('|')")
        page.evaluate("document.querySelectorAll('.maplibregl-popup').forEach(e => e.remove())")
        page.mouse.click(*at(18.0015, y0 - 0.00025))                                  # nothing there
        page.wait_for_timeout(200)
        cleared = fs("ov1", 0).get("select")
        browser.close()
    assert errors == []
    assert got["south lane"][:2] == got["south of the middle"][:2] == got["sign fwd"][:2] == [0, 10]     # the eastbound drives on the south
    assert got["north lane"][:2] == got["north of the middle"][:2] == got["sign back"][:2] == [1, 11]
    assert got["lane"] == [2, 12, ["lanes", "L1"]]                           # the item and its road
    assert hover == (True, None) and selected == (True, None) and not cleared
    assert "lanes" in popup and "L1" in popup


def test_the_class_filter_hides_the_names_and_arrows_of_a_class(tmp_path):
    """With filter_col, a name or an arrow (whose slot carries the chain's highway) hides with its road's class (__rs_cls)."""
    import geopandas as gpd
    from shapely.geometry import LineString

    from roadstyle.render_web import render

    ys = [59.3000, 59.3006]
    g = gpd.GeoDataFrame({"highway": ["primary"] * 2, "fc": ["A", "B"], "name": ["Alpha", "Beta"], "oneway": [True, True]},
                         geometry=[LineString([(18.000, y), (18.004, y)]) for y in ys], crs=4326)
    path = tmp_path / "classes.html"
    render(g, basemap="blank", filter_col="fc", labels=True, arrows=True).save(path)
    shown = """async call => { eval(call); await new Promise(r => { map.once('idle', r); map.triggerRepaint(); setTimeout(r, 3000); });
      const ids = map.getStyle().layers.map(l => l.id).filter(id => /^roads-(labels|arrows)/.test(id));
      return [...new Set(map.queryRenderedFeatures({layers: ids}).map(f => f.layer.id.split('-')[1] + ':' + f.properties.name))].sort(); }"""
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 600})
        errors = _open(page, path, (18.0012, 59.3003), 18)                    # a name and its road's arrow apart
        steps = {c: page.evaluate(shown, c) for c in ("0", "rsSetClasses(['A'])", "rsSetClasses(RS_CLASSES)")}
        browser.close()
    assert errors == []
    assert steps["0"] == steps["rsSetClasses(RS_CLASSES)"] == ["arrows:Alpha", "arrows:Beta", "labels:Alpha", "labels:Beta"]
    assert steps["rsSetClasses(['A'])"] == ["arrows:Alpha", "labels:Alpha"]
