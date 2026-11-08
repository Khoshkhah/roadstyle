"""The design-edit part (dashboard/design/design_part.js, docs/design/design_edit_part.md) with a Studio-shaped host: a dashboard page, a data adapter with
storage of its own (the saved design of the area), a host tab with a summary, and a card to link to. The part is the only code that the host has around the
design panel: the card and its line, the layout, the restore, the save, the redraw and the link."""
import contextlib
import functools
import http.server
import json
import shutil
import threading
import urllib.parse
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_design_panel_browser import _ARGS, _edges, _look  # noqa: E402

import roadstyle as rs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "rust/roadstyle-assets/files/static/dashboard"

_HOST = """<script type="module">
import {designEditPart} from "./dashboard/design/design_part.js";
import {roadLayers} from "./dashboard/roadlayers.js";
const look = await (await fetch("look.json")).json();
const restore = new URLSearchParams(location.search).get("restore"), numbered = new URLSearchParams(location.search).has("numbered");
window.saves = []; window.calls = []; window.reason = ""; window.failSave = false; window.closes = 0; window.changes = [];
rs.sections.add({id: "export", label: "Export", fold: true, html: "<p>files</p>"});
rs.sections.fold("export", true);
const data = {look: async () => look,
  loadDesign: async () => restore,                                            // the saved design of the area
  saveDesign: async (t) => { window.saves.push(t); if(window.failSave) throw new Error("disk full"); },
  setLook: async () => { window.calls.push("setLook"); return undefined; },     // always new tiles
  redraw: async (t, draw) => { window.calls.push("redraw:" + draw); return draw ? "Drawn." : ""; },
  redrawReason: () => window.reason};
const tiles = {id: "tiles", name: "Tiles", key: "profile", keep: "Keep the tile profile", make: () => ({zoom: 14}), normalize: (p) => ({zoom: +p?.zoom || 14}),
  summary: (v) => `Tiles: zoom ${v.zoom}.`, draw: (el, v) => { el.innerHTML = "<p>tiles</p>"; }};
window.part = await designEditPart({dashboard: rs, map, data, roads: roadLayers({map, dashboard: rs, prefix: "rs-", also: ["rs-low-"]}),
  card: numbered ? {id: "design", label: "Edit design", step: 9, before: "export"} : {id: "design", label: "Edit design"}, link: {label: "Export →", card: "export"}, tabs: [tiles], storageKey: "dp-part-" + Math.random()});
part.addEventListener("close", () => window.closes++);
part.addEventListener("change", (e) => window.changes.push(e.detail.edited));
window.partReady = true;
</script>"""


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextlib.contextmanager
def served(tmp_path):
    shutil.copytree(DASH, tmp_path / "dashboard")
    (tmp_path / "look.json").write_text(_look())
    page = tmp_path / "page.html"
    rs.render_dashboard(_edges(), basemap="blank", name="Design").save(page)
    page.write_text(page.read_text().replace("</body>", _HOST + "</body>"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}/page.html"
    finally:
        srv.shutdown()


def _open(p, url):
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors, warnings = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: warnings.append(m.text) if m.type == "warning" else None)
    page.goto(url)
    page.wait_for_function("window.map && map.loaded() && window.rsReady && window.partReady", timeout=60_000)
    return browser, page, errors, warnings


def _note(page):
    return page.evaluate("document.querySelector('#sb [data-rs-section=design] .rs-sec-note').textContent")


def _casing(page, value):
    page.evaluate("window.part.panel.open('bridges')")
    page.evaluate("""v => { const el = document.querySelector('#design-pane [data-p="bridges.casing"]'); el.value = v; el.dispatchEvent(new Event("input", {bubbles: true})); }""", value)
    page.evaluate("window.part.panel.flush()")


