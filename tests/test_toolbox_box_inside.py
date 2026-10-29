"""A box of the bar (the settings, the colour box, the attribution) keeps 12 px from the top and the bottom of the window, whatever the height of the window and
whichever edge of the box is fixed to the bar. The settings have no "Reset transparency" button and no note about the key, and the value of a slider is
in the row of its label. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_URL = "http://rs.test/page.html"
_BOX = """async (id) => { rs.tools.open(id); await new Promise(f => requestAnimationFrame(() => requestAnimationFrame(f))); const r = document.querySelector(id === "settings" ? "#rs-settings-box" : "#rs-attr-box").getBoundingClientRect();
  const sl = document.querySelector(".rs-set-slide"), lab = sl && sl.querySelector("span").getBoundingClientRect(), val = sl && sl.querySelector("b").getBoundingClientRect();
  const out = {top: r.top, bottom: r.bottom, same_row: !sl || Math.abs(lab.top - val.top) < 6, text: document.querySelector("#rs-settings-box").textContent}; rs.tools.close(id); return out; }"""


def _serve(html):
    return lambda route, request: route.fulfill(content_type="text/html", body=html)


def _edges():
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary", "residential"], "edge_id": [1, 2]}, crs=4326,
                            geometry=[LineString([(18.0, 59.3), (18.001, 59.301)]), LineString([(18.002, 59.3), (18.003, 59.301)])])


def test_the_boxes_of_the_bar_stay_inside_the_window_and_the_settings_have_no_reset_or_key_note():
    html, errors = rs.render_dashboard(_edges(), basemap="blank").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        for height in (900, 760, 600, 480):
            page = browser.new_page(viewport={"width": 1280, "height": height})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(_URL, lambda r: r.fulfill(content_type="text/html", body=html))
            page.goto(_URL)
            page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
            for box in ("settings", "attribution"):
                r = page.evaluate(_BOX, box)
                assert r["top"] >= 11 and r["bottom"] <= height - 11, (height, box, r)
            assert r["same_row"] or box == "attribution", r
            assert "Reset transparency" not in r["text"] and "never written into the page file" not in r["text"]
            page.close()
        browser.close()
    assert not errors, errors


def test_a_tooltip_of_the_bar_does_not_cover_the_bar_after_an_earlier_one():
    """The tooltip is measured at the corner of the window. It was measured where the last one stood: at the right edge it wrapped narrower, then grew over the bar."""
    html, errors = rs.render_dashboard(_edges(), basemap="blank", dashboard={"toolbar": {"position": "right", "navigation": "buttons"}}).html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1100, "height": 760})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(_URL, lambda r: r.fulfill(content_type="text/html", body=html))
        page.goto(_URL)
        page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
        seen = []
        for title in ("Zoom in", "Google 3D is off", "Zoom in", "Drag to turn"):
            button = page.locator(f"#rs-toolbar button[title^='{title}'], #rs-toolbar button[data-rs-tip^='{title}']").first
            button.hover()
            page.wait_for_selector("#rs-tip:not([hidden])", timeout=3000)
            seen.append(page.evaluate("""() => { const t = document.querySelector('#rs-tip').getBoundingClientRect(), b = document.querySelector('#rs-toolbar').getBoundingClientRect();
                return {tipRight: t.right, tipLeft: t.left, barLeft: b.left, w: t.width}; }"""))
            page.mouse.move(5, 5)
            page.wait_for_selector("#rs-tip", state="hidden", timeout=3000)
        browser.close()
    assert not errors, errors
    assert all(s["tipRight"] <= s["barLeft"] + 1 and s["w"] <= 222 for s in seen), seen


def test_dragging_the_compass_changes_the_tilt_and_a_click_sets_north_and_the_tilt_back():
    html, errors = rs.render_dashboard(_edges(), basemap="blank", dashboard={"toolbar": {"navigation": "buttons"}}).html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1100, "height": 760})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(_URL, lambda r: r.fulfill(content_type="text/html", body=html))
        page.goto(_URL)
        page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
        box = page.locator(".maplibregl-ctrl-compass").bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 20, y - 60, steps=8)          # right turns the map, up tilts it
        page.mouse.up()
        page.wait_for_timeout(300)
        moved = page.evaluate("[map.getPitch(), map.getBearing()]")
        page.locator(".maplibregl-ctrl-compass").click()
        page.wait_for_timeout(1200)
        reset = page.evaluate("[map.getPitch(), map.getBearing()]")
        browser.close()
    assert not errors, errors
    assert moved[0] > 5 and abs(moved[1]) > 1, moved
    assert reset[0] < 1 and abs(reset[1]) < 1, reset


def test_navigation_box_is_one_button_with_the_compass_needle_and_ctrl_drag_turns_and_tilts_the_map():
    buttons = rs.render_dashboard(_edges(), basemap="blank", dashboard={"toolbar": {"navigation": "buttons"}}).html
    one = rs.render_dashboard(_edges(), basemap="blank").html                                   # the default
    errors, tools, got = [], [], None
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        for html in (buttons, one):
            page = browser.new_page(viewport={"width": 1100, "height": 760})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(_URL, _serve(html))
            page.goto(_URL)
            page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
            tools.append(page.evaluate("rs.tools.list().map(t => t.id)"))
            if html is one:
                page.evaluate("rs.tools.open('navigate')")
                got = page.evaluate("""async () => { const set = (k, v) => { const i = document.querySelector('#rs-nav-box [data-k=' + k + ']'); i.value = v; i.dispatchEvent(new Event('input')); };
                    set('p', 50); set('b', -40); set('z', 15.5); await new Promise(r => setTimeout(r, 300));
                    const a = [Math.round(map.getPitch()), Math.round(map.getBearing()), +map.getZoom().toFixed(1)];
                    const needle = document.querySelector('#rs-toolbar .rs-nav-ctrl .rs-needle').getAttribute('transform');
                    document.querySelector('#rs-nav-box .rs-nb-reset').click(); await new Promise(r => setTimeout(r, 800));
                    return {set: a, needle, reset: [Math.round(map.getPitch()), Math.round(map.getBearing())]}; }""")
                page.evaluate("rs.tools.close('navigate')")
                page.mouse.move(700, 400)                          # Ctrl + drag on the map: MapLibre's own turn and tilt
                page.keyboard.down("Control")
                page.mouse.down()
                page.mouse.move(760, 340, steps=8)
                page.mouse.up()
                page.keyboard.up("Control")
                page.wait_for_timeout(300)
                got["ctrl_drag"] = page.evaluate("[Math.round(map.getPitch()), Math.round(map.getBearing())]")
            page.close()
        browser.close()
    assert not errors, errors
    assert {"zoom_in", "zoom_out", "compass", "view3d"} <= set(tools[0]) and "navigate" not in tools[0]
    assert "navigate" in tools[1] and not {"zoom_in", "zoom_out", "compass", "view3d"} & set(tools[1])
    assert got["set"] == [50, -40, 15.5] and got["reset"] == [0, 0] and "rotate(40" in got["needle"], got
    assert got["ctrl_drag"][0] > 3 or abs(got["ctrl_drag"][1]) > 3, got


def test_a_button_whose_box_is_open_shows_no_tooltip():
    html, errors = rs.render_dashboard(_edges(), basemap="blank").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1100, "height": 760})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(_URL, lambda r: r.fulfill(content_type="text/html", body=html))
        page.goto(_URL)
        page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
        button = page.locator("#rs-toolbar .rs-nav-ctrl button").first
        button.hover()
        page.wait_for_selector("#rs-tip:not([hidden])", timeout=3000)            # closed: it explains itself
        button.click()                                                          # the box opens
        page.mouse.move(5, 5)
        button.hover()
        page.wait_for_timeout(900)
        shown = page.evaluate("!!document.querySelector('#rs-tip') && !document.querySelector('#rs-tip').hidden")
        browser.close()
    assert not errors, errors
    assert shown is False


def test_the_credits_button_is_in_the_corner_box_on_the_side_opposite_to_the_panel_and_in_the_bar_on_a_phone():
    left, right = rs.render_dashboard(_edges(), basemap="blank").html, rs.render_dashboard(_edges(), basemap="blank", dashboard={"panel": {"side": "right"}}).html
    errors, seen = [], {}
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        for name, html, width in (("panel at the left", left, 1200), ("panel at the right", right, 1200), ("phone", left, 500)):
            page = browser.new_page(viewport={"width": width, "height": 760})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(_URL, _serve(html))
            page.goto(_URL)
            page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
            page.wait_for_timeout(500)
            seen[name] = page.evaluate("""() => { const b = document.querySelector('.rs-attr-ctrl button'), r = b.getBoundingClientRect(), parent = b.closest('#rs-scalebox') ? 'corner' : b.closest('#rs-toolbar') ? 'bar' : 'elsewhere';
                const open = () => { rs.tools.open('attribution'); const x = document.querySelector('#rs-attr-box').getBoundingClientRect(); rs.tools.close('attribution'); return [x.top >= 0, x.left >= 0, x.right <= innerWidth, x.bottom <= innerHeight]; };
                return {parent, right: innerWidth - r.right, left: r.left, bottom: innerHeight - r.bottom, w: innerWidth, box: open()}; }""")
            page.close()
        browser.close()
    assert not errors, errors
    a, b, c = seen["panel at the left"], seen["panel at the right"], seen["phone"]
    assert a["parent"] == "corner" and a["right"] < 24 and a["bottom"] < 24 and all(a["box"]), a        # the bottom right corner
    assert b["parent"] == "corner" and b["left"] < 24 and b["bottom"] < 24 and all(b["box"]), b         # the bottom left corner
    assert c["parent"] == "bar", c


def test_the_credits_button_has_no_tooltip_but_a_label_for_a_screen_reader():
    html, errors = rs.render_dashboard(_edges(), basemap="blank").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1200, "height": 760})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(_URL, _serve(html))
        page.goto(_URL)
        page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
        button = page.locator(".rs-attr-ctrl button").first
        button.hover()
        page.wait_for_timeout(900)
        got = page.evaluate("""() => { const b = document.querySelector('.rs-attr-ctrl button'), t = document.getElementById('rs-tip');
            return {title: b.getAttribute('title'), label: b.getAttribute('aria-label'), tip: !!t && !t.hidden, tool: rs.tools.list().find(x => x.id === 'attribution').title}; }""")
        browser.close()
    assert not errors, errors
    assert got["title"] is None and got["label"] == "Attribution" and got["tip"] is False and got["tool"] == "Attribution", got
