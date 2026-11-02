"""The dashboard manual (docs/guides/dashboard-manual/): python.md names every option of `dashboard=` and every python block runs, javascript.md names every
member of `window.rs` and every `rs:` event, and every block marked `javascript` runs without an error in a fresh dashboard page (the same page as
docs/build_maps.py makes for the testbed). Skipped without playwright."""
import json
import re
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "docs" / "guides" / "dashboard-manual"
PYTHON = (DIR / "python.md").read_text(encoding="utf-8")
JAVASCRIPT = (DIR / "javascript.md").read_text(encoding="utf-8")
_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
# `layers` is a list of the page's own layers, `sections` and `rows` hold the page's HTML: their keys are checked as words in the manual
_BLOCKS = re.findall(r"```javascript\n(.*?)```", JAVASCRIPT, re.S)


def _edges(n=40):
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame(
        {"edge_id": [str(10**17 + i) for i in range(n)], "highway": ["primary", "secondary", "tertiary", "residential"] * (n // 4),
         "name": [f"Storgatan {i}" for i in range(n)], "maxspeed_kmh": [30, 50, 70, 50] * (n // 4), "lanes": [1, 2, 2, 1] * (n // 4)},
        geometry=[LineString([(18.0 + i * 1e-3, 59.30), (18.0 + i * 1e-3, 59.31)]) for i in range(n)], crs=4326)


def _page(tmp_path):
    path = tmp_path / "testbed.html"
    # the same keywords as the testbed in docs/build_maps.py
    rs.render_dashboard(_edges(), basemap="blank", live_data=True,
                        color_options={"Road class": {}, "Speed limit": {"color_by": "maxspeed_kmh", "cmap": "plasma", "vmin": 20, "vmax": 60}},
                        views={"Normal": {"road_fill": True}, "Casing only": {"road_fill": False}},
                        dashboard={"toolbar": {"position": "top"}}).save(path)
    return path


def _dashboard_option(html):
    j = html.index("{", html.index("const RS_OPTIONS = "))
    return json.JSONDecoder().raw_decode(html[j:])[0]["dashboard"]


def _keys(d):
    for k, v in d.items():
        yield k
        if isinstance(v, dict):
            yield from _keys(v)


def test_the_manual_names_every_option_of_the_dashboard(tmp_path):
    keys = set(_keys(_dashboard_option(_page(tmp_path).read_text(encoding="utf-8"))))
    keys |= {"style", "kind", "source", "scope", "match", "max", "on", "arrows", "label", "id",                       # a layer of google_3d
             "dash", "fill", "width_m", "width_prop", "radius", "color", "width", "outline", "outline_width",          # its style
             "html", "after", "before", "fold", "shape"}                                                              # a section, a legend row
    missing = sorted(k for k in keys if k not in PYTHON)
    assert not missing, f"python.md does not name these options: {missing}"


def test_the_manual_names_every_member_of_rs_and_every_event(tmp_path):
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page()
        page.goto(_page(tmp_path).resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded()", timeout=60_000)
        members = page.evaluate("Object.fromEntries(Object.entries(window.rs).map(([k, v]) => [k, v && typeof v === 'object' ? Object.keys(v) : []]))")
        browser.close()
    # `error` is a value, `destroy` and the rest are named by their words
    missing = [f"rs.{k}" for k in members if f"rs.{k}" not in JAVASCRIPT]
    missing += [f"rs.{k}.{m}" for k, ms in members.items() for m in ms if not re.search(rf"\b{m}\b", JAVASCRIPT)]
    src = ROOT / "rust" / "roadstyle-assets" / "files" / "static"
    events = {m for f in src.rglob("*.js") for m in re.findall(r"""["'`](rs:[a-z0-9]+)["'`]""", f.read_text(encoding="utf-8"))}
    missing += sorted(e for e in events if e not in JAVASCRIPT)
    assert not missing, f"javascript.md does not name: {missing}"


@pytest.mark.parametrize("n", range(len(_BLOCKS)))
def test_every_javascript_block_of_the_manual_runs(tmp_path, n):
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(_page(tmp_path).resolve().as_uri())
        page.wait_for_function("window.map && window.map.loaded() && window.rsReady", timeout=60_000)
        page.wait_for_timeout(300)
        page.evaluate("async () => {\n" + _BLOCKS[n] + "\n}")
        page.wait_for_timeout(200)
        browser.close()
    assert not errors, f"block {n}:\n{_BLOCKS[n]}\n{errors}"


def test_every_python_block_of_the_manual_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env = {"edges": _edges()}                       # the blocks run one after another, as docs/build_maps.py runs them
    for block in re.findall(r"```python\n(.*?)```", PYTHON, re.S):
        exec(block, env)
    saved = sorted(p.name for p in tmp_path.glob("dashboard*.html"))
    assert saved == ["dashboard.html", "dashboard_dock.html", "dashboard_left.html"]       # the maps that python.md shows under its blocks
