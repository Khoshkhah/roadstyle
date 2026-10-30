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


def test_the_base_map_box_has_no_explanation_marks_and_the_credits_are_short():
    html, errors = rs.render_dashboard(_edges(), basemap="ofm_liberty").html, []
    sat = rs.render_dashboard(_edges(), basemap="satellite").html
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        out = []
        for page_html in (html, sat):
            page = browser.new_page(viewport={"width": 1200, "height": 800})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(_URL, _serve(page_html))
            page.goto(_URL)
            page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=90_000)
            page.evaluate("rs.tools.open('basemap')")
            page.wait_for_timeout(400)
            marks = page.evaluate("document.querySelectorAll('.rs-bm-i').length")
            page.evaluate("rs.tools.close('basemap'); rs.tools.open('attribution')")
            page.wait_for_timeout(400)
            out.append((marks, page.evaluate("[...document.querySelectorAll('#rs-attr-box .rs-attr-row')].map(r => r.textContent.trim())")))
            page.close()
        browser.close()
    assert not errors, errors
    assert out[0][0] == 0 and out[1][0] == 0, out
    for _, rows in out:
        assert rows and all(len(r) <= 50 and "Sources" not in r for r in rows), rows
        assert any("MapLibre" in r for r in rows), rows



def test_the_roads_tool_filters_the_road_types_with_all_none_and_show_only():
    import geopandas as gpd
    from shapely.geometry import LineString
    edges = gpd.GeoDataFrame({"highway": ["primary", "primary", "residential", "service"], "edge_id": [1, 2, 3, 4]}, crs=4326,
                             geometry=[LineString([(18.0 + i * 1e-3, 59.30), (18.0 + i * 1e-3, 59.31)]) for i in range(4)])
    html, errors = rs.render_dashboard(edges, basemap="blank").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1200, "height": 760})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(_URL, _serve(html))
        page.goto(_URL)
        page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
        got = page.evaluate("""async () => { const order = rs.tools.list().map(t => t.id), events = [];
            document.addEventListener('rs:filterchange', e => events.push(e.detail.visible ? e.detail.visible.join(',') : null));
            rs.tools.open('roads'); const box = document.querySelector('#rs-roads-box');
            const rows = [...box.querySelectorAll('.rs-rd-row')].map(r => [r.querySelector('button').textContent, r.querySelector('b').textContent, r.querySelector('input').checked]);
            const click = s => { box.querySelector(s).click(); return new Promise(r => setTimeout(r, 150)); };
            await click('button[data-only="primary"]'); const only = [...box.querySelectorAll('input[data-c]')].map(i => i.checked);
            await click('button[data-a="none"]'); const none = events[events.length - 1];
            await click('button[data-a="all"]'); const all = events[events.length - 1];
            return {order, rows, only, none, all}; }""")
        browser.close()
    assert not errors, errors
    assert got["order"].index("roads") == got["order"].index("basemap") + 1, got["order"]
    assert got["rows"] == [["primary", "2", True], ["residential", "1", True], ["service", "1", True]], got["rows"]
    assert got["only"] == [True, False, False] and got["none"] == "" and got["all"] == "primary,residential,service", got


def test_a_long_legend_label_wraps_inside_the_colour_box():
    html, errors = rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}}).html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(_URL, _serve(html))
        page.goto(_URL)
        page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
        got = page.evaluate("""() => { rs.legend.add({id: 'long', color: '#cccccc', label: 'counted: no range, a label that is much too long for one column'});
            rs.tools.open('legend'); const box = document.querySelector('#rs-color-box').getBoundingClientRect();
            return [...document.querySelectorAll('#rs-color-box .lg-row')].map(r => [Math.round(r.getBoundingClientRect().right - box.right), r.scrollWidth <= r.clientWidth + 1]); }""")
        browser.close()
    assert not errors, errors
    assert got and all(right <= 0 and fits for right, fits in got), got


def test_the_credits_list_has_the_pages_own_data_credit_first_and_not_twice():
    blank = rs.render_dashboard(_edges(), basemap="blank").html
    none = rs.render_dashboard(_edges(), basemap="blank", dashboard={"credits": []}).html
    liberty = rs.render_dashboard(_edges(), basemap="ofm_liberty").html
    errors, rows = [], []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        for html in (blank, none, liberty):
            page = browser.new_page(viewport={"width": 1200, "height": 800})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(_URL, _serve(html))
            page.goto(_URL)
            page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=90_000)
            page.evaluate("rs.tools.open('attribution')")
            page.wait_for_timeout(400)
            rows.append(page.evaluate("[...document.querySelectorAll('#rs-attr-box .rs-attr-row')].map(r => [r.textContent.trim(), r.getAttribute('href')])"))
            page.close()
        browser.close()
    assert not errors, errors
    # first: the credit of OpenStreetMap's data ("Data from OpenStreetMap" when the style's source gives the credit, else the page's own "\u00a9 OpenStreetMap contributors"), once
    assert rows[0][0][1] == "https://www.openstreetmap.org/copyright" and "OpenStreetMap" in rows[0][0][0] and rows[0][-1][0] == "MapLibre", rows[0]
    assert sum("OpenStreetMap" in r[0] for r in rows[0]) == 1, rows[0]
    # credits=[] leaves out the page's own credit. With the blank base map MapLibre lists no source, so the credit that the style's roads source carries (OpenStreetMap) is the row
    assert [r[0] for r in rows[1]] == ["Data from OpenStreetMap", "MapLibre"], rows[1]
    assert sum("OpenStreetMap" in r[0] for r in rows[2]) == 1, rows[2]                                           # the base map names it: not twice


