"""The 3D bridge mesh on the terrain: the checks that a fix must not break, in a real browser. The ground is a synthetic Terrarium tile (a steep slope, answered here, no network), so every run has the same hills. Each check is a thing that was wrong once and came back with a later fix:
no deck piece under the ground, no slab upside down or thicker than it is made, the free end of a deck flush with the ground, the chains that meet at a node
agreeing on its height, every chain drawn (a chain longer than the screen too), a click on a deck picked on the mesh with the marker on the deck. Skipped without playwright."""
import struct
import zlib

import pytest

pw = pytest.importorskip("playwright.sync_api")

import geopandas as gpd  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

import roadstyle as rs  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
_A, _B, _C, _D = (18.000, 59.3000), (18.002, 59.3015), (18.004, 59.3025), (18.004, 59.3005)      # a Y of three bridges: A-B 200 m, B-C and B-D 160 m
_TINY = [(18.010, 59.300), (18.01003, 59.30001)]                                                    # a bridge of 3 m: it must not be a wall


def _tile():
    """A Terrarium tile: the height rises 4 m for each pixel, from 0 m at the left to 1020 m at the right (R*256 + G + B/256 - 32768): a steep hill, so that the ground
    differs by metres across the width of a deck."""
    row = b"\x00" + b"".join(bytes(((32768 + 4 * x) >> 8, (32768 + 4 * x) & 255, 0)) for x in range(256))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 256, 256, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(row * 256)) + chunk(b"IEND", b"")


def _edges():
    lines = [[_A, _B], [_B, _C], [_B, _D], _TINY]
    return gpd.GeoDataFrame({"highway": ["primary"] * 4, "bridge": ["yes"] * 4, "layer": ["1"] * 4, "edge_id": [1, 2, 3, 4]}, crs=4326, geometry=[LineString(c) for c in lines])


@pytest.fixture(scope="module")
def page():
    html = rs.render_dashboard(_edges(), view_3d=True, basemap="blank").html
    errors = []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=_ARGS)
        pg = browser.new_context(viewport={"width": 1200, "height": 800}).new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type in ("warning", "error") and "roadstyle" in m.text else None)
        pg.route("**/elevation-tiles-prod/**", lambda r: r.fulfill(content_type="image/png", body=_tile(), headers={"access-control-allow-origin": "*"}))
        pg.route("http://rs.test/p.html", lambda r: r.fulfill(content_type="text/html", body=html))
        pg.goto("http://rs.test/p.html")
        pg.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rs", timeout=60_000)
        pg.evaluate("map.jumpTo({center: [18.002, 59.301], zoom: 17.2, pitch: 55, bearing: 20})")
        pg.wait_for_function("_bmStats().rows > 0", timeout=30_000)
        pg.errors = errors
        yield pg
        browser.close()


def _settled(page):
    page.wait_for_function("_bmStats().rows > 0 && !_bmMiss", timeout=40_000)
    page.wait_for_timeout(600)
    return page.evaluate("_bmStats()")


def test_the_mesh_has_nothing_wrong_in_its_own_vertices_on_flat_ground_and_on_the_terrain(page):
    flat = _settled(page)
    assert flat["inverted"] == 0 and flat["tooThick"] == 0 and flat["underGround"] == 0 and flat["maxEndGap"] < 0.05, flat
    page.evaluate("rsTerrain(true)")
    page.wait_for_timeout(500)
    hills = _settled(page)
    assert hills["rows"] > 0 and hills["inverted"] == 0 and hills["tooThick"] == 0 and hills["underGround"] == 0, hills
    assert hills["maxEndGap"] < 0.05, hills          # the free end of a deck is flush with the ground that the map draws
    assert not [e for e in page.errors if "pageerror" in e or "Error" in e], page.errors


def test_every_chain_has_its_ground_heights_and_a_bridge_of_3_m_is_not_a_wall(page):
    page.evaluate("rsTerrain(true)")
    _settled(page)
    r = page.evaluate("""()=>{ const nulls=[..._bmEnds.values()].filter(v=>v.za==null||v.zb==null).length, chains=_bmEnds.size;
        const tiny=_bmFeats.filter(f=>!f.properties.__rs_casing_slab && f.properties.__rs_full<=5.01 && f.properties.__rs_s1<=1 && Math.abs(f.geometry.coordinates[0][0][0]-18.010)<0.0005);
        return {nulls, chains, tinyTop: Math.max(0,...tiny.map(f=>f.properties.__rs_height))}; }""")
    assert r["chains"] >= 4 and r["nulls"] == 0, r
    assert r["tinyTop"] < 1.6, r                      # a bridge of 3 m rises as far as the grade lets it (a few cm), plus the slab


