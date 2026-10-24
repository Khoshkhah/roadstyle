"""The two stages of the Rust engine as their own calls (docs/rust/architecture.md, "The three stages and the one call"):
export_geojson writes stage 1's files, tile_geojson makes stage 2's tiles from them, and the tiles are the tiles of the one call
(the Tiler of render(tiles=True) and export_style). rust/roadstyle-rs/tests/stages.rs compares them decoded on Monaco and Tartu."""
import json
from pathlib import Path

import pytest

import roadstyle as rs

DATA = Path(__file__).resolve().parents[1] / "rust" / "roadstyle-rs" / "tests" / "data"
pytestmark = pytest.mark.skipif(not __import__("roadstyle._engine", fromlist=["available"]).available(), reason="no roadstyle._rust")


@pytest.fixture(scope="module")
def part():
    import geopandas as gpd
    import pyarrow.parquet as pq
    import shapely

    df = pq.read_table(DATA / "monaco_part" / "roads.parquet").to_pandas(integer_object_nulls=True)
    return gpd.GeoDataFrame(df.drop(columns="geometry"), geometry=shapely.from_wkb(df["geometry"]), crs="EPSG:4326")


@pytest.fixture(scope="module")
def keywords():
    look = json.loads((DATA / "look.json").read_text())
    return {"palette": look["palette"], "settings": look["settings"], **look["args"], "arrows": True, "labels": True}


@pytest.mark.parametrize("fmt", ["geojson", "geoparquet"])
def test_tiles_from_the_files_are_the_tiles_of_the_one_call(part, keywords, tmp_path, fmt):
    from roadstyle import _engine

    ext = "geojson" if fmt == "geojson" else "parquet"
    files = rs.export_geojson(part, tmp_path / fmt, format=fmt, **keywords)
    assert {"style.json", f"roads.{ext}", f"simple.{ext}", "road_table.parquet"} <= set(files)
    style = json.loads((tmp_path / fmt / "style.json").read_text())
    assert style["sources"]["simple"]["data"] == f"simple.{ext}"
    out = rs.tile_geojson(tmp_path / fmt, tmp_path / f"{fmt}.pmtiles")
    # the one call: the same look, the tiles of the Tiler (render(tiles=True), export_style)
    kw = dict(keywords)
    kw.setdefault("view_3d", True)          # as export_geojson
    lk = _engine._look_of(kw)
    t = _engine.rust().Tiler(_engine._geoparquet(part), json.dumps(lk), None, "roads", "", [])
    one = t.archive(list(t.bounds()), t.layers())
    if fmt == "geojson":
        assert out.read_bytes() == one          # the same text: the same bytes
        return
    # GeoParquet: the same features, decoded (the keys of a tile can be in another order)
    mvt = pytest.importorskip("mapbox_vector_tile")
    import math

    f = _engine.rust().tile_files(str(tmp_path / fmt), [], "")
    assert (f.zooms(), f.layers(), f.bounds()) == (t.zooms(), t.layers(), t.bounds())
    b = t.bounds()
    for z in range(t.zooms()[0], t.zooms()[1] + 1):
        n = 2 ** z
        tx = lambda lon: int((lon + 180) / 360 * n)                                         # noqa: E731
        ty = lambda lat: int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)   # noqa: E731
        for x in range(tx(b[0]), tx(b[2]) + 1):
            for y in range(ty(b[3]), ty(b[1]) + 1):
                assert mvt.decode(f.tile(z, x, y)) == mvt.decode(t.tile(z, x, y)), f"{z}/{x}/{y}"
