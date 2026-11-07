"""The design panel (docs/guides/design-panel.md, dashboard/design/): the design model's checks (tests/design_units.js) and the panel on a dashboard page.
The page imports the panel as a module from a local server, as a host page does. Each ready theme gives a look that roadstyle reads (Look.from_json).
Skipped without playwright."""
import contextlib
import functools
import http.server
import json
import shutil
import threading
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402
from roadstyle import _engine  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "rust/roadstyle-assets/files/static/dashboard"
_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
# the panel on the page: no setLook unless the test gives a style (window.nextStyle); redraw keeps what it got; one host tab with a value of its own
_HOST = """<script type="module">
import {designPanel} from "./dashboard/design/design_panel.js";
const look = await (await fetch("look.json")).json();
window.drawn = []; window.changes = 0; window.backs = 0;
window.dz = await designPanel({panel: document.getElementById("sb"), look,
  setLook: async () => window.nextStyle,
  redraw: async (text, draw) => { window.drawn.push({text, draw}); return draw ? "A new map." : ""; },
  boundary: (b) => { window.lastBoundary = b; }, link: {label: "Export", onClick: () => { window.linked = true; }},
  tabs: [{id: "tiles", name: "Tiles", key: "profile", keep: "Keep the tile profile in the theme", make: () => ({zoom: 14}),
          normalize: (p) => ({zoom: Math.min(18, +p?.zoom || 14)}),
          draw: (el, v, put, c) => { el.innerHTML = c.sec("Zoom", `<input id="hz" type="number" value="${v.zoom}">`); el.querySelector("#hz").oninput = (e) => put({zoom: +e.target.value}); }}]});
dz.addEventListener("change", () => window.changes++);
dz.addEventListener("back", () => window.backs++);
window.dzReady = true;
</script>"""


def _look():
    """The saved look of the theme liberty with the duckOSM page's options, as test_set_look_browser makes it."""
    o = {"args": {"color_options": {"Road class": {}}, "access_col": "access", "arrows": True, "labels": True, "state": "live"},
         "base_map": {"mode": "all", "theme": "liberty", "paths": "google"}}
    return _engine.rust().resolve_look(json.dumps(o)).json()


def _edges():
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary", "residential", "motorway"] * 2, "name": [f"Street {i}" for i in range(6)], "oneway": [True, False] * 3,
                             "edge_id": list(range(1, 7))},
                            geometry=[LineString([(18.0 + i * 1e-3, 59.30), (18.0 + i * 1e-3, 59.31)]) for i in range(6)], crs=4326)


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextlib.contextmanager
def served(tmp_path):
    """A folder with the dashboard's files, the look, the units and a dashboard page with the panel, on a local server: yields the base URL."""
    shutil.copytree(DASH, tmp_path / "dashboard")
    shutil.copy(ROOT / "tests/design_units.js", tmp_path / "design_units.js")
    (tmp_path / "look.json").write_text(_look())
    page = tmp_path / "page.html"
    rs.render_dashboard(_edges(), basemap="blank", name="Design").save(page)
    page.write_text(page.read_text().replace("</body>", _HOST + "</body>"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}/"
    finally:
        srv.shutdown()


def open_page(p, url, width=1280, height=900):
    """The page with the panel ready; gives (browser, page, errors)."""
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_page(viewport={"width": width, "height": height})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url + "page.html")
    page.wait_for_function("window.map && map.loaded() && window.rsReady && window.dzReady", timeout=60_000)
    return browser, page, errors


