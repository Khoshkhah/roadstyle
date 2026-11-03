"""Street View beside Google: the window's provider switch (Google / Panoramax / Mapillary), the nearest photo of a provider in its own viewer, the
coverage layers, and the credit rows. The services are answered by the test (no network). Skipped without playwright."""
import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _edges, _open  # noqa: E402

import roadstyle as rs  # noqa: E402

_PAN = {"features": [{"id": "pic-123", "geometry": {"type": "Point", "coordinates": [18.0, 59.305]},
                      "properties": {"view:azimuth": 10, "geovisio:producer": "someone"},
                      "assets": {"sd": {"href": "https://pics.example/pic-123/sd.jpg"}}}]}
_MLY = {"data": [{"id": "999", "geometry": {"type": "Point", "coordinates": [18.0003, 59.305]}},
                 {"id": "111", "geometry": {"type": "Point", "coordinates": [18.0, 59.3051]}}]}
_BLANK = "<html><body>viewer</body></html>"
# stand-ins for the two viewer libraries (loaded from a CDN): they keep what they were given and their listeners
_PSV_JS = """export class Viewer{constructor(o){window.__psv=o; window.__psvl={}; this.yaw=0.5; window.__psvv=this;}
addEventListener(n,f){window.__psvl[n]=f;} setPanorama(u,o){window.__psvgo=[u,o]; return Promise.resolve();}
setOptions(o){window.__psvopt=o;} zoom(){} rotate(p){window.__psvrot=p;} getPosition(){return {yaw:this.yaw,pitch:0};} destroy(){window.__psvgone=true;}}"""
_MLY_JS = """window.mapillary={Viewer:class{constructor(o){window.__mly=o; window.__mlyh={};} on(n,f){window.__mlyh[n]=f;}
moveTo(id){window.__mlyto=id; return Promise.resolve();} resize(){} remove(){window.__mlygone=true;}}};"""


def _run(tmp_path, body, panoramax=_PAN, mapillary=_MLY):
    path = tmp_path / "d.html"
    rs.render_dashboard(_edges(), basemap="blank", street_view="window", road_popup=False).save(path)      # no popup over the coverage dots
    asked = []
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            def route(r):
                u = r.request.url
                asked.append(u)
                if "/api/search" in u:
                    return r.fulfill(json=panoramax, headers={"access-control-allow-origin": "*"})
                if "/api/collections/" in u:
                    return r.fulfill(json={"id": "dot-1", "geometry": {"type": "Point", "coordinates": [18.0, 59.3052]},
                                           "properties": {"view:azimuth": 200, "geovisio:producer": "x"},
                                           "assets": {"sd": {"href": "https://pics.example/dot-1/sd.jpg"}}}, headers={"access-control-allow-origin": "*"})
                if "graph.mapillary.com" in u:
                    return r.fulfill(json=mapillary, headers={"access-control-allow-origin": "*"})
                if ".mvt" in u or "tiles.mapillary.com" in u:
                    return r.fulfill(status=204, headers={"access-control-allow-origin": "*"})
                if "cdn.jsdelivr.net" in u:
                    js = _PSV_JS if "photo-sphere-viewer" in u and u.endswith("+esm") else _MLY_JS if u.endswith("mapillary.js") else ""
                    return r.fulfill(body=js, content_type="text/css" if u.endswith(".css") else "application/javascript",
                                     headers={"access-control-allow-origin": "*"})
                r.fulfill(body=_BLANK, content_type="text/html")
            for host in ("api.panoramax.xyz", "panoramax.openstreetmap.fr", "graph.mapillary.com", "tiles.mapillary.com", "www.mapillary.com", "www.google.com", "cdn.jsdelivr.net"):
                page.route(f"https://{host}/**", route)
            page.evaluate("localStorage.clear()")
            xy = page.evaluate("(() => { const p = map.project([18.0, 59.305]); const r = map.getCanvas().getBoundingClientRect(); return [r.left + p.x, r.top + p.y]; })()")
            page.mouse.move(xy[0] - 30, xy[1] - 30)
            page.mouse.move(*xy, steps=5)                                                # a road is picked where the mouse hovers it
            page.wait_for_function("map.getCanvas().style.cursor === 'pointer'", timeout=5000)
            page.mouse.click(*xy)
            page.evaluate("rsSetStreetView(true)")                                       # opened after the pick: the window would cover the road
            page.wait_for_function("!document.querySelector('.rs-svw-msg').textContent.startsWith('Click a road')")
            body(page, asked)
        finally:
            browser.close()
    assert [e for e in errors if "accelerometer" not in e] == []


def _pick(page, name):
    page.click(f".rs-svw-prov button[data-p='{name}']")


def test_the_window_offers_the_three_providers_and_starts_on_google(tmp_path):
    def body(page, asked):
        assert page.locator(".rs-svw-prov button").all_inner_texts() == ["Google", "Panoramax", "Mapillary"]
        assert page.locator(".rs-svw-prov button.on").inner_text() == "Google"
        assert page.locator(".rs-svw-cov").is_hidden()                                   # Google has no coverage layer here
        assert "needs this page served" in page.inner_text(".rs-svw-msg")               # Google's embed stays grey in a file:// page (the others do not)
    _run(tmp_path, body)


