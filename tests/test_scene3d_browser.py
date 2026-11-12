"""The 3D road tiles (`scene_3d=`, docs/design/scene_3d_tiles.md, dashboard/scene3d.js): a PMTiles archive of GLB files drawn in the map. The archive here is made by the test
(two tiles: a road and a bridge deck, in the project CRS of SimReady's archives); the positions are checked against pyproj, not against the page's own formula. Skipped without
playwright and pyproj. The render-time checks (the ground, the CRS) need no browser."""
import gzip
import io
import json
import math
import re
import struct
from pathlib import Path

import numpy as np
import pytest

import roadstyle as rs
from roadstyle._engine import rust

pw = pytest.importorskip("playwright.sync_api")
pyproj = pytest.importorskip("pyproj")
pytest.importorskip("pmtiles")
from pmtiles.tile import Compression, TileType, zxy_to_tileid  # noqa: E402
from pmtiles.writer import write  # noqa: E402

_ARGS = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
GROUND_ID = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
Z = 16
# the places of the CRS of the page: (EPSG code, an origin in that CRS)
PLACES = {"EPSG:32632": (371500.0, 4842300.0), "EPSG:3006": (674000.0, 6580000.0), "EPSG:3301": (659000.0, 6474000.0), "EPSG:32756": (334000.0, 6252000.0),
          "EPSG:3857": (826000.0, 5430000.0)}


# ---- the archive: GLB tiles in a PMTiles v3 file, as SimReady writes them
def _glb(parts, crs, origin, ground=GROUND_ID):
    """parts: {kind: [{"quad": [(east, north, height) x 4], "extras": {...}, "color": [r, g, b]}]}. A vertex is (east - origin.x, height, -(north - origin.y))."""
    nodes = [{"name": "simready", "children": [], "extras": {"simready": {"crs": crs, "vertical_datum": "EGM2008", "origin": [origin[0], origin[1], 0.0],
                                                                         "axes": "x=east, y=up, z=-north", "area": "test", "ground": ground}}}]
    meshes, accessors, views, materials, blob = [], [], [], [], bytearray()

    def add(data, kind, ctype, count, ty):
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)})
        accessors.append({"bufferView": len(views) - 1, "componentType": ctype, "count": count, "type": ty})
        blob.extend(data)
        return len(accessors) - 1

    for kind, prims in parts.items():
        kid = len(nodes)
        nodes.append({"name": kind, "children": []})
        nodes[0]["children"].append(kid)
        for k, p in enumerate(prims):
            pos = np.array([[e - origin[0], h, -(n - origin[1])] for e, n, h in p["quad"]], dtype="<f4")
            nrm = np.tile(np.array([0, 1, 0], dtype="<f4"), (4, 1))
            idx = np.array([0, 1, 2, 0, 2, 3], dtype="<u4")
            a = add(pos.tobytes(), "p", 5126, 4, "VEC3")
            b = add(nrm.tobytes(), "n", 5126, 4, "VEC3")
            c = add(idx.tobytes(), "i", 5125, 6, "SCALAR")
            materials.append({"name": kind, "pbrMetallicRoughness": {"baseColorFactor": [*p["color"], 1.0]}})
            meshes.append({"name": f"{kind} {k}", "primitives": [{"attributes": {"POSITION": a, "NORMAL": b}, "indices": c, "material": len(materials) - 1, "extras": p["extras"]}]})
            nodes[kid]["children"].append(len(nodes))
            nodes.append({"name": f"{kind} {k}", "mesh": len(meshes) - 1})
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes, "meshes": meshes, "accessors": accessors, "bufferViews": views,
           "materials": materials, "buffers": [{"byteLength": len(blob)}]}
    j = json.dumps(doc).encode()
    j += b" " * (-len(j) % 4)
    blob += b"\0" * (-len(blob) % 4)
    body = struct.pack("<II", len(j), 0x4E4F534A) + j + struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body


