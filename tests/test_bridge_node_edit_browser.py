"""Step 4c of docs/design/bridge_profile_edit.md: a node of the bridge profile gets another height in the open page (rsSetBridgeNode, the number in the Height box), the chains that meet at the
node are drawn from the profile with it, and rsBridgeProfile() gives the profile with the new height. The page evaluates the profile as the engine's maker does: the test makes the pieces of
the same profile with the engine and requires the same heights. Skipped without playwright."""
import geopandas as gpd
import pytest
from shapely.geometry import LineString

pw = pytest.importorskip("playwright.sync_api")

import roadstyle as rs  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
_A, _B, _C, _D = (18.000, 59.3000), (18.010, 59.3075), (18.020, 59.3125), (18.020, 59.3025)      # roads of 700 m to 900 m: long enough for a flat top and curves


def _edges():
    lines = [[_A, _B], [_B, _C], [_B, _D], [(18.03, 59.3), (18.0303, 59.3002)]]
    return gpd.GeoDataFrame({"highway": ["primary"] * 4, "bridge": ["yes"] * 4, "layer": ["1"] * 4, "edge_id": [1, 2, 3, 4], "name": ["A", "B", "C", "D"]},
                            geometry=[LineString(c) for c in lines], crs=4326)


def _open(p, html, errors):
    pg = p.chromium.launch(args=_ARGS).new_context(viewport={"width": 1300, "height": 800}).new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("http://rs.test/p.html", lambda r: r.fulfill(content_type="text/html", body=html))
    pg.goto("http://rs.test/p.html")
    pg.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
    pg.evaluate("map.jumpTo({center: [18.010, 59.3065], zoom: 15.6, pitch: 55, bearing: 20})")
    pg.wait_for_function("_bmStats().rows > 0", timeout=30_000)
    return pg


@pytest.fixture(scope="module", params=["smooth", "design"])
def curve(request):
    return request.param


@pytest.fixture(scope="module")
def pw_run():
    with pw.sync_playwright() as p:
        yield p


@pytest.fixture(scope="module")
def page(pw_run, curve):
    errors = []
    html = rs.render_dashboard(_edges(), view_3d=True, basemap="blank", bridge_profile={"parameters": {"height_rule": "design"} if curve == "design" else {}}).html
    pg = _open(pw_run, html, errors)
    pg.errors = errors
    yield pg
    pg.context.browser.close()


def _junction(page):
    return page.evaluate("()=>{ const g=rsBridgeGroups().find(x=>x.nodes.some(n=>n.kind==='junction')); return g.nodes.find(n=>n.kind==='junction').id; }")


def test_a_node_height_redraws_the_chains_that_meet_there_and_goes_back(page):
    page.evaluate("rsSetBridgeNode(" + repr(_junction(page)) + ", null)")
    node = _junction(page)
    before = page.evaluate("rsBridgeProfile()")
    z0 = next(n["z_m"] for g in before["groups"] for n in g["nodes"] if n["id"] == node)
    assert page.evaluate("_bmEdits().size") == 0, "nothing is edited at the start"
    page.evaluate(f"rsSetBridgeNode({node!r}, {z0 + 3.0})")
    meet = page.evaluate(f"rsBridgeGroups().flatMap(g=>g.nodes).find(n=>n.id==={node!r}).chains")
    edited = page.evaluate("[..._bmEdits().keys()]")
    assert sorted(edited) == sorted(int(c[1:]) for c in meet), (edited, meet)           # the chains that meet at the node, and only those
    after = page.evaluate("rsBridgeProfile()")
    n = next(n for g in after["groups"] for n in g["nodes"] if n["id"] == node)
    assert (n["z_m"], n["source"], n["method"]) == (pytest.approx(z0 + 3.0), "page", "chosen")
    assert all(c["top_m"] >= z0 + 3.0 - 1e-9 for g in after["groups"] for c in g["chains"] if c["id"] in meet), "the top of a chain is raised to its highest node"
    page.evaluate("map.triggerRepaint()")
    page.wait_for_timeout(500)
    st = page.evaluate("_bmStats()")
    assert st["rows"] > 0 and st["inverted"] == 0 and st["tooThick"] == 0, st
    page.evaluate(f"rsSetBridgeNode({node!r}, null)")
    assert page.evaluate("_bmEdits().size") == 0 and page.evaluate("rsBridgeProfile()") == before
    assert not page.errors, page.errors


