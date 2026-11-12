"""The 3D bridge decks in two parts (docs/guides/bridge-profile.md, docs/reference/formats.md): today's rule writes a complete bridge profile (`rs.bridge_profile`), and the maker makes the decks
from a profile (`bridge_profile=`). The maker, given the profile that today's rule wrote, makes the same decks as today."""
import base64
import gzip
import json
import re
import warnings

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


def test_an_empty_input_gives_the_profile_of_today_and_a_complete_profile_gives_itself():
    today = rs.bridge_profile(_roads())
    for empty in ({}, {"groups": []}, {"parameters": {}, "groups": [{"nodes": [], "chains": []}]}):
        assert rs.bridge_profile(_roads(), empty) == today                                                    # Part 1 of nothing: every value is filled by the rules
    assert rs.bridge_profile(_roads(), today) == today                                                        # Part 1 of a complete profile: no change
    junction = next(n for g in today["groups"] for n in g["nodes"] if n["kind"] == "junction")
    once = rs.bridge_profile(_roads(), {"groups": [{"nodes": [{"lonlat": junction["lonlat"], "z_m": 4.0}]}]})
    assert rs.bridge_profile(_roads(), once) == once                                                          # Part 1 twice is Part 1 once


def test_a_given_height_is_kept_by_position_or_by_id_and_the_rest_is_filled():
    today = rs.bridge_profile(_roads())
    junction = next(n for g in today["groups"] for n in g["nodes"] if n["kind"] == "junction")
    by_position = rs.bridge_profile(_roads(), {"groups": [{"nodes": [{"lonlat": [junction["lonlat"][0] + 2e-5, junction["lonlat"][1]], "z_m": 4.0}]}]})   # 1.5 m away
    by_id = rs.bridge_profile(_roads(), {"groups": [{"nodes": [{"id": junction["id"], "z_m": 4.0}]}]})
    node = next(n for g in by_id["groups"] for n in g["nodes"] if n["id"] == junction["id"])
    assert (node["z_m"], node["source"], node["method"]) == (4.0, "given", "chosen")                         # kept, and marked as the person's
    assert [g["chains"] for g in by_id["groups"]] == [g["chains"] for g in today["groups"]]                  # the chains: the rules'
    assert [n["z_m"] for g in by_position["groups"] for n in g["nodes"]] == [n["z_m"] for g in by_id["groups"] for n in g["nodes"]]
    assert _decks(_page(bridge_profile=by_id)) == _decks(_page(bridge_profile={"groups": [{"nodes": [{"id": junction["id"], "z_m": 4.0}]}]}))   # the page fills it too
    assert _decks(_page(bridge_profile=by_id)) != _decks(_page())
    own = rs.bridge_profile(_roads(), {"groups": [{"nodes": [{"id": junction["id"], "z_m": 4.0, "source": "survey", "method": "measured"}]}]})
    node = next(n for g in own["groups"] for n in g["nodes"] if n["id"] == junction["id"])
    assert (node["source"], node["method"]) == ("survey", "measured")                                         # the person's words are kept
    wide = rs.bridge_profile(_roads(), {"parameters": {"design_speed_kmh": 30}, "groups": [{"name": "Y", "nodes": [{"id": junction["id"]}], "chains": [{"id": "c4", "width_m": 9.0}]}]})
    assert wide["parameters"]["design_speed_kmh"] == 30 and wide["parameters"]["design_grade"] == today["parameters"]["design_grade"]
    assert wide["groups"][0]["name"] == "Y" and wide["groups"][1]["chains"][0]["width_m"] == 9.0 and wide["groups"][1]["chains"][0]["width_source"] == "given"