def test_the_close_button_stays_at_the_top_right_when_the_pointer_is_on_it(tmp_path):
    # the tooltip code takes a button's `title` away on hover: a rule that finds the button by its title let it fall into the second row
    def body(page, asked):
        _pick(page, "panoramax")
        x = page.locator(".rs-svw:not(.rs-g3d) .rs-svw-x")
        x.hover()
        assert not page.evaluate("document.querySelector('.rs-svw:not(.rs-g3d) .rs-svw-x').hasAttribute('title')")
        b, w = x.bounding_box(), page.locator(".rs-svw:not(.rs-g3d)").bounding_box()
        assert b["y"] - w["y"] < 12 and (w["x"] + w["width"]) - (b["x"] + b["width"]) < 12
    _run(tmp_path, body)


def test_panoramax_shows_the_nearest_photo_with_no_key_and_remembers_the_choice(tmp_path):
    def body(page, asked):
        _pick(page, "panoramax")
        page.wait_for_function("window.__psv")
        assert page.evaluate("window.__psv.panorama") == "https://pics.example/pic-123/sd.jpg"
        assert page.locator(".rs-svw-alt").is_visible()
        assert any("place_position=18.0" in u and "place_distance=0-30" in u for u in asked)
        assert page.evaluate("localStorage.getItem('rs-street-view-provider')") == "panoramax"
        assert page.locator(".rs-svw:not(.rs-g3d) .rs-svw-mode").is_hidden()                                  # Linked / Classic are Google's
        _pick(page, "google")
        assert page.locator(".rs-svw-alt").is_hidden() and page.evaluate("window.__psvgone") is True
        assert "needs this page served" in page.inner_text(".rs-svw-msg")
    _run(tmp_path, body)


def test_the_marker_turns_with_the_view_in_the_panoramax_window(tmp_path):
    def body(page, asked):
        _pick(page, "panoramax")
        page.wait_for_function("window.__psv")
        page.evaluate("window.__psvv.yaw = 1.0; window.__psvl['position-updated']()")      # turned 1 rad = 57.3 degrees from the photo's 10
        page.wait_for_function("Math.abs(rsGetStreetViewSpot().heading - 67.3) < 0.5")
    _run(tmp_path, body)


def test_the_marker_turns_and_moves_with_the_view_in_the_mapillary_window(tmp_path):
    def body(page, asked):
        page.evaluate("localStorage.setItem('rs-key:mapillary', 'MLY|test')")
        _pick(page, "mapillary")
        page.wait_for_function("window.__mly")
        page.evaluate("window.__mlyh.image({image: {lngLat: {lng: 18.0, lat: 59.3051}}}); window.__mlyh.bearing({bearing: 77})")
        page.wait_for_function("Math.abs(rsGetStreetViewSpot().heading - 77) < 0.5")
    _run(tmp_path, body)


def test_no_photo_within_50_m_is_said_and_not_hidden_behind_the_last_photo(tmp_path):
    def body(page, asked):
        _pick(page, "panoramax")
        page.wait_for_function("document.querySelector('.rs-svw-msg').textContent.startsWith('No Panoramax')")
        assert "No Panoramax photos within 30 m" in page.inner_text(".rs-svw-msg")
        assert page.locator(".rs-svw-alt").is_hidden()
    _run(tmp_path, body, panoramax={"features": []})


def test_mapillary_asks_for_a_token_then_picks_the_nearest_of_its_images(tmp_path):
    def body(page, asked):
        _pick(page, "mapillary")
        page.wait_for_selector(".rs-svw-msg:visible")
        assert "free token" in page.inner_text(".rs-svw-msg")
        assert not any("graph.mapillary.com" in u for u in asked)                        # nothing is asked without a token
        page.evaluate("localStorage.setItem('rs-key:mapillary', 'MLY|test')")
        _pick(page, "google")
        _pick(page, "mapillary")
        page.wait_for_function("window.__mly")
        assert page.evaluate("window.__mly.imageId") == "111" and page.evaluate("window.__mly.accessToken") == "MLY|test"   # 111 stands nearer the spot than 999
        graph = [u for u in asked if "graph.mapillary.com" in u]
        assert graph and "access_token=MLY%7Ctest" in graph[-1] and "bbox=17.999472" in graph[-1]
    _run(tmp_path, body)


