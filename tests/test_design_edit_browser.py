"""`roadstyle design edit ROADS` (the Rust program, no Python): the design editor on its own page, a host of the standard dashboard.

The test copies a road file (Monaco's level-area edges, GeoParquet) to a folder, starts the editor, and drives it in Chromium: the map with
the panel open, a new look on the same tiles, the design file that the page saves and reads at the next start, and the phone. The browser
job gives the program's path in ROADSTYLE_BIN. A build with no WebAssembly package of the editor (CI builds none) cannot serve the page:
the test is skipped then. The page's CDN MapLibre is answered from a file, and the standard base map is Blank, so the test needs no network.
"""
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

BIN = os.environ.get("ROADSTYLE_BIN", "")
pytestmark = pytest.mark.skipif(not BIN, reason="ROADSTYLE_BIN: the path of the Rust program roadstyle (cargo build -p roadstyle-cli)")

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "rust" / "roadstyle-assets" / "files" / "vendor"
EDGES = ROOT / "rust" / "roadstyle-rs" / "tests" / "data" / "level_area" / "edges.parquet"


@pytest.fixture(scope="module")
def editor(tmp_path_factory):
    folder = tmp_path_factory.mktemp("design")
    shutil.copy(EDGES, folder / "monaco roads.parquet")              # a space in the name: the address and the server decode it
    (folder / "secret.txt").write_text("not for the page")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([BIN, "design", "edit", str(folder / "monaco roads.parquet"), "--port", str(port)], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    time.sleep(1)
    if proc.poll() is not None:
        pytest.skip(proc.stderr.read().strip())
    line = proc.stdout.readline()
    url = line.split()[2]
    yield folder, url, port
    proc.terminate()
    proc.wait()


def _open(browser, url, **kw):
    ctx = browser.new_context(**kw)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("**/maplibre-gl@*/dist/maplibre-gl.js", lambda r: r.fulfill(path=str(VENDOR / "maplibre-gl.js"), content_type="text/javascript"))
    page.route("**/maplibre-gl@*/dist/maplibre-gl.css", lambda r: r.fulfill(path=str(VENDOR / "maplibre-gl.css"), content_type="text/css"))
    page.goto(url)
    page.wait_for_selector("#dz-boot", state="detached", timeout=60000)
    page.wait_for_function("window.dz && dz.isOpen() && map.loaded()", timeout=60000)
    return page, errors


def _set(page, p, value):
    page.evaluate("""([p, v]) => { const el = document.querySelector(`#design-pane [data-p="${p}"]`);
      if (el.type === "checkbox") el.checked = v; else el.value = v; el.dispatchEvent(new Event("input", {bubbles: true})); }""", [p, value])


def test_the_address_names_the_files_and_the_server_gives_no_other_file(editor):
    folder, url, _ = editor
    assert "/design_editor/?roads=monaco%20roads.parquet&design=monaco%20roads.design.json" in url
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.goto(url.split("?")[0] + "index.html")
        got = page.evaluate("""async () => [(await fetch('/area/monaco%20roads.parquet')).status, (await fetch('/area/secret.txt')).status,
          (await fetch('/area/monaco%20roads.parquet', {method: 'PUT', body: 'x'})).status]""")
        b.close()
    assert got == [200, 404, 405]
    assert (folder / "secret.txt").read_text() == "not for the page"


def test_the_page_draws_the_roads_and_saves_a_design_that_the_next_start_reads(editor):
    folder, url, _ = editor
    design = folder / "monaco roads.design.json"
    with sync_playwright() as p:
        b = p.chromium.launch()
        page, errors = _open(b, url, viewport={"width": 1300, "height": 800})
        assert page.evaluate("document.documentElement.classList.contains('rs-has-toolbar')"), "the dashboard's bar"
        assert page.evaluate("map.getStyle().layers.some(l => l.id === 'rs-roads-simple')"), "the roads on the map"
        assert page.evaluate("[...document.querySelectorAll('#design-tabs [role=tab]')].map(t => t.textContent)") == [
            "Theme", "Roads", "Bridges & tunnels", "Text", "Layers"]
        assert page.evaluate("RS_SIDE.props.length") > 100
        # a new street-name colour: a new look on the same tiles, and the design file beside the roads
        page.evaluate("dz.tab('text')")
        _set(page, "labels.color", "#123456")
        page.evaluate("dz.flush()")
        assert page.evaluate("dz.state()").startswith("The map shows this design: a new look on the same tiles"), page.evaluate("dz.state()")
        assert page.evaluate("map.getPaintProperty('rs-roads-labels', 'text-color')") is not None
        # a bridge colour: the look of the map has it (the same tiles or a new map)
        page.evaluate("dz.tab('bridges')")
        _set(page, "bridges.casing", "#ff00aa")
        page.evaluate("dz.flush()")
        assert "#ff00aa" in json.dumps(page.evaluate("map.getStyle().layers.filter(l => l.id.startsWith('rs-')).map(l => l.paint)"))
        for _ in range(40):
            if design.exists() and json.loads(design.read_text())["bridges"]["casing"] == "#ff00aa":
                break
            time.sleep(0.1)
        saved = json.loads(design.read_text())
        assert saved["format"] == "roadstyle-design" and saved["labels"]["color"] == "#123456" and saved["bridges"]["casing"] == "#ff00aa"
        # the next start: the file wins over the design that this browser kept
        saved["labels"]["color"] = "#654321"
        design.write_text(json.dumps(saved))
        page.reload()
        page.wait_for_function("window.dz && dz.isOpen() && map.loaded()", timeout=60000)
        assert page.evaluate("dz.get().labels.color") == "#654321"
        assert page.evaluate("map.getPaintProperty('rs-roads-labels', 'text-color')") is not None
        b.close()
    assert not errors, errors


def _pick(page, p, text):
    """Click the select box of the control `p` and its option `text`, as a person does (the box sends the events, not the test)."""
    page.locator(f'#design-pane .rs-sel:has([data-p="{p}"]) .rs-sel-btn').click()
    page.locator(".rs-sel-list .rs-sel-opt", has_text=text).first.click()


def test_a_click_on_each_tunnel_list_changes_the_map(editor):
    _, url, _ = editor
    with sync_playwright() as p:
        b = p.chromium.launch()
        page, errors = _open(b, url, viewport={"width": 1300, "height": 800})
        page.evaluate("dz.tab('bridges')")
        state = "map.getGlobalState()"
        _pick(page, "tunnels.palette", "Blue + cyan")
        assert page.evaluate(state)["rs_tun_c0"] == "#315b7d" and page.evaluate("dz.get().tunnels.palette") == "Blue + cyan"
        _pick(page, "tunnels.toward", "Teal")
        assert page.evaluate(state)["rs_tun_toward"] == page.evaluate("RS_TUNNEL_TOWARDS.Teal")
        _pick(page, "tunnels.ratio", "2:1")
        assert page.evaluate(state)["rs_tun_ratio"] == [2, 1]
        assert page.evaluate("document.getElementById('tn-pal')?.value ?? 'Blue + cyan'") == "Blue + cyan"
        # an open list is as wide as its longest option, inside the window (the base map list: "Checkerboard", "OpenFreeMap ...")
        page.evaluate("dz.tab('theme')")
        page.locator(".rs-sel:has(#design-preview) .rs-sel-btn").click()
        cut = page.evaluate("""() => { const l = document.querySelector('.rs-sel-list'), r = l.getBoundingClientRect();
          return {cut: [...l.querySelectorAll('.rs-sel-opt span')].filter(s => s.scrollWidth > s.clientWidth + 1).map(s => s.textContent),
                  inside: r.left >= 0 && r.right <= innerWidth}; }""")
        assert cut == {"cut": [], "inside": True}, cut
        # a colour box has the hover of a button: the accent border
        page.keyboard.press("Escape")
        page.evaluate("dz.tab('bridges')")
        box = page.locator('#design-pane input[type=color][data-p="bridges.casing"]')
        border = "getComputedStyle(document.querySelector('#design-pane input[type=color][data-p=\"bridges.casing\"]')).borderColor"
        rest = page.evaluate(border)
        box.hover()
        page.wait_for_timeout(200)
        assert page.evaluate(border) != rest
        b.close()
    assert not errors, errors


def test_the_page_fits_a_phone(editor):
    _, url, _ = editor
    with sync_playwright() as p:
        b = p.chromium.launch()
        page, errors = _open(b, url, viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        assert page.evaluate("document.documentElement.classList.contains('rs-phone')")
        for tab in ("theme", "roads", "bridges", "text", "layers"):
            page.evaluate(f"rs.sheet(2); dz.tab('{tab}')")
            page.wait_for_timeout(200)
            m = page.evaluate("""() => { const root = document.querySelector('.rs-dz'), r = root.getBoundingClientRect();
              return {page: document.documentElement.scrollWidth - innerWidth, inside: r.left >= 0 && r.right <= innerWidth + 1,
                      wide: [...root.querySelectorAll('*')].filter(e => e.offsetParent && !e.closest('#design-tabs') && e.getBoundingClientRect().right > r.right + 1).length}; }""")
            assert m == {"page": 0, "inside": True, "wide": 0}, (tab, m)
        b.close()
    assert not errors, errors