def _tile_of(lon, lat, z=Z):
    n = 2 ** z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def _to_lonlat(code, e, n):
    c = pyproj.CRS.from_user_input(code)
    return pyproj.Transformer.from_crs(c, c.geodetic_crs, always_xy=True).transform(e, n)


def _archive(path, tiles, crs, origin, kinds=("roads", "kerbs", "markings", "structures"), ground=GROUND_ID):
    """tiles: {(x, y): glb bytes}."""
    with write(str(path)) as w:
        for (x, y), g in sorted(tiles.items()):
            w.write_tile(zxy_to_tileid(Z, x, y), gzip.compress(g))
        w.finalize({"tile_type": TileType.UNKNOWN, "tile_compression": Compression.GZIP, "min_lon_e7": 0, "min_lat_e7": 0, "max_lon_e7": 1, "max_lat_e7": 1, "center_zoom": Z,
                    "center_lon_e7": 0, "center_lat_e7": 0},
                   {"name": "test", "format": "glb", "kinds": list(kinds), "zoom": Z,
                    "simready": {"crs": crs, "vertical_datum": "EGM2008", "origin": [origin[0], origin[1], 0.0], "axes": "x=east, y=up, z=-north", "area": "test", "ground": ground}})


def _quad(e, n, h, s=20.0):
    return [(e, n, h), (e + s, n, h), (e + s, n + s, h), (e, n + s, h)]


def _ground(lon, lat, ground=GROUND_ID):
    """A flat ground at 0 m (a 0.04 degree square of 1 arc-second cells) around the point: the ground option, with its terrain file."""
    d, cols = 1 / 3600, 144
    r, c = np.mgrid[0:cols, 0:cols]
    west, north = lon - cols * d / 2, lat + cols * d / 2
    facts = {"id": ground, "source": "test", "product": "DTM", "vertical_datum": "EGM2008", "resolution_m": 30, "license": "CC0"}
    arch = rust().terrain_pmtiles(c.ravel().tolist(), r.ravel().tolist(), (west + (c.ravel() + 0.5) * d).tolist(), (north - (r.ravel() + 0.5) * d).tolist(),
                                  np.zeros(cols * cols).tolist(), json.dumps(facts))
    import base64
    return {**facts, "terrain": "data:application/vnd.pmtiles;base64," + base64.b64encode(arch).decode()}


def _edges(lon, lat):
    import geopandas as gpd
    from shapely.geometry import LineString
    return gpd.GeoDataFrame({"highway": ["primary"], "name": ["A street"], "edge_id": [1]}, geometry=[LineString([(lon, lat), (lon + 1e-3, lat)])], crs=4326)


def _scene(tmp_path, code="EPSG:32632", ground=None, with_ground=True, buildings=False, **kw):
    """The place of `code` with a road tile (the tile of the origin + 10 m) and a deck tile (the next tile to the east). Returns (html, facts)."""
    o = PLACES[code]
    lon, lat = _to_lonlat(code, o[0] + 10, o[1] + 10)
    tx, ty = _tile_of(lon, lat)
    # the middle of the next tile to the east, in the CRS
    n = 2 ** Z
    lon_b = (tx + 1.5) / n * 360 - 180
    lat_b = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (ty + 0.5) / n))))
    t = pyproj.Transformer.from_crs(pyproj.CRS.from_user_input(code).geodetic_crs, pyproj.CRS.from_user_input(code), always_xy=True)
    eb, nb = t.transform(lon_b, lat_b)
    road = {"quad": _quad(o[0], o[1], 5.0), "extras": {"lane_id": "4064037692617345284", "role": "through", "use": ["auto", "bus"]}, "color": [0.9, 0.2, 0.2]}
    deck = {"quad": _quad(eb, nb, 20.0), "extras": {"structure_id": "S9", "role": "deck"}, "color": [0.2, 0.2, 0.9]}
    path = tmp_path / "scene.pmtiles"
    house = {"quad": _quad(o[0] + 40, o[1] + 40, 12.0), "extras": {"building_id": "B1"}, "color": [0.8, 0.8, 0.7]}
    kinds = ("roads", "kerbs", "markings", "structures") + (("buildings",) if buildings else ())
    _archive(path, {(tx, ty): _glb({"roads": [road], **({"buildings": [house]} if buildings else {})}, code, o), (tx + 1, ty): _glb({"structures": [deck]}, code, o)}, code, o, kinds=kinds)
    g = ground if ground is not None else (_ground(lon, lat) if with_ground else None)
    html = rs.render_dashboard(_edges(lon, lat), basemap="blank", ground=g, scene_3d={"tiles": str(path), "url": "http://rs.test/scene.pmtiles"}, minzoom=False, **kw).html
    return html, dict(path=path, lon=lon, lat=lat, road=road, deck=deck, origin=o, code=code, quads={"roads": (o, 5.0), "structures": ((eb, nb), 20.0)})


