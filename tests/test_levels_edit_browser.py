"""`roadstyle levels edit AREA` (the Rust program, no Python): the level editor as a page of the standard dashboard.

The test makes an area with the program, starts the editor, and drives it in Chromium: the one panel, the bar, the dark theme, the phone
sheet, and an edit that reaches edits.csv. The browser job gives the program's path in ROADSTYLE_BIN. A build with no WebAssembly package
of the editor (CI builds none) cannot serve the page: the test is skipped then. The page's CDN MapLibre and base-map style are answered
from files, so the test needs no network.
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
BLANK_STYLE = '{"version": 8, "sources": {}, "layers": []}'


@pytest.fixture(scope="module")
def editor(tmp_path_factory):
    area = tmp_path_factory.mktemp("area")
    subprocess.run([BIN, "levels", "make", str(EDGES), str(area)], check=True, capture_output=True)
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
    page.route("https://tiles.openfreemap.org/**", lambda r: r.fulfill(body=BLANK_STYLE, content_type="application/json"))
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
        assert page.locator("#sb .sb-top .t").inner_text() == "Edit levels" and page.locator("#sb-hide").is_visible()
        assert page.locator("button[title='Light / dark']").is_visible()
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