def test_the_page_draws_the_heights_that_the_engine_makes_from_the_profile_it_gives(page, pw_run, curve):
    """The page's evaluation of the profile (JavaScript) and the maker's (Rust) are two copies of one curve: they must give the same height along each edited chain."""
    node = _junction(page)
    page.evaluate(f"rsSetBridgeNode({node!r}, 7.5)")
    profile = page.evaluate("rsBridgeProfile()")
    mine = page.evaluate("""()=>Object.fromEntries([..._bmEdits()].map(([k,e])=>[k,e.full]))""")
    page.evaluate(f"rsSetBridgeNode({node!r}, null)")
    errors = []
    other = _open(pw_run, rs.render_dashboard(_edges(), view_3d=True, basemap="blank", bridge_profile=profile).html, errors)
    try:
        # the pieces that the engine made: the height at the two ends of every piece of an edited chain
        pieces = other.evaluate("""()=>_bmFeats.filter(f=>!f.properties.__rs_casing_slab).map(f=>({chain:f.properties.__rs_chain, s0:f.properties.__rs_s0, s1:f.properties.__rs_s1,
            z0:f.properties.__rs_lift0*f.properties.__rs_full, z1:f.properties.__rs_lift1*f.properties.__rs_full}))""")
        assert pieces and not errors, errors
        worst, compared = 0.0, 0
        page.evaluate(f"rsSetBridgeNode({node!r}, 7.5)")
        for q in pieces:
            if str(q["chain"]) not in mine:
                continue
            for s_, z in ((q["s0"], q["z0"]), (q["s1"], q["z1"])):
                mine_z = page.evaluate("([c,s])=>{ const e=_bmEdits().get(c); return e.z(s*e.length); }", [q["chain"], s_])
                worst, compared = max(worst, abs(mine_z - z)), compared + 1
        assert compared >= 6, compared
        assert worst < 0.02, f"the page and the engine differ by {worst:.3f} m ({curve})"
        page.evaluate(f"rsSetBridgeNode({node!r}, null)")
    finally:
        other.context.browser.close()


def test_the_group_height_and_the_node_heights_give_way_to_the_last_one_that_was_given(page):
    node = _junction(page)
    group = page.evaluate(f"rsBridgeGroups().find(g=>g.nodes.some(n=>n.id==={node!r})).group")
    page.evaluate(f"rsSetBridgeNode({node!r}, 5)")
    page.evaluate(f"rsSetBridgeHeight({group}, 30)")
    assert page.evaluate("_bmEdits().size") == 0 and page.evaluate(f"rsBridgeGroups().find(g=>g.group==={group}).nodesSet") == [], "the group height was given last"
    page.evaluate(f"rsSetBridgeNode({node!r}, 5)")
    assert page.evaluate(f"rsBridgeGroups().find(g=>g.group==={group}).set") is False, "the node height was given last"
    page.evaluate(f"rsSetBridgeNode({node!r}, null)")
    page.evaluate(f"rsSetBridgeHeight({group}, null)")
    with pytest.raises(Exception, match="no node"):
        page.evaluate("rsSetBridgeNode('n999', 3)")
    with pytest.raises(Exception, match="0 or more"):
        page.evaluate(f"rsSetBridgeNode({node!r}, -2)")


def test_the_height_box_has_a_number_for_each_node_and_reset_and_copy(page):
    node = _junction(page)
    page.evaluate("rsDeselect()")
    group = page.evaluate(f"rsBridgeGroups().find(g=>g.nodes.some(n=>n.id==={node!r})).group")
    page.evaluate(f"document.dispatchEvent(new CustomEvent('rs:select', {{detail: {{properties: {{__rs_group: {group}}}}}}}))")
    page.evaluate("rs.tools.open('roads')")
    page.wait_for_timeout(300)
    inputs = page.evaluate("[...document.querySelectorAll('#rs-roads-box input[data-bn]')].map(i=>i.dataset.bn)")
    assert node in inputs and len(inputs) >= 2, inputs
    assert page.evaluate("document.querySelector('#rs-roads-box button[data-bn-reset]').disabled") is True
    sel = f'#rs-roads-box input[data-bn="{node}"]'
    page.fill(sel, "4.5")
    page.press(sel, "Enter")
    page.wait_for_timeout(400)
    assert page.evaluate(f"rsBridgeGroups().flatMap(g=>g.nodes).find(n=>n.id==={node!r}).z_m") == 4.5
    assert page.evaluate("document.querySelector('#rs-roads-box button[data-bn-reset]').disabled") is False
    assert page.evaluate(f'document.querySelector(\'#rs-roads-box .rs-rd-bn[data-node="{node}"] em\').textContent') == "page"
    page.click("#rs-roads-box button[data-bn-reset]")
    page.wait_for_timeout(300)
    assert page.evaluate("_bmEdits().size") == 0
    page.evaluate("rsDeselect()")
    assert not page.errors, page.errors


def test_a_free_end_of_a_bridge_is_on_the_ground_and_its_number_is_fixed(page):
    ground = page.evaluate("rsBridgeGroups().flatMap(g=>g.nodes).find(n=>n.kind==='ground').id")
    with pytest.raises(Exception, match="free end of its bridge"):
        page.evaluate(f"rsSetBridgeNode({ground!r}, 3)")
    page.evaluate(f"rsSetBridgeNode({ground!r}, 0)")                      # 0 is what it is
    assert page.evaluate("_bmEdits().size") == 0
    node = _junction(page)
    group = page.evaluate(f"rsBridgeGroups().find(g=>g.nodes.some(n=>n.id==={node!r})).group")
    page.evaluate(f"document.dispatchEvent(new CustomEvent('rs:select', {{detail: {{properties: {{__rs_group: {group}}}}}}}))")
    page.evaluate("rs.tools.open('roads')")
    page.wait_for_timeout(300)
    assert page.evaluate(f'document.querySelector(\'#rs-roads-box input[data-bn="{ground}"]\').disabled') is True
    assert page.evaluate(f'document.querySelector(\'#rs-roads-box input[data-bn="{node}"]\').disabled') is False
    page.evaluate("rsDeselect()")
