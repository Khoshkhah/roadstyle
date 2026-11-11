"""Makes granville_input_profile.json: the input profile of the Granville Bridge group (docs/design/bridge_profile_edit.md), in the form that the engine would write for a person to edit: the group with its
13 nodes (the position of each, ground or junction, and its height z) and its 12 chains (the OSM ways, the length, the two end nodes, and the interior control points: none here). The 8 nodes on the
ground are 0 and come from the data. The 5 junction heights are the example of docs/design/bridge_height_design.md (each at the highest height that a grade of 6 % allows, not above 22 m). Run it again after
a change of the nodes or of the example:

    python docs/img/bridge-height/granville_input_profile.py"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from granville_nodes import example_profile, graph  # noqa: E402

DESIGN_SPEED_KMH, DESIGN_GRADE = 50, 0.06


def input_profile():
    """The input profile of the group, as a dictionary."""
    at, ends, chains = graph()
    height, _ = example_profile(DESIGN_GRADE)
    order = sorted(at, key=lambda k: -k[1])                                   # the nodes from the north to the south
    ids = {k: f"n{i}" for i, k in enumerate(order, 1)}
    nodes = []
    for k in order:
        ground = len(at[k]) == 1
        nodes.append({"id": ids[k], "lonlat": list(k), "kind": "ground" if ground else "junction", "chains": [f"c{n}" for n, _, _ in sorted(at[k])],
                      "z_m": round(height[k], 1), "source": "data" if ground else "example", "method": "mapped" if ground else "chosen"})
    out = []
    for n, c in enumerate(chains, 1):
        na, nb, ell = ends[n]
        out.append({"id": f"c{n}", "osm_ways": sorted({f["properties"]["osm_id"] for f in c["pieces"]}), "length_m": round(ell, 1), "from": ids[na], "to": ids[nb], "points": []})
    return {"format": "roadstyle.bridge_profile/1", "parameters": {"design_speed_kmh": DESIGN_SPEED_KMH, "design_grade": DESIGN_GRADE},
            "groups": [{"name": "Granville Bridge", "nodes": nodes, "chains": out}]}


def main():
    profile = input_profile()
    text = json.dumps(profile, indent=1)
    # a short form: one line for each node, chain and point list
    (HERE / "granville_input_profile.json").write_text(text + "\n")
    g = profile["groups"][0]
    print(f"{len(g['nodes'])} nodes ({sum(1 for n in g['nodes'] if n['kind'] == 'ground')} ground, {sum(1 for n in g['nodes'] if n['kind'] == 'junction')} junction), {len(g['chains'])} chains")
    print(json.dumps(g["nodes"][0]), json.dumps(g["chains"][0]), sep="\n")


if __name__ == "__main__":
    main()
