"""A page with MLT tiles (the default tile format) draws the roads in Chromium, Firefox and WebKit, at a desktop and a phone size, with no error
(docs/rust/tiles.md). A browser that is not installed, or that has no WebGL here, is skipped."""
import io
from pathlib import Path

import pytest

import roadstyle as rs
from roadstyle import _engine

pytestmark = pytest.mark.skipif(not _engine.available(), reason="no roadstyle._rust")
DATA = Path(__file__).resolve().parents[1] / "rust" / "roadstyle-rs" / "tests" / "data"
SIZES = {"desktop": (1280, 800), "phone": (390, 844)}


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    import geopandas as gpd
    import pyarrow.parquet as pq
    import shapely

    df = pq.read_table(DATA / "monaco" / "roads.parquet").to_pandas(integer_object_nulls=True)
    g = gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")
    out = tmp_path_factory.mktemp("mlt_browsers") / "monaco.html"
    out.write_text(rs.render_dashboard(g, basemap="blank").html)
    assert '"encoding":"mlt"' in out.read_text().replace(" ", ""), "the page's tiles are not MLT"
    return out


@pytest.mark.parametrize("browser", ["chromium", "firefox", "webkit"])
@pytest.mark.parametrize("size", list(SIZES))
def test_the_roads_are_drawn_from_mlt_tiles(page, browser, size):
    sync_api = pytest.importorskip("playwright.sync_api")
    import numpy as np
    from PIL import Image

    with sync_api.sync_playwright() as p:
        try:
            b = getattr(p, browser).launch()
        except Exception as e:
            pytest.skip(f"{browser} cannot start here: {str(e)[:80]}")
        w, h = SIZES[size]
        pg = b.new_page(viewport={"width": w, "height": h})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(page.as_uri())
        try:
            pg.wait_for_function("!!(window.map && window.map.loaded())", timeout=60000)
        except Exception:
            b.close()
            pytest.skip(f"{browser} has no WebGL here")
        pg.evaluate("window.map.jumpTo({center: [7.4243, 43.7384], zoom: 15, pitch: 0})")
        pg.wait_for_function("window.map.loaded()", timeout=60000)
        pg.wait_for_timeout(500)
        drawn = pg.evaluate("window.map.queryRenderedFeatures().length")
        png = pg.locator("canvas.maplibregl-canvas").screenshot()
        b.close()
    a = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(int)
    ink = float((np.abs(a - np.median(a.reshape(-1, 3), axis=0)).max(axis=2) > 40).mean())
    assert not errors, errors[:3]
    assert drawn > 100 and ink > 0.01, f"{browser} {size}: {drawn} features, {ink:.3f} of the canvas drawn"
