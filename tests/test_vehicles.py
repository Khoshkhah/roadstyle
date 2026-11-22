"""The option `vehicles` of a page from Python (render_edges(..., vehicles={"fcd": path, "net": path})) on the Monaco SUMO run of roadstyle-sim
(rust/roadstyle-sim/tests/data: 60 vehicles, 90 s): the local files go into the page, and with no `wasm` the page gets roadstyle's vehicles
module (rust/roadstyle-wasm/build_vehicles.sh) and the play bar. The tests that need the module are skipped when it is not built; the
browser test is skipped without playwright."""
from pathlib import Path

import pytest
from test_render_web import _opt

import roadstyle as rs
from roadstyle.render import VEHICLES_PKG

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "rust/roadstyle-sim/tests/data"
FCD, NET = RUN / "monaco_fcd.parquet", RUN / "monaco_net.xml"
built = pytest.mark.skipif(not (VEHICLES_PKG / "roadstyle_wasm_bg.wasm.gz").is_file(),
                           reason="roadstyle's vehicles module is not built (rust/roadstyle-wasm/build_vehicles.sh)")


def _monaco():
    import geopandas as gpd
    import pandas as pd
    df = pd.read_parquet(ROOT / "rust/roadstyle-rs/tests/data/monaco/roads.parquet")
    return gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=gpd.GeoSeries.from_wkb(df["geometry"]), crs=4326)


def test_local_files_go_into_the_page_and_urls_stay():
    v = _opt(rs.render_edges(_monaco(), backend="web", vehicles={"wasm": "./pkg/roadstyle_wasm.js", "fcd": FCD, "net": str(NET)}).html, "vehicles")
    assert v["wasm"] == "./pkg/roadstyle_wasm.js" and "wasm_bin" not in v
    assert v["fcd"].startswith("data:application/vnd.apache.parquet;base64,")
    assert v["net"] == NET.read_text(encoding="utf-8-sig")
    url = {"wasm": "./pkg/roadstyle_wasm.js", "fcd": "./data/run.parquet", "net": "./data/run.net.xml"}
    assert _opt(rs.render_edges(_monaco(), backend="web", vehicles=url).html, "vehicles") == url


def test_a_missing_file_or_key_is_an_error():
    with pytest.raises(FileNotFoundError, match="no file"):
        rs.render_edges(_monaco(), backend="web", vehicles={"fcd": RUN / "none.parquet", "net": NET})
    with pytest.raises(ValueError, match="'net'"):
        rs.render_edges(_monaco(), backend="web", vehicles={"fcd": FCD})


@built
def test_the_page_gets_the_module_and_the_play_bar():
    html = rs.render_edges(_monaco(), backend="web", vehicles={"fcd": FCD, "net": NET}, page_script="window.mine = 1;").html
    v = _opt(html, "vehicles")
    assert v["wasm"].startswith("data:text/javascript;base64,") and v["wasm_bin"].startswith("data:application/gzip;base64,")
    assert html.index('data-a="play"') < html.index("window.mine = 1;")


# the vertices of the lanes in view that the drawn tiles do not have, at zoom z (a tile keeps a vertex on a grid of 1/4096 of the tile:
# a data vertex counts as drawn when a tile vertex is within 2 steps of it)
_SAME_SHAPE = """(z) => new Promise(r => {
  const lanes = map.getSource('vehicle-lanes').serialize().data.features.filter(f => f.properties.kind === 'lane');
  const c0 = lanes[0].geometry.coordinates[0];
  map.jumpTo({center: c0, zoom: z, pitch: 0, bearing: 0});
  map.once('idle', () => {
    const q = 360 / 2 ** Math.min(Math.floor(z), 18) / 4096, cell = (c) => [Math.floor(c[0] / q), Math.floor(c[1] / q)];
    const b = map.getBounds(), drawn = new Set();
    for(const f of map.querySourceFeatures('vehicle-lanes', {filter: ['==', ['get', 'kind'], 'lane']}))
      (f.geometry.type === 'LineString' ? [f.geometry.coordinates] : f.geometry.coordinates).forEach(l => l.forEach(c => drawn.add(cell(c).join())));
    let lost = 0;
    for(const f of lanes) for(const c of f.geometry.coordinates) if(b.contains(c)){
      const [x, y] = cell(c); let ok = false;
      for(let dx = -2; dx <= 2 && !ok; dx++) for(let dy = -2; dy <= 2 && !ok; dy++) ok = drawn.has((x + dx) + ',' + (y + dy));
      if(!ok) lost++; }
    r(lost); }); })"""


@built
def test_the_run_plays_in_the_browser(tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from test_dashboard_sections_browser import _open
    path = tmp_path / "v.html"
    rs.render_dashboard(_monaco(), basemap="blank", vehicles={"fcd": FCD, "net": NET}).save(path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, path)
        try:
            page.wait_for_function("rs.vehicles.report()", timeout=60_000)
            assert page.evaluate("rs.vehicles.report()")["vehicles"] == 60
            page.evaluate("rs.vehicles.seek(45)")
            page.click('[data-a="play"]')
            page.wait_for_function("rs.vehicles.time() > 46 && rs.vehicles.count() > 0", timeout=30_000)
            assert page.locator('[data-a="play"]').inner_text() == "Pause"
            # the lanes of net.xml under the vehicles, in the colours of each theme
            assert page.evaluate("map.getSource('vehicle-lanes').serialize().data.features.length") > 0
            fill = page.evaluate("map.getLayersOrder().find(k => k.startsWith('vehicle-lane-fill-'))")
            col = f"JSON.stringify(map.getPaintProperty('{fill}', 'line-color'))"
            light = page.evaluate(col)
            page.evaluate("rsSetTheme('dark')")
            assert page.evaluate(col) != light
            # the same lanes at two zooms: every vertex of the data in view is drawn (MapLibre simplified a GeoJSON source at each zoom,
            # so a lane had another shape at another zoom)
            for z in (15.5, 19.0):
                assert page.evaluate(_SAME_SHAPE, z) == 0, f"lane vertices not drawn at zoom {z}"
        finally:
            browser.close()
    assert errors == []


def test_duckosm_page_takes_the_run_too(tmp_path):
    """duckosm.page (the page of duckOSM's net.map) puts the run's local files into the page, as render_edges does."""
    from test_duckosm import _tiny

    from roadstyle import duckosm
    db = _tiny(tmp_path / "t.duckdb")
    v = _opt(duckosm.page(db, "driving", levels="tags", vehicles={"wasm": "./pkg/roadstyle_wasm.js", "fcd": FCD, "net": NET}).html, "vehicles")
    assert v["fcd"].startswith("data:application/vnd.apache.parquet;base64,") and v["net"].startswith("<")


@built
def test_duckosm_page_gets_the_module_and_the_play_bar(tmp_path):
    from test_duckosm import _tiny

    from roadstyle import duckosm
    html = duckosm.page(_tiny(tmp_path / "t.duckdb"), "driving", levels="tags", vehicles={"fcd": FCD, "net": NET}).html
    v = _opt(html, "vehicles")
    assert v["wasm"].startswith("data:text/javascript;base64,") and v["wasm_bin"].startswith("data:application/gzip;base64,")
    assert 'data-a="play"' in html
