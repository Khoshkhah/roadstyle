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
_LEGEND = {"rows": [{"color": "#ff0066", "label": "Events"}]}


def _edges(n=6):
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary"] * n, "name": [f"Street {i}" for i in range(n)], "edge_id": list(range(1, n + 1))},
                            geometry=[LineString([(18.0 + i * 1e-3, 59.30), (18.0 + i * 1e-3, 59.31)]) for i in range(n)], crs=4326)


def _page(tmp_path, **dash):
    path = tmp_path / "s.html"
    rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}}, dashboard=dash).save(path)
    return path


def _open(p, path):
    browser = p.chromium.launch(args=_ARGS)
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
            panelRows: document.querySelectorAll('#sb-legend-extra .sb-lgrow').length})""")
        browser.close()
    assert not errors
    assert got["ids"] == ["base_map", "colour_by", "legend", "notes", "query", "selected_road", "last"]
    assert got["hidden"] is True and got["visible"] == "none" and got["shown"] is False and got["notes"] and got["panelRows"] == 1


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