def _serve(page, html, path):
    data = Path(path).read_bytes()

    def archive(route):
        r = route.request.headers.get("range")
        m = re.match(r"bytes=(\d+)-(\d*)", r or "")
        if not m:
            return route.fulfill(status=200, body=data, headers={"content-type": "application/octet-stream"})
        a = int(m.group(1))
        b = min(int(m.group(2)) if m.group(2) else len(data) - 1, len(data) - 1)
        route.fulfill(status=206, body=data[a:b + 1], headers={"content-range": f"bytes {a}-{b}/{len(data)}", "content-type": "application/octet-stream"})

    page.route("http://rs.test/p.html", lambda r: r.fulfill(content_type="text/html", body=html))
    page.route("http://rs.test/scene.pmtiles", archive)


def _open(p, html, path, zoom=18, center=None, terrain=True):
    browser = p.chromium.launch(args=_ARGS)
    page = browser.new_page(viewport={"width": 900, "height": 600})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _serve(page, html, path)
    page.goto("http://rs.test/p.html")
    page.wait_for_function("window.map && window.map.loaded() && !!window.rsScene3dStatus", timeout=60_000)
    if terrain:
        page.evaluate("rsTerrain(true)")
        page.wait_for_function("!!map.getTerrain()", timeout=60_000)
    return browser, page, errors


def _goto(page, lon, lat, zoom=18):
    page.evaluate("c => map.jumpTo({center: c, zoom: %s, pitch: 0, bearing: 0})" % zoom, [lon, lat])
    page.wait_for_function("(() => { const s = rsScene3dStatus(); return s.tiles.wanted > 0 && s.tiles.loading === 0; })()", timeout=60_000)
    page.wait_for_timeout(1500)


def _pixel(page, lon, lat):
    from PIL import Image
    x, y = page.evaluate("c => { const p = map.project(c); return [p.x, p.y]; }", [lon, lat])
    im = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
    return (x, y), im.getpixel((int(round(x)), int(round(y))))


def _centre(code, en):
    return _to_lonlat(code, en[0] + 10.0, en[1] + 10.0)


# ---- the checks that need no browser
def test_a_ground_that_is_not_the_archives_is_an_error_that_names_both_ids(tmp_path):
    o = PLACES["EPSG:32632"]
    path = tmp_path / "a.pmtiles"
    _archive(path, {(34000, 23000): _glb({"roads": []}, "EPSG:32632", o)}, "EPSG:32632", o)
    lon, lat = _to_lonlat("EPSG:32632", *o)
    other = "f" * 64
    with pytest.raises(ValueError, match=rf"{GROUND_ID}.*{other}|{other}.*{GROUND_ID}"):
        rs.render_dashboard(_edges(lon, lat), ground=_ground(lon, lat, other), scene_3d=str(path))
    with pytest.raises(ValueError, match="the page has no ground"):
        rs.render_dashboard(_edges(lon, lat), scene_3d=str(path))


