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
        tx = lambda lon, n=n: int((lon + 180) / 360 * n)                                         # noqa: E731
        ty = lambda lat, n=n: int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)   # noqa: E731
        for x in range(tx(b[0]), tx(b[2]) + 1):
            for y in range(ty(b[3]), ty(b[1]) + 1):
                assert mvt.decode(f.tile(z, x, y)) == mvt.decode(t.tile(z, x, y)), f"{z}/{x}/{y}"


def test_the_road_table_of_rust_is_pythons(part, keywords):
    """The road table of stage 1 (roadstyle::write_road_table) is tiles.sidecar of the roads source, the page's table, byte for byte:
    every field, the middle by length (shapely's interpolate), the box, the heading at the middle and the line of each road."""
    from roadstyle import _engine
    from roadstyle.tiles import sidecar

    kw = dict(keywords)
    kw.setdefault("view_3d", True)
    lk = _engine._look_of(kw)
    s = _engine.rust().make_sources(_engine._geoparquet(part), json.dumps(lk), None, None, "roads")
    roads = rs.export_inline(part, engine="rust", **keywords)["sources"]["roads"]["data"]
    want = json.dumps(sidecar(roads), separators=(",", ":"))
    got = s.road_table()
    assert got == want
    t = json.loads(got)
    assert len(t["props"]) == len(t["lines"]) == len(t["headings"]) == len(part)
    assert all(h is None or 0 <= h < 360 for h in t["headings"])


def test_live_data_reads_the_feature_state_of_the_road(part, keywords):
    """R22: with live_data the road layer reads its colour (rs_c) and its width factor (rs_w) from the feature state of the road's row,
    over the baked values (the pieces have the row as their id, promoteId, in every style), and roadstyle:live names the states. Off, the
    style is as before."""
    off = rs.export_inline(part, engine="rust", **keywords)
    on = rs.export_inline(part, engine="rust", live_data=True, **keywords)
    road = lambda st: next(l for l in st["layers"] if l["id"] == "roads-simple")["paint"]      # noqa: E731
    assert "roadstyle:live" not in off["metadata"]
    assert on["sources"]["simple"]["promoteId"] == off["sources"]["simple"]["promoteId"] == "__rs_edge"
    live = on["metadata"]["roadstyle:live"]
    assert (live["color"], live["width"], live["types"]) == ("rs_c", "rs_w", {"rs_c": "color", "rs_w": "factor"})
    assert len(live["ramp"]) == 9 and live["nodata"].startswith("#")
    text = json.dumps(road(on))
    assert '["feature-state", "rs_c"]' in text and '["coalesce", ["feature-state", "rs_w"], 1]' in text
    # the width is still a zoom curve at the top (MapLibre), the factor in each stop
    assert road(on)["line-width"][:3] == road(off)["line-width"][:3]
    off.pop("metadata"), on.pop("metadata")
    for st in (off, on):
        for l in st["layers"]:
            if l["id"] == "roads-simple":
                l.pop("paint")
    assert on == off


def test_live_data_needs_the_rust_page(part):
    with pytest.raises(ValueError, match="live_data"):
        rs.render_edges(part, engine="python", live_data=True)


def test_a_live_page_gives_the_dashboard_the_states(part):
    """The page has no style metadata: it gives roadstyle:live to rsDashboard as the option `live` (null without live_data)."""
    from test_render_web import _opt, _style
    on = rs.render_edges(part, engine="rust", live_data=True, basemap="osm").html
    off = rs.render_edges(part, engine="rust", basemap="osm").html
    assert _opt(on, "live")["color"] == "rs_c" and _opt(off, "live") is None
    road = next(l for l in _style(on)["layers"] if l["id"] == "roads-simple")
    assert '["feature-state", "rs_c"]' in json.dumps(road["paint"]["line-color"])
