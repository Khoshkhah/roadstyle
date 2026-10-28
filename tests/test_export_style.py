"""export_style: the roads as style.json + vector tiles + a sprite, for other apps (docs/design/style_export.md)."""
import functools
import http.server
import json
import re
import threading

import geopandas as gpd
import pytest
from shapely.geometry import LineString, box

pytest.importorskip("mapbox_vector_tile")
pytest.importorskip("pmtiles")

BASE = "https://example.org/rs"


def _edges():
    """A one-way grid with a tunnel and a bridge: arrows, the tunnel look and a bridge position."""
    n = 12
    return gpd.GeoDataFrame(
        {"highway": ["primary"] * n, "name": [f"Street {i}" for i in range(n)], "oneway": ["yes"] * n,
         "tunnel": ["yes"] + [None] * (n - 1), "bridge": [None, "yes"] + [None] * (n - 2),
         "layer": [-1, 1] + [0] * (n - 2)},
        geometry=[LineString([(18.0 + i * 1e-3, 59.3), (18.0 + i * 1e-3, 59.302)]) for i in range(n)],
        crs=4326)


def _export(tmp_path, **kw):
    import roadstyle as rs
    p = rs.export_style(_edges(), tmp_path, base_url=BASE + "/", boundary=box(17.999, 59.299, 18.012, 59.303), **kw)
    return p, json.loads(p.read_text())


def test_style_points_at_its_own_files(tmp_path):
    from pmtiles.reader import MmapSource, Reader

    p, s = _export(tmp_path, format="pmtiles")
    assert not re.search(r"__[A-Z][A-Z_]+__", p.read_text())          # no page placeholder left
    assert [k for k, v in s["sources"].items() if v["type"] == "geojson"] == []      # RustGIS draws no GeoJSON source
    assert s["sources"]["roads"]["url"] == f"pmtiles://{BASE}/roads.pmtiles" and s["sprite"] == f"{BASE}/sprite"
    with open(tmp_path / "roads.pmtiles", "rb") as f:
        names = {v["id"] for v in Reader(MmapSource(f)).metadata()["vector_layers"]}
    for lyr in s["layers"]:
        assert lyr.get("source") in (None, *s["sources"])
        if lyr.get("source") == "roads":
            assert lyr["source-layer"] in names, lyr["id"]
    assert "boundary" in names                                             # a GeoJSON source went into the archive
    assert "decks" in names and any(lyr["type"] == "fill-extrusion" for lyr in s["layers"])   # view_3d by default: the bridge decks
    assert "roads" not in names and not {"roads-fill", "roads-highlight"} & {lyr["id"] for lyr in s["layers"]}      # D5: the pieces pick and glow
    assert s["metadata"]["roadstyle:contract"] == 2 and s["metadata"]["roadstyle:interaction"]["props"] == f"{BASE}/props.json"
    sprite = json.loads((tmp_path / "sprite.json").read_text())
    assert sprite["oneway"]["sdf"] is True
    arrows = [lyr for lyr in s["layers"] if lyr["id"].startswith("roads-arrows")]
    assert arrows and all("icon-color" in lyr["paint"] for lyr in arrows)
    assert all(lyr["layout"]["symbol-placement"] == "line-center" and "__rs_arw" in json.dumps(lyr["filter"]) for lyr in arrows)   # fewer arrows


def test_tile_folder_is_plain_mvt(tmp_path):
    _, s = _export(tmp_path)
    assert s["sources"]["roads"]["tiles"] == [f"{BASE}/tiles/{{z}}/{{x}}/{{y}}.pbf"] and "url" not in s["sources"]["roads"]
    tiles = list((tmp_path / "tiles").rglob("*.pbf"))
    assert tiles and all(t.read_bytes()[:2] != b"\x1f\x8b" for t in tiles)   # a static server sends no Content-Encoding


def test_the_style_holds_the_roads_only(tmp_path):
    import roadstyle as rs
    s = json.loads(rs.export_style(_edges(), tmp_path, base_url=BASE).read_text())
    assert "bm" not in s["sources"] and not [lyr for lyr in s["layers"] if lyr["type"] in ("background", "raster")]
    assert "state" not in s and "global-state" not in json.dumps(s) and '"let"' not in json.dumps(s)    # the page state baked
    with pytest.raises(ValueError, match="base map"):
        rs.export_style(_edges(), tmp_path, base_url=BASE, basemap="osm")


def test_from_a_duckosm_geoparquet_file(tmp_path):
    """Version 2: the edges and their drawing positions from one GeoParquet file; every column in the road tiles, an id past 2**53 as text;
    a file without the positions is an error that says how to save them."""
    import mapbox_vector_tile

    import roadstyle as rs
    g = _edges().assign(edge_id=[2 ** 60 + i for i in range(12)], lanes=2)
    lv = rs.compute_levels(g)
    with_levels, without = tmp_path / "e.parquet", tmp_path / "n.parquet"
    lv.to_parquet(with_levels)
    g.to_parquet(without)
    rs.export_style(str(with_levels), tmp_path / "out", base_url=BASE)
    props = json.loads((tmp_path / "out" / "props.json").read_text())             # the fields of each road, by its row (the pieces' id)
    assert len(props) == 12 and all("lanes" in p and "name" in p for p in props)
    assert [p["edge_id"] for p in props] == [str(2 ** 60 + i) for i in range(12)]
    ids = {f["id"] for t in (tmp_path / "out" / "tiles").rglob("15/*/*.pbf") for f in mapbox_vector_tile.decode(t.read_bytes()).get("simple", {}).get("features", [])}
    assert ids and ids <= set(range(12))
    with pytest.raises(ValueError, match="save_levels"):
        rs.export_style(str(without), tmp_path / "out2", base_url=BASE)