def test_an_archive_of_a_crs_that_is_not_in_the_table_is_an_error_that_lists_the_codes(tmp_path):
    o = PLACES["EPSG:32632"]
    path = tmp_path / "a.pmtiles"
    _archive(path, {(34000, 23000): _glb({"roads": []}, "EPSG:2154", o)}, "EPSG:2154", o)
    lon, lat = _to_lonlat("EPSG:32632", *o)
    with pytest.raises(ValueError, match=r"EPSG:2154.*32601-32660.*3301"):
        rs.render_dashboard(_edges(lon, lat), ground=_ground(lon, lat), scene_3d=str(path))


def test_a_wrong_value_of_the_keyword_is_an_error(tmp_path):
    lon, lat = _to_lonlat("EPSG:32632", *PLACES["EPSG:32632"])
    with pytest.raises(ValueError, match="scene_3d"):
        rs.render_dashboard(_edges(lon, lat), scene_3d=5)
    with pytest.raises(ValueError, match="not a PMTiles|No such file|did not|os error"):
        rs.render_dashboard(_edges(lon, lat), scene_3d=str(tmp_path / "none.pmtiles"))


# ---- the page
@pytest.mark.parametrize("code", list(PLACES))
def test_the_triangles_are_where_the_crs_and_the_origin_say(tmp_path, code):
    """Each vertex of the road quad, as the page holds it, against pyproj (the same CRS to its own geodetic CRS): within 2 mm, and the height as it is."""
    html, f = _scene(tmp_path, code)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, html, f["path"])
        try:
            _goto(page, f["lon"], f["lat"])
            st = page.evaluate("rsScene3dStatus()")
            assert st["problems"] == [] and st["drawn"], st
            vs = page.evaluate("rsScene3dVertices(100)")
            road = [v for v in vs if v["kind"] == "roads"]
            want = [(*_to_lonlat(code, e, n), h) for e, n, h in f["road"]["quad"]]
            assert len(road) == 4
            for v, (lon, lat, h) in zip(road, want, strict=True):
                assert abs(v["lng"] - lon) < 2e-8 and abs(v["lat"] - lat) < 2e-8 and abs(v["h"] - h) < 1e-4, (v, lon, lat, h)
        finally:
            browser.close()
    assert errors == []


def test_a_part_switch_hides_its_part_and_a_click_gives_the_extras(tmp_path):
    html, f = _scene(tmp_path)
    code = f["code"]
    road_c, deck_c = _centre(code, f["quads"]["roads"][0]), _centre(code, f["quads"]["structures"][0])
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, html, f["path"])
        try:
            _goto(page, *road_c)
            page.evaluate("window.__sel = []; document.addEventListener('rs:scene3dselect', e => window.__sel.push(e.detail))")
            (x, y), on = _pixel(page, *road_c)
            assert on[0] > 100 and on[0] > on[2] + 40, on                                     # the red road quad, lit
            page.mouse.click(x, y)
            page.wait_for_timeout(500)
            sel = page.evaluate("window.__sel")
            assert len(sel) == 1 and sel[0]["kind"] == "roads" and sel[0]["extras"]["lane_id"] == "4064037692617345284" and sel[0]["tile"][0] == 16, sel
            assert "4064037692617345284" in page.locator(".maplibregl-popup").inner_text()
            assert page.evaluate("rsScene3dPick({x: %s, y: %s})" % (x + 300, y + 200)) is None          # beside the quad: nothing
            # the switch of the part: the road is not drawn, not picked
            page.evaluate("rsScene3dKind('roads', false)")
            page.wait_for_timeout(500)
            _, off = _pixel(page, *road_c)
            assert not (off[0] > off[2] + 40), off
            assert page.evaluate("rsScene3dPick({x: %s, y: %s})" % (x, y)) is None
            # the deck, in the other tile: its part is still on
            _goto(page, *deck_c)
            (dx, dy), pd = _pixel(page, *deck_c)
            assert pd[2] > pd[0] + 40, pd                                                      # the blue deck quad
            assert page.evaluate("rsScene3dPick({x: %s, y: %s})" % (dx, dy))["extras"]["structure_id"] == "S9"
            page.evaluate("rsScene3dKind('structures', false)")
            assert page.evaluate("rsScene3dPick({x: %s, y: %s})" % (dx, dy)) is None
            # the whole scene: off and on
            page.evaluate("rsScene3dKind('structures', true); rsScene3d(false)")
            page.wait_for_timeout(500)
            assert page.evaluate("rsScene3dPick({x: %s, y: %s})" % (dx, dy)) is None
            with pytest.raises(Exception, match="no part"):
                page.evaluate("rsScene3dKind('bridges', false)")
        finally:
            browser.close()
    assert errors == []


