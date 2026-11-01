"""Street View beside Google: the window's provider switch (Google / Panoramax / Mapillary), the nearest photo of a provider in its own viewer, the
coverage layers, and the credit rows. The services are answered by the test (no network). Skipped without playwright."""
import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_dashboard_sections_browser import _edges, _open  # noqa: E402

import roadstyle as rs  # noqa: E402

_PAN = {"features": [{"id": "pic-123", "geometry": {"type": "Point", "coordinates": [18.0, 59.305]},
                      "properties": {"view:azimuth": 10, "geovisio:producer": "someone"}}]}
_MLY = {"data": [{"id": "999", "geometry": {"type": "Point", "coordinates": [18.0003, 59.305]}},
                 {"id": "111", "geometry": {"type": "Point", "coordinates": [18.0, 59.3051]}}]}
_BLANK = "<html><body>viewer</body></html>"


def _run(tmp_path, body, panoramax=_PAN, mapillary=_MLY):
    path = tmp_path / "d.html"
    rs.render_dashboard(_edges(), basemap="blank", street_view="window").save(path)
    asked = []
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            def route(r):
                u = r.request.url
                asked.append(u)
                if "/api/search" in u:
                    return r.fulfill(json=panoramax, headers={"access-control-allow-origin": "*"})
                if "graph.mapillary.com" in u:
                    return r.fulfill(json=mapillary, headers={"access-control-allow-origin": "*"})
                if ".mvt" in u or "tiles.mapillary.com" in u:
                    return r.fulfill(status=204, headers={"access-control-allow-origin": "*"})
                r.fulfill(body=_BLANK, content_type="text/html")
            for host in ("api.panoramax.xyz", "panoramax.openstreetmap.fr", "graph.mapillary.com", "tiles.mapillary.com", "www.mapillary.com", "www.google.com"):
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


def test_panoramax_shows_the_nearest_photo_with_no_key_and_remembers_the_choice(tmp_path):
    def body(page, asked):
        _pick(page, "panoramax")
        page.wait_for_function("(document.querySelector('.rs-svw iframe').getAttribute('src') || '').includes('pic=pic-123')")
        src = page.get_attribute(".rs-svw iframe", "src")
        assert src.startswith("https://panoramax.openstreetmap.fr/") and "xyz=" in src
        assert any("place_position=18.0" in u and "place_distance=0-50" in u for u in asked)
        assert page.evaluate("localStorage.getItem('rs-street-view-provider')") == "panoramax"
        assert page.locator(".rs-svw-mode").is_hidden()                                  # Linked / Classic are Google's
        _pick(page, "google")
        assert page.locator(".rs-svw iframe").is_hidden() and "needs this page served" in page.inner_text(".rs-svw-msg")
    _run(tmp_path, body)


def test_no_photo_within_50_m_is_said_and_not_hidden_behind_the_last_photo(tmp_path):
    def body(page, asked):
        _pick(page, "panoramax")
        page.wait_for_selector(".rs-svw-msg:visible")
        assert "No Panoramax photos within 50 m" in page.inner_text(".rs-svw-msg")
        assert page.locator(".rs-svw iframe").is_hidden()
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
        page.wait_for_function("(document.querySelector('.rs-svw iframe').getAttribute('src') || '').includes('image_key=')")
        assert page.get_attribute(".rs-svw iframe", "src").endswith("image_key=111")     # 111 stands nearer the spot than 999
        graph = [u for u in asked if "graph.mapillary.com" in u]
        assert graph and "access_token=MLY%7Ctest" in graph[-1] and "radius=50" in graph[-1]
    _run(tmp_path, body)


def test_coverage_is_drawn_for_the_chosen_provider_and_goes_with_the_window(tmp_path):
    def layers(page):
        return page.evaluate("['rs-sv-cov-lines','rs-sv-cov-dots'].filter(i => map.getLayer(i))")

    def body(page, asked):
        _pick(page, "panoramax")
        assert layers(page) == []
        page.click(".rs-svw-cov")
        assert layers(page) == ["rs-sv-cov-lines", "rs-sv-cov-dots"]
        assert page.evaluate("map.getLayer('rs-sv-cov-lines').sourceLayer") == "sequences"
        assert page.evaluate("localStorage.getItem('rs-street-view-cov')") == "1"
        _pick(page, "google")                                                            # Google has none: the layers go
        assert layers(page) == []
        page.evaluate("localStorage.setItem('rs-key:mapillary', 'MLY|test')")
        _pick(page, "mapillary")
        assert page.evaluate("map.getLayer('rs-sv-cov-lines').sourceLayer") == "sequence"
        assert "mly1_public" in json.dumps(page.evaluate("map.getSource('rs-sv-cov').serialize().tiles"))
        page.evaluate("rsSetStreetView(false)")
        assert layers(page) == [] and page.evaluate("!map.getSource('rs-sv-cov')")
        page.evaluate("rsSetStreetView(true)")                                           # the switch is remembered: back with the window
        assert layers(page) == ["rs-sv-cov-lines", "rs-sv-cov-dots"]
    _run(tmp_path, body)


def test_mapillary_coverage_waits_for_the_token(tmp_path):
    def body(page, asked):
        _pick(page, "mapillary")
        page.click(".rs-svw-cov")
        assert page.evaluate("!map.getLayer('rs-sv-cov-lines')")
    _run(tmp_path, body)
