"""The height of the selected 3D bridge in the Roads box: a click on a deck selects its group of bridges, the box under "3D bridges" has the group's height in metres,
a new number gives the whole group that height, Reset gives the first one back, and the block is only there while a 3D bridge is selected and the bridges are 3D. Skipped without playwright."""
import geopandas as gpd
import pytest
from shapely.geometry import LineString

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
_A, _B, _C, _D = (18.000, 59.3000), (18.002, 59.3015), (18.004, 59.3025), (18.004, 59.3005)


def _edges():
    lines = [[_A, _B], [_B, _C], [_B, _D], [(18.01, 59.3), (18.0103, 59.3002)]]
    return gpd.GeoDataFrame({"highway": ["primary"] * 4, "bridge": ["yes"] * 4, "layer": ["1"] * 4, "edge_id": [1, 2, 3, 4], "name": ["A", "B", "C", "D"]},
                            geometry=[LineString(c) for c in lines], crs=4326)


@pytest.fixture(scope="module")
def page():
    html = rs.render_dashboard(_edges(), view_3d=True, basemap="blank").html
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        pg = browser.new_context(viewport={"width": 1300, "height": 800}).new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route("http://rs.test/p.html", lambda r: r.fulfill(content_type="text/html", body=html))
        pg.goto("http://rs.test/p.html")
        pg.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
        pg.evaluate("map.jumpTo({center: [18.002, 59.301], zoom: 17.2, pitch: 55, bearing: 20})")
        pg.wait_for_function("_bmStats().rows > 0", timeout=30_000)
        pg.errors = errors
        yield pg
        browser.close()


def _click_the_deck_of_the_y(page):
    c = page.evaluate("""()=>{ const f=_bmFeats.find(f=>!f.properties.__rs_casing_slab && f.properties.__rs_edges[0]===0 && f.properties.__rs_lift0>0.95 && f.properties.__rs_lift1>0.95);
        const r=f.geometry.coordinates[0], n=r.length-1; let x=0,y=0; for(let i=0;i<n;i++){x+=r[i][0];y+=r[i][1];} const c=[x/n,y/n];
        return {group:f.properties.__rs_group, px:_bmProject(c[0],c[1],_bmDeckZ(c[0],c[1],f.properties.__rs_edges[0]))}; }""")
    page.mouse.move(*c["px"])
    page.wait_for_timeout(300)
    page.mouse.click(*c["px"])
    page.wait_for_timeout(800)
    return c["group"]


def _box(page):
    page.evaluate("rs.tools.open('roads')")
    page.wait_for_timeout(300)
    return page.evaluate("""()=>{ const i=document.querySelector('#rs-roads-box input[data-bh]'), b=document.querySelector('#rs-roads-box button[data-bh-reset]'), n=document.querySelector('#rs-roads-box .rs-rd-bhn');
        return {has: !!i, value: i&&+i.value, reset: b&&!b.disabled, note: n&&n.textContent}; }""")


def test_the_box_has_the_height_of_the_selected_bridge_and_sets_it_for_the_whole_group(page):
    page.evaluate("rsDeselect()")
    assert _box(page)["has"] is False                                  # nothing selected: no block
    group = _click_the_deck_of_the_y(page)
    first = page.evaluate("(g)=>rsBridgeHeight(g)", group)
    box = _box(page)
    assert box["has"] and box["value"] == pytest.approx(first, abs=0.05) and box["reset"] is False, box
    assert "3 roads" in box["note"], box                               # the three roads of the Y are one group
    page.fill("#rs-roads-box input[data-bh]", "12")
    page.press("#rs-roads-box input[data-bh]", "Enter")
    page.wait_for_timeout(500)
    assert page.evaluate("(g)=>rsBridgeHeight(g)", group) == 12
    box = _box(page)
    assert box["value"] == 12 and box["reset"] is True, box
    page.click("#rs-roads-box button[data-bh-reset]")
    page.wait_for_timeout(500)
    box = _box(page)
    assert box["value"] == pytest.approx(first, abs=0.05) and box["reset"] is False, box


def test_a_wrong_number_is_not_taken_and_the_block_goes_with_the_selection_and_with_the_3d_switch(page):
    group = _click_the_deck_of_the_y(page)
    before = page.evaluate("(g)=>rsBridgeHeight(g)", group)
    _box(page)
    page.fill("#rs-roads-box input[data-bh]", "-4")
    page.press("#rs-roads-box input[data-bh]", "Enter")
    page.wait_for_timeout(400)
    assert page.evaluate("(g)=>rsBridgeHeight(g)", group) == before     # a negative height does nothing (the box shows the height again)
    assert _box(page)["value"] == pytest.approx(before, abs=0.05)
    page.evaluate("rsSetBridges3D(false)")
    assert _box(page)["has"] is False                                   # the bridges are flat: no height to set
    page.evaluate("rsSetBridges3D(true)")
    assert _box(page)["has"] is True
    page.evaluate("rsDeselect()")
    assert _box(page)["has"] is False
    assert not page.errors, page.errors