def test_the_default_base_map_list_has_no_openfreemap_bright():
    html, errors = rs.render_dashboard(_edges(), basemap="blank").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(_URL, _serve(html))
        page.goto(_URL)
        page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
        page.evaluate("rs.tools.open('basemap')")
        page.wait_for_timeout(400)
        names = page.evaluate("[...document.querySelectorAll('.bm-menu .rs-bm-n')].map(e => e.textContent.trim())")
        browser.close()
    assert not errors, errors
    assert names[:7] == ["OpenFreeMap Liberty", "OpenFreeMap Positron", "OpenStreetMap", "Esri Gray", "Esri Streets", "Esri Satellite", "Blank"], names


def test_the_corner_strip_does_not_blur_itself_so_the_credits_box_inside_it_blurs_like_the_other_boxes():
    html, errors = rs.render_dashboard(_edges(), basemap="blank").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(_URL, _serve(html))
        page.goto(_URL)
        page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
        got = page.evaluate("""() => { rs.tools.open('attribution'); const s = document.getElementById('rs-scalebox'), b = document.getElementById('rs-attr-box'), tb = document.getElementById('rs-toolbar');
            const blur = (e, p) => getComputedStyle(e, p).backdropFilter; return {strip: blur(s), stripLayer: blur(s, '::before'), box: blur(b), bar: blur(tb), barLayer: blur(tb, '::before'),
              stripBg: getComputedStyle(s, '::before').backgroundColor, barBg: getComputedStyle(tb, '::before').backgroundColor}; }""")
        browser.close()
    assert not errors, errors
    assert got["strip"] == "none" and "blur" in got["stripLayer"] and "blur" in got["box"], got          # nothing blurred around the credits box
    assert got["bar"] == "none" and "blur" in got["barLayer"] and got["stripBg"] == got["barBg"], got    # the strip is the bar's level


def _openfreemap_answers():
    import urllib.request
    try:
        urllib.request.urlopen(urllib.request.Request("https://tiles.openfreemap.org/styles/liberty", headers={"User-Agent": "roadstyle-tests"}), timeout=8).read(10)
        return True
    except OSError:
        return False


def test_a_persons_switch_of_the_3d_buildings_tilts_and_zooms_the_map_and_off_flattens_it():
    if not _openfreemap_answers():
        pytest.skip("no network: the OpenFreeMap style cannot load")
    html, errors = rs.render_dashboard(_edges(), basemap="ofm_liberty").html, []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(_URL, _serve(html))
        page.goto(_URL)
        page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=90_000)
        page.wait_for_function("document.getElementById('rs-top-buildings') === null || !document.getElementById('rs-top-buildings').disabled", timeout=60_000)
        page.evaluate("map.jumpTo({zoom: 11, pitch: 0})")
        page.evaluate("rs.tools.open('basemap')")
        page.wait_for_timeout(500)
        start = page.evaluate("[document.getElementById('rs-top-buildings').checked, Math.round(map.getPitch()), Math.round(map.getZoom())]")
        page.evaluate("document.getElementById('rs-top-buildings').click()")           # the box starts with the buildings on: this click switches them off
        page.wait_for_timeout(300)
        off = page.evaluate("[rsBuildings(), Math.round(map.getPitch())]")
        page.evaluate("document.getElementById('rs-top-buildings').click()")           # on again: the map tilts and zooms in
        page.wait_for_timeout(1500)
        on = page.evaluate("[rsBuildings(), Math.round(map.getPitch()), Math.round(map.getZoom())]")
        page.evaluate("document.getElementById('rs-top-buildings').click()")           # off: flat again
        page.wait_for_timeout(1200)
        flat = page.evaluate("Math.round(map.getPitch())")
        scripted = page.evaluate("(() => { rsBuildings(true); return Math.round(map.getPitch()); })()")      # a script moves nothing
        browser.close()
    assert not errors, errors
    assert start[0] is True and start[1] == 0, start
    assert off == [False, 0], off
    assert on[0] is True and on[1] >= 50 and on[2] >= 15, on
    assert flat == 0 and scripted == 0, (flat, scripted)