def test_a_profile_with_values_missing_is_filled_and_one_that_is_not_for_these_roads_is_an_error_that_says_what():
    profile = rs.bridge_profile(_roads())

    def changed(change):
        p = json.loads(json.dumps(profile))
        change(p)
        return p

    for p in (changed(lambda p: p["groups"][0]["nodes"][0].pop("z_m")), changed(lambda p: p["groups"][0]["chains"][0].pop("top_m")), changed(lambda p: p["groups"][0]["chains"].pop()),
              changed(lambda p: p.pop("parameters")), changed(lambda p: p["groups"].pop())):
        assert rs.bridge_profile(_roads(), p) == profile                                                      # every value is optional: the rules fill it again
        assert _decks(_page(bridge_profile=p)) == _decks(_page())

    def error(p, exc=ValueError):
        with pytest.raises(exc) as e:
            _page(bridge_profile=p)
        return str(e.value)

    assert "interior control points" in error(changed(lambda p: p["groups"][0]["chains"][0].update(points=[{"s": 5.0, "z_m": 2.0}])))
    assert "unknown field `extra`" in error(changed(lambda p: p.update(extra=1)))
    assert "this engine reads" in error(changed(lambda p: p.update(format="other")))
    assert "not for these roads" in error(changed(lambda p: p["groups"][0]["chains"][0].update(id="c99")))
    assert "not for these roads" in error({"groups": [{"nodes": [{"lonlat": [0.0, 0.0], "z_m": 3.0}]}]})
    j = next(n for g in profile["groups"] for n in g["nodes"] if n["kind"] == "junction")                    # a junction: the end of a bridge is on the ground and cannot be raised
    assert "cannot be above the top" in error({"groups": [{"nodes": [{"id": j["id"], "z_m": 3.0}], "chains": [{"id": j["chains"][0], "top_m": 1.0}]}]})
    ground = next(n for g in profile["groups"] for n in g["nodes"] if n["kind"] == "ground")
    assert "free end of its bridge, so it is on the ground" in error({"groups": [{"nodes": [{"id": ground["id"], "z_m": 3.0}]}]})
    with pytest.raises(TypeError, match="dictionary or the path"):
        _page(bridge_profile=42)
    with pytest.raises(TypeError, match="once"):
        rs.bridge_profile(_roads(), {}, bridge_profile={})


def test_a_grade_above_the_design_grade_between_a_given_height_and_the_other_end_is_a_warning():
    junction = next(n for g in rs.bridge_profile(_roads())["groups"] for n in g["nodes"] if n["kind"] == "junction")
    given = {"parameters": {"design_grade": 0.01}, "groups": [{"nodes": [{"id": junction["id"], "z_m": 4.0}]}]}
    with pytest.warns(UserWarning, match=r"the chain c\d rises .* the design grade is 0.01"):
        _page(bridge_profile=given)
    with warnings.catch_warnings():                                                                           # a profile that the engine wrote has no heights of the person: no warning
        warnings.simplefilter("error")
        _page(bridge_profile={**rs.bridge_profile(_roads()), "parameters": {"design_speed_kmh": 50, "design_grade": 0.01}})


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


def test_the_filler_completes_the_five_heights_of_the_granville_example():
    """docs/samples/bridge-profile/granville_input_partial.json: 5 junction heights, each named by its position. The engine finds the 13 nodes and 12 chains, keeps the 5 heights, and fills the rest."""
    from pathlib import Path
    samples = Path(__file__).resolve().parents[1] / "docs" / "samples" / "bridge-profile"
    edges = gpd.read_parquet(samples / "granville_bridge_edges.parquet")
    given = json.loads((samples / "granville_input_partial.json").read_text())
    with pytest.warns(UserWarning, match=r"the chain c3 rises 5.8 m in 96 m .* the design grade is 0.06"):     # 5.3 m and 11.1 m are 96 m apart: 0.061
        filled = rs.bridge_profile(edges, given)
    group = filled["groups"][0]
    assert (len(filled["groups"]), len(group["nodes"]), len(group["chains"])) == (1, 13, 12)
    assert filled["parameters"] == {"design_speed_kmh": 50.0, "design_grade": 0.06, "curve": "smooth"}          # the two given parameters, and the curve of the rules
    junctions = {n["id"]: (n["z_m"], n["source"], n["method"]) for n in group["nodes"] if n["kind"] == "junction"}
    assert sorted(junctions.values()) == sorted((e["z_m"], "example", "chosen") for e in given["groups"][0]["nodes"])
    assert all(n["z_m"] == 0 and n["source"] == "data" for n in group["nodes"] if n["kind"] == "ground") and sum(n["kind"] == "ground" for n in group["nodes"]) == 8
    assert {c["top_m"] for c in group["chains"]} == {22.0}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert rs.bridge_profile(edges, filled) == filled                                                       # the filler twice is the filler once
        page = _decks(rs.render_edges(edges, backend="web", view_3d=True, bridge_profile=given).html)
        assert page and page != _decks(rs.render_edges(edges, backend="web", view_3d=True).html)                 # the 5 heights change the pieces
        assert page == _decks(rs.render_edges(edges, backend="web", view_3d=True, bridge_profile=filled).html)   # the input and the filled profile make one page


