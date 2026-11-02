"""The panel's sections and the legend's rows (docs/guides/dashboard-panel.md): the panel starts empty; the typed options `dashboard.panel.sections`
(the page's HTML or a part: "query", "road_card") and `dashboard.legend.rows`, and the run-time calls `rs.sections` and `rs.legend`. The HTML that a
page adds and the parts follow the light and the dark theme. Skipped without playwright."""
import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
_PANEL = {"sections": [
    {"id": "q", "part": "query", "label": "Query", "text": "p.edge_id <= 3"},
    {"id": "road", "part": "road_card", "label": "Selected road", "fields": ["name", "edge_id"]},
    {"id": "notes", "label": "Notes", "html": '<p>Page text</p><p class="sb-note">Small print</p><a href="#x">a link</a>'
                                              '<div class="rs-sec-box">in a box</div>', "before": "road"},
    {"id": "last", "html": "<p>The end</p>"}]}
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
    ({"panel": {"sections": [{"id": "a", "html": ""}, {"id": "a", "html": ""}]}}, "used twice"),
    ({"panel": {"sections": [{"id": "a", "html": "", "after": "nowhere"}]}}, "not an earlier section"),
    ({"panel": {"sections": [{"id": "a", "part": "chart"}]}}, "unknown variant"),
    ({"panel": {"hide": ["query"]}}, "panel.hide is gone"),
    ({"legend": {"rows": [{"color": "#f00"}]}}, "label"),
])
def test_a_wrong_section_or_row_is_an_error(tmp_path, bad, message):
    with pytest.raises(ValueError, match=message):
        _page(tmp_path, **bad)


def test_the_typed_sections_are_in_the_panel_in_order_and_the_parts_work(tmp_path):
    """The sections are in the order of the call (`before` moves one); the query part runs its start text and lists the roads; the road card shows the
    selected road's fields (only `fields`) and empties on a deselect."""
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, _page(tmp_path, panel=_PANEL, legend=_LEGEND))
        got = page.evaluate("""() => { const q = document.querySelector('[data-rs-section=q]');
            q.querySelector('[data-q=run]').click();
            const out = {ids: rs.sections.list(), notes: !!document.querySelector('[data-rs-section=notes] label'), start: q.querySelector('.rs-q').value,
                         count: q.querySelector('.rs-q-count').textContent, rows: q.querySelectorAll('.rs-q-list a').length};
            q.querySelector('.rs-q-list a').click();
            out.card = document.querySelector('.rs-road-card').textContent;
            rsDeselect(); out.empty = document.querySelector('.rs-road-card').textContent;
            return out; }""")
        browser.close()
    assert not errors
    assert got["ids"] == ["q", "notes", "road", "last"] and got["notes"]
    assert got["start"] == "p.edge_id <= 3" and got["count"] == "3 edges match" and got["rows"] == 3
    assert "Street 0" in got["card"] and "highway" not in got["card"] and got["empty"] == "Click a road."


def test_the_run_time_calls_add_move_and_remove(tmp_path):
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, _page(tmp_path))
        got = page.evaluate("""() => {
            const start = rs.sections.list();
            rs.sections.add({id: 'q', part: 'query', label: 'Query'});
            rs.sections.add({id: 'mine', html: '<p>mine</p>', before: 'q'});
            const after = rs.sections.list();
            rs.sections.hide('mine'); const hidden = rs.sections.get('mine').hidden; rs.sections.show('mine');
            rs.sections.remove('mine'); rs.sections.remove('q');
            let bad = null; try { rs.sections.add({id: 'c', part: 'chart'}); } catch (e) { bad = String(e.message); }
            rs.legend.add({id: 'ev', color: '#ff0066', label: 'Events'});
            return {start, after, hidden, end: rs.sections.list(), bad, rows: rs.legend.list()}; }""")
        box_rows = page.evaluate("""() => { rs.tools.open('legend'); return document.querySelectorAll('.rs-cb-lg .lg-row').length; }""")
        text = page.evaluate("document.querySelector('.rs-cb-lg').textContent")
        browser.close()
    assert not errors
    assert got["start"] == [] and got["after"] == ["mine", "q"] and got["hidden"] is True and got["end"] == []
    assert "no part 'chart'" in got["bad"] and "query, road_card" in got["bad"]
    assert got["rows"] == ["ev"] and box_rows >= 2 and "Events" in text