def test_the_card_the_layout_the_save_the_redraw_and_the_link(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors, warnings = _open(p, url)
        # the card has the name of the design and the summary of the host tab; nothing is changed yet
        assert page.locator("#sb [data-rs-section=design]").count() == 1
        assert _note(page).endswith("Tiles: zoom 14.") and "(changed)" not in _note(page)
        # the open: the panel in the host's panel, the layout attribute; "← Steps" closes it and the map gets its size back
        page.evaluate("window.part.open()")
        assert page.evaluate("[window.part.isOpen(), document.body.dataset.rsEditing]") == [True, "design"]
        # a change: the line says "(changed)", the event has `edited`, the new look went to the adapter, and the design is saved after the quiet time
        _casing(page, "#112233")
        assert "(changed)" in _note(page) and page.evaluate("window.part.edited") is True and page.evaluate("window.changes.at(-1)") is True
        assert "redraw:true" in page.evaluate("window.calls")                       # setLook gave no style: new tiles
        page.wait_for_function("window.saves.length >= 1", timeout=10_000)
        assert json.loads(page.evaluate("window.saves.at(-1)"))["bridges"]["casing"] == "#112233"
        # the host cannot redraw now (its level editor is open): the panel shows the reason, and the adapter only remembers the look
        page.evaluate("window.reason = 'The level editor is open.'; window.calls.length = 0")
        _casing(page, "#445566")
        assert page.evaluate("window.part.panel.state()").startswith("The level editor is open.")
        assert "redraw:true" not in page.evaluate("window.calls") and "redraw:false" in page.evaluate("window.calls")
        page.evaluate("window.reason = ''")
        page.wait_for_function("window.saves.length >= 2", timeout=10_000)           # the second change is saved too (after the quiet time)
        # a failed save is a warning, not an error
        page.evaluate("window.failSave = true")
        _casing(page, "#778899")
        page.wait_for_function("window.saves.length >= 3", timeout=10_000)
        for _ in range(20):
            if any("was not saved" in w for w in warnings):
                break
            page.wait_for_timeout(250)
        assert any("was not saved" in w for w in warnings), warnings
        # the link: it closes the panel, unfolds the card that it names
        assert page.evaluate("rs.sections.folded('export')") is True
        page.locator("#design-link").click()
        assert page.evaluate("[window.part.isOpen(), document.body.dataset.rsEditing ?? null, window.closes, rs.sections.folded('export')]") == [False, None, 1, False]
        assert not errors, errors
        browser.close()


def test_the_saved_design_is_loaded_before_the_first_draw_and_a_host_tab_value_is_not_a_change(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors, warnings = _open(p, url)
        page.evaluate("window.part.open()")
        _casing(page, "#112233")
        page.wait_for_function("window.saves.length >= 1", timeout=10_000)
        text = page.evaluate("window.saves.at(-1)")
        browser.close()
        browser, page, errors, warnings = _open(p, url + "?restore=" + urllib.parse.quote(text))
        # the saved design of the area is the design now, and the card says that it is changed; the panel drew it with `draw: false` (the host's first draw does it)
        assert page.evaluate("window.part.panel.get().bridges.casing") == "#112233" and "(changed)" in _note(page)
        # a value of the host tab shows in the line but it is not a change of the style
        browser.close()
        browser, page, errors, warnings = _open(p, url)
        page.evaluate("window.part.panel.setHost('profile', {zoom: 12})")
        assert _note(page).endswith("Tiles: zoom 12.") and page.evaluate("window.part.edited") is False
        assert not errors, errors
        browser.close()


def test_the_card_takes_the_options_of_sections_add_a_numbered_card_before_another(tmp_path):
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser, page, errors, warnings = _open(p, url + "?numbered")
        assert page.evaluate("[...document.querySelectorAll('#sb .sb-sec')].map(e => e.dataset.rsSection).filter(x => x === 'design' || x === 'export')") == ["design", "export"]
        assert page.evaluate("document.querySelector('#sb [data-rs-section=design] .rs-sec-n').textContent") == "9"
        assert not errors, errors
        browser.close()