def test_the_rows_are_in_the_base_map_box_and_the_scene_needs_the_terrain(tmp_path):
    html, f = _scene(tmp_path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, html, f["path"], terrain=False)
        try:
            rows = page.evaluate("[...document.querySelectorAll('.rs-bm-box label.rs-bm-row')].map(l => [l.textContent.trim(), l.querySelector('input').disabled]).filter(r => /^3D (scene|roads|kerbs|markings|structures)$/.test(r[0]))")
            names = [r[0] for r in rows]
            assert names == ["3D scene", "3D roads", "3D kerbs", "3D markings", "3D structures"], rows
            assert all(r[1] for r in rows if r[0] in ("3D kerbs", "3D markings"))             # no terrain: greyed
            assert page.evaluate("rsScene3dStatus().drawn") is False
            page.evaluate("rsTerrain(true)")
            page.wait_for_function("!!map.getTerrain()", timeout=60_000)
            page.wait_for_timeout(500)
            assert not any(page.evaluate("[...document.querySelectorAll('.rs-bm-box label.rs-bm-row input')].filter(i => i.parentElement.textContent.includes('3D k')).map(i => i.disabled)"))
        finally:
            browser.close()
    assert errors == []


def test_the_toolbar_button_switches_the_scenes_buildings_and_no_row_repeats_it(tmp_path):
    """One button for the 3D buildings of every source: the part `buildings` of the scene has no row in the base-map box, and the toolbar's button
    (the same one that works for OpenFreeMap's buildings and the area's own) is on while they show and switches them."""
    html, f = _scene(tmp_path, buildings=True)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, html, f["path"])
        try:
            page.wait_for_function("rsScene3dStatus().drawn", timeout=60_000)
            names = page.evaluate("[...document.querySelectorAll('.rs-bm-box label.rs-bm-row')].map(l => l.textContent.trim()).filter(t => t.startsWith('3D '))")
            assert "3D buildings" not in names and "3D roads" in names, names
            btn = "document.getElementById('rs-b3d-btn')"
            page.wait_for_function(f"!{btn}.disabled", timeout=10_000)
            assert page.evaluate(f"{btn}.classList.contains('rs-on')") is True
            page.evaluate(f"{btn}.click()")
            page.wait_for_function(f"!{btn}.classList.contains('rs-on')", timeout=10_000)
            assert page.evaluate("[rsScene3dKind('buildings'), rsScene3dKind('roads')]") == [False, True]
            page.evaluate(f"{btn}.click()")
            page.wait_for_function(f"{btn}.classList.contains('rs-on')", timeout=10_000)
            assert page.evaluate("rsScene3dKind('buildings')") is True
        finally:
            browser.close()
    assert errors == []


