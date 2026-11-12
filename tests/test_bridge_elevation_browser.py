"""A bridge profile with z_reference "elevation" (docs/guides/bridge-profile.md, "Heights as elevations"): the heights are elevations in the vertical datum of the area's ground, the deck
is drawn at its elevation over the page's ground, and a free end that is not on the ground is an error that says so (the bridge is not drawn). The ground is a plane (100 + 2 c + r metres,
as in test_ground_terrain), so the height of the ground at each node is known. Skipped without playwright."""
import geopandas as gpd
import pytest
from shapely.geometry import LineString
from test_ground_terrain import COLS, FACTS, NORTH, ROWS, WEST, D, _archive, _grid, _plane

pw = pytest.importorskip("playwright.sync_api")

import base64  # noqa: E402

import roadstyle as rs  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
# a Y of three bridges on the grid of the ground: the junction B in the middle, the free ends A, C and D (about 400 m, 400 m and 500 m long)
_CELL = {"A": (8, 12), "B": (22, 20), "C": (36, 14), "D": (22, 34)}
assert max(c for c, _ in _CELL.values()) < COLS and max(r for _, r in _CELL.values()) < ROWS


def _at(name):
    c, r = _CELL[name]
    return (WEST + (c + 0.5) * D, NORTH - (r + 0.5) * D)


def _ground_z(name):
    return _plane(*_CELL[name])


def _edges():
    lines = [[_at("A"), _at("B")], [_at("B"), _at("C")], [_at("B"), _at("D")]]
    return gpd.GeoDataFrame({"highway": ["primary"] * 3, "bridge": ["yes"] * 3, "layer": ["1"] * 3, "edge_id": [1, 2, 3]}, crs=4326, geometry=[LineString(c) for c in lines])


def _given(heights):
    """The input profile: `heights` is the elevation of each node (name -> metres)."""
    return {"parameters": {"z_reference": "elevation"},
            "ground": {k: FACTS[k] for k in ("id", "source", "product", "vertical_datum")},
            "groups": [{"nodes": [{"lonlat": list(_at(n)), "z_m": z, "source": "test", "method": "measured"} for n, z in heights.items()]}]}


_ON_GROUND = {"A": _ground_z("A"), "B": 190.0, "C": _ground_z("C"), "D": _ground_z("D")}


def _ground_option():
    archive = _archive(_grid(_plane))
    return {**FACTS, "terrain": "data:application/vnd.pmtiles;base64," + base64.b64encode(archive).decode()}


@pytest.fixture(scope="module")
def pw_run():
    with pw.sync_playwright() as p:
        yield p


def _open(p, given, errors):
    html = rs.render_dashboard(_edges(), view_3d=True, basemap="blank", ground=_ground_option(), bridge_profile=given).html
    pg = p.chromium.launch(args=_ARGS).new_context(viewport={"width": 1300, "height": 800}).new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("http://rs.test/p.html", lambda r: r.fulfill(content_type="text/html", body=html))
    pg.goto("http://rs.test/p.html")
    pg.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rsTerrain", timeout=60_000)
    centre = [WEST + 22 * D, NORTH - 22 * D]
    pg.evaluate("""c => new Promise(ok => { document.addEventListener('rs:terrainchange', ok, {once: true}); map.jumpTo({center: c, zoom: 15.2, pitch: 55}); rsTerrain(true); })""", centre)
    pg.wait_for_function("map.getTerrain() && map.areTilesLoaded() && !_bmMiss", timeout=40_000)
    pg.wait_for_timeout(800)
    return pg


