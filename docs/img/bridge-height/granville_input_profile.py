"""The input profile of the Granville Bridge group and the two parts of the engine that work on it (docs/design/bridge_profile_edit.md): a prototype in Python, not the engine.

    Part 1, `fill`: reads an input profile that can be incomplete, and writes a complete one. It finds the nodes and chains from the roads, keeps every value that the input gives, and fills what is
    missing: a node on the ground is 0; a junction gets a height from a stand-in rule (the highest height that the design grade allows, not above 22 m); a chain gets its width from the engine's deck.
    Part 2, `make`: reads a complete input profile and makes the height along each chain: a straight grade between the control points, with a vertical curve at each interior point. It has no rules and no
    defaults. A value that is missing is an error.

It writes docs/samples/bridge-profile/granville_input_profile_colored.html (the complete profile with the values of the input and the values that the engine added in two colors), docs/samples/bridge-profile/granville_input_partial.json (the 5 junction heights, found by their position: the least input) and granville_input_profile.json (the complete profile), in the same folder. Run it again after a change:

    python docs/img/bridge-height/granville_input_profile.py"""
import html
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLES = HERE.parents[1] / "samples" / "bridge-profile"
sys.path.insert(0, str(HERE))
from design_rules import curve_length, vertical_profile  # noqa: E402
from granville import KX, KY  # noqa: E402
from granville_nodes import distance_to_ground, example_profile, graph  # noqa: E402

DEFAULTS = {"design_speed_kmh": 50, "design_grade": 0.05}        # what Part 1 fills when the input has no parameters
EXAMPLE_GRADE = 0.06            # the grade of the example: the 5 junction heights are the highest that it allows
CAP_M = 22.0                    # the stand-in rule: not above the height that the engine gives today
MATCH_M = 5.0                   # a given node is the node of the group within this distance


def partial_input():
    """The least input that a person gives: the 5 junction heights, each with the position of its node. Everything else is filled."""
    at, _, _ = graph()
    height, _ = example_profile(EXAMPLE_GRADE)
    junctions = sorted((k for k, v in at.items() if len(v) > 1), key=lambda k: -k[1])
    return {"parameters": {**DEFAULTS, "design_grade": EXAMPLE_GRADE},
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


def given_paths(given, filled):
    """The values of the complete profile `filled` that come from the input `given`, as paths (tuples of keys and indexes). Every other value was added by the engine."""
    paths = {("parameters", k) for k in (given.get("parameters") or {})}
    group = (given.get("groups") or [{}])[0]
    for entry in group.get("nodes", []):
        lon, lat = entry["lonlat"]
        for i, node in enumerate(filled["groups"][0]["nodes"]):
            if math.hypot((node["lonlat"][0] - lon) * KX, (node["lonlat"][1] - lat) * KY) <= MATCH_M:
                paths |= {("groups", 0, "nodes", i, k) for k in entry if k in node}
    given_chains = {frozenset(c["osm_ways"]): c for c in group.get("chains", []) if "osm_ways" in c}
    for i, chain in enumerate(filled["groups"][0]["chains"]):
        entry = given_chains.get(frozenset(chain["osm_ways"]), {})
        paths |= {("groups", 0, "chains", i, k) for k in entry if k in chain and k != "osm_ways"}
    return paths


def dump_html(filled, given):
    """The complete profile as the HTML of a `pre` block: each value in the span of its class, `given` (in the input: profile 1) or `added` (by the engine: profile 2). The text without the tags is the
    JSON of `dump`."""
    marked = given_paths(given, filled)

    def span(path, key, value):
        text = html.escape(json.dumps(key) + ": " + json.dumps(value, separators=(", ", ": ")), quote=False)
        return f'<span class="given" title="given in your input">{text}</span>' if path in marked else f'<span class="added">{text}</span>'

    def line(prefix, path, item):
        return prefix + "{" + ", ".join(span(path + (k,), k, v) for k, v in item.items()) + "}"

    rows = []
    for key, value in filled.items():
        if key == "parameters":
            rows.append(f' {json.dumps(key)}: ' + "{" + ", ".join(span((key, k), k, v) for k, v in value.items()) + "}")
        elif key != "groups":
            rows.append(" " + span((key,), key, value))
        else:
            group = []
            for gkey, gvalue in value[0].items():
                if gkey in ("nodes", "chains"):
                    group.append(f'   "{gkey}": [\n' + ",\n".join(line("    ", ("groups", 0, gkey, i), item) for i, item in enumerate(gvalue)) + "\n   ]")
                else:
                    group.append("   " + span(("groups", 0, gkey), gkey, gvalue))
            rows.append(' "groups": [\n  {\n' + ",\n".join(group) + "\n  }\n ]")
    return '<pre class="rs-bp"><code>{\n' + ",\n".join(rows) + "\n}</code></pre>"


LEGEND = '<span class="rs-bp-key"><span class="given">Given in your input (profile 1)</span> &nbsp; <span class="added">Added by the engine (profile 2)</span></span>'


def view_html(filled, given):
    """A page of its own with the colored profile, for a person who updates the input file: what they gave, and what the engine added."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>The complete input profile of the Granville Bridge</title>
<style>
:root {{ --bg: #ffffff; --fg: #1f2937; --given: #1d4ed8; --added: #c2410c; --line: #d1d5db; color-scheme: light dark; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #111827; --fg: #e5e7eb; --given: #93c5fd; --added: #fdba74; --line: #374151; }} }}
body {{ margin: 0; padding: 16px; background: var(--bg); color: var(--fg); font: 15px/1.5 system-ui, sans-serif; }}
h1 {{ font-size: 1.1rem; margin: 0 0 .4rem; }}
.rs-bp-key {{ display: inline-block; margin: .2rem 0 .8rem; }}
pre.rs-bp {{ margin: 0; padding: 12px; overflow: auto; border: 1px solid var(--line); border-radius: 6px; font: 13px/1.5 ui-monospace, Menlo, Consolas, monospace; }}
.given {{ color: var(--given); font-weight: 700; }}
.added {{ color: var(--added); }}
</style></head><body>
<h1>The complete input profile of the Granville Bridge</h1>
<p>Bold blue: what you gave in the input (profile 1). Orange: what the engine added (profile 2). Point at a bold blue value to see its tooltip.</p>
{LEGEND}
{dump_html(filled, given)}
</body></html>
"""


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
    (SAMPLES / "granville_input_partial.json").write_text(dump(partial))
    (SAMPLES / "granville_input_profile.json").write_text(dump(filled))
    (SAMPLES / "granville_input_profile_colored.html").write_text(view_html(filled, partial))
    paths = given_paths(partial, filled)
    print(f"values from the input: {len(paths)}")
    g = filled["groups"][0]
    print(f"input: {len(partial['groups'][0]['nodes'])} nodes. filled: {len(g['nodes'])} nodes ({sum(1 for n in g['nodes'] if n['kind'] == 'ground')} ground, "
          f"{sum(1 for n in g['nodes'] if n['kind'] == 'junction')} junction), {len(g['chains'])} chains")
    heights = make(filled)
    print("made the height along", len(heights), "chains; steepest slope:", round(max(abs(float(s)) for xs, z in heights.values() for s in __import__("numpy").gradient(z, xs)) * 100, 2), "%")


if __name__ == "__main__":
    main()
