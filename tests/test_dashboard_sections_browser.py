"""The panel's sections and the legend's rows (docs/guides/migrating-dashboard.md): the typed options `dashboard.panel.sections`, `hide`, `dashboard.legend.rows`
and the run-time calls `rs.sections` and `rs.legend`. The HTML that a page adds follows the light and the dark theme. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
_PANEL = {"sections": [
    {"id": "notes", "label": "Notes", "html": '<p>Page text</p><p class="sb-note">Small print</p><a href="#x">a link</a>'
                                              '<div class="rs-sec-box">in a box</div>', "after": "legend"},
    {"id": "last", "html": "<p>The end</p>"}], "hide": ["base_map"]}
_LEGEND = {"rows": [{"color": "#ff0066", "label": "Events"}, {"color": "#16a34a", "label": "Sensors", "shape": "circle"}, {"color": "#2563eb", "label": "Bus route", "shape": "line"}]}


def _edges(n=6):
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary"] * n, "name": [f"Street {i}" for i in range(n)], "edge_id": list(range(1, n + 1))},
                            geometry=[LineString([(18.0 + i * 1e-3, 59.30), (18.0 + i * 1e-3, 59.31)]) for i in range(n)], crs=4326)


def _page(tmp_path, **dash):
    path = tmp_path / "s.html"
    rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}}, dashboard=dash).save(path)
    return path


def _open(p, path, scrollbars=False):
    browser = p.chromium.launch(args=_ARGS, ignore_default_args=["--hide-scrollbars"] if scrollbars else None)       # headless hides the scrollbars by default
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(path.resolve().as_uri())
    page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
    page.wait_for_timeout(300)
    return browser, page, errors


@pytest.mark.parametrize("bad, message", [
    ({"panel": {"sections": [{"id": "legend", "html": ""}]}}, "used twice"),
    ({"panel": {"sections": [{"id": "a", "html": "", "after": "nowhere"}]}}, "not a section here"),
    ({"panel": {"hide": ["nope"]}}, "not a section"),
    ({"legend": {"rows": [{"color": "#f00"}]}}, "label"),
])
def test_a_wrong_section_or_row_is_an_error(tmp_path, bad, message):
    with pytest.raises(ValueError, match=message):
        _page(tmp_path, **bad)


def test_the_typed_sections_are_in_the_panel_in_order_and_the_hidden_one_is_hidden(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, _page(tmp_path, panel=_PANEL, legend=_LEGEND))
        got = page.evaluate("""() => ({ids: rs.sections.list(), hidden: rs.sections.get('base_map').hidden,
            visible: getComputedStyle(document.getElementById('bm').closest('.sb-sec')).display,
            shown: rs.sections.get('legend').hidden, notes: !!document.querySelector('[data-rs-section=notes] label'),
            panelRows: document.querySelectorAll('#sb-legend-extra .sb-lgrow').length,
            panelShapes: [...document.querySelectorAll('#sb-legend-extra .sb-lgrow i')].map(i => i.className)})""")
        browser.close()
    assert not errors
    assert got["ids"] == ["base_map", "colour_by", "legend", "notes", "query", "selected_road", "last"]
    assert got["hidden"] is True and got["visible"] == "none" and got["shown"] is False and got["notes"] and got["panelRows"] == 3
    assert got["panelShapes"] == ["square", "circle", "line"]


def test_the_run_time_calls_add_move_and_remove(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, _page(tmp_path))
        got = page.evaluate("""() => {
            rs.sections.add({id: 'mine', html: '<p>mine</p>', before: 'query'});
            const after = rs.sections.list();
            rs.sections.hide('legend'); rs.sections.show('legend'); rs.sections.remove('mine');
            let own = null; try { rs.sections.remove('query'); } catch (e) { own = String(e.message); }
            rs.legend.add({id: 'ev', color: '#ff0066', label: 'Events'});
            return {after, end: rs.sections.list(), own, rows: rs.legend.list()}; }""")
        box_rows = page.evaluate("""() => { rs.tools.open('legend'); return document.querySelectorAll('.rs-cb-lg .lg-row').length; }""")
        text = page.evaluate("document.querySelector('.rs-cb-lg').textContent")
        browser.close()
    assert not errors
    assert got["after"].index("mine") == got["after"].index("query") - 1 and "mine" not in got["end"]
    assert "hide it" in got["own"] and got["rows"] == ["ev"] and box_rows >= 2 and "Events" in text


def test_the_added_html_follows_the_light_and_the_dark_theme(tmp_path):
    """The text, the small print, the link and the box of a page section have a readable colour in each theme (contrast 4.5 or more), and the colours change."""
    probe = """() => { const ctx = document.createElement('canvas').getContext('2d');
        const rgb = c => { ctx.fillStyle = '#000'; ctx.fillStyle = c; ctx.clearRect(0, 0, 1, 1); ctx.fillRect(0, 0, 1, 1); return [...ctx.getImageData(0, 0, 1, 1).data].slice(0, 3); };   // any CSS color, also color-mix
        const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }); return .2126 * r + .7152 * g + .0722 * b; };
        const cr = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + .05) / (y + .05); };
        const sec = document.querySelector('[data-rs-section=notes]'), cs = s => getComputedStyle(sec.querySelector(s));
        const card = cs('.rs-sec-box').backgroundColor;
        return {text: cs('p').color, note: cs('.sb-note').color, link: cs('a').color, card,
                ratios: [cr(cs('p').color, card), cr(cs('.sb-note').color, card), cr(cs('a').color, card), cr(cs('.rs-sec-box').color, card)]}; }"""
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, _page(tmp_path, panel=_PANEL))
        light = page.evaluate(probe)
        page.evaluate("rsSetTheme('dark')")
        page.wait_for_timeout(300)
        dark = page.evaluate(probe)
        browser.close()
    assert not errors
    assert light["text"] != dark["text"] and light["card"] != dark["card"] and light["link"] != dark["link"]
    assert min(light["ratios"]) >= 4.5 and min(dark["ratios"]) >= 4.5, (light, dark)


@pytest.mark.parametrize("side", ["left", "right"])
def test_the_scrollbar_of_the_panel_is_at_its_outer_edge(tmp_path, side):
    """A tall panel scrolls: the scrollbar is at the left of a left panel and at the right of a right panel, and the content keeps its left-to-right text."""
    path = tmp_path / "scroll.html"
    tall = {"id": "tall", "label": "Tall", "html": "".join(f"<p>Line {i}</p>" for i in range(60))}
    rs.render_dashboard(_edges(), basemap="blank", dashboard={"panel": {"side": side, "sections": [tall]}}).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path, scrollbars=True)
        got = page.evaluate("""() => { const b = document.querySelector('#sb .sb-body'), l = b.querySelector('[data-rs-section=tall] label').getBoundingClientRect(), r = b.getBoundingClientRect();
            return {bar: b.offsetWidth - b.clientWidth, scrolls: b.scrollHeight > b.clientHeight, gapLeft: l.left - r.left, gapRight: r.right - l.right,
                    dir: getComputedStyle(b.querySelector('[data-rs-section=tall] label')).direction}; }""")
        browser.close()
    assert not errors and got["scrolls"] and got["bar"] > 0 and got["dir"] == "ltr"
    assert (got["gapLeft"] > got["gapRight"]) == (side == "left")        # the scrollbar's width is on the outer side


def test_the_panel_scrollbar_is_hidden_at_rest_has_enough_contrast_and_the_fade_follows_the_scroll(tmp_path):
    """At rest the thumb is transparent; over the panel it shows with a contrast of 3:1 or more against the panel, in both themes; `data-more` (the fade) is
    on while there is more below and off at the end."""
    path = tmp_path / "thumb.html"
    tall = {"id": "tall", "label": "Tall", "html": "".join(f"<p>Line {i}</p>" for i in range(60))}
    rs.render_dashboard(_edges(), basemap="blank", dashboard={"panel": {"sections": [tall]}}).save(path)
    probe = """() => { const b = document.querySelector('#sb .sb-body'), ctx = document.createElement('canvas').getContext('2d'); ctx.canvas.width = ctx.canvas.height = 1;
        const rgba = c => { ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = c; ctx.fillRect(0, 0, 1, 1); return [...ctx.getImageData(0, 0, 1, 1).data]; };
        const lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
        const bg = rgba(getComputedStyle(document.getElementById('sb')).getPropertyValue('--bg').trim()).slice(0, 3);
        const sc = getComputedStyle(b).scrollbarColor, thumb = sc.slice(0, sc.indexOf(') ') + 1);
        const [r, g, bl, a] = rgba(thumb), over = [r, g, bl].map((v, i) => v * a / 255 + bg[i] * (1 - a / 255));
        const [x, y] = [lum(over), lum(bg)].sort((m, n) => n - m);
        return {alpha: a, ratio: (x + .05) / (y + .05)}; }"""
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        rest = page.evaluate("getComputedStyle(document.querySelector('#sb .sb-body')).scrollbarColor")
        more_top = page.evaluate("document.querySelector('#sb .sb-body').hasAttribute('data-more')")
        page.evaluate("document.querySelector('#sb .sb-body').classList.add('rs-scrolling')")
        light = page.evaluate(probe)
        page.evaluate("rsSetTheme('dark')")
        page.wait_for_timeout(300)
        dark = page.evaluate(probe)
        page.evaluate("const b = document.querySelector('#sb .sb-body'); b.scrollTop = b.scrollHeight")
        page.wait_for_timeout(300)
        more_end = page.evaluate("document.querySelector('#sb .sb-body').hasAttribute('data-more')")
        browser.close()
    assert not errors
    assert rest.startswith("rgba(0, 0, 0, 0)"), rest                       # at rest the thumb is transparent
    assert more_top is True and more_end is False
    assert light["ratio"] >= 3.0 and dark["ratio"] >= 3.0, (light, dark)


def test_the_default_panel_shows_only_the_query_and_the_selected_road_and_the_toolbox_has_the_rest(tmp_path):
    """The toolbox has boxes for the base map, the colour and the legend, so the panel hides their sections; the page starts with no scale box."""
    path = tmp_path / "default.html"
    rs.render_dashboard(_edges(), color_options={"Road class": {}}).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        got = page.evaluate("""() => ({shown: rs.sections.list().filter(id => !rs.sections.get(id).hidden), tools: rs.tools.list().map(t => t.id),
            scale: getComputedStyle(document.querySelector('.maplibregl-ctrl-scale')).display, rows: document.querySelectorAll('#bm option').length})""")
        browser.close()
    assert not errors and got["shown"] == ["query", "selected_road"]
    assert {"basemap", "legend"} <= set(got["tools"]) and got["scale"] == "none"


def test_the_base_map_follows_the_theme_from_the_start(tmp_path):
    """The blank map (and any base map with a dark twin) turns dark with the theme, and light again, with no earlier choice of a base map."""
    path = tmp_path / "theme.html"
    rs.render_dashboard(_edges(), color_options={"Road class": {}}).save(path)
    probe = "({key: rs.getState().basemap, bg: getComputedStyle(map.getContainer()).backgroundColor})"
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        light = page.evaluate(probe)
        page.evaluate("rsSetTheme('dark')")
        page.wait_for_timeout(600)
        dark = page.evaluate(probe)
        page.evaluate("rsSetTheme('light')")
        page.wait_for_timeout(600)
        back = page.evaluate(probe)
        browser.close()
    assert not errors
    assert (light["key"], dark["key"], back["key"]) == ("blank", "blank_dark", "blank")
    assert dark["bg"] != light["bg"] and back["bg"] == light["bg"]


def test_the_toolbox_is_fixed_and_a_tool_that_the_page_cannot_use_is_greyed_out(tmp_path):
    """The same tools are in the bar of every dashboard, in the same order; the ones that this page cannot use are disabled, with a title that says why."""
    fixed = ["theme", "zoom_in", "zoom_out", "compass", "view3d", "street_view", "google_3d", "basemap", "buildings", "legend", "settings", "attribution"]
    path = tmp_path / "bare.html"
    rs.render_dashboard(_edges(), basemap="blank", basemap_switcher=False, street_view=False).save(path)         # no colour option, no Google 3D, one base map
    full = tmp_path / "full.html"
    rs.render_dashboard(_edges(), color_options={"Road class": {}}, google_3d=True, street_view_key="AIzaTEST").save(full)
    probe = """() => rs.tools.list().map(t => [t.id, t.disabled, (document.querySelector(`#rs-toolbar [title="${t.title}"]`) || {}).disabled === true])"""
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        bare = page.evaluate(probe)
        titles = page.evaluate("Object.fromEntries(rs.tools.list().filter(t => t.disabled).map(t => [t.id, t.title]))")
        browser.close()
        browser, page, errors2 = _open(p, full)
        rich = page.evaluate(probe)
        browser.close()
    assert not errors and not errors2
    assert [t[0] for t in bare] == fixed and [t[0] for t in rich] == fixed
    assert {t[0] for t in bare if t[1]} == {"street_view", "google_3d", "basemap", "buildings", "legend"}
    assert all(t[2] for t in bare if t[1])                                   # the button is disabled in the page
    assert "street_view=False" in titles["street_view"] and "google_3d=True" in titles["google_3d"] and "one base map" in titles["basemap"]
    assert not any(t[1] for t in rich if t[0] in ("street_view", "google_3d", "legend"))


def test_a_legend_row_has_a_mark_in_the_colour_box_too_and_a_wrong_shape_is_an_error(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, _page(tmp_path, legend=_LEGEND))
        got = page.evaluate("""() => { rs.tools.open('legend');
            const marks = [...document.querySelectorAll('.rs-cb-lg .lg-sw')].map(e => ({c: e.className, r: getComputedStyle(e).borderRadius, w: e.getBoundingClientRect().width, h: e.getBoundingClientRect().height}));
            let bad = null; try { rs.legend.add({id: 'x', color: '#f00', label: 'X', shape: 'star'}); } catch (e) { bad = String(e.message); }
            return {marks, bad}; }""")
        browser.close()
    assert not errors
    circle = next(m for m in got["marks"] if "circle" in m["c"])
    assert circle["w"] == circle["h"] and circle["r"] in ("50%", "5.5px", "5px") and any("line" in m["c"] and m["h"] < 6 for m in got["marks"])
    assert "square, circle or line" in got["bad"]
