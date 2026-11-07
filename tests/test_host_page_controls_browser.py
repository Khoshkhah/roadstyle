"""The buttons and the fields of Ask and the data dock have the same look on a JavaScript host page (it loads dashboard.css and not the
dashboard template: duckOSM Studio, duckosm edit) as on a roadstyle page, in the light and the dark theme. Before, the base rules of
`#sb button` and `#sb .rs-q` were in the template only, and a host page got the browser's buttons. Skipped without playwright."""
import contextlib
import functools
import http.server
import json
import shutil
import threading
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

from test_ask_browser import _HOST as _ASK  # noqa: E402
from test_ask_browser import served  # noqa: E402
from test_dashboard_sections_browser import _ARGS  # noqa: E402
from test_host_page_gaps_browser import HOST  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / "rust/roadstyle-assets/files"
# the controls to compare: a plain button, a filled one, a chip and a field of Ask, and a button of the data dock
_CONTROLS = {"New": ".rs-ask-new", "AI": ".rs-ask-keyb", "Done": ".rs-ask-keyhd button", "Save key": ".rs-ask-btns .sb-primary",
             "Clear": ".rs-ask-btns button:not(.sb-primary)", "key field": ".rs-ask-key input.rs-q", "dock button": "#rs-dock .rs-dd-acts button"}
_READ = """(sels) => Object.fromEntries(Object.entries(sels).map(([k, s]) => { const e = document.querySelector(s); if(!e) return [k, null];
  const c = getComputedStyle(e); return [k, ["border-top-width", "border-top-style", "border-top-color", "border-radius", "background-color", "color",
  "padding-left", "font-size", "font-family"].map(p => c.getPropertyValue(p))]; }))"""


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextlib.contextmanager
def host_page(tmp_path):
    """A host page: MapLibre, dashboard.css and rsDashboard on the page's own map and panel, then Ask and the data dock, with no template."""
    for part in ("static", "vendor", "data"):
        shutil.copytree(FILES / part, tmp_path / part)
    opts = json.loads((FILES / "data/host_options.json").read_text())
    opts["basemaps"] = [b for b in opts["basemaps"] if b["key"] == "blank"]
    page = HOST.replace("FILES", ".").replace("__OPTS__", json.dumps({k: opts[k] for k in ("dashboard", "basemaps", "ontop")}))
    (tmp_path / "page.html").write_text(page.replace("</body>", _ASK.replace("./dashboard/", "./static/dashboard/") + "</body>"))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}/page.html"
    finally:
        srv.shutdown()


def _controls(p, url, ready, theme):
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("http://rs.test/**", lambda r: r.fulfill(content_type="application/json", body="{}"))
    page.goto(url)
    page.wait_for_function(ready, timeout=60_000)
    page.evaluate(f"rsSetTheme({json.dumps(theme)}); releaseLoad(); data.open(); ask.open()")
    page.wait_for_selector("#rs-dock .rs-dd-acts button")
    page.click(".rs-ask-keyb")
    page.wait_for_selector(".rs-ask-key input.rs-q")
    found = page.evaluate(_READ, _CONTROLS)
    browser.close()
    return found, errors


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_ask_and_the_data_dock_have_the_same_controls_on_a_host_page(tmp_path, theme):
    (tmp_path / "rs").mkdir()
    (tmp_path / "host").mkdir()
    with pw.sync_playwright() as p:
        with served(tmp_path / "rs") as url:
            want, errors = _controls(p, url, "window.map && map.loaded() && window.rsReady && window.hostReady", theme)
        with host_page(tmp_path / "host") as url:
            got, host_errors = _controls(p, url, "window.ready === true && window.hostReady", theme)
    assert errors == [] and host_errors == [], (errors, host_errors)
    assert all(want.values()), want
    assert want["New"][0] == "1px" and want["New"][3] == "6px" and want["key field"][0] == "1px" and want["key field"][3] != "0px", want   # roadstyle's look, not the browser's
    assert got == want, json.dumps({k: [want[k], got[k]] for k in want if got[k] != want[k]}, indent=1)


