"""A bridge profile of urbanstyle as an input profile of roadstyle (docs/design/bridge_profile_edit.md, step 5; docs/guides/bridge-profile.md).

urbanstyle writes one ``<name>.bridge.json`` for each bridge (format ``urbanstyle.bridge/1``): an axis for each chain of road ways, with a height line ``[s, z]`` in metres, measured or derived. This module reads
the axes of that file and writes an input profile for ``bridge_profile=``: the height of each node, and the grade points of each chain as interior control points of the curve ``design``. It is outside the
engine: the engine reads the input profile and knows nothing of urbanstyle.

An axis is a chain when they have the same OSM ways. An axis can run the other way and can go on past the end of the chain (urbanstyle continues a landing on fill along the next roads), so the heights are
read at the place on the axis that is nearest to each node of the chain.
"""
import json
import warnings
from pathlib import Path

__all__ = ["bridge_profile_from_urbanstyle"]

FORMAT = "urbanstyle.bridge/1"
_GROUND_M = 0.5                     # an axis that is this high or less at a free end of the bridge is on the ground there (the LiDAR and the rounding of the axis)
_EDGE_M = 1.0                       # a grade point nearer than this to an end of the chain is the node's height, not an interior point


def _read(bridge):
    if isinstance(bridge, dict):
        return bridge
    if isinstance(bridge, (str, Path)):
        return json.loads(Path(bridge).read_text())
    raise TypeError(f"the bridge is a dictionary or the path of a .bridge.json file, not {type(bridge).__name__}")


def _along(line, x, y):
    """The distance along the polyline ``line`` (metres) of the point on it that is nearest to (x, y), and how far (x, y) is from it."""
    best, run = (float("inf"), 0.0), 0.0
    for (x0, y0), (x1, y1) in zip(line, line[1:], strict=False):
        dx, dy = x1 - x0, y1 - y0
        seg = (dx * dx + dy * dy) ** 0.5
        t = 0.0 if seg == 0 else max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / (seg * seg)))
        d = ((x - (x0 + t * dx)) ** 2 + (y - (y0 + t * dy)) ** 2) ** 0.5
        if d < best[0]:
            best = (d, run + t * seg)
        run += seg
    return best[1], best[0]


def _z_at(samples, s):
    """The height of the axis at ``s`` metres: the line of ``samples`` (``[s, z]``, every 10 m), straight between two."""
    if s <= samples[0][0]:
        return samples[0][1]
    for (s0, z0), (s1, z1) in zip(samples, samples[1:], strict=False):
        if s <= s1:
            return z0 + (z1 - z0) * (s - s0) / (s1 - s0) if s1 > s0 else z1
    return samples[-1][1]


def _fit(pts, length):
    """Shorten the curves of ``pts`` (in order of ``s``, inside a chain of ``length`` metres) so that no curve reaches past an end of the chain or into its neighbour. The axis goes on past the ends
    of the chain, and a point that was inside its axis can be near the end of the chain."""
    ss = [0.0] + [q["s"] for q in pts] + [length]
    half = [0.0] + [q["curve_m"] / 2.0 for q in pts] + [0.0]
    for i in range(len(ss) - 1):
        gap = ss[i + 1] - ss[i]
        if half[i] + half[i + 1] > gap:
            f = gap / (half[i] + half[i + 1]) * (1 - 1e-9)
            half[i] *= f
            half[i + 1] *= f
    for q, h in zip(pts, half[1:-1], strict=True):
        q["curve_m"] = round(h * 2.0 - 0.005, 2) if h > 0 else 0.0           # down to 0.01 m: a rounded-up curve could overlap its neighbour by a hair