# ---- the design rules and the curve `design` (docs/design/bridge_height_design.md) ----

def _long_roads():
    """A bridge of 1 km on its own, and a Y of three bridges of 700 m to 900 m."""
    a, b, c, d = (18.000, 59.3000), (18.010, 59.3075), (18.020, 59.3125), (18.020, 59.3025)
    lines = [[a, b], [b, c], [b, d], [(18.05, 59.3), (18.0640, 59.3)]]
    return gpd.GeoDataFrame({"highway": ["primary"] * 4, "bridge": ["yes"] * 4, "layer": ["1"] * 4, "edge_id": [1, 2, 3, 4]}, geometry=[LineString(x) for x in lines], crs=4326)


def test_the_design_rule_gives_a_top_ramps_at_the_design_grade_and_a_crest_for_drainage():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        p = rs.bridge_profile(_long_roads(), bridge_profile={"parameters": {"height_rule": "design"}})
    assert (p["parameters"]["curve"], p["parameters"]["design_grade"], p["parameters"]["height_rule"]) == ("design", 0.05, "design")
    assert not [str(x.message) for x in w if "level top" in str(x.message)], "the rule makes no level top"
    lone = p["groups"][-1]["chains"][0]
    assert lone["top_m"] == pytest.approx(9.0, abs=0.5), lone                                                  # the clearance 5 m and the depth 4 m
    assert [q["s"] for q in lone["points"]] == sorted(q["s"] for q in lone["points"]) and len(lone["points"]) == 3, lone["points"]   # the foot of the crest, the middle, the other foot
    first, mid, last = lone["points"]
    assert first["z_m"] == pytest.approx(last["z_m"]) and mid["z_m"] > first["z_m"], "a crest in the middle of the top"
    assert (mid["z_m"] - first["z_m"]) / (mid["s"] - first["s"]) == pytest.approx(0.005, abs=1e-4), "0.5 % each side"
    assert first["s"] == pytest.approx((first["z_m"]) / 0.05, abs=1.0), "the ramp is 5 %"
    assert all(q["curve_m"] >= 30 for q in lone["points"]), "every curve is at least 0.6 V = 30 m"


def test_the_curve_design_makes_pieces_whose_slope_is_never_above_the_design_grade_and_the_page_gets_the_profile():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        html = rs.render_edges(_long_roads(), backend="web", view_3d=True, bridge_profile={"parameters": {"height_rule": "design"}}).html
    feats = [f["properties"] for f in _decks(html) if "__rs_casing_slab" not in f["properties"]]
    length = {c["id"]: c["length_m"] for g in rs.bridge_profile(_long_roads(), bridge_profile={"parameters": {"height_rule": "design"}})["groups"] for c in g["chains"]}
    assert feats
    for q in feats:
        l = length[f"c{q['__rs_chain']}"]
        ds = (q["__rs_s1"] - q["__rs_s0"]) * l
        assert abs(q["__rs_lift1"] - q["__rs_lift0"]) * q["__rs_full"] / ds <= 0.05 + 0.002, q


def test_a_given_height_is_a_fixed_point_of_the_design_rule_and_the_filler_twice_is_the_filler_once():
    first = rs.bridge_profile(_long_roads(), bridge_profile={"parameters": {"height_rule": "design"}})
    junction = next(n for g in first["groups"] for n in g["nodes"] if n["kind"] == "junction")
    given = {"parameters": {"height_rule": "design"}, "groups": [{"nodes": [{"id": junction["id"], "z_m": 4.0}]}]}
    second = rs.bridge_profile(_long_roads(), bridge_profile=given)
    node = next(n for g in second["groups"] for n in g["nodes"] if n["id"] == junction["id"])
    assert (node["z_m"], node["source"]) == (4.0, "given") and junction["z_m"] > 4.0
    assert rs.bridge_profile(_long_roads(), bridge_profile=second) == second                                    # the filler twice is the filler once