_EDGES = """() => {
  rs.sections.add({id: 'tint', label: 'Ask', note: 'Ask a question', open: () => {}, background: true});
  rs.sections.add({id: 'plain', label: 'Open', note: 'Opens a thing', open: () => {}});
  rs.sections.add({id: 'fold', label: 'Folds', fold: true, html: '<p>x</p>'});
  rs.sections.get('fold').classList.contains('folded') || rs.sections.get('fold').querySelector('.rs-sec-title').click();   // closed: the thin edge
  const rgb = (c) => { const p = document.createElement('i'); p.style.color = c; document.body.append(p);
    const v = getComputedStyle(p).color; p.remove(); const m = v.match(/[\\d.]+/g).map(Number);
    return v.startsWith('color(') ? m.map((x) => x * 255) : m; };          // a color-mix() is color(srgb r g b), 0 to 1
  const lum = (c) => { const v = c.slice(0, 3).map((x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
  const ratio = (a, b) => { const [h, l] = [lum(a), lum(b)].sort((x, y) => y - x); return (h + 0.05) / (l + 0.05); };
  const sb = getComputedStyle(document.getElementById('sb')), card = rgb(sb.getPropertyValue('--card'));
  const edge = (id) => { const s = getComputedStyle(rs.sections.get(id)).boxShadow; return s === 'none' ? null : rgb(s.match(/^(rgba?|color)\\([^)]*\\)/)[0]); };
  const accent = rgb(sb.getPropertyValue('--accent'));
  return {tint: edge('tint'), accent, plain: ratio(edge('plain'), card), fold: ratio(edge('fold'), card)};
}"""


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_cards_of_style_f_have_the_light_edge_and_the_tinted_card_has_an_accent_edge(tmp_path, theme):
    """Kaveh's style F (the mock-up he chose): the edge of a closed card is a light line (1.6:1 on the card in the light theme, 2.8:1 in the dark, not 3:1 or more), and a card
    with the tint (`background: true`, the Ask card) has an edge of the accent (Kaveh, 2026-11-06: with no edge it did not look like a card to press)."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(url)
        page.wait_for_function("window.map && map.loaded() && window.rsReady && window.hostReady", timeout=60_000)
        page.evaluate(f"rsSetTheme({json.dumps(theme)})")
        found = page.evaluate(_EDGES)
        browser.close()
    tint, accent = found["tint"], found["accent"]
    far = lambda c: sum(abs(a - b) for a, b in zip(tint[:3], c[:3], strict=True))   # noqa: E731
    assert tint is not None and far(accent) < far([255 * (theme == "light")] * 3), found   # nearer the accent than the panel's white or black
    assert 1.3 < found["plain"] < 3 and abs(found["plain"] - found["fold"]) < 0.01, found     # light 1.6:1, dark 2.8:1 (the old edge was 3:1 or more)


def test_the_title_row_of_the_dock_is_inside_a_phone(tmp_path):
    """390 px: the title row of the data dock (the label, the note, the actions, the arrow) was wider than the screen. Now the actions are
    a row of their own that scrolls sideways, and nothing of the title row is past the screen's edge. The SQL line (the tables icon, the line,
    Run, the download icon; Kaveh, 2026-11-07) is inside the screen too."""
    with served(tmp_path) as url, pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True).new_page()
        page.goto(url)
        page.wait_for_function("window.map && map.loaded() && window.rsReady && window.hostReady", timeout=60_000)
        page.evaluate("releaseLoad(); data.open()")
        page.wait_for_selector("#rs-dock .rs-dd-acts button")
        out = page.evaluate("""() => { const hd = document.querySelector('#rs-dock .rs-dock-hd'), acts = hd.querySelector('.rs-dock-acts');
          const past = [...hd.children].filter((e) => e.offsetParent && e.getBoundingClientRect().right > innerWidth + 0.5).map((e) => e.className);
          const inActs = [...acts.querySelectorAll('button')].filter((b) => b.offsetParent);
          acts.scrollLeft = acts.scrollWidth; const last = inActs.at(-1).getBoundingClientRect();
          const qEls = [...document.querySelectorAll('#rs-dock .rs-dd-q > *')], qPast = qEls.filter((e) => e.getBoundingClientRect().right > innerWidth + 0.5).length;
          const x = (c) => document.querySelector('#rs-dock .rs-dd-q .' + c).getBoundingClientRect().left;
          const qOrder = x('rs-dd-ib:not(.rs-dd-tablesb)') < x('rs-dd-line') && x('rs-dd-line') < x('rs-dd-run') && x('rs-dd-run') < x('rs-dd-tablesb');
          return {past, page: document.documentElement.scrollWidth - innerWidth, lastIn: last.right <= innerWidth + 0.5 && last.left >= 0, n: inActs.length, qPast, qOrder}; }""")
        browser.close()
    assert out["past"] == [] and out["page"] <= 0 and out["lastIn"] and out["n"] >= 5 and out["qPast"] == 0 and out["qOrder"], out


_PARTS = """() => {
  const body = document.querySelector('#sb .sb-body');
  body.insertAdjacentHTML('beforeend', '<button id="t-plain">Plain</button><button id="t-off" disabled>Off</button><button id="t-poff" class="sb-primary" disabled>Save</button>' +
    '<div class="rs-sec-box" id="t-box"><h3>Box</h3><div class="rs-sec-box" id="t-inner">Inner</div></div><div class="rs-qrow" id="t-row"><b>A road</b><span>12 m</span></div>');
  const c = (s, ...p) => { const st = getComputedStyle(document.querySelector(s)); return p.map((k) => st.getPropertyValue(k)); };
  return {plain: c('#t-plain', 'border-top-width', 'border-radius', 'background-color', 'color', 'padding-left'), off: c('#t-off', 'opacity', 'cursor'),
          poff: c('#t-poff', 'opacity'), box: c('#t-box', 'background-color', 'border-radius'), inner: c('#t-inner', 'box-shadow'),
          row: c('#t-row span', 'color'), mut: getComputedStyle(document.getElementById('sb')).getPropertyValue('--mut').trim()};
}"""


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_panel_controls_and_the_box_have_roadstyle_look_on_a_host_page(tmp_path, theme):
    """A plain and a disabled button, a box (`rs-sec-box`) and a box in a box, and a row of the query list (`rs-qrow`): the same on a host page
    as on a roadstyle page, from dashboard.css. A disabled button is dimmed, a box in a box has the card's edge, and the row has the theme's colours."""
    (tmp_path / "rs").mkdir()
    (tmp_path / "host").mkdir()
    out = {}
    with pw.sync_playwright() as p:
        for name, ctx, ready in [("rs", served(tmp_path / "rs"), "window.map && map.loaded() && window.rsReady && window.hostReady"),
                                 ("host", host_page(tmp_path / "host"), "window.ready === true && window.hostReady")]:
            with ctx as url:
                browser = p.chromium.launch(args=_ARGS)
                page = browser.new_page(viewport={"width": 1400, "height": 900})
                page.route("http://rs.test/**", lambda r: r.fulfill(content_type="application/json", body="{}"))
                page.goto(url)
                page.wait_for_function(ready, timeout=60_000)
                page.evaluate(f"rsSetTheme({json.dumps(theme)})")
                out[name] = page.evaluate(_PARTS)
                browser.close()
    rs_, host = out["rs"], out["host"]
    assert host == rs_, json.dumps({k: [rs_[k], host[k]] for k in rs_ if host[k] != rs_[k]}, indent=1)
    assert host["plain"][0] == "1px" and host["off"] == ["0.5", "default"] and host["poff"] == ["0.5"], host
    assert host["box"][1] == "12px" and host["inner"] != ["none"], host
    assert host["mut"] and host["row"][0] != "rgb(138, 138, 138)", host        # the theme's muted colour, not the old fixed grey


def test_set_theme_on_a_page_with_no_map(tmp_path):
    """rsSetTheme on a page that has no map (an editor of its own) sets the theme and does not throw: before, it called the map's
    setGlobalStateProperty on null."""
    shutil.copytree(FILES / "static", tmp_path / "static")
    (tmp_path / "p.html").write_text('<!doctype html><html><body><script type="module">import {rsSetTheme} from "./static/dashboard/theme.js";'
                                     'rsSetTheme("dark"); window.done = document.documentElement.dataset.rsTheme;</script></body></html>')
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch(args=_ARGS)
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{srv.server_port}/p.html")
            page.wait_for_function("window.done !== undefined", timeout=20_000)
            got = page.evaluate("window.done")
            browser.close()
    finally:
        srv.shutdown()
    assert errors == [] and got == "dark", (errors, got)
