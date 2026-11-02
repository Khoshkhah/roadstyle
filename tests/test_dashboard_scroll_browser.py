"""Every scroll area of a dashboard uses the panel's scroll rules (dashboard.css and panelscroll.js, `_PS_AREAS`): a thin scrollbar that is transparent at
rest and shows while the pointer is over the area, no scroll handed on to the map (`overscroll-behavior: contain`), and the scroll script on it. The areas:
the help window, the boxes of the toolbox, the panel's own select list, the query part's list (with a fade while there is more below) and a page's
`rs-scroll`. The window is short, so that the boxes scroll. Skipped without playwright."""
import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_AREAS = [   # (the area, the call that opens it, its selector)
    ("help window", "rs.help.open({title: 'Help', intro: 'Words.', terms: Array.from({length: 30}, (_, i) => ['Term ' + i, 'Its meaning.'])})", "#rs-help .rs-help-box"),
    ("roads box", "rs.tools.open('roads')", "#rs-roads-box"),
    ("colour box", "rs.tools.open('legend')", "#rs-color-box"),
    ("base map box", "rs.tools.open('basemap')", "#rs-toolbar .bm-menu"),
    ("settings box", "rs.tools.open('settings')", "#rs-settings-box"),
    ("select list", "document.querySelector('[data-rs-section=pick] .rs-sel-btn').click()", ".rs-sel-list"),
    ("query list", "document.querySelector('#sb [data-q=run]').click()", "#sb .rs-q-list"),
    ("page's rs-scroll", None, "#sb .rs-scroll"),
]


def _edges(n=60):
    import geopandas as gpd
    from shapely.geometry import LineString
    classes = ["primary", "secondary", "tertiary", "residential", "service", "footway"]
    return gpd.GeoDataFrame({"highway": [classes[i % 6] for i in range(n)], "name": [f"Street {i}" for i in range(n)], "edge_id": list(range(1, n + 1))},
                            geometry=[LineString([(18.0 + i * 1e-4, 59.30), (18.0 + i * 1e-4, 59.31)]) for i in range(n)], crs=4326)


def test_every_scroll_area_has_the_panels_scroll_rules(tmp_path):
    path = tmp_path / "scroll.html"
    pick = "<select>" + "".join(f"<option>Option {i}</option>" for i in range(40)) + "</select>"
    table = "<div class='rs-scroll' style='--rs-scroll-h:120px'><table class='rs-table'><tbody>" + "".join(f"<tr><td>Row {i}</td></tr>" for i in range(40)) + "</tbody></table></div>"
    rs.render_dashboard(_edges(), basemap="blank", color_options={"Road class": {}}, dashboard={"panel": {"sections": [
        {"id": "q", "part": "query", "label": "Query", "text": "true"}, {"id": "pick", "label": "A list", "html": pick},
        {"id": "table", "label": "A table", "html": table}]}}).save(path)
    got = {}
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1100, "height": 460})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(path.resolve().as_uri())
        page.wait_for_function("window.map && map.loaded() && window.rsReady", timeout=60_000)
        for name, act, sel in _AREAS:
            page.keyboard.press("Escape")
            page.mouse.move(1, 1)                                  # the pointer away: "at rest" is with no pointer over the area
            if act:
                page.evaluate(f"() => {{ {act} }}")
            page.wait_for_timeout(400)
            el = page.locator(sel).first
            rest = page.evaluate(f"""() => {{ const e = document.querySelector({json.dumps(sel)}); const cs = getComputedStyle(e);
                return {{contain: cs.overscrollBehaviorY, width: cs.scrollbarWidth, color: cs.scrollbarColor, wired: !!e.dataset.rsScroll,
                         scrolls: e.scrollHeight > e.clientHeight + 2, more: e.hasAttribute('data-more')}}; }}""")
            el.hover()
            page.wait_for_timeout(100)
            rest["hover"] = page.evaluate(f"getComputedStyle(document.querySelector({json.dumps(sel)})).scrollbarColor")
            got[name] = rest
        browser.close()
    assert not errors, errors
    for name, g in got.items():
        assert g["contain"] == "contain" and g["width"] == "thin" and g["wired"], (name, g)
        assert g["color"].startswith("rgba(0, 0, 0, 0)") and not g["hover"].startswith("rgba(0, 0, 0, 0)"), (name, g)      # hidden at rest, shown over it
    for name in ("help window", "settings box", "select list", "query list", "page's rs-scroll"):                        # these are taller than the window here,
        assert got[name]["scrolls"], (name, got[name])                                                                  # so the check means something
    assert got["query list"]["more"] and got["page's rs-scroll"]["more"]                                                  # the fade of an area inside a box