def test_the_design_model_checks_pass_and_roadstyle_reads_every_theme(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page()
        page.goto(url + "look.json")
        out = page.evaluate("""async () => { const u = await import("./design_units.js");
          const [look, data] = await Promise.all([fetch("look.json").then(r => r.json()), fetch("dashboard/design/themes.json").then(r => r.json())]);
          return u.run(look, data); }""")
        browser.close()
    assert out["failures"] == []
    assert len(out["looks"]) >= 13
    for theme, text in out["looks"].items():
        _engine.rust().Look.from_json(text)                                    # an error names the theme in the traceback
        assert theme


def _set(page, p, value):
    """Set the control `data-p=p` of the pane as a person does (the event input)."""
    page.evaluate("""([p, v]) => { const el = document.querySelector(`#design-pane [data-p="${p}"]`);
      if (el.type === "checkbox") el.checked = v; else el.value = v; el.dispatchEvent(new Event("input", {bubbles: true})); }""", [p, value])


def test_the_panel_opens_in_the_host_panel_and_draws_a_theme(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = open_page(p, url)
        page.evaluate("dz.open()")
        got = page.evaluate("""() => ({body: getComputedStyle(document.querySelector('#sb .sb-body')).display, title: document.querySelector('#sb .sb-top .rs-dz-title .t').textContent,
          tabs: [...document.querySelectorAll('#design-tabs [role=tab]')].map(b => b.textContent), on: document.querySelector('#design-tabs .on').textContent,
          themes: document.querySelectorAll('#ready-list [data-look]').length})""")
        assert got == {"body": "none", "title": "Edit design", "tabs": ["Theme", "Roads", "Bridges & tunnels", "Text", "Layers", "Tiles"], "on": "Theme", "themes": got["themes"]}
        assert got["themes"] >= 13
        # a theme draws a new map (no setLook style): the host gets the look; the host value stays
        page.evaluate("document.querySelector('[data-look=print]').click(); dz.flush()")
        page.wait_for_function("dz.state() === 'A new map.'")
        last = page.evaluate("window.drawn.at(-1)")
        assert last["draw"] is True and json.loads(last["text"])["labels"]["color"] == "#000000"
        assert page.evaluate("[dz.get().theme, dz.get().profile.zoom, window.lastBoundary.color, window.changes > 0]") == ["print", 14, "#000000", True]
        assert page.evaluate("document.getElementById('design-changes').textContent") == "Style: changed"
        # the back button and the link of the bar; close() shows the host's panel again
        page.evaluate("document.getElementById('design-back').click(); document.getElementById('design-link').click()")
        assert page.evaluate("[window.backs, window.linked]") == [1, True]
        page.evaluate("dz.close()")
        assert page.evaluate("[getComputedStyle(document.querySelector('#sb .sb-body')).display !== 'none', !!document.querySelector('.rs-dz'), dz.isOpen()]") == [True, False, False]
        browser.close()
    assert not errors, errors


def test_the_ground_the_layers_and_the_opacity_paint_with_no_new_map(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = open_page(p, url)
        page.evaluate("dz.open('roads')")
        n = page.evaluate("window.drawn.length")
        _set(page, "roads.opacity.fill", "0.5")
        page.evaluate("dz.flush()")
        op = page.evaluate("JSON.stringify(map.getPaintProperty('roads-simple', 'line-opacity'))")
        assert "0.5" in op and page.evaluate("window.drawn.length") == n, op       # painted on the road layer, no new map
        _set(page, "roads.opacity.outline", True)
        assert page.evaluate("JSON.stringify(map.getPaintProperty('roads-simple', 'line-gap-width'))") not in ("0", "null")
        # the theme Roads overlay: a transparent ground (the layer bg) and the checkerboard on the Blank base map, when its look shows
        page.evaluate("dz.tab('theme'); document.querySelector('[data-look=overlay]').click()")
        page.evaluate("dz.flush()")
        assert page.evaluate("[map.getPaintProperty('bg', 'background-opacity'), map.getContainer().classList.contains('rs-checker')]") == [0, True]
        assert page.evaluate("document.getElementById('design-notice').textContent").startswith("The ground is transparent")
        # a layer switch: the names; and roadstyle's own arrows switch comes back to the design
        page.evaluate("dz.tab('layers')")
        _set(page, "visible.names", False)
        assert page.evaluate("map.getLayoutProperty('roads-labels', 'visibility')") == "none"
        page.evaluate("rsSetArrows(true)")
        assert page.evaluate("dz.get().visible.arrows") is True
        browser.close()
    assert not errors, errors


def test_a_new_look_on_the_same_tiles_goes_through_rs_restyle(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = open_page(p, url)
        # rs.restyle: the same layers take the new paint; other layers give false
        assert page.evaluate("""async () => { const st = structuredClone(style); st.layers.find(l => l.id === 'roads-labels').paint['text-color'] = '#ff0000';
          const a = await rs.restyle(st), b = await rs.restyle({...st, layers: st.layers.slice(1)});
          return [a, b, map.getPaintProperty('roads-labels', 'text-color')]; }""") == [True, False, "#ff0000"]
        # the panel: setLook gives a style, so no new map
        page.evaluate("dz.open('text'); window.nextStyle = structuredClone(style)")
        n = page.evaluate("window.drawn.length")
        _set(page, "labels.color", "#123456")
        page.evaluate("dz.flush()")
        assert page.evaluate("dz.state()").startswith("The map shows this design: a new look on the same tiles")
        assert page.evaluate("window.drawn.length") == n
        browser.close()
    assert not errors, errors


def test_the_bridges_and_tunnels_tab_writes_the_look_and_the_tunnel_look_is_one_state_with_the_tunnels_box(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = open_page(p, url)
        page.evaluate("dz.open('bridges')")
        assert page.evaluate("[...document.querySelectorAll('#design-pane h3')].map(h => h.textContent)") == ["Bridges", "Tunnels"]
        # a bridge value is in the look: the map is drawn again with it
        _set(page, "bridges.casing", "#112233")
        page.evaluate("dz.flush()")
        assert json.loads(page.evaluate("window.drawn.at(-1).text"))["bridges"]["casing_color"] == "#112233"
        # the shadow switch turns its other controls on and off
        _set(page, "bridges.shadow", False)
        page.evaluate("dz.flush()")
        assert page.evaluate("document.querySelector('#design-pane [data-p=\"bridges.shadow_blur\"]').disabled") is True
        # a tunnel value goes to roadstyle's tunnel look (rsSetTunnelStyle) at once, with no new map
        page.evaluate("""() => { window.tun = []; window.rsSetTunnelStyle = (o) => window.tun.push(o); }""")
        n = page.evaluate("window.drawn.length")
        page.evaluate("""() => { const s = document.querySelector('#design-pane [data-p="tunnels.ratio"]'); s.value = '2:1'; s.dispatchEvent(new Event('input', {bubbles: true})); }""")
        page.evaluate("dz.flush()")
        assert page.evaluate("[window.tun.at(-1).ratio, dz.get().tunnels.ratio, window.drawn.length]") == [[2, 1], [2, 1], n]
        # the Tunnels box: its event comes back to the design
        page.evaluate("document.dispatchEvent(new CustomEvent('rs:tunnelchange', {detail: {strength: 25, palette: 'One colour', ratio: [1, 1], toward: 'Dark'}}))")
        assert page.evaluate("[dz.get().tunnels.strength, dz.get().tunnels.toward, dz.get().theme]") == [25, "Dark", "custom"]
        assert page.evaluate("document.querySelector('#design-pane [data-p=\"tunnels.toward\"]').value") == "Dark"
        browser.close()
    assert not errors, errors


def test_the_switch_events_of_a_new_style_are_not_the_persons_and_the_host_fold_button_hides(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = open_page(p, url)
        page.evaluate("rs.sections.add({id: 'f', label: 'A card that folds', fold: true, html: '<p>x</p>'})")
        assert page.evaluate("getComputedStyle(document.getElementById('rs-fold-all')).display") != "none"
        page.evaluate("window.ids = []; document.addEventListener('rs:sectionchange', (e) => window.ids.push(e.detail.id))")
        page.evaluate("dz.open('theme')")
        # the host's "Collapse all" is hidden while the panel is open; the panel's event has a detail, as the events of rs.sections have
        assert page.evaluate("getComputedStyle(document.getElementById('rs-fold-all')).display") == "none"
        assert "design" in page.evaluate("window.ids")
        # rs.setStyle switches the layers of the old style again and sends their events before rs:stylechange: a theme stays the theme
        page.evaluate("""() => { window.nextStyle = structuredClone(style); const orig = rs.restyle;
          rs.restyle = async (st, o) => { document.dispatchEvent(new CustomEvent('rs:overlaychange', {detail: {overlay: 'water', visible: false}}));
            document.dispatchEvent(new CustomEvent('rs:arrowschange', {detail: {on: false}})); return orig(st, o); }; }""")
        page.evaluate("document.querySelector('[data-look=print]').click(); dz.flush()")
        page.wait_for_function("dz.state().startsWith('The map shows this design')")
        assert page.evaluate("[dz.get().theme, dz.get().visible.water]") == ["print", True]      # the events of the restyle changed nothing
        # a person's switch outside a restyle still comes back to the design
        on = page.evaluate("dz.get().visible.arrows")
        page.evaluate(f"rsSetArrows({'false' if on else 'true'})")
        assert page.evaluate("[dz.get().theme, dz.get().visible.arrows]") == ["custom", not on]
        page.evaluate("dz.close()")
        assert page.evaluate("getComputedStyle(document.getElementById('rs-fold-all')).display") != "none"
        browser.close()
    assert not errors, errors


def test_a_host_tab_keeps_its_value_through_a_theme_a_reset_and_the_file(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors = open_page(p, url)
        page.evaluate("dz.open('tiles')")
        page.evaluate("const el = document.getElementById('hz'); el.value = 9; el.dispatchEvent(new Event('input', {bubbles: true}))")
        assert page.evaluate("dz.get().profile.zoom") == 9
        page.evaluate("dz.tab('theme'); document.querySelector('[data-look=night]').click()")
        assert page.evaluate("[dz.get().theme, dz.get().profile.zoom]") == ["night", 9]
        page.evaluate("document.getElementById('design-reset').click()")
        assert page.evaluate("[dz.get().theme, dz.get().profile.zoom]") == ["light", 9]
        page.evaluate("dz.setHost('profile', {zoom: 12})")
        assert page.evaluate("JSON.parse(dz.text()).profile.zoom") == 12
        assert page.evaluate("JSON.parse(localStorage.getItem('roadstyle.design')).profile.zoom") == 12
        # a theme of your own keeps the host value only with the check box
        page.evaluate("dz.tab('theme'); document.getElementById('mine-name').value = 'Mine'; document.getElementById('mine-save').click()")
        assert page.evaluate("JSON.parse(localStorage.getItem('roadstyle.themes'))[0].design.profile") is None
        browser.close()
    assert not errors, errors


def test_every_tab_fits_a_phone(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url + "page.html")
        page.wait_for_function("window.map && map.loaded() && window.rsReady && window.dzReady", timeout=60_000)
        page.evaluate("rs.sheet(2); dz.open('theme'); document.getElementById('mine-name').value = 'Phone theme'; document.getElementById('mine-save').click()")
        page.wait_for_selector("[data-mine=phone-theme]")       # a saved theme: its card has three buttons that must fit
        for tab in ("theme", "roads", "bridges", "text", "layers", "tiles"):
            page.evaluate(f"dz.tab('{tab}')")
            page.wait_for_timeout(300)
            m = page.evaluate("""() => {
              const root = document.querySelector('.rs-dz'), b = root.querySelector('.rs-dz-body'), r = root.getBoundingClientRect();
              const wide = [...root.querySelectorAll('*')].filter(e => e.offsetParent && !e.closest('#design-tabs') && e.getBoundingClientRect().right > r.right + 1).map(e => e.id || e.className || e.tagName).slice(0, 4);
              const tabs = document.getElementById('design-tabs').getBoundingClientRect(), bar = root.querySelector('.rs-dz-bar').getBoundingClientRect();
              // the tab row is one row that scrolls sideways on a phone (frame.js): its tabs can be past the edge
              return {over: b.scrollWidth - b.clientWidth, page: document.documentElement.scrollWidth - innerWidth, wide, tabs: tabs.left >= 0 && tabs.right <= innerWidth,
                      bar: bar.bottom <= innerHeight + 1 && bar.height > 0, phone: document.documentElement.classList.contains('rs-phone')}; }""")
            assert m == {"over": m["over"], "page": m["page"], "wide": [], "tabs": True, "bar": True, "phone": True} and m["over"] <= 1 and m["page"] <= 1, (tab, m)
        browser.close()
    assert not errors, errors