def test_the_end_of_a_bridge_is_on_the_ground_and_the_filler_and_the_maker_warn_of_what_they_see():
    p = rs.bridge_profile(_long_roads(), bridge_profile={"parameters": {"height_rule": "design"}})
    chain = p["groups"][0]["chains"][0]
    ground = next(n for n in p["groups"][0]["nodes"] if n["kind"] == "ground")
    # a free end that is raised: an error, because the end of a bridge is on the ground
    with pytest.raises(ValueError, match=f"the node {ground['id']} is a free end of its bridge, so it is on the ground"):
        rs.bridge_profile(_long_roads(), bridge_profile={"groups": [{"nodes": [{"id": ground["id"], "z_m": 4.0}]}]})
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        # a level top of the person (800 m), and a point that makes a straight grade of 17 %
        edit = {"parameters": {"height_rule": "design"}, "groups": [{"chains": [{"id": chain["id"], "points": [{"s": 100.0, "z_m": 9.0, "curve_m": 30.0}, {"s": chain["length_m"] - 100.0, "z_m": 9.0, "curve_m": 30.0}]}]}]}
        rs.render_edges(_long_roads(), backend="web", view_3d=True, bridge_profile=edit)
        steep = {"parameters": {"curve": "design"}, "groups": [{"chains": [{"id": chain["id"], "points": [{"s": 100.0, "z_m": 40.0}]}]}]}
        rs.bridge_profile(_long_roads(), bridge_profile=steep)
    text = " | ".join(str(x.message) for x in w)
    assert f"the chain {chain['id']} has a level top" in text, text                                             # a flat top of the person
    assert f"the chain {chain['id']} goes from 0.0 m to 40.0 m" in text and "the design grade is 0.125" in text, text      # a straight grade that is too steep


# ---- the ground of the profile (the standard "The ground reference", docs/design/ground_terrain.md) ----

_GROUND = {"id": "a" * 64, "source": "FABDEM V1-2", "product": "DTM", "vertical_datum": "EGM2008", "resolution_m": 30, "license": "CC BY-NC-SA 4.0", "terrain": "https://example.test/t.pmtiles"}


def _page_profile(html):
    at = html.index("const RS_OPTIONS = ") + len("const RS_OPTIONS = ")
    return json.JSONDecoder().raw_decode(html, at)[0]["bridge_profile"]


def test_a_page_with_a_ground_writes_it_into_the_profile_and_two_different_grounds_are_an_error():
    html = rs.render_edges(_roads(), backend="web", view_3d=True, ground=_GROUND).html
    assert _page_profile(html)["ground"] == {"id": "a" * 64, "source": "FABDEM V1-2", "product": "DTM", "vertical_datum": "EGM2008"}      # the facts, not the file or the license
    same = rs.render_edges(_roads(), backend="web", view_3d=True, ground=_GROUND, bridge_profile={"ground": {"id": "a" * 64}}).html
    assert _page_profile(same)["ground"] == {"id": "a" * 64}                                                                          # the profile's own ground is kept
    with pytest.raises(ValueError, match=r"ground b{64}, and the page draws the ground a{64}: two products of one area"):
        rs.render_edges(_roads(), backend="web", view_3d=True, ground=_GROUND, bridge_profile={"ground": {"id": "b" * 64}})
    # a profile with a ground and no id (a source, a product) is not compared; a page with no ground says nothing in the profile
    assert "ground" not in _page_profile(rs.render_edges(_roads(), backend="web", view_3d=True).html)
    with pytest.warns(UserWarning, match="the page has no ground"):
        rs.render_edges(_roads(), backend="web", view_3d=True, bridge_profile={"ground": {"id": "b" * 64}})


def test_the_ground_of_an_input_is_kept_in_the_complete_profile_and_the_filler_twice_is_the_filler_once():
    p = rs.bridge_profile(_roads(), {"ground": {"id": "c" * 64, "product": "DTM"}})
    assert p["ground"] == {"id": "c" * 64, "product": "DTM"}
    assert rs.bridge_profile(_roads(), p) == p
    assert "ground" not in rs.bridge_profile(_roads())                                                      # not said: not written
    with pytest.raises(ValueError, match="unknown field"):
        rs.bridge_profile(_roads(), {"ground": {"file": "x.tif"}})


