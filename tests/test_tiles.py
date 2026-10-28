"""tiles=True — PMTiles archive building and the embedded-tiles web output."""
import gzip
import json
import math

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
    # the style's rule (zoom_rules): the one layer on the roads hides service below zoom 13
    layers = [{"id": "r", "source": "roads", "filter": ["all", [">=", ["zoom"], ["match", ["get", "highway"], "service", 13, 0]]]}]
    data = build_pmtiles(fc, keep={"highway", "__rs_twoway", "lvl"}, layers=layers, minzoom=8, maxzoom=14)
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
    assert all(set(f["properties"]) <= {"highway", "__rs_twoway", "lvl", "__rs_fill"} for f in top)
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
    data = build_pmtiles(fc, keep={"highway"}, minzoom=8, maxzoom=15,
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
    html = render(_edges(), basemap="blank", tiles=True, simple=False).html
    i = html.index("const style = ") + len("const style = ")
    style = json.JSONDecoder().raw_decode(html, i)[0]
    assert style["sources"]["roads"]["type"] == "vector"
    assert style["sources"]["roads"]["url"] == "pmtiles://roads"
    assert "slots" not in style["sources"] and "casings" not in style["sources"] and "ends" not in style["sources"]   # they ride in the archive
    for lyr in style["layers"]:
        if lyr.get("source") == "roads":
            assert lyr["source-layer"] in ("roads", "slots", "casings", "ends")
    assert '"tiles": true, "simple"' in html
    assert 'id="rs-side"' in html                       # the sidecar blob
    assert "pmtiles.Protocol" in html                   # vendored pmtiles.js + setup


def _archive_of(html):
    import base64
    return base64.b64decode(html.split('atob("')[1].split('")')[0])


def _tile_classes(data, z, layer="roads", lon=18.03, lat=59.301):
    import math

    import mapbox_vector_tile
    from pmtiles.reader import MemorySource, Reader
    n = 1 << z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    raw = Reader(MemorySource(data)).get(z, x, y)
    if not raw:
        return set()
    t = mapbox_vector_tile.decode(gzip.decompress(raw))
    return {f["properties"].get("highway", f["properties"].get("__rs_cls")) for f in t.get(layer, {}).get("features", [])}   # a piece: __rs_cls


def test_tile_class_gating_follows_the_minzoom_parameter():
    """minzoom=False: NO class thinning in the tiles (residential shows at every zoom). The default (since 2026-10-25) is the settings
    table: the pieces' layer hides a class below its first zoom, so the low-zoom tiles leave it out (zoom_rules)."""
    from roadstyle.render_web import render
    g = _edges()
    plain = _archive_of(render(g, basemap="blank", tiles=True, minzoom=False).html)
    assert "service" in _tile_classes(plain, 10, "simple")               # everything, even at z10
    thin = _archive_of(render(g, basemap="blank", tiles=True).html)
    assert "service" not in _tile_classes(thin, 10, "simple")            # service minzoom is 15
    assert "primary" in _tile_classes(thin, 10, "simple")


def test_render_without_tiles_is_unchanged():
    from roadstyle.render_web import render
    html = render(_edges(), basemap="blank").html
    assert '"tiles": false, "simple"' in html
    assert "pmtiles.Protocol" not in html
    i = html.index("const style = ") + len("const style = ")
    style = json.JSONDecoder().raw_decode(html, i)[0]
    assert style["sources"]["simple"]["type"] == "geojson" and "roads" not in style["sources"]     # a page: the pieces; the road table


def test_sidecar_mid_is_half_the_length():
    """rsSelect anchors its popup and Street View spot at `mids`: the middle of the length, not
    the middle vertex (a two-point edge's middle vertex is its END, so stepping forward from it
    along the edge had nowhere to go)."""
    from roadstyle.tiles import sidecar
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": "LineString",
                                                           "coordinates": [[18.0, 59.3], [18.02, 59.3]]}}]}
    assert sidecar(fc)["mids"][0] == pytest.approx([18.01, 59.3])


def test_tiles_carry_the_casing_pieces_and_the_end_caps():
    """Position drawing in tiles (docs/design/levels_split_casing.md, 12.1): the divided casing and the twin end caps are tile layers of the archive."""
    import math

    import mapbox_vector_tile
    from pmtiles.reader import MemorySource, Reader

    from roadstyle import render_edges
    a, b, c = (18.0, 59.3), (18.001, 59.3), (18.002, 59.3)
    g = gpd.GeoDataFrame({"highway": ["primary"] * 4},
                         geometry=[LineString([a, b]), LineString([b, a]), LineString([b, c]), LineString([c, b])], crs=4326)
    html = render_edges(g, backend="web", basemap="blank", tiles=True, simple=False, settings={"config": {"twin_casing": "each"}}).html   # the end caps: today's look
    style = json.JSONDecoder().raw_decode(html, html.index("const style = ") + 14)[0]
    kinds = {l["source-layer"] for l in style["layers"] if l.get("source") == "roads"}
    assert {"roads", "casings", "ends"} <= kinds
    z = 15
    n = 1 << z
    x = int((18.001 + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(59.3))) / math.pi) / 2 * n)
    t = mapbox_vector_tile.decode(gzip.decompress(Reader(MemorySource(_archive_of(html))).get(z, x, y)))
    assert t["casings"]["features"] and t["ends"]["features"]
    assert all("__rs_edge" in f["properties"] for f in t["casings"]["features"])