def test_page_only_keywords_refused(tmp_path):
    import roadstyle as rs
    with pytest.raises(ValueError, match="views"):
        rs.export_style(_edges(), tmp_path, base_url=BASE, views=[{"name": "a"}])
    with pytest.raises(ValueError, match="format"):
        rs.export_style(_edges(), tmp_path, base_url=BASE, format="mbtiles")


def test_plain_maplibre_page_draws_the_export(tmp_path):
    """A MapLibre page with no roadstyle code opens style.json from a server and draws the roads."""
    pw = pytest.importorskip("playwright.sync_api")
    import roadstyle as rs
    from roadstyle import _assets
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    rs.export_style(_edges(), tmp_path, base_url=base, labels=False)     # no glyphs: no network
    js = _assets.text("vendor/maplibre-gl.js")
    (tmp_path / "index.html").write_text(
        f'<div id="m" style="width:800px;height:600px"></div><script>{js}</script><script>window.errs=[];'
        f'window.map=new maplibregl.Map({{container:"m",style:"{base}/style.json"}});'
        'map.on("error",e=>errs.push(String(e.error&&e.error.message)));</script>')
    errors = []
    try:
        with pw.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base + "/index.html")
            page.wait_for_function("window.map && map.loaded() && map.areTilesLoaded()", timeout=30_000)
            n = page.evaluate("map.querySourceFeatures('roads',{sourceLayer:'simple'}).length")
            errors += page.evaluate("errs")
            browser.close()
    finally:
        srv.shutdown()
    assert errors == []
    assert n > 0


def test_look_for_a_data_layer(tmp_path):
    """export_look: one casing and one fill layer per drawing position, no source, the class colours by highway, tunnels faded."""
    import roadstyle as rs

    g = _edges().assign(casing_level=[-1, 1] + [0] * 10, fill_level=[-1, 1] + [0] * 10)
    look = rs.export_look(tmp_path / "look.json", edges=g)
    assert json.loads((tmp_path / "look.json").read_text()) == look
    assert [l["id"] for l in look["layers"]] == ["casing--1", "fill--1", "casing-0", "fill-0", "casing-1", "fill-1"]
    assert all("source" not in l and l["metadata"]["roadstyle:position"] in (-1, 0, 1) for l in look["layers"])
    assert {"highway", "oneway", "tunnel", "bridge", "casing_level", "fill_level"} <= set(look["columns"])
    fill = look["layers"][1]["paint"]["line-color"]
    assert fill[0] == "case" and fill[2] != fill[3]                   # a tunnel has its own (faded) colours
    primary = fill[3][fill[3].index("primary") + 1]
    t = rs._settings.theme()
    assert primary == t["palettes"][t["active"]["palette"]]["primary"]["fill"]
    assert [l["id"] for l in rs.export_look(positions=[2])["layers"]] == ["casing-2", "fill-2"]
    assert look["boundary"]["layers"][0]["paint"]["line-color"] == t["boundary"]["color"]
    assert look["hover"]["id"] == "edge_id" and look["hover"]["layers"][0]["paint"]["line-color"] == t["selection"]["hover"]
    assert look["popup"]["title"] == "name" and "edge_id" in look["popup"]["columns"]


def test_both_engines_give_an_app_the_road_roles_and_the_pick_layers(tmp_path):
    """export_style's metadata has roadstyle:sources (the road roles) and roadstyle:controls.pick (the layers a road is picked on), from
    the style's final layers, in both engines: an app's dashboard on the exported style finds the roads and picks them (audit 3, N27)."""
    from pathlib import Path

    import pyarrow.parquet as pq
    import shapely

    import roadstyle as rs
    df = pq.read_table(Path(__file__).parents[1] / "rust/roadstyle-rs/tests/data/monaco_part/roads.parquet").to_pandas(integer_object_nulls=True)
    part = gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")
    meta = {e: json.loads(rs.export_style(part, tmp_path / e, base_url=BASE, engine=e).read_text())["metadata"] for e in ("python", "rust")}
    for e, m in meta.items():
        assert set(m["roadstyle:sources"]) >= {"simple", "slots"}, e
        assert "roads-simple" in m["roadstyle:controls"]["pick"] or "roads-fill" in m["roadstyle:controls"]["pick"], e
    assert meta["rust"]["roadstyle:sources"] == meta["python"]["roadstyle:sources"]
    assert meta["rust"]["roadstyle:controls"] == meta["python"]["roadstyle:controls"]