def bridge_profile_from_urbanstyle(edges, bridge, *, way_col="osm_id", max_node_gap_m=3.0, **kwargs) -> dict:
    """The input profile of roadstyle for the 3D bridges of ``edges``, from the axes of an urbanstyle bridge file.

    ``bridge``: the dictionary of a ``.bridge.json`` file (format ``urbanstyle.bridge/1``) or its path. ``way_col``: the column of ``edges`` with the OSM way id (``osm_id``). ``kwargs`` are the keywords
    of ``render_edges`` that change which bridges are 3D (``bridge_col``, ``layer_col``...).

    Every chain of the roads must have an axis with the same OSM ways: a chain with no axis is an error that names it. A free end of a bridge (a node where one chain ends) is on the ground: an axis that is
    more than 0.5 m high there is an error that names every such node and its height (the OSM bridge is shorter than the real one, and the converter does not draw a cliff in its place). An axis that no chain has is a warning (urbanstyle can draw a bridge that roadstyle
    does not). The result has ``parameters.curve = "design"``, the height of each node (``source`` of the axis, and ``method`` ``measured``, or ``derived`` for urbanstyle's own rule; the mean of the axes that end at a node, with a warning where they differ
    by more than ``max_node_gap_m``) and, for each chain, the grade points of its axis with the length of each vertical curve. Give it to ``bridge_profile=`` or to ``rs.bridge_profile``::

        given = rs.bridge_profile_from_urbanstyle(edges, "granville-bridge.bridge.json")
        rs.render_dashboard(edges, view_3d=True, bridge_profile=given).save("map.html")
    """
    from pyproj import Transformer

    from ._engine import export_inline

    data = _read(bridge)
    z_datum = data.get("z_datum")
    z_datum = z_datum.get("value") if isinstance(z_datum, dict) else z_datum
    warnings.warn("the heights of an urbanstyle bridge file are above urbanstyle's own reference ground" + (f" ({str(z_datum)[:110].rstrip()}...)" if z_datum else "")
                  + ", which is the ground of the area only if urbanstyle used the same elevation file; the profile does not name a ground. Give the ground of the area in the input if the two agree", stacklevel=2)
    if data.get("format") != FORMAT:
        raise ValueError(f"the bridge file has the format {data.get('format')!r}; this reads {FORMAT!r}")
    kwargs.pop("view_3d", None)
    kwargs.pop("bridge_profile", None)
    style = export_inline(edges, view_3d=True, **kwargs)
    base = style["metadata"]["roadstyle:bridge_profile"]
    if not base["groups"]:
        raise ValueError("the roads have no 3D bridges (a bridge with a level of 1 or more), so there is no chain for an axis")
    if way_col not in edges.columns:
        raise ValueError(f"the roads have no column {way_col!r}: it holds the OSM way id that a chain and an axis are matched by (way_col=)")
    decks = style["sources"]["decks"]["data"]["features"]
    ways: dict[str, set[int]] = {}
    for f in decks:
        p = f["properties"]
        if "__rs_casing_slab" not in p and p.get(way_col) is not None:
            ways.setdefault(f"c{p['__rs_chain']}", set()).add(int(p[way_col]))
    to_m = Transformer.from_crs(4326, data["crs"], always_xy=True).transform
    nodes = {n["id"]: n for g in base["groups"] for n in g["nodes"]}
    axes = {a["id"]: {**a, "ways": {int(w[1:]) for w in a["ways"]}} for a in data["axes"]}
    heights: dict[str, list[tuple[float, str, str]]] = {}       # node id -> (z, source, method) of each axis that ends there
    chains, unmatched, raised = [], [], []
    for g in base["groups"]:
        for c in g["chains"]:
            mine = ways.get(c["id"], set())
            axis = max(axes.values(), key=lambda a: len(mine & a["ways"]), default=None)
            if axis is None or not mine or mine - axis["ways"]:
                unmatched.append(f"{c['id']} (OSM ways {sorted(mine)})")
                continue
            line = axis["line"]["value"]
            v = axis["vertical"]
            ends = [to_m(*nodes[c[k]]["lonlat"]) for k in ("from", "to")]
            (a0, d0), (a1, d1) = (_along(line, *e) for e in ends)
            for k, d in (("from", d0), ("to", d1)):
                if d > 15.0:
                    raise ValueError(f"the node {c[k]} of the chain {c['id']} is {d:.0f} m from the axis {axis['id']} that has its OSM ways: the file is not for these roads")
            # the chain runs along the axis from a0 to a1 (a1 < a0: the other way)
            sign = 1.0 if a1 >= a0 else -1.0
            length = c["length_m"]          # the engine's length of the chain: the points are placed on it (the axis and the chain differ by a few metres)
            src = v.get("source", "urbanstyle")
            method = "derived" if src == "urbanstyle" else "measured"           # urbanstyle's own rule, or a survey or LiDAR that it read
            for k, a in (("from", a0), ("to", a1)):
                z = max(0.0, _z_at(v["samples"], a))
                if nodes[c[k]]["kind"] == "ground":
                    # the end of a bridge is on the ground, so the axis must be on it there. An axis that is above the ground at a free end goes on past the end of the OSM bridge (a landing on fill, or
                    # a deck that OSM does not tag as a bridge): that is an error, listed after the loop. The converter does not set the end to 0: that would draw a cliff
                    if z > _GROUND_M:
                        raised.append((c[k], axis["id"], z))
                    z = 0.0                    # within 0.5 m of the ground: the end is on it
                heights.setdefault(c[k], []).append((z, src, method))
            pts = []
            for (s, z), curve in zip(v["points"], v["curves"], strict=True):
                s_chain = (s - a0) * sign
                if _EDGE_M < s_chain < length - _EDGE_M:
                    pts.append({"s": round(s_chain, 2), "z_m": round(max(0.0, z), 2), "curve_m": curve, "source": src, "method": method})
            pts.sort(key=lambda q: q["s"])
            # a curve cannot reach past an end of the chain: the axis goes on there, the chain does not
            _fit(pts, length)
            chains.append({"id": c["id"], "points": pts})
    if unmatched:
        raise ValueError("these chains of the roads have no axis with the same OSM ways in the bridge file: " + "; ".join(unmatched))
    if raised:
        names = ", ".join(f"{n} (the axis {a} is {z:.1f} m high)" for n, a, z in sorted(set(raised), key=lambda r: int(r[0][1:])))
        raise ValueError(f"the bridge file is above the ground at {len(set(r[0] for r in raised))} free ends of the bridge in these roads: {names}. The end of a bridge is on the ground, so the axis goes on past the end "
                         "of the OSM bridge (a landing on fill, or a deck that OSM does not tag as a bridge). The converter does not set such an end to 0: the deck would drop to the ground in a few metres. "
                         "Fix the roads (the group must include the part where the deck is still above the ground) or the heights in the bridge file")
    used = {w for c in chains for w in ways[c["id"]]}
    for a in axes.values():
        if not a["ways"] & used:
            warnings.warn(f"the axis {a['id']} of the bridge file has no chain in these roads (its OSM ways are not 3D bridges here)", stacklevel=2)
    node_entries = []
    for nid, hs in sorted(heights.items(), key=lambda kv: int(kv[0][1:])):
        zs = [h[0] for h in hs]
        if max(zs) - min(zs) > max_node_gap_m:
            warnings.warn(f"the node {nid}: the axes that end there differ by {max(zs) - min(zs):.1f} m ({', '.join(f'{z:.1f}' for z in zs)}); the node gets the mean", stacklevel=2)
        node_entries.append({"id": nid, "z_m": round(sum(zs) / len(zs), 2), "source": hs[0][1], "method": hs[0][2]})
    return {"parameters": {"curve": "design"}, "groups": [{"nodes": node_entries, "chains": chains}]}