def test_the_chains_that_meet_at_a_node_have_one_height_there(page):
    page.evaluate("rsTerrain(true)")
    _settled(page)
    nodes = page.evaluate("""()=>{ const by=new Map(); _bmFeats.forEach(f=>{ const p=f.properties; if(p.__rs_casing_slab) return;
        for(const [end,lift] of [[p.__rs_enda,p.__rs_lift0],[p.__rs_endb,p.__rs_lift1]]) if(end){ const k=end.join(','); let e=by.get(k); if(!e) by.set(k,e=[]); e.push([p.__rs_chain,lift]); } });
        return [...by.entries()].map(([k,v])=>({k, chains:[...new Set(v.map(x=>x[0]))].length, spread:Math.max(...v.map(x=>x[1]))-Math.min(...v.map(x=>x[1]))})); }""")
    joined = [n for n in nodes if n["chains"] >= 2]
    assert joined and all(n["spread"] < 1e-9 for n in joined), nodes


def test_a_click_on_a_deck_is_picked_on_the_mesh_and_the_marker_stands_on_the_deck(page):
    page.evaluate("rsTerrain(true); rsSetStreetViewMarker(true)")
    _settled(page)
    c = page.evaluate("""()=>{ const f=_bmFeats.find(f=>!f.properties.__rs_casing_slab && f.properties.__rs_lift0>0.95 && f.properties.__rs_lift1>0.95); const r=f.geometry.coordinates[0], n=r.length-1; let x=0,y=0;
        for(let i=0;i<n;i++){x+=r[i][0];y+=r[i][1];} const c=[x/n,y/n], road=f.properties.__rs_edges[0]; const z=_bmDeckZ(c[0],c[1],road), g=_bmElev(c);
        return {c, road, px:_bmProject(c[0],c[1],g+z)}; }""")
    x, y = c["px"]
    page.mouse.move(x, y)
    page.wait_for_timeout(300)
    page.mouse.click(x, y)
    page.wait_for_timeout(1500)
    r = page.evaluate("""()=>{ const e=document.querySelector('.rs-svm'); const b=e&&e.getBoundingClientRect(); return {id:_svPos&&_svPos.id, marker:b&&[b.x+b.width/2,b.y+b.height/2]}; }""")
    assert r["id"] == c["road"], r                      # the click went to the deck, not to the road under it
    assert r["marker"] and abs(r["marker"][0] - x) < 25 and abs(r["marker"][1] - y) < 25, (r, x, y)


def test_a_deck_and_its_casing_slabs_have_one_height_across_their_width(page):
    """The ground is read on the chain's centre line: a casing slab lies to the side of its deck, where the ground is metres higher or lower on a hill, and it came off the deck
    (tall strips beside the road) when each vertex read the ground under itself."""
    page.evaluate("rsTerrain(true)")
    _settled(page)
    worst = page.evaluate("""()=>{ const top=(k,mz)=>{ const [a,b]=_bmRanges[k]; let m=-1e9; for(let v=a; v<b; v++) m=Math.max(m,_bmPosArr[v*3+2]/mz); return m; };
        let worst=0, pairs=0;
        _bmFeats.forEach((f,k)=>{ const p=f.properties; if(!p.__rs_casing_slab) return; const [a,b]=_bmRanges[k]; if(b<=a) return;
          const j=_bmFeats.findIndex((g,i)=>!g.properties.__rs_casing_slab && g.properties.__rs_chain===p.__rs_chain && g.properties.__rs_s0===p.__rs_s0 && _bmRanges[i][1]>_bmRanges[i][0]); if(j<0) return;
          const lat=f.geometry.coordinates[0][0][1], mz=maplibregl.MercatorCoordinate.fromLngLat([18,lat]).meterInMercatorCoordinateUnits();
          worst=Math.max(worst, Math.abs(top(k,mz)-top(j,mz))); pairs++; });
        return {worst, pairs}; }""")
    assert worst["pairs"] > 10 and worst["worst"] < 1.0, worst        # the slab's top is within the slab's own thickness of the deck's top