def test_an_elevation_profile_draws_the_deck_at_its_elevation_over_the_ground(pw_run):
    errors = []
    pg = _open(pw_run, _given(_ON_GROUND), errors)
    pg.wait_for_function("_bmStats().rows > 0", timeout=40_000)
    assert pg.evaluate("rsBridgeProblems()") == []
    st = pg.evaluate("_bmStats()")
    assert st["inverted"] == 0 and st["tooThick"] == 0 and st["underGround"] == 0, st
    # a free end is at the clearance over the ground, to the cross slope of this plane (0.09 m for each metre: the deck is level across its width, so a side of it is 0.2 m from the ground's height at its middle)
    assert st["maxEndGap"] < 0.5 and st["minEndClearance"] >= 0.3, st
    # the highest vertex is the junction's elevation plus the slab (190 m): the deck is where the profile says, not over a level line between the ends
    top = pg.evaluate("""() => { const f = _bmFeats.find(f => !f.properties.__rs_casing_slab), mz = 1 / (_bmM * Math.cos(f.geometry.coordinates[0][0][1] * Math.PI / 180));
                                 let m = -1e9; for(let i = 2; i < _bmPosArr.length; i += 3) m = Math.max(m, _bmPosArr[i] / mz); return [m, f.properties.__rs_thick]; }""")
    assert 190.0 <= top[0] <= 190.0 + top[1] + 0.35, top
    groups = pg.evaluate("rsBridgeGroups()")
    assert groups[0]["zReference"] == "elevation" and groups[0]["height"] == pytest.approx(190.0)
    # the page evaluates the profile as the engine does: a chain with no interior point is one straight grade from node to node
    mid = pg.evaluate("() => { const e = _bmEdits().get(1); return [e.z(0), e.z(e.length / 2), e.z(e.length)]; }")
    assert mid[1] == pytest.approx((mid[0] + mid[2]) / 2) and {round(mid[0], 3), round(mid[2], 3)} <= {round(v, 3) for v in _ON_GROUND.values()}, mid
    assert not errors, errors
    pg.context.browser.close()


def test_a_free_end_that_is_not_on_the_ground_is_an_error_and_its_bridge_is_not_drawn(pw_run):
    errors = []
    bad = {**_ON_GROUND, "A": _ground_z("A") + 20.0}
    pg = _open(pw_run, _given(bad), errors)
    pg.wait_for_function("rsBridgeProblems().length > 0", timeout=40_000)
    problems = pg.evaluate("rsBridgeProblems()")
    assert len(problems) == 1 and problems[0]["z_m"] == pytest.approx(bad["A"]) and problems[0]["ground_m"] == pytest.approx(_ground_z("A"), abs=0.5), problems
    assert "must be on the ground" in problems[0]["message"] and problems[0]["node"] in problems[0]["message"]
    # the bridge that ends there is not drawn: the chain A-B has no vertex, the others have
    drawn = pg.evaluate("""p => { const n = {}; _bmFeats.forEach((f, k) => { if(f.properties.__rs_casing_slab) return; const c = f.properties.__rs_chain; n[c] = (n[c] || 0) + (_bmRanges[k][1] - _bmRanges[k][0]); }); return n; }""", problems)
    bad_chain = int(problems[0]["chains"][0][1:])
    assert drawn[str(bad_chain)] == 0 and all(v > 0 for k, v in drawn.items() if k != str(bad_chain)), (drawn, bad_chain)
    # the page says so on the screen, not only in the console
    pg.wait_for_function("[...document.querySelectorAll('#rs-toasts .rs-toast.error')].some(t => t.textContent.includes('free end'))", timeout=10_000)
    pg.wait_for_function("document.querySelectorAll('#rs-toasts .rs-toast.error:not(.out)').length === 1", timeout=10_000)         # the message of the page without terrain went when the terrain came
    # a person fixes the elevation in the page: the problem goes and the bridge is drawn
    pg.evaluate(f"rsSetBridgeNode({problems[0]['node']!r}, {_ground_z('A')})")
    pg.wait_for_function("rsBridgeProblems().length === 0", timeout=20_000)
    pg.wait_for_function("document.querySelectorAll('#rs-toasts .rs-toast.error:not(.out)').length === 0", timeout=10_000)         # the message goes when the problem is solved
    pg.wait_for_timeout(500)
    assert pg.evaluate("_bmStats().rows") > 0
    assert not [e for e in errors if "pageerror" in e], errors
    pg.context.browser.close()


def test_an_elevation_has_no_group_height_and_any_number_is_an_elevation(pw_run):
    errors = []
    pg = _open(pw_run, _given(_ON_GROUND), errors)
    pg.wait_for_function("_bmStats().rows > 0", timeout=40_000)
    with pytest.raises(Exception, match="elevations"):
        pg.evaluate("rsSetBridgeHeight(rsBridgeGroups()[0].group, 20)")
    # a free end can be set (it has an elevation), and a negative number is allowed (below the sea)
    nid = pg.evaluate("rsBridgeGroups()[0].nodes.find(n => n.kind === 'ground').id")
    pg.evaluate(f"rsSetBridgeNode({nid!r}, -4.5)")
    prof = pg.evaluate("rsBridgeProfile()")
    assert prof["parameters"]["z_reference"] == "elevation" and prof["ground"]["id"] == FACTS["id"]
    assert any(n["z_m"] == -4.5 and n["source"] == "page" for g in prof["groups"] for n in g["nodes"])
    pg.context.browser.close()
