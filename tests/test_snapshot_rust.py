"""The Rust snapshot (rust/roadstyle-snapshot, the program's `roadstyle snapshot`) gives the PNG of Python's rs.snapshot.

Both draw the saved page with the same Chromium. Python is the reference. The browser CI job (browser-smoke) builds the program and
gives its path in ROADSTYLE_BIN.
"""
import os
import pathlib
import subprocess

import pytest

pytest.importorskip("playwright.sync_api")
BIN = os.environ.get("ROADSTYLE_BIN", "")
pytestmark = pytest.mark.skipif(not BIN, reason="ROADSTYLE_BIN: the path of the Rust program roadstyle (cargo build -p roadstyle-cli)")

MONACO = pathlib.Path(__file__).parents[1] / "rust/roadstyle-rs/tests/data/monaco/roads.parquet"
# measured on Monaco (2026-10-24): 0 pixels differ in all three shots (default, camera, scale 2); the limit leaves room for a late font
DIFFERENT_MAX = 0.001


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    import geopandas as gpd
    import pandas as pd
    import shapely

    import roadstyle as rs

    d = pd.read_parquet(MONACO)
    g = gpd.GeoDataFrame(d, geometry=shapely.from_wkb(d.pop("geometry")), crs=4326)
    p = tmp_path_factory.mktemp("snap") / "monaco.html"
    rs.render_edges(g, basemap="blank").save(str(p))
    return p


def _pixels(path):
    import numpy as np
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB")).astype(int)


@pytest.mark.parametrize("camera, args", [
    ({"center": (7.4246, 43.7384), "zoom": 16.5, "pitch": 45, "bearing": 20},
     ["--center", "7.4246,43.7384", "--zoom", "16.5", "--pitch", "45", "--bearing", "20"]),
    ({"scale": 2}, ["--scale", "2"]),
])
def test_rust_snapshot_is_python_snapshot(page, tmp_path, camera, args):
    import roadstyle as rs

    py, rust = tmp_path / "py.png", tmp_path / "rust.png"
    rs.snapshot(str(page), py, width=500, height=400, **camera)
    subprocess.run([BIN, "snapshot", str(page), str(rust), "--width", "500", "--height", "400", *args], check=True, timeout=120)
    a, b = _pixels(py), _pixels(rust)
    assert a.shape == b.shape == (400 * camera.get("scale", 1), 500 * camera.get("scale", 1), 3)
    assert len({tuple(p) for p in b.reshape(-1, 3)[::97]}) > 20          # not a blank picture
    different = (abs(a - b).max(axis=2) > 0).mean()
    assert different <= DIFFERENT_MAX, f"{different:.4%} of the pixels differ"


def test_no_browser_is_an_error_that_names_where_it_looked(page, tmp_path):
    r = subprocess.run([BIN, "snapshot", str(page), str(tmp_path / "x.png")], capture_output=True, text=True,
                       env={**os.environ, "CHROME": "/nowhere/chrome"})
    assert r.returncode == 2 and "no Chromium found (searched: CHROME=/nowhere/chrome)" in r.stderr, r.stderr
    assert not (tmp_path / "x.png").exists()


def test_a_map_that_does_not_load_is_taken_with_a_warning(tmp_path):
    # as Python: the picture is taken when the time is over; Rust also says why the picture can be incomplete
    page = tmp_path / "never.html"
    page.write_text("<!doctype html><body style='background:#2a6'><script>window.map = {loaded: () => false}</script></body>")
    out = tmp_path / "never.png"
    r = subprocess.run([BIN, "snapshot", str(page), str(out), "--timeout", "1", "--settle", "0"], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert "warning: the map did not load in 1 s" in r.stderr
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
