"""The Roads box with the class minzoom (the default since 2026-10-25): a class that the map does not draw at this zoom has its row
dimmed, with the title "from zoom N" (roadstyle:controls.filter.minzoom). On Tartu at zoom 12 and 15."""
import json
import math
import pathlib

import pytest

pw = pytest.importorskip("playwright.sync_api")
TARTU = pathlib.Path(__file__).parents[1] / "rust" / "roadstyle-rs" / "tests" / "data" / "tartu" / "roads.parquet"


def test_a_class_hidden_at_this_zoom_is_dimmed_in_the_roads_box(tmp_path):
    if not TARTU.is_file():
        pytest.skip("no Tartu roads (rust/roadstyle-rs/tests/get_goldens.sh)")
    if not __import__("roadstyle._engine", fromlist=["available"]).available():
        pytest.skip("no roadstyle._rust")
    import geopandas as gpd
    import pyarrow.parquet as pq
    import shapely

    import roadstyle as rs
    df = pq.read_table(TARTU).to_pandas(integer_object_nulls=True)
    g = gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")
    page = tmp_path / "tartu.html"
    rs.render_edges(g, basemap="blank").save(str(page))
    html = page.read_text()
    flt = json.JSONDecoder().raw_decode(html, html.index("const RS_OPTIONS = ") + len("const RS_OPTIONS = "))[0]["filter"]
    mz = flt["minzoom"]
    assert mz and set(mz) <= set(flt["classes"]), "the class minzoom is on by default"
    with pw.sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1000, "height": 800})
        pg.goto(page.as_uri())
        pg.wait_for_function("typeof window.map?.loaded === 'function' && map.loaded() && document.querySelector('.flt-ctrl label')", timeout=120000)
        seen = {}
        for z in (12, 15):
            pg.evaluate("z => new Promise(r => { map.once('zoomend', r); map.jumpTo({zoom: z}); })", z)
            rows = pg.evaluate("""() => [...document.querySelectorAll('.flt-ctrl .flt-body label')]
                                    .map(l => [l.textContent.trim(), l.classList.contains('flt-below'), l.title])""")
            dim = {c: t for c, below, t in rows if below}
            want = {c: f"from zoom {m:g}" for c, m in mz.items() if math.floor(z) < m}
            assert dim == want, (z, dim, want)
            seen[z] = set(dim)
        browser.close()
    assert seen[12] > seen[15], seen          # zoom 12 hides more classes than zoom 15
