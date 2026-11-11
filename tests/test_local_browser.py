"""`roadstyle local ROADS.parquet` (way D, the Rust program, no Python): the standard dashboard with the adapter of way D. The page has no road table: the
program makes the tiles, the rows and the lines of the roads and runs the queries of the data dock when the page asks (docs/guides/data-and-memory.md).
The browser job gives the program's path in ROADSTYLE_BIN. The page's CDN MapLibre is answered from a file, and the base map's tiles are not fetched, so the
test needs no network. Skipped without playwright."""
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
ROADS = ROOT / "rust" / "roadstyle-rs" / "tests" / "data" / "monaco" / "roads.parquet"


@pytest.fixture(scope="module")
def program():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([BIN, "local", str(ROADS), "--port", str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(100):                                # the program reads the roads and makes stage 1 before it listens
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            if proc.poll() is not None:
                pytest.fail(proc.stderr.read())
            time.sleep(0.2)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    proc.wait()


def test_the_dashboard_reads_everything_from_the_program(program):
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors, asked = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: asked.append((r.method, r.url.replace(program, ""))) if r.url.startswith(program) else None)
        page.route("**/maplibre-gl@*/dist/maplibre-gl.js", lambda r: r.fulfill(path=str(VENDOR / "maplibre-gl.js"), content_type="text/javascript"))
        page.route("**/maplibre-gl@*/dist/maplibre-gl.css", lambda r: r.fulfill(path=str(VENDOR / "maplibre-gl.css"), content_type="text/css"))
        page.route("**/tile.openstreetmap.org/**", lambda r: r.abort())
        try:
            page.goto(program + "/local/")
            page.wait_for_function("window.rsLocalReady === true", timeout=60_000)
            page.wait_for_function("map.loaded() && map.queryRenderedFeatures({layers: ['rs-roads-simple']}).length > 0", timeout=60_000)
            # the page has no road table: the tiles come from the program's address
            assert page.evaluate("typeof window.RS_SIDE") == "undefined" or page.evaluate("window.RS_SIDE") is None
            assert page.evaluate("map.getStyle().sources['rs-roads'].tiles[0]").startswith(program + "/tiles/roads/{z}/{x}/{y}")
            # a road: its row is asked from the program, one time, and the selection shows it
            road = page.evaluate("map.queryRenderedFeatures({layers: ['rs-roads-simple']}).find(f => f.id != null).id")
            page.evaluate(f"rsSelect({road})")
            page.wait_for_selector(".maplibregl-popup-content, .rs-card", timeout=20_000)
            assert len([a for a in asked if a == ("POST", "/rows/roads")]) == 1
            row = page.evaluate(f"rs.request.row('roads', {road})")
            assert row["highway"] in page.inner_text(".maplibregl-popup-content, .rs-card")
            # a query of the data dock runs in the program (DuckDB), and a BIGINT keeps its digits
            page.evaluate("data.open()")
            page.evaluate("data.run('SELECT count(*) AS n, max(edge_id) AS big FROM roads')")
            page.wait_for_function("document.querySelector('#rs-dock tbody tr') !== null", timeout=20_000)
            assert ("POST", "/query") in asked
            n = int(page.evaluate("document.querySelector('#rs-dock tbody tr td:nth-child(1)').textContent.replace(/[^0-9]/g, '')"))
            assert n > 1000
            assert page.evaluate("rs.request.query('SELECT 1 AS one').then(r => r.rows[0][0])") == 1
        finally:
            browser.close()
    assert errors == []
