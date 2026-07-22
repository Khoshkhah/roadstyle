"""tiles=True — PMTiles archive building and the embedded-tiles web output."""
import gzip
import json

import geopandas as gpd
import pytest
from shapely.geometry import LineString

pytest.importorskip("mapbox_vector_tile")
pytest.importorskip("pmtiles")


def _edges(n=60):
    return gpd.GeoDataFrame(
        {"highway": (["primary"] * (n // 2)) + (["service"] * (n - n // 2)),
         "name": [f"Street {i}" for i in range(n)],
         "aadt": list(range(n))},
        geometry=[LineString([(18.0 + i * 1e-3, 59.3), (18.0 + i * 1e-3, 59.302)])
                  for i in range(n)],
        crs=4326)


def _fc(g):
    fc = json.loads(g.to_json())
    for ft in fc["features"]:
        ft["properties"]["__rs_fill"] = "#abcdef"
    return fc


def test_build_pmtiles_round_trip():
    import mapbox_vector_tile
    from pmtiles.reader import MemorySource, Reader

    from roadstyle.tiles import build_pmtiles
    fc = _fc(_edges())
    data = build_pmtiles(fc, class_col="highway", keep={"highway", "twoway", "lvl"},
                         minzoom_table={"service": 13}, minzoom=8, maxzoom=14)
    r = Reader(MemorySource(data))
    h = r.header()
    assert (h["min_zoom"], h["max_zoom"]) == (8, 14)

    def layers_at(z):
        import math
        n = 1 << z
        x = int((18.03 + 180) / 360 * n)
        y = int((1 - math.asinh(math.tan(math.radians(59.301))) / math.pi) / 2 * n)
        raw = r.get(z, x, y)
        return mapbox_vector_tile.decode(gzip.decompress(raw)) if raw else {}

    top = layers_at(14)["roads"]["features"]
    assert {f["properties"]["highway"] for f in top} == {"primary", "service"}
    assert all(isinstance(f["id"], int) for f in top)          # id = feature index
    assert all(set(f["properties"]) <= {"highway", "twoway", "lvl", "__rs_fill"} for f in top)
    low = layers_at(10)["roads"]["features"]
    assert {f["properties"]["highway"] for f in low} == {"primary"}   # service below its minzoom


def test_extra_layers_ride_along_from_their_minzoom():
    import mapbox_vector_tile
    from pmtiles.reader import MemorySource, Reader

    from roadstyle.tiles import build_pmtiles
    fc = _fc(_edges(10))
    slots = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": 0, "properties": {"slot": 0, "name": "A", "oneway": 1},
         "geometry": {"type": "LineString", "coordinates": [[18.0, 59.3], [18.001, 59.301]]}}]}
    data = build_pmtiles(fc, class_col="highway", keep={"highway"}, minzoom=8, maxzoom=15,
                         extra_layers=[{"name": "slots", "fc": slots, "minzoom": 14}])
    r = Reader(MemorySource(data))

    def tile(z):
        import math
        n = 1 << z
        x = int((18.0005 + 180) / 360 * n)
        y = int((1 - math.asinh(math.tan(math.radians(59.3005))) / math.pi) / 2 * n)
        raw = r.get(z, x, y)
        return mapbox_vector_tile.decode(gzip.decompress(raw)) if raw else {}

    assert "slots" not in tile(12)          # below the extra layer's minzoom
    t15 = tile(15)
    assert t15["slots"]["features"][0]["properties"]["name"] == "A"


def test_sidecar_shape():
    from roadstyle.tiles import sidecar
    fc = _fc(_edges(5))
    sc = sidecar(fc)
    assert len(sc["props"]) == len(sc["mids"]) == len(sc["bboxes"]) == 5
    assert sc["props"][0]["name"] == "Street 0"
    assert len(sc["mids"][0]) == 2 and len(sc["bboxes"][0]) == 4


def test_render_tiles_swaps_source_and_embeds_archive():
    from roadstyle.render_web import render
    html = render(_edges(), basemap="blank", tiles=True).html
    i = html.index("const style = ") + len("const style = ")
    style = json.JSONDecoder().raw_decode(html, i)[0]
    assert style["sources"]["roads"]["type"] == "vector"
    assert style["sources"]["roads"]["url"] == "pmtiles://roads"
    assert "slots" not in style["sources"]              # slots ride in the archive
    for lyr in style["layers"]:
        if lyr.get("source") == "roads":
            assert lyr["source-layer"] in ("roads", "slots")
    assert "const RS_TILED = true" in html
    assert 'id="rs-side"' in html                       # the sidecar blob
    assert "pmtiles.Protocol" in html                   # vendored pmtiles.js + setup


def test_render_without_tiles_is_unchanged():
    from roadstyle.render_web import render
    html = render(_edges(), basemap="blank").html
    assert "const RS_TILED = false" in html
    assert "pmtiles.Protocol" not in html
    i = html.index("const style = ") + len("const style = ")
    style = json.JSONDecoder().raw_decode(html, i)[0]
    assert style["sources"]["roads"]["type"] == "geojson"