def test_coverage_is_drawn_for_the_chosen_provider_and_goes_with_the_window(tmp_path):
    def layers(page):
        return page.evaluate("['rs-sv-cov-load','rs-sv-cov-lines','rs-sv-cov-dots'].filter(i => map.getLayer(i))")

    def body(page, asked):
        _pick(page, "panoramax")
        assert layers(page) == []
        page.click(".rs-svw-cov")
        assert layers(page) == ["rs-sv-cov-load", "rs-sv-cov-lines", "rs-sv-cov-dots"]
        assert page.evaluate("map.getLayer('rs-sv-cov-load').sourceLayer") == "sequences"
        assert page.evaluate("localStorage.getItem('rs-street-view-cov')") == "1"
        _pick(page, "google")                                                            # Google has none: the layers go
        assert layers(page) == []
        page.evaluate("localStorage.setItem('rs-key:mapillary', 'MLY|test')")
        _pick(page, "mapillary")
        assert page.evaluate("map.getLayer('rs-sv-cov-load').sourceLayer") == "sequence"
        assert "mly1_public" in json.dumps(page.evaluate("map.getSource('rs-sv-cov').serialize().tiles"))
        page.evaluate("rsSetStreetView(false)")
        assert layers(page) == [] and page.evaluate("!map.getSource('rs-sv-cov')")
        page.evaluate("rsSetStreetView(true)")                                           # the switch is remembered: back with the window
        assert layers(page) == ["rs-sv-cov-load", "rs-sv-cov-lines", "rs-sv-cov-dots"]
    _run(tmp_path, body)


def test_a_click_on_a_coverage_dot_opens_that_photo_and_puts_the_marker_there(tmp_path):
    def body(page, asked):
        _pick(page, "panoramax")
        page.click(".rs-svw-cov")
        page.wait_for_function("map.getSource('rs-sv-cov-out')")
        page.evaluate("""() => { const q = map.querySourceFeatures.bind(map);      // the (empty) tiles are given one photo
            map.querySourceFeatures = (id, o) => o.sourceLayer === 'pictures' ? [{type: 'Feature',
              properties: {id: 'dot-1', first_sequence: 'seq-1', heading: 200}, geometry: {type: 'Point', coordinates: [18.0, 59.3052]}}] : q(id, o);
            map.fire('moveend'); }""")
        page.wait_for_function("map.queryRenderedFeatures({layers: ['rs-sv-cov-dots']}).length > 0")
        page.evaluate("map.jumpTo({center: [18.0, 59.3052]}); map.panBy([-400, 0], {duration: 0})")      # the dot, clear of the window
        page.wait_for_timeout(500)
        xy = page.evaluate("(() => { const p = map.project([18.0, 59.3052]); const r = map.getCanvas().getBoundingClientRect(); return [r.left + p.x, r.top + p.y]; })()")
        page.mouse.click(*xy)
        page.wait_for_function("window.__psvgo && window.__psvgo[0] === 'https://pics.example/dot-1/sd.jpg' || (window.__psv && window.__psv.panorama === 'https://pics.example/dot-1/sd.jpg')")
        assert any("/api/collections/seq-1/items/dot-1" in u for u in asked)
        assert page.evaluate("map.getSource('rs-sv-cov-sel')._data.geojson.features.length") == 1          # a ring marks the opened photo
        page.evaluate("window.__psvv.yaw = 0; window.__psvl['position-updated']()")                  # looking straight ahead in the photo
        spot = page.evaluate("rsGetStreetViewSpot()")
        assert abs(spot["lng"] - 18.0) < 1e-4 and abs(spot["lat"] - 59.3052) < 1e-4 and abs(spot["heading"] - 200) < 1 and spot["onRoad"] is False      # on the road, yet kept where the photo was taken
    _run(tmp_path, body)


def test_mapillary_coverage_waits_for_the_token(tmp_path):
    def body(page, asked):
        _pick(page, "mapillary")
        page.click(".rs-svw-cov")
        assert page.evaluate("!map.getLayer('rs-sv-cov-load')")
    _run(tmp_path, body)


def test_coverage_lines_are_cut_at_the_edge_of_the_area():
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content("<script>" + __import__("pathlib").Path("src/roadstyle/static/dashboard/svproviders.js").read_text().replace("import ", "//import ").replace("export ", "")
                         .replace("savedKey(", "(()=>'')(") + "</script>")
        got = page.evaluate("""() => ({
            cut: _spCut([[-5, 5], [5, 5], [15, 5]], [0, 0, 10, 10]),
            out: _spCut([[-5, 20], [15, 20]], [0, 0, 10, 10]),
            twice: _spCut([[-5, 5], [5, 5], [20, 20], [20, 8], [8, 8]], [0, 0, 10, 10]),
            tri: _spCutRings([[-5, 2], [15, 2]], [[[0, 0], [10, 0], [0, 10], [0, 0]]]),
            pin: [_spIn([[[0, 0], [10, 0], [0, 10], [0, 0]]], 2, 2), _spIn([[[0, 0], [10, 0], [0, 10], [0, 0]]], 8, 8)]})""")
        browser.close()
    assert got["cut"] == [[[0, 5], [5, 5], [10, 5]]] and got["out"] == []
    assert len(got["twice"]) == 2
    assert got["tri"] == [[[0, 2], [8, 2]]] and got["pin"] == [True, False]          # a boundary that is not a rectangle cuts to its own shape
