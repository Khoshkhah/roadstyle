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


def _run(tmp_path, body, panoramax=_PAN, mapillary=_MLY, items=None):
    path = tmp_path / "d.html"
    rs.render_dashboard(_edges(), basemap="blank", street_view="window", road_popup=False, dashboard={"panel": None}).save(path)      # no popup over the coverage dots; no panel: it is not used
    asked = []
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            def route(r):
                u = r.request.url
                asked.append(u)
                if "/api/search" in u:
                    return r.fulfill(json=panoramax, headers={"access-control-allow-origin": "*"})
                if "/api/collections/" in u and u.rsplit("/", 1)[-1] in (items or {}):
                    return r.fulfill(json=items[u.rsplit("/", 1)[-1]], headers={"access-control-allow-origin": "*"})
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
        assert page.locator(".rs-svw:not(.rs-g3d) .rs-svw-mode").count() == 0                                 # the bar has no Linked / Classic switch
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
        # no road is selected, so no photos were loaded for one: the photos around this photo are asked for, as a box (a "near this point" search gives only the nearest photo of each sequence)
        assert any("/api/search" in u and "bbox=" in u and "limit=100" in u for u in asked)
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


@pytest.mark.parametrize("steps, popups", [("", 1), ("rsSetStreetView(true)", 0), ("rsSetStreetView(true); rsSetStreetView(false)", 1)])
def test_no_road_popup_while_street_view_is_open(tmp_path, steps, popups):
    path = tmp_path / "d.html"
    rs.render_dashboard(_edges(), basemap="blank", street_view="window").save(path)        # road_popup stays on (the default)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            page.evaluate(steps or "0")
            page.wait_for_timeout(200)
            page.evaluate("rsSelect(rsQuery(p => p.name)[5])")
            page.wait_for_timeout(300)
            assert page.evaluate("document.querySelectorAll('.maplibregl-popup').length") == popups      # open: the road is selected, with no popup
            assert not errors
        finally:
            browser.close()


def test_the_google_frame_is_credentialless(tmp_path):
    # a page with COEP require-corp (duckOSM Studio) blocks a cross-origin frame that has no `credentialless`: "refused to connect"
    def body(page, asked):
        assert page.evaluate("document.querySelector('.rs-svw:not(.rs-g3d) iframe').hasAttribute('credentialless')")
    _run(tmp_path, body)


def test_the_street_view_page_frame_is_credentialless():
    assert 'id="sv-frame" title="Google Street View" hidden allowfullscreen credentialless' in rs.render_street_view(_edges()).html


@pytest.mark.parametrize("kw, visible", [({"street_view_key": "AIzaTEST"}, False), ({"street_view_key": "AIzaTEST", "street_view_mode": "classic"}, True), ({}, True)])
def test_the_bar_has_step_buttons_except_in_the_linked_panel(tmp_path, kw, visible):
    """Linked (a key, no `street_view_mode`) has no ◀ ▶ buttons in the bar: the panorama has Google's own arrows. Classic, and a page with no key, have them."""
    path = tmp_path / "d.html"
    rs.render_dashboard(_edges(), basemap="blank", street_view="window", dashboard={"panel": None}, **kw).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            page.route("https://maps.googleapis.com/**", lambda r: r.fulfill(body="", content_type="text/javascript"))
            page.evaluate("rsSetStreetView(true)")
            shown = page.evaluate("!!document.querySelector('.rs-svw:not(.rs-g3d) .rs-svw-step').offsetParent")
        finally:
            browser.close()
    assert shown is visible


