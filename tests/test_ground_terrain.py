"""The map terrain from the area's own ground (docs/design/ground_terrain.md): the terrain file that the engine makes from a ground grid,
its check against the grid (decoded here by the pmtiles package and PIL, not by the engine), roadstyle.duckosm.ground, and a page with
the option `ground` that draws its hillshade and 3D terrain with no request to the AWS Terrain Tiles. The browser part is skipped without
playwright."""
import base64
import io
import json

import numpy as np
import pytest

import roadstyle as rs
from roadstyle import duckosm
from roadstyle._engine import rust

D, WEST, NORTH, COLS, ROWS = 1 / 3600, 7.405, 43.752, 50, 40       # a 1 arc-second grid at Monaco
FACTS = {"id": "0123456789abcdef", "source": "test DTM", "product": "DTM", "vertical_datum": "EGM2008", "resolution_m": 30, "license": "CC0"}


def _grid(height):
    r, c = np.mgrid[0:ROWS, 0:COLS]
    return c.ravel(), r.ravel(), WEST + (c.ravel() + 0.5) * D, NORTH - (r.ravel() + 0.5) * D, height(c, r).astype(float).ravel()


def _steep(c, r):
    """A slope, a hill and a 60 m cliff: steep as Monaco."""
    return 3.0 * c + 150.0 * np.sin(r / 7.0) + np.where(c > 30, 60.0, 0.0) - 20.0


def _archive(cells, facts=FACTS):
    return rust().terrain_pmtiles(*(a.tolist() for a in cells), json.dumps(facts))


def _tiles(archive):
    """Each tile of the archive: (z, x, y, heights[256, 256]), the PNG decoded by PIL."""
    from PIL import Image
    from pmtiles.reader import MemorySource, Reader, all_tiles
    for (z, x, y), png in all_tiles(MemorySource(archive)):
        px = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(float)
        yield z, x, y, px[..., 0] * 256 + px[..., 1] + px[..., 2] / 256 - 32768
    assert Reader(MemorySource(archive)).header()["tile_type"].value == 2          # PNG


def test_every_tile_pixel_equals_the_grid():
    """Check 1 of the design: each tile pixel minus the grid's bilinear value at the pixel's point (its north-west corner), at most 0.10 m (expected: the
    Terrarium step, 1/512 m)."""
    pytest.importorskip("PIL")
    pytest.importorskip("pmtiles")
    cells = _grid(_steep)
    z_grid = cells[4].reshape(ROWS, COLS)
    worst, n, zooms = 0.0, 0, set()
    for z, x, y, h in _tiles(_archive(cells)):
        zooms.add(z)
        u, v = np.meshgrid(np.arange(256.0), np.arange(256.0))       # MapLibre's point of a DEM pixel: its north-west corner
        gx, gy = (x * 256 + u) / (256 * 2**z), (y * 256 + v) / (256 * 2**z)
        lon, lat = gx * 360 - 180, np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * gy))))
        fc, fr = (lon - WEST) / D - 0.5, (NORTH - lat) / D - 0.5
        c, r = np.floor(fc).astype(int), np.floor(fr).astype(int)
        ok = (c >= 0) & (r >= 0) & (c < COLS - 1) & (r < ROWS - 1)
        c, r, a, b = c[ok], r[ok], (fc - np.floor(fc))[ok], (fr - np.floor(fr))[ok]
        want = (z_grid[r, c] * (1 - a) + z_grid[r, c + 1] * a) * (1 - b) + (z_grid[r + 1, c] * (1 - a) + z_grid[r + 1, c + 1] * a) * b
        if want.size:
            worst, n = max(worst, float(np.abs(h[ok] - want).max())), n + want.size
    assert zooms == set(range(8, 14))                 # 1 arc-second: the last zoom 13, and the 5 zooms below it
    assert n > 1000 and worst <= 1 / 512 + 1e-9, (n, worst)


def test_a_grid_that_is_not_a_rectangle_is_an_error():
    c, r, lon, lat, z = _grid(_steep)
    with pytest.raises(ValueError, match="full rectangle"):
        rust().terrain_pmtiles(c[1:].tolist(), r[1:].tolist(), lon[1:].tolist(), lat[1:].tolist(), z[1:].tolist(), "{}")


