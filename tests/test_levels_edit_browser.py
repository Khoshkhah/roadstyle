"""`roadstyle levels edit AREA` (the Rust program, no Python): the level editor as a page of the standard dashboard.

The test makes an area with the program, starts the editor, and drives it in Chromium: the one panel, the bar, the dark theme, the phone
sheet, and an edit that reaches edits.csv. The browser job gives the program's path in ROADSTYLE_BIN. A build with no WebAssembly package
of the editor (CI builds none) cannot serve the page: the test is skipped then. The page's CDN MapLibre is answered from a file, and the
standard base map is Blank, so the test needs no network.
"""
import csv
import os
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
    area = tmp_path_factory.mktemp("area")
    square = area.parent / "square.geojson"
    square.write_text('{"type": "Polygon", "coordinates": [[[7.4, 43.7], [7.5, 43.7], [7.5, 43.8], [7.4, 43.7]]]}')
    subprocess.run([BIN, "levels", "make", str(EDGES), str(area), "--boundary", str(square)], check=True, capture_output=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([BIN, "levels", "edit", str(area), "--port", str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1)
    if proc.poll() is not None:
        pytest.skip(proc.stderr.read().strip())
    yield area, f"http://127.0.0.1:{port}/level_editor/"
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
    page.wait_for_selector("#lv-boot", state="detached", timeout=60000)
    page.wait_for_selector("#sb .sb-card #lv", timeout=60000)
    return page, errors


def test_the_page_is_the_dashboards_panel_and_bar_in_both_themes(editor):
    _, url = editor
    with sync_playwright() as p:
        b = p.chromium.launch()
        page, errors = _open(b, url, viewport={"width": 1300, "height": 800})
        assert page.evaluate("document.documentElement.classList.contains('rs-has-toolbar')"), "the dashboard's bar"
        assert page.evaluate("map.getStyle().layers.some(l => l.id.endsWith('boundary'))"), "the area's boundary.geojson: the dashed line"
        assert page.locator("#sb .sb-top .t").inner_text() == "Edit levels" and page.locator("#sb-hide").is_visible()
        assert page.locator("button[title='Light / dark']").is_visible()
        # the standard base-map box of every dashboard: Blank is the default, and the list has the other maps
        page.click("button[title='Base map and layers']")
        assert page.locator(".rs-bm-box input[name='rs-bm']:checked").get_attribute("value") == "blank"
        assert page.locator(".rs-bm-box .rs-bm-row").count() >= 7
        page.keyboard.press("Escape")
        assert page.get_attribute("#sb", "data-theme") == "light"
        page.click("button[title='Light / dark']")
        assert page.get_attribute("#sb", "data-theme") == "dark" and page.evaluate("document.documentElement.dataset.rsTheme") == "dark"
        # the panel's own colours turn with the theme: its text is not dark on the dark card
        card = page.evaluate("getComputedStyle(document.querySelector('#sb .sb-card')).backgroundColor")
        ink = page.evaluate("getComputedStyle(document.querySelector('#lv .tabs button.on, #lv-tabs button.on')).color")
        lum = lambda c: sum(int(v) for v in c[c.index("(") + 1:c.index(")")].split(",")[:3])  # noqa: E731
        assert lum(ink) > lum(card), (ink, card)
        assert errors == []
        b.close()


def test_the_phone_form_is_a_sheet_with_the_apply_bar(editor):
    _, url = editor
    with sync_playwright() as p:
        b = p.chromium.launch()
        page, errors = _open(b, url, viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        assert page.evaluate("document.documentElement.classList.contains('rs-phone')")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "no horizontal scroll"
        sheet = page.evaluate("(() => { const r = document.querySelector('#sb').getBoundingClientRect(); return [r.top, r.bottom]; })()")
        assert sheet[0] > 100 and sheet[1] <= 844 + 1, sheet            # a bottom sheet: the map stays above it
        for t in ("Light / dark", "Settings"):
            r = page.evaluate(f"document.querySelector(\"button[title='{t}']\").getBoundingClientRect().toJSON()")
            assert r["width"] >= 32 and r["height"] >= 32 and 0 <= r["right"] <= 390, (t, r)
        assert errors == []
        b.close()


def test_an_edit_is_saved_to_edits_csv(editor):
    area, url = editor
    pairs = list(csv.DictReader((area / "pairs.csv").open()))
    order = next(r for r in pairs if r["relation"] == "order")
    before = (area / "edits.csv").read_text()
    with sync_playwright() as p:
        b = p.chromium.launch()
        page, errors = _open(b, url, viewport={"width": 1300, "height": 800})
        for road in (order["a"], order["b"]):
            page.fill("#lv-find", road)
            page.wait_for_timeout(500)
            page.press("#lv-find", "Enter")
            page.wait_for_timeout(1000)
        page.locator(".row:has(.chip:text-is('order')) button[data-a='off']").first.click()
        assert page.locator("#lv-bar").is_visible(), "the apply bar shows when a change waits"
        page.click("#lv-apply")
        deadline = time.time() + 30
        while (area / "edits.csv").read_text() == before and time.time() < deadline:
            time.sleep(0.5)
        rows = list(csv.DictReader((area / "edits.csv").open()))
        assert any(r["relation"] == "order" and r["a"] == order["a"] and r["b"] == order["b"] and r["enabled"] == "false" for r in rows), rows
        assert errors == []
        b.close()


def test_the_help_window_explains_the_editor_in_both_themes_and_on_a_phone(editor):
    _, url = editor
    with sync_playwright() as p:
        b = p.chromium.launch()
        page, errors = _open(b, url, viewport={"width": 1300, "height": 800})
        btn = page.locator(".lv-title #rs-help-btn")
        assert btn.is_visible() and btn.get_attribute("title") == "How to use the level editor", "the ? button next to the title"
        assert page.is_hidden("#rs-help")
        btn.click()
        assert page.is_visible("#rs-help .rs-help-box")
        text = page.inner_text("#rs-help")
        for word in ("which road is drawn over which road", "road 1", "road 2", "Order", "Stack", "Meet", "On top", "Casing parts", "Add to the list", "Discard",
                     "Apply and solve", "History", "edits.csv", "Issues", "Given up", "Near warnings", "Order wishes not kept"):
            assert word in text, word
        dots = page.evaluate("[...document.querySelectorAll('#rs-help .rs-help-intro span')].map(e => getComputedStyle(e).backgroundColor)")
        assert len(dots) == 2 and dots[0] != dots[1], dots
        box = page.evaluate("document.querySelector('#rs-help .rs-help-box').getBoundingClientRect().toJSON()")
        assert box["top"] >= 0 and box["bottom"] <= 800 and box["right"] <= 1300, box
        light = page.evaluate("getComputedStyle(document.querySelector('#rs-help .rs-help-box')).backgroundColor")
        page.keyboard.press("Escape")
        assert page.is_hidden("#rs-help"), "Esc closes it"
        page.click("button[title='Light / dark']")
        btn.click()
        assert page.evaluate("getComputedStyle(document.querySelector('#rs-help .rs-help-box')).backgroundColor") != light, "the dark theme"
        page.click("#rs-help .rs-help-x")
        assert page.is_hidden("#rs-help")
        assert errors == []
        b.close()
        b = p.chromium.launch()
        page, errors = _open(b, url, viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
        page.locator(".lv-title #rs-help-btn").tap()
        box = page.evaluate("document.querySelector('#rs-help .rs-help-box').getBoundingClientRect().toJSON()")
        assert box["width"] == 390 and abs(box["bottom"] - 844) < 1 and box["top"] > 0, ("a sheet at the bottom", box)
        assert errors == []
        b.close()