def test_the_toolbar_button_is_grey_when_the_page_has_no_buildings_at_all(tmp_path):
    html, f = _scene(tmp_path)                       # a scene with no part `buildings`, a blank base map
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, html, f["path"])
        try:
            assert page.evaluate("document.getElementById('rs-b3d-btn').disabled") is True
            assert "3D scene with buildings" in page.evaluate("document.getElementById('rs-b3d-btn').title")
        finally:
            browser.close()
    assert errors == []


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_scene_shows_against_the_map_in_both_themes(tmp_path, theme):
    html, f = _scene(tmp_path)
    c = _centre(f["code"], f["quads"]["roads"][0])
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, html, f["path"])
        try:
            page.evaluate("t => rsSetTheme(t)", theme)
            _goto(page, *c)
            (x, y), px = _pixel(page, *c)
            _, bg = _pixel(page, c[0] + 3e-4, c[1] + 3e-4)
            assert max(abs(a - b) for a, b in zip(px, bg, strict=True)) > 40, (theme, px, bg)
        finally:
            browser.close()
    assert errors == []


def test_a_flat_road_is_one_colour_all_over(tmp_path):
    """Every normal of the quad points up, so the light is the same on all of it. A wrong stride of the normal buffer gave stripes and fans."""
    html, f = _scene(tmp_path)
    c = _centre(f["code"], f["quads"]["roads"][0])
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, html, f["path"])
        try:
            _goto(page, *c)
            from PIL import Image
            x, y = page.evaluate("c => { const p = map.project(c); return [p.x, p.y]; }", c)
            im = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
            px = [im.getpixel((int(x) + dx, int(y) + dy)) for dx in (-14, -7, 0, 7, 14) for dy in (-14, -7, 0, 7, 14)]
            spread = max(max(q[i] for q in px) - min(q[i] for q in px) for i in range(3))
            assert spread <= 2, (spread, px)
        finally:
            browser.close()
    assert errors == []


def test_a_ground_that_is_not_the_archives_is_an_error_in_the_page_too(tmp_path):
    """A host that gives another ground later (rsGround) gets the error in the page, and no triangle is drawn."""
    html, f = _scene(tmp_path)
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, html, f["path"])
        try:
            _goto(page, f["lon"], f["lat"])
            page.evaluate("g => rsGround(g)", {"id": "e" * 64, "source": "other", "product": "DTM", "vertical_datum": "EGM2008", "terrain": None})
            page.wait_for_function("rsScene3dStatus().problems.length > 0", timeout=20_000)
            msg = page.evaluate("rsScene3dProblems()[0].message")
            assert GROUND_ID in msg and "e" * 64 in msg, msg
            assert page.evaluate("rsScene3dStatus().drawn") is False
        finally:
            browser.close()
    assert not any("pageerror" in e for e in errors)


# ---- the real file of SimReady's Monaco (skipped where it is not)
MONACO = Path("/home/kaveh/projects/simready/out/monaco-rust/gltf/monaco.page.pmtiles")


@pytest.mark.skipif(not MONACO.exists(), reason="SimReady's Monaco archive is not on this machine")
def test_the_real_monaco_archive_loads_and_its_vertices_are_where_pyproj_says(tmp_path):
    from pmtiles.reader import MmapSource, Reader
    with open(MONACO, "rb") as fh:
        sr = Reader(MmapSource(fh)).metadata()["simready"]
    lon, lat = _to_lonlat(sr["crs"], sr["origin"][0] + 400, sr["origin"][1] + 400)
    html = rs.render_dashboard(_edges(lon, lat), basemap="blank", ground=_ground(lon, lat, sr["ground"]), scene_3d={"tiles": str(MONACO), "url": "http://rs.test/scene.pmtiles"}, minzoom=False).html
    with pw.sync_playwright() as p:
        browser, page, errors = _open(p, html, MONACO)
        try:
            _goto(page, lon, lat, zoom=17)
            st = page.evaluate("rsScene3dStatus()")
            assert st["problems"] == [] and st["drawn"] and st["tiles"]["loaded"] > 0, st
            vs = page.evaluate("rsScene3dVertices(400)")
            assert {v["kind"] for v in vs} >= {"roads"}
            for v in vs[::40]:
                assert -50 < v["h"] < 200
                assert abs(v["lng"] - 7.42) < 0.05 and abs(v["lat"] - 43.74) < 0.05
        finally:
            browser.close()
    assert errors == []