def test_duckosm_ground_reads_the_grid_and_the_facts(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    c, r, lon, lat, z = _grid(_steep)
    db = tmp_path / "area.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE main.elevation_grid (col INTEGER, row INTEGER, lon DOUBLE, lat DOUBLE, z DOUBLE)")
    con.executemany("INSERT INTO main.elevation_grid VALUES (?, ?, ?, ?, ?)",
                    [(int(a), int(b), float(x), float(y), None if (a, b) == (3, 3) else float(h)) for a, b, x, y, h in zip(c, r, lon, lat, z, strict=True)])
    con.execute("CREATE TABLE main.elevation_metadata (ele_column VARCHAR, source VARCHAR, product VARCHAR, vertical_datum VARCHAR, "
                "resolution_m DOUBLE, license VARCHAR)")
    con.execute("INSERT INTO main.elevation_metadata VALUES ('ele', 'FABDEM V1-2', 'DTM', 'EGM2008', 30, 'CC BY-NC-SA 4.0')")
    con.close()
    g = duckosm.ground(db)
    assert {k: g[k] for k in ("source", "product", "vertical_datum")} == {"source": "FABDEM V1-2", "product": "DTM", "vertical_datum": "EGM2008"}
    assert base64.b64decode(g["terrain"].split(",", 1)[1])[:7] == b"PMTiles"


def test_duckosm_ground_is_none_without_a_grid(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    db = tmp_path / "area.duckdb"
    duckdb.connect(str(db)).close()
    assert duckosm.ground(db) is None


# ---- the page --------------------------------------------------------------------------------------------------------------------------

def _plane(c, r):
    """A plane: MapLibre's interpolation of it is the plane again, so the terrain's height must equal the grid."""
    return 100.0 + 2.0 * c + 1.0 * r


def _page_html(ground):
    import geopandas as gpd
    from shapely.geometry import LineString
    roads = gpd.GeoDataFrame({"highway": ["primary"], "edge_id": [1]}, crs=4326,
                             geometry=[LineString([(WEST + 10 * D, NORTH - 10 * D), (WEST + 30 * D, NORTH - 25 * D)])])
    return rs.render_dashboard(roads, basemap="blank", ground=ground).html


def test_the_page_draws_the_ground_with_no_request_to_aws():
    pw = pytest.importorskip("playwright.sync_api")
    archive = _archive(_grid(_plane))
    ground = {**FACTS, "terrain": "data:application/vnd.pmtiles;base64," + base64.b64encode(archive).decode()}
    html, aws, errors = _page_html(ground), [], []
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_context(viewport={"width": 1000, "height": 700}).new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/elevation-tiles-prod/**", lambda r: (aws.append(r.request.url), r.abort()))
        page.route("http://rs.test/p.html", lambda r: r.fulfill(content_type="text/html", body=html))
        page.goto("http://rs.test/p.html")
        page.wait_for_function("window.map && window.map.loaded && window.map.loaded() && !!window.rsTerrain", timeout=60_000)
        page.evaluate("""c => new Promise(ok => { document.addEventListener('rs:terrainchange', ok, {once: true});
                                                 map.jumpTo({center: c, zoom: 15, pitch: 55}); rsTerrain(true); })""", [WEST + 20 * D, NORTH - 20 * D])
        page.wait_for_function("map.getTerrain() && map.areTilesLoaded()", timeout=30_000)
        page.wait_for_timeout(500)
        src = page.evaluate("(() => { const s = map.getSource('rs-dem'); return {tiles: s.tiles, maxzoom: s.maxzoom, attr: s.attribution}; })()")
        # the terrain's height at cell centres: the plane, to 0.10 m (the standard's limit)
        pts = [(cc, rr) for cc in (12, 20, 28) for rr in (12, 20, 26)]
        got = page.evaluate("pts => pts.map(p => map.queryTerrainElevation(p))", [[WEST + (cc + 0.5) * D, NORTH - (rr + 0.5) * D] for cc, rr in pts])
        assert all(g is not None and abs(g - _plane(cc, rr)) <= 0.10 for g, (cc, rr) in zip(got, pts, strict=True)), list(zip(got, pts, strict=True))
        # without the ground, the page goes back to the AWS tiles and says so
        aws_before = len(aws)
        page.evaluate("rsGround(null)")
        page.wait_for_timeout(1500)
        aws_attr = page.evaluate("map.getSource('rs-dem').attribution")
        browser.close()
    assert src["tiles"][0].startswith("rsground://") and src["maxzoom"] == 13, src
    assert "Ground: test DTM (DTM, EGM2008), id 01234567" in src["attr"], src
    assert aws_before == 0 and aws and "Ground: AWS Terrain Tiles" in aws_attr, (aws_before, len(aws), aws_attr)
    assert not errors, errors


def test_the_page_without_ground_names_the_aws_tiles():
    html = _page_html(None)
    assert "Ground: AWS Terrain Tiles" in html
