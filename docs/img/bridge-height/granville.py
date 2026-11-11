"""Makes the pictures and the table of "A real example: the Granville Bridge" (docs/guides/bridge-height.md) from granville_bridge_edges.parquet, the 41 edges of
the Granville Bridge and its ramps in Vancouver (OpenStreetMap data, ODbL, through duckOSM's `driving.edges` of vancouver_city.duckdb: the edges of the bridge group,
27 OSM ways). Run it again after a change of the height rules:

    python docs/img/bridge-height/granville.py

It writes granville_plan.png and granville.png, and prints the table. The chains are numbered here from the longest (1) to the shortest. The numbers on the
page are pinned by tests/test_render_web.py (test_the_granville_bridge_example_is_the_engines)."""
import base64
import collections
import gzip
import json
import math
import re
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import roadstyle as rs

HERE = Path(__file__).resolve().parent
KX = 111320 * math.cos(math.radians(49.27))        # metres of a degree of longitude at Vancouver
KY = 111320.0


def deck_pieces(edges):
    """The deck pieces (no casing slabs) of the source `decks` of the page that the engine makes from `edges`, with the compressed source opened."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        html = rs.render_edges(edges, backend="web", view_3d=True).html
    style = json.JSONDecoder().raw_decode(html, html.index("const style = ") + len("const style = "))[0]
    blobs = re.search(r'<script id="rs-gz" type="application/json">(.*?)</script>', html, re.S)
    if blobs:
        for sid, blob in json.loads(blobs.group(1)).items():
            if sid in style["sources"]:
                style["sources"][sid]["data"] = json.loads(gzip.decompress(base64.b64decode(blob)))
    return [f for f in style["sources"]["decks"]["data"]["features"] if not f["properties"].get("__rs_casing_slab")]


def side(ring):
    """The side A of a piece's outline (its first half: the points along the chain), as longitude and latitude."""
    return ring[: (len(ring) - 1) // 2]


def chains_of(edges):
    """The chains of the bridge group: for each chain (numbered from the longest) its pieces in order along it (one ribbon for each place), its length in metres and
    the roads on it."""
    by = collections.defaultdict(dict)
    for f in deck_pieces(edges):
        p = f["properties"]
        by[p["__rs_chain"]].setdefault((p["__rs_s0"], p["__rs_s1"]), f)
    out = []
    for pieces in by.values():
        ordered = [f for _, f in sorted(pieces.items())]
        length = sum(math.hypot((a[0] - b[0]) * KX, (a[1] - b[1]) * KY) for f in ordered for a, b in zip(side(f["geometry"]["coordinates"][0])[1:], side(f["geometry"]["coordinates"][0]), strict=False))
        out.append({"pieces": ordered, "length": length,
                    "roads": collections.Counter(f["properties"].get("name") or "no name" for f in ordered)})
    out.sort(key=lambda c: -c["length"])
    return out


def centre_line(chain):
    """The chain's line on the map: the middle of the two sides of each piece, in order (longitude, latitude)."""
    pts = []
    for f in chain["pieces"]:
        ring = f["geometry"]["coordinates"][0]
        m = (len(ring) - 1) // 2
        a, b = ring[:m], ring[2 * m - 1: m - 1: -1]
        pts += [((x[0] + y[0]) / 2, (x[1] + y[1]) / 2) for x, y in zip(a, b, strict=False)]
    return pts


def main():
    edges = gpd.read_parquet(HERE / "granville_bridge_edges.parquet")
    chains = chains_of(edges)
    full = chains[0]["pieces"][0]["properties"]["__rs_full"]
    total = sum(c["length"] for c in chains)
    print(f"{len(chains)} chains, the group is {total:.0f} m long, H = {full:.2f} m, {sum(len(c['pieces']) for c in chains)} deck pieces")
    print("| Chain | Roads | Length | Lift at the first end | Lift at the last end | Deck pieces |\n|---|---|---|---|---|---|")
    for n, c in enumerate(chains, 1):
        p0, p1 = c["pieces"][0]["properties"], c["pieces"][-1]["properties"]
        roads = ", ".join(sorted(c["roads"]))
        print(f"| {n} | {roads} | {c['length']:.0f} m | {p0['__rs_lift0']:.2f} | {p1['__rs_lift1']:.2f} | {len(c['pieces'])} |")

    colors = plt.get_cmap("tab20").colors
    fig, ax = plt.subplots(figsize=(6.2, 6.6))
    for n, c in enumerate(chains, 1):
        line = centre_line(c)
        xs, ys = [(x + 123.13) * KX for x, _ in line], [(y - 49.27) * KY for _, y in line]
        ax.plot(xs, ys, color=colors[(n - 1) % 20], linewidth=3, solid_capstyle="round")
        k = len(xs) // 2
        ax.annotate(str(n), (xs[k], ys[k]), fontsize=10, weight="bold", ha="center", va="center", bbox={"boxstyle": "circle,pad=0.2", "fc": "white", "ec": colors[(n - 1) % 20]})
    ax.set_aspect("equal")
    ax.set_xlabel("metres east", fontsize=9)
    ax.set_ylabel("metres north", fontsize=9)
    ax.tick_params(labelsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(HERE / "granville_plan.png", dpi=130)

    fig, axes = plt.subplots(3, 4, figsize=(12.5, 7.6), sharey=True)
    for n, (ax, c) in enumerate(zip(axes.flat, chains, strict=False), 1):
        xs, under, top = [], [], []
        length = c["length"]
        for f in c["pieces"]:
            p = f["properties"]
            for s, lift in ((p["__rs_s0"], p["__rs_lift0"]), (p["__rs_s1"], p["__rs_lift1"])):
                xs.append(s * length)
                under.append(full * lift)
                top.append(full * lift + p["__rs_thick"] * min(1.0, 2.0 * lift))
        ax.fill_between(xs, under, top, color=colors[(n - 1) % 20], linewidth=0)
        ax.axhline(0, color="#64748b", linewidth=1.2)
        ax.axhline(full, color="#64748b", linewidth=0.8, linestyle=(0, (4, 3)))
        p0, p1 = c["pieces"][0]["properties"], c["pieces"][-1]["properties"]
        ax.set_title(f"Chain {n}: {length:.0f} m\nlift {p0['__rs_lift0']:.2f} at the first end, {p1['__rs_lift1']:.2f} at the last", fontsize=9)
        ax.set_xlim(0, length)
        ax.set_ylim(-1, 25)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=8)
        if n > 8:
            ax.set_xlabel("metres along the chain", fontsize=8)
        if n % 4 == 1:
            ax.set_ylabel("metres above the ground", fontsize=8)
    fig.tight_layout()
    fig.savefig(HERE / "granville.png", dpi=120)


if __name__ == "__main__":
    main()