def test_a_narrow_street_view_window_keeps_a_long_name_and_the_provider_tabs_in_one_row(tmp_path):
    """Under 440 px, the name of the road is cut with an ellipsis, so the provider tabs stay on the row of the name."""
    path = tmp_path / "d.html"
    rs.render_dashboard(_edges(), basemap="blank", street_view="window", dashboard={"panel": None}).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            page.route("https://www.google.com/**", lambda r: r.fulfill(body="<html></html>", content_type="text/html"))
            page.evaluate("rsSetStreetView(true)")
            got = page.evaluate("""() => { const w = document.querySelector('.rs-svw:not(.rs-g3d)'); w.style.width = '340px';
                const t = w.querySelector('.rs-svw-t'); t.textContent = 'Boulevard Princesse Charlotte of Monaco, the long road';
                return new Promise(r => setTimeout(() => { const kids = [...w.querySelector('.rs-svw-bar').children].filter(e => e.offsetParent && !e.classList.contains('rs-svw-x'));
                  const mid = e => { const b = e.getBoundingClientRect(); return (b.top + b.bottom) / 2; }, mids = kids.map(mid);
                  r({narrow: w.classList.contains('rs-svw-narrow'), spread: Math.max(...mids) - Math.min(...mids), cut: t.scrollWidth > t.clientWidth}); }, 400)); }""")
        finally:
            browser.close()
    assert got["narrow"] and got["spread"] < 6 and got["cut"], got


def _photo(i, lng, lat, az=0):
    return {"id": f"p{i}", "geometry": {"type": "Point", "coordinates": [lng, lat]}, "properties": {"view:azimuth": az, "geovisio:producer": "x"},
            "assets": {"sd": {"href": f"https://pics.example/p{i}/sd.jpg"}}}


def test_panoramax_has_arrows_over_its_picture_chosen_as_mapillary_chooses_and_mapillary_has_none(tmp_path):
    """Like Mapillary's viewer: at most one arrow on the picture for each of forward, left, back and right (the best photo of each: up to 20 m away, within 30 degrees of that
    direction, looking about the way this photo looks); a click goes to that photo and the marker goes where it was taken. The bar has no steps for Panoramax and Mapillary."""
    # the road runs north along 18.0, the spot is at 59.305, 0.00015 degrees of latitude are 16.6 m: p1 is behind p2, p3 and p4 ahead, p5 is 12 m to the west and looks north too,
    # p6 is a side street photo that looks west (it is not a step: it looks another way)
    pts = [(18.0, 59.30480), (18.0, 59.30495), (18.0, 59.30510), (18.0, 59.30525), (17.99977, 59.30495), (18.0, 59.30485)]
    photos = [_photo(i + 1, lng, lat, 270 if i == 5 else 0) for i, (lng, lat) in enumerate(pts)]

    def body(page, asked):
        _pick(page, "panoramax")
        page.wait_for_function("window.__psv")
        assert page.evaluate("window.__psv.panorama") == "https://pics.example/p2/sd.jpg"      # the photo nearest to the spot
        arrows = lambda: sorted(round(float(b)) for b in page.eval_on_selector_all(".rs-svw-nav button", "bs => bs.map(b => b.dataset.bearing)"))   # noqa: E731
        assert arrows() == [0, 180, 270]                                                  # p3 ahead, p1 behind, p5 on the left; p4 is a worse "ahead" than p3; p6 looks another way
        assert page.locator(".rs-svw-nav").is_visible() and page.locator(".rs-svw-step").is_hidden()
        page.click(".rs-svw-nav button[data-bearing^='0']")
        page.wait_for_function("window.__psvgo && window.__psvgo[0].endsWith('/p3/sd.jpg')", timeout=5000)
        assert page.evaluate("Math.abs(rsGetStreetViewSpot().lat - 59.30510) < 1e-6")      # the marker is where p3 was taken
        assert arrows() == [0, 180]                                                       # p4 ahead, p2 behind (p5 is 13 m to the left behind: neither)
        page.click(".rs-svw-nav button[data-bearing^='180']")
        page.wait_for_function("window.__psvgo[0].endsWith('/p2/sd.jpg')", timeout=5000)
        _pick(page, "mapillary")
        assert page.locator(".rs-svw-nav").is_hidden() and page.locator(".rs-svw-step").is_hidden()
    _run(tmp_path, body, panoramax={"features": photos})
