"""The 3D bridge decks in two parts (docs/guides/bridge-profile.md, docs/reference/formats.md): today's rule writes a complete bridge profile (`rs.bridge_profile`), and the maker makes the decks
from a profile (`bridge_profile=`). The maker, given the profile that today's rule wrote, makes the same decks as today."""
import base64
import gzip
import json
import re

import geopandas as gpd
import pytest
from shapely.geometry import LineString

import roadstyle as rs


def _roads():
    """Three bridges that meet at a node (A-B, B-C, B-D: one group, 3 chains), a bridge apart from them (one group, one chain) and a road on the ground."""
    a, b, c, d = (18.0000, 59.3000), (18.0003, 59.3002), (18.0006, 59.3004), (18.0006, 59.3000)
    lines = [[a, b], [b, c], [b, d], [(18.01, 59.3), (18.0103, 59.3002)], [(18.02, 59.3), (18.0203, 59.3002)]]
    return gpd.GeoDataFrame({"highway": ["primary"] * 5, "bridge": ["yes"] * 4 + [None], "layer": ["1"] * 4 + [None], "edge_id": [1, 2, 3, 4, 5]},
                            geometry=[LineString(x) for x in lines], crs=4326)


def _decks(html):
    """The features of the source `decks` of a page."""
    style = json.JSONDecoder().raw_decode(html, html.index("const style = ") + len("const style = "))[0]
    blobs = re.search(r'<script id="rs-gz" type="application/json">(.*?)</script>', html, re.S)
    if blobs and "decks" in json.loads(blobs.group(1)):
        return json.loads(gzip.decompress(base64.b64decode(json.loads(blobs.group(1))["decks"])))["features"]
    return style["sources"]["decks"]["data"]["features"]


def _page(**kw):
    return rs.render_edges(_roads(), backend="web", view_3d=True, **kw).html


def test_the_profile_of_a_page_is_complete_and_has_the_nodes_and_chains_of_its_bridges():
    p = rs.bridge_profile(_roads())
    assert p["format"] == "roadstyle.bridge_profile/1" and p["parameters"]["curve"] == "smooth"
    assert [len(g["chains"]) for g in p["groups"]] == [3, 1]                                                 # the Y is one group of 3 chains, the lone bridge another
    nodes = [n for g in p["groups"] for n in g["nodes"]]
    assert sorted(n["kind"] for n in nodes) == ["ground"] * 5 + ["junction"]                                 # 5 ends on the ground, one junction (the node of the Y)
    junction = next(n for n in nodes if n["kind"] == "junction")
    assert len(junction["chains"]) == 3 and (junction["source"], junction["method"]) == ("rule", "derived")
    assert all(n["z_m"] == 0 and (n["source"], n["method"]) == ("data", "mapped") for n in nodes if n["kind"] == "ground")
    assert [c["id"] for g in p["groups"] for c in g["chains"]] == ["c1", "c2", "c3", "c4"]
    assert all(c["points"] == [] and c["top_m"] >= 5.0 for g in p["groups"] for c in g["chains"])


def test_the_maker_makes_the_decks_of_today_from_the_profile_of_today(tmp_path):
    today = _decks(_page())
    profile = rs.bridge_profile(_roads())
    assert today and _decks(_page(bridge_profile=profile)) == today                                          # from a dictionary
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile))
    assert _decks(_page(bridge_profile=path)) == today and _decks(_page(bridge_profile=str(path))) == today    # from a file
    assert rs.bridge_profile(_roads(), bridge_profile=profile) == profile                                    # the profile that a page is given is the profile that it writes


def test_a_person_changes_a_number_and_the_page_changes():
    today = _decks(_page())
    profile = rs.bridge_profile(_roads())
    junction = next(n for g in profile["groups"] for n in g["nodes"] if n["kind"] == "junction")
    junction["z_m"] = junction["z_m"] / 2
    junction["source"], junction["method"] = "given", "chosen"
    changed = _decks(_page(bridge_profile=profile))
    assert changed != today                                                                                  # other ramps: other pieces, and other heights
    assert max(f["properties"]["__rs_base"] for f in changed) < max(f["properties"]["__rs_base"] for f in today)
    wide = rs.bridge_profile(_roads())
    wide["groups"][1]["chains"][0]["width_m"] = 9.0                                                          # the width of one chain
    assert _decks(_page(bridge_profile=wide)) != today


def test_a_profile_that_is_incomplete_or_not_for_these_roads_is_an_error_that_says_what():
    profile = rs.bridge_profile(_roads())

    def error(change):
        p = json.loads(json.dumps(profile))
        change(p)
        with pytest.raises(ValueError) as e:
            _page(bridge_profile=p)
        return str(e.value)

    assert "missing field `z_m`" in error(lambda p: p["groups"][0]["nodes"][0].pop("z_m")) and "fill it first" in error(lambda p: p["groups"][0]["nodes"][0].pop("z_m"))
    assert "no top_m" in error(lambda p: p["groups"][0]["chains"][0].pop("top_m"))
    assert "not built yet" in error(lambda p: p["parameters"].update(curve="design"))
    assert "interior control points" in error(lambda p: p["groups"][0]["chains"][0].update(points=[{"s": 5.0, "z_m": 2.0}]))
    assert "not for these roads" in error(lambda p: p["groups"].pop())
    with pytest.raises(TypeError, match="dictionary or the path"):
        _page(bridge_profile=42)


def test_a_profile_on_a_page_with_no_3d_bridges_does_nothing_and_says_so():
    profile = rs.bridge_profile(_roads())
    with pytest.warns(UserWarning, match="no 3D bridges"):
        html = rs.render_edges(_roads(), backend="web", view_3d=False, bridge_profile=profile).html
    style = json.JSONDecoder().raw_decode(html, html.index("const style = ") + len("const style = "))[0]
    assert "decks" not in style["sources"]


def test_the_granville_sample_is_the_profile_that_the_engine_writes_and_the_maker_reads_it_again():
    """docs/samples/bridge-profile/granville_bridge_profile_today.json (docs/img/bridge-height/granville_engine_profile.py) is real output of the engine for the roads of the Granville Bridge, and the maker
    makes the same decks from it as today. The heights are the ones that the guide gives for today's engine: 22 m at four junctions and 11.2 m at the fifth."""
    from pathlib import Path
    samples = Path(__file__).resolve().parents[1] / "docs" / "samples" / "bridge-profile"
    edges = gpd.read_parquet(samples / "granville_bridge_edges.parquet")
    saved = json.loads((samples / "granville_bridge_profile_today.json").read_text())
    assert rs.bridge_profile(edges) == saved                                                                 # the file is what the engine writes
    group = saved["groups"][0]
    assert (len(saved["groups"]), len(group["nodes"]), len(group["chains"])) == (1, 13, 12)
    assert sorted(n["kind"] for n in group["nodes"]) == ["ground"] * 8 + ["junction"] * 5
    assert sorted(round(n["z_m"], 1) for n in group["nodes"] if n["kind"] == "junction") == [11.2, 22.0, 22.0, 22.0, 22.0]
    assert {c["top_m"] for c in group["chains"]} == {22.0}
    today = _decks(rs.render_edges(edges, backend="web", view_3d=True).html)
    assert today and _decks(rs.render_edges(edges, backend="web", view_3d=True, bridge_profile=samples / "granville_bridge_profile_today.json").html) == today