def test_the_added_html_follows_the_light_and_the_dark_theme(tmp_path):
    """The text, the small print, the link and the box of a page section have a readable colour in each theme (contrast 4.5 or more), and the colours change."""
    probe = """() => { const ctx = document.createElement('canvas').getContext('2d');
        const rgb = c => { ctx.fillStyle = '#000'; ctx.fillStyle = c; ctx.clearRect(0, 0, 1, 1); ctx.fillRect(0, 0, 1, 1); return [...ctx.getImageData(0, 0, 1, 1).data].slice(0, 3); };   // any CSS color, also color-mix
        const lum = c => { const [r, g, b] = rgb(c).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }); return .2126 * r + .7152 * g + .0722 * b; };
        const cr = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + .05) / (y + .05); };
        const sec = document.querySelector('[data-rs-section=notes]'), cs = s => getComputedStyle(sec.querySelector(s));
        const card = cs('.rs-sec-box').backgroundColor, part = s => getComputedStyle(document.querySelector(s));
        rsSelect(1);
        const rc = part('.rs-road-card'), q = part('.rs-q'), bg = getComputedStyle(document.getElementById('sb')).backgroundColor;
        return {text: cs('p').color, note: cs('.sb-note').color, link: cs('a').color, card, roadCard: rc.backgroundColor,
                ratios: [cr(cs('p').color, card), cr(cs('.sb-note').color, card), cr(cs('a').color, card), cr(cs('.rs-sec-box').color, card),
                         cr(getComputedStyle(document.querySelector('.rs-road-card .rs-kv b')).color, rc.backgroundColor), cr(q.color, q.backgroundColor)]}; }"""
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, _page(tmp_path, panel=_PANEL))
        light = page.evaluate(probe)
        page.evaluate("rsSetTheme('dark')")
        page.wait_for_timeout(300)
        dark = page.evaluate(probe)
        browser.close()
    assert not errors
    assert light["text"] != dark["text"] and light["card"] != dark["card"] and light["link"] != dark["link"] and light["roadCard"] != dark["roadCard"]
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


def test_the_default_panel_is_empty_and_the_toolbox_has_the_base_map_and_the_legend(tmp_path):
    """The panel starts empty (2026-11-02): the page adds its parts; the toolbox has boxes for the base map, the colour and the legend; the page starts
    with no scale box."""
    path = tmp_path / "default.html"
    rs.render_dashboard(_edges(), color_options={"Road class": {}}).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        got = page.evaluate("""() => ({shown: rs.sections.list().filter(id => !rs.sections.get(id).hidden), tools: rs.tools.list().map(t => t.id),
            scale: getComputedStyle(document.querySelector('.maplibregl-ctrl-scale')).display, body: document.querySelector('#sb .sb-body').children.length})""")
        browser.close()
    assert not errors and got["shown"] == [] and got["body"] == 0
    assert {"basemap", "legend"} <= set(got["tools"]) and got["scale"] == "none"


def test_the_base_map_follows_the_theme_from_the_start(tmp_path):
    """The blank map (and any base map with a dark twin) turns dark with the theme, and light again, with no earlier choice of a base map."""
    path = tmp_path / "theme.html"
    rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}}).save(path)
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
    fixed = ["theme", "navigate", "street_view", "google_3d", "basemap", "roads", "buildings", "legend", "settings", "attribution"]
    path = tmp_path / "bare.html"
    rs.render_dashboard(_edges(), basemap="blank", basemap_switcher=False, street_view=False, google_3d=False).save(path)         # no colour option, no Google 3D, one base map
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