def test_simple_mode_tiles_carry_the_pieces():
    """simple=True (the default) with tiles=True: the one road layer's pieces are the archive's "simple" layer, with what its expressions read."""
    import math

    import mapbox_vector_tile
    from pmtiles.reader import MemorySource, Reader

    from roadstyle.render_web import render
    a, b, c = (18.0, 59.3), (18.001, 59.3), (18.002, 59.3)
    g = gpd.GeoDataFrame({"highway": ["primary", "primary", "footway"], "bridge": [None, "yes", None]},
                         geometry=[LineString([a, b]), LineString([b, c]), LineString([a, c])], crs=4326)
    html = render(g, basemap="blank", tiles=True).html
    style = json.JSONDecoder().raw_decode(html, html.index("const style = ") + 14)[0]
    assert "simple" not in style["sources"]
    lyr = {l["id"]: l for l in style["layers"]}
    assert (lyr["roads-simple"]["source"], lyr["roads-simple"]["source-layer"]) == ("roads", "simple")
    assert "roads-fill" not in lyr and style["sources"]["roads"]["promoteId"] == {"simple": "__rs_edge"}      # the pieces pick and glow
    z = 15
    n = 1 << z
    x = int((18.001 + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(59.3))) / math.pi) / 2 * n)
    feats = mapbox_vector_tile.decode(gzip.decompress(Reader(MemorySource(_archive_of(html))).get(z, x, y)))["simple"]["features"]
    ps = [f["properties"] for f in feats]
    assert {p["__rs_k"] for p in ps} == {0, 1, 2}                       # casings, fills, the bridge's shadow
    assert all({"__rs_s", "__rs_edge", "__rs_cls", "__rs_ci"} <= p.keys() for p in ps)        # the class as the filter's and as the index (R1, R8)
    assert any(isinstance(p.get("__rs_dash"), str) for p in ps)         # the footway's dash pattern, as text (the dasharray match)
    assert any(p.get("__rs_fill") for p in ps if p["__rs_k"] == 1)


def test_single_line_pair_rides_the_tiles():
    import mapbox_vector_tile
    from pmtiles.reader import MemorySource, Reader
    from test_render_web import _pairs

    from roadstyle.render_web import render
    html = render(_pairs(), basemap="blank", tiles=True).html
    z, n = 15, 1 << 15
    x = int((18.04 + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(59.305))) / math.pi) / 2 * n)
    feats = mapbox_vector_tile.decode(gzip.decompress(Reader(MemorySource(_archive_of(html))).get(z, x, y)))
    from road_table import roads_of
    foot = [f["properties"] for f in roads_of(html)["features"] if f["properties"].get("highway") == "footway"]     # the road table
    assert sorted(bool(p.get("__rs_dup")) for p in foot) == [False, True] and {p["__rs_edge2"] for p in foot} == {7, 8}
    assert "roads" not in feats                         # a page's tiles have no road lines
    assert {f["properties"]["__rs_edge"] for f in feats["simple"]["features"] if f["properties"]["__rs_cls"] == "footway"} == {7}


def test_tiles_carry_a_two_way_pairs_one_casing():
    """tiles=True: the pair's one casing (twin_casing "one") rides in the archive's "simple" layer with what the layer reads: only the first
    edge has casing pieces, flagged __rs_pair and naming the other edge (__rs_edge2); both directions have their fill."""
    import mapbox_vector_tile
    from pmtiles.reader import MemorySource, Reader

    from roadstyle.render_web import render
    a, b = (18.0, 59.3), (18.001, 59.3)
    g = gpd.GeoDataFrame({"highway": ["primary"] * 2}, geometry=[LineString([a, b]), LineString([b, a])], crs=4326)
    html = render(g, basemap="blank", tiles=True).html
    style = json.JSONDecoder().raw_decode(html, html.index("const style = ") + 14)[0]
    assert "__rs_pair" in json.dumps(next(l for l in style["layers"] if l["id"] == "roads-simple")["paint"]["line-width"])
    z = 15
    n = 1 << z
    x = int((18.0005 + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(59.3))) / math.pi) / 2 * n)
    ps = [f["properties"] for f in mapbox_vector_tile.decode(gzip.decompress(Reader(MemorySource(_archive_of(html))).get(z, x, y)))["simple"]["features"]]
    assert sorted((p["__rs_edge"], p["__rs_k"], p.get("__rs_pair"), p.get("__rs_edge2")) for p in ps) == [(0, 0, True, 1), (0, 1, None, None), (1, 1, None, None)]

