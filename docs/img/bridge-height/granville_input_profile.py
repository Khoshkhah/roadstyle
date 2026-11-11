"""The input profile of the Granville Bridge group and the two parts of the engine that work on it (docs/design/bridge_profile_edit.md): a prototype in Python, not the engine.

    Part 1, `fill`: reads an input profile that can be incomplete, and writes a complete one. It finds the nodes and chains from the roads, keeps every value that the input gives, and fills what is
    missing: a node on the ground is 0; a junction gets a height from a stand-in rule (the highest height that the design grade allows, not above 22 m); a chain gets its width from the engine's deck.
    Part 2, `make`: reads a complete input profile and makes the height along each chain: a straight grade between the control points, with a vertical curve at each interior point. It has no rules and no
    defaults. A value that is missing is an error.

It writes granville_input_partial.json (the 5 junction heights, found by their position: the least input) and granville_input_profile.json (the complete profile). Run it again after a change:

    python docs/img/bridge-height/granville_input_profile.py"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from design_rules import curve_length, vertical_profile  # noqa: E402
from granville import KX, KY  # noqa: E402
from granville_nodes import distance_to_ground, example_profile, graph  # noqa: E402

DEFAULTS = {"design_speed_kmh": 50, "design_grade": 0.06}
CAP_M = 22.0                    # the stand-in rule: not above the height that the engine gives today
MATCH_M = 5.0                   # a given node is the node of the group within this distance


def partial_input():
    """The least input that a person gives: the 5 junction heights, each with the position of its node. Everything else is filled."""
    at, _, _ = graph()
    height, _ = example_profile(DEFAULTS["design_grade"])
    junctions = sorted((k for k, v in at.items() if len(v) > 1), key=lambda k: -k[1])
    return {"parameters": dict(DEFAULTS),
            "groups": [{"nodes": [{"lonlat": list(k), "z_m": round(height[k], 1), "source": "example", "method": "chosen"} for k in junctions]}]}


def fill(given):
    """Part 1. The complete input profile of the group, from `given` (an input profile that can be incomplete, down to an empty dictionary)."""
    at, ends, chains = graph()
    dist = distance_to_ground(at, ends)
    params = {**DEFAULTS, **(given.get("parameters") or {})}
    given_group = (given.get("groups") or [{}])[0]
    matched = {}
    for entry in given_group.get("nodes", []):
        lon, lat = entry["lonlat"]
        near = [k for k in at if math.hypot((k[0] - lon) * KX, (k[1] - lat) * KY) <= MATCH_M]
        if len(near) != 1:
            raise ValueError(f"the node at {entry['lonlat']} is within {MATCH_M:.0f} m of {len(near)} nodes of the group; it must be one")
        if near[0] in matched:
            raise ValueError(f"two entries for the node at {entry['lonlat']}")
        if entry.get("z_m") is not None and entry["z_m"] < 0:
            raise ValueError(f"the node at {entry['lonlat']} has a height below 0")
        matched[near[0]] = entry
    order = sorted(at, key=lambda k: -k[1])
    ids = {k: f"n{i}" for i, k in enumerate(order, 1)}
    nodes = []
    for k in order:
        ground = len(at[k]) == 1
        entry = matched.get(k, {})
        if entry.get("z_m") is not None:
            z, source, method = entry["z_m"], entry.get("source", "given"), entry.get("method", "chosen")      # the person's value is kept as it is
        elif ground:
            z, source, method = 0.0, "data", "mapped"
        else:
            z, source, method = min(CAP_M, params["design_grade"] * dist[k]), "rule", "derived"
        nodes.append({"id": ids[k], "lonlat": list(k), "kind": "ground" if ground else "junction", "chains": [f"c{n}" for n, _, _ in sorted(at[k])],
                      "z_m": round(z, 1), "source": source, "method": method})
    given_chains = {frozenset(c["osm_ways"]): c for c in given_group.get("chains", []) if "osm_ways" in c}
    out = []
    for n, c in enumerate(chains, 1):
        na, nb, ell = ends[n]
        ways = sorted({f["properties"]["osm_id"] for f in c["pieces"]})
        entry = given_chains.get(frozenset(ways), {})
        chain = {"id": f"c{n}", "osm_ways": ways, "length_m": round(ell, 1), "from": ids[na], "to": ids[nb], "points": entry.get("points", [])}
        if entry.get("width_m") is not None:
            chain["width_m"], chain["width_source"] = entry["width_m"], entry.get("width_source", "given")
        else:
            chain["width_m"], chain["width_source"] = round(c["width"], 1), "rule"                              # the deck width that the engine draws
        out.append(chain)
    return {"format": "roadstyle.bridge_profile/1", "parameters": params, "groups": [{"name": "Granville Bridge", "nodes": nodes, "chains": out}]}


def make(filled):
    """Part 2. The height along each chain of a complete input profile: {chain id: (x, z)}. A value that is missing is an error. There are no defaults here."""
    group = filled["groups"][0]
    zs = {}
    for node in group["nodes"]:
        if node.get("z_m") is None:
            raise ValueError(f"the node {node['id']} has no z_m: fill the profile first")
        zs[node["id"]] = node["z_m"]
    speed = filled["parameters"]["design_speed_kmh"]
    out = {}
    for chain in group["chains"]:
        if chain.get("width_m") is None:
            raise ValueError(f"the chain {chain['id']} has no width_m: fill the profile first")
        points = [(0.0, zs[chain["from"]])] + [(p["s"], p["z_m"]) for p in chain["points"]] + [(chain["length_m"], zs[chain["to"]])]
        curves = [0.0]
        for (x0, z0), (x1, z1), (x2, z2) in zip(points, points[1:], points[2:], strict=False):                  # a vertical curve at each interior point
            g1, g2 = (z1 - z0) / (x1 - x0), (z2 - z1) / (x2 - x1)
            curves.append(curve_length(speed, abs(g2 - g1) * 100, crest=g2 < g1))
        curves.append(0.0)
        out[chain["id"]] = vertical_profile(points, curves)
    return out


def input_profile():
    """The complete input profile of the group, from the least input."""
    return fill(partial_input())


def dump(profile):
    """The profile as JSON text, with each node and each chain on one line."""
    def line(x):
        return json.dumps(x, separators=(", ", ": "))

    rows = []
    for key, value in profile.items():
        if key != "groups":
            rows.append(f' "{key}": {line(value)}')
            continue
        group = []
        for gkey, gvalue in value[0].items():
            if gkey in ("nodes", "chains"):
                group.append(f'   "{gkey}": [\n' + ",\n".join("    " + line(item) for item in gvalue) + "\n   ]")
            else:
                group.append(f'   "{gkey}": {line(gvalue)}')
        rows.append(' "groups": [\n  {\n' + ",\n".join(group) + "\n  }\n ]")
    return "{\n" + ",\n".join(rows) + "\n}\n"


def main():
    partial, filled = partial_input(), input_profile()
    (HERE / "granville_input_partial.json").write_text(dump(partial))
    (HERE / "granville_input_profile.json").write_text(dump(filled))
    g = filled["groups"][0]
    print(f"input: {len(partial['groups'][0]['nodes'])} nodes. filled: {len(g['nodes'])} nodes ({sum(1 for n in g['nodes'] if n['kind'] == 'ground')} ground, "
          f"{sum(1 for n in g['nodes'] if n['kind'] == 'junction')} junction), {len(g['chains'])} chains")
    heights = make(filled)
    print("made the height along", len(heights), "chains; steepest slope:", round(max(abs(float(s)) for xs, z in heights.values() for s in __import__("numpy").gradient(z, xs)) * 100, 2), "%")


if __name__ == "__main__":
    main()