def test_a_free_end_where_a_tunnel_starts_is_a_portal_and_no_other_node_says_so():
    a, b, c, d = (18.0000, 59.3000), (18.0003, 59.3002), (18.0006, 59.3004), (17.9994, 59.2998)
    roads = gpd.GeoDataFrame({"highway": ["primary"] * 3, "bridge": ["yes", "yes", None], "tunnel": [None, None, "yes"], "layer": ["1", "1", "-1"], "edge_id": [1, 2, 3]},
                             geometry=[LineString(x) for x in ([a, b], [b, c], [d, a])], crs=4326)
    p = rs.bridge_profile(roads)
    nodes = {tuple(n["lonlat"]): n for g in p["groups"] for n in g["nodes"]}
    assert nodes[a]["portal"] is True and nodes[a]["kind"] == "ground", nodes[a]          # the bridge goes into the tunnel at a
    assert "portal" not in nodes[c]                                                      # the other end of the bridge is a free end that is not a portal
    assert rs.bridge_profile(roads, p) == p                                              # the filler twice is the filler once
    wrong = {"groups": [{"nodes": [{"id": nodes[c]["id"], "portal": True}]}]}
    with pytest.raises(ValueError, match=r"not a portal in these roads.*the input says portal true"):
        rs.bridge_profile(roads, wrong)
    assert all("portal" not in n for g in rs.bridge_profile(_roads())["groups"] for n in g["nodes"])      # no tunnel in these roads


def _elevation_input(base=100.0, ground_id="a" * 64):
    """Every node of the Y and of the lone bridge at `base` metres plus the height that today's rule gives it: an input with z_reference "elevation"."""
    nodes = [{"id": n["id"], "z_m": base + n["z_m"], "source": "test", "method": "measured"} for g in rs.bridge_profile(_roads())["groups"] for n in g["nodes"]]
    return {"parameters": {"z_reference": "elevation"}, "ground": {"id": ground_id, "vertical_datum": "EGM2008"}, "groups": [{"nodes": nodes}]}


def test_a_profile_with_elevations_keeps_them_and_the_free_ends_are_not_forced_to_0():
    p = rs.bridge_profile(_roads(), _elevation_input())
    assert p["parameters"]["z_reference"] == "elevation" and p["parameters"]["curve"] == "design" and p["ground"]["vertical_datum"] == "EGM2008"
    ends = [n["z_m"] for g in p["groups"] for n in g["nodes"] if n["kind"] == "ground"]
    assert ends and all(z >= 100.0 for z in ends)                                                           # a free end is on the ground, and the ground is at 100 m here
    assert all(c["top_m"] >= 100.0 for g in p["groups"] for c in g["chains"])
    assert rs.bridge_profile(_roads(), p) == p                                                              # the filler twice is the filler once


def test_a_profile_with_elevations_says_what_is_missing_or_cannot_be_used():
    with pytest.raises(ValueError, match=r"must name its ground"):
        rs.bridge_profile(_roads(), {k: v for k, v in _elevation_input().items() if k != "ground"})
    short = _elevation_input()
    short["groups"][0]["nodes"].pop(0)
    with pytest.raises(ValueError, match=r"every node needs its elevation.*1 nodes have none"):
        rs.bridge_profile(_roads(), short)
    with pytest.raises(ValueError, match=r"height_rule.*cannot be used"):
        rs.bridge_profile(_roads(), {**_elevation_input(), "parameters": {"z_reference": "elevation", "height_rule": "design"}})
    with pytest.raises(ValueError, match=r"needs the curve"):
        rs.bridge_profile(_roads(), {**_elevation_input(), "parameters": {"z_reference": "elevation", "curve": "smooth"}})


def test_a_page_with_elevations_needs_the_ground_that_they_are_in():
    given = _elevation_input(ground_id="a" * 64)
    with pytest.raises(ValueError, match=r"elevations in the ground a{64}, and the page has no ground"):
        rs.render_edges(_roads(), backend="web", view_3d=True, bridge_profile=given)
    ok = rs.render_edges(_roads(), backend="web", view_3d=True, ground=_GROUND, bridge_profile=given).html
    assert _page_profile(ok)["parameters"]["z_reference"] == "elevation"
    with pytest.raises(ValueError, match=r"ground b{64}, and the page draws the ground a{64}"):
        rs.render_edges(_roads(), backend="web", view_3d=True, ground=_GROUND, bridge_profile=_elevation_input(ground_id="b" * 64))
