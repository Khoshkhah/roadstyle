"""The nodes of the Granville Bridge group, and the heights that a profile of the bridge needs (docs/design/bridge_height_design.md, "How many heights a profile needs"): the 13 nodes of its
12 chains, the 8 free ends on the ground (height 0: nothing to give) and the 5 junction nodes (a height to give), and for each junction the highest height that a design grade allows, from the
real chain lengths. It writes granville_nodes.png and prints the table. Run it again after a change of the rules:

    python docs/img/bridge-height/granville_nodes.py"""
import collections
import heapq
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from granville import KX, KY, centre_line, chains_of  # noqa: E402

GRADES = (0.05, 0.06, 0.08)


def graph():
    """The nodes of the chains and the chains between them: ({node: [(chain, end, lift)]}, {chain: (node_first, node_last, length)}, the chains)."""
    chains = chains_of(gpd.read_parquet(HERE / "granville_bridge_edges.parquet"))
    at, ends = collections.defaultdict(list), {}
    for n, c in enumerate(chains, 1):
        first, last = c["pieces"][0]["properties"], c["pieces"][-1]["properties"]
        a = next(f["properties"]["__rs_enda"] for f in c["pieces"] if "__rs_enda" in f["properties"])
        b = next(f["properties"]["__rs_endb"] for f in c["pieces"] if "__rs_endb" in f["properties"])
        na, nb = (round(a[0], 5), round(a[1], 5)), (round(b[0], 5), round(b[1], 5))
        at[na].append((n, "first", first["__rs_lift0"]))
        at[nb].append((n, "last", last["__rs_lift1"]))
        ends[n] = (na, nb, c["length"])
    return at, ends, chains


def distance_to_ground(at, ends):
    """The shortest distance along the chains from each node to a free end (a node where one chain ends)."""
    dist = {k: 0.0 for k, v in at.items() if len(v) == 1}
    heap = [(0.0, k) for k in dist]
    heapq.heapify(heap)
    while heap:
        d, k = heapq.heappop(heap)
        if d > dist.get(k, 1e18):
            continue
        for n, _, _ in at[k]:
            na, nb, ell = ends[n]
            other = nb if na == k else na
            if d + ell < dist.get(other, 1e18):
                dist[other] = d + ell
                heapq.heappush(heap, (d + ell, other))
    return dist


def junctions():
    """The junction nodes, from the north (J1) to the south: (name, node, chains that meet, distance to the ground, height of today's engine)."""
    at, ends, chains = graph()
    dist = distance_to_ground(at, ends)
    full = chains[0]["pieces"][0]["properties"]["__rs_full"]
    rows = []
    for k, v in sorted(((k, v) for k, v in at.items() if len(v) > 1), key=lambda kv: -kv[0][1]):
        rows.append((f"J{len(rows) + 1}", k, sorted(n for n, _, _ in v), dist[k], full * max(lift for _, _, lift in v)))
    return rows, at, chains


def example_profile(grade=0.06, cap=22.0):
    """An example set of the 5 junction heights: the highest height that the design `grade` allows at each junction (`grade` x the distance to the ground), and not above `cap`. A free end is 0.
    Between two nodes, a chain is a straight grade from the height at its first node to the height at its last node. Returns the heights of the nodes, and for each chain (numbered from the
    longest) its length, the two end heights and its slope in percent."""
    at, ends, chains = graph()
    dist = distance_to_ground(at, ends)
    height = {k: (0.0 if len(v) == 1 else min(cap, grade * dist[k])) for k, v in at.items()}
    rows = []
    for n in sorted(ends):
        na, nb, ell = ends[n]
        rows.append((n, ell, height[na], height[nb], abs(height[nb] - height[na]) / ell * 100))
    return height, rows


def main():
    rows, at, chains = junctions()
    print(f"nodes: {len(at)}, free ends (on the ground): {sum(1 for v in at.values() if len(v) == 1)}, junctions: {len(rows)}")
    print("| Junction | Chains that meet | Distance to the nearest ground end | Highest height at 5 % | at 6 % | at 8 % | Height of today's engine |\n|---|---|---|---|---|---|---|")
    for name, _, cs, d, today in rows:
        print(f"| {name} | {', '.join(map(str, cs))} | {d:.0f} m | " + " | ".join(f"{g * d:.1f} m" for g in GRADES) + f" | {today:.1f} m |")
    names = {k: name for name, k, *_ in rows}
    height, chain_rows = example_profile()
    print("\nexample: each junction at the highest height that 6 % allows (not above 22 m): " + ", ".join(f"{names[k]} {height[k]:.1f} m" for k in names))
    print("| Chain | Length | Height at the first end | Height at the last end | Slope |\n|---|---|---|---|---|")
    for n, ell, za, zb, slope in chain_rows:
        print(f"| {n} | {ell:.0f} m | {za:.1f} m | {zb:.1f} m | {slope:.1f} % |")
    fig, ax = plt.subplots(figsize=(6.4, 6.8))
    colors = plt.get_cmap("tab20").colors
    for n, c in enumerate(chains, 1):
        line = centre_line(c)
        ax.plot([(x + 123.13) * KX for x, _ in line], [(y - 49.27) * KY for _, y in line], color=colors[(n - 1) % 20], linewidth=2.5, solid_capstyle="round", zorder=1)
    for k in at:
        x, y = (k[0] + 123.13) * KX, (k[1] - 49.27) * KY
        if k in names:
            ax.scatter([x], [y], s=240, color="#dc2626", zorder=3)
            ax.annotate(names[k], (x, y), color="white", fontsize=8, weight="bold", ha="center", va="center", zorder=4)
        else:
            ax.scatter([x], [y], s=70, color="#16a34a", zorder=3)
    ax.scatter([], [], s=70, color="#16a34a", label="8 free ends on the ground: height 0, nothing to give")
    ax.scatter([], [], s=140, color="#dc2626", label="5 junctions: a height to give")
    ax.legend(fontsize=8, loc="lower right", frameon=False)
    ax.set_aspect("equal")
    ax.set_xlabel("metres east", fontsize=9)
    ax.set_ylabel("metres north", fontsize=9)
    ax.tick_params(labelsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(HERE / "granville_nodes.png", dpi=130)

    fig, axes = plt.subplots(3, 4, figsize=(12.5, 7.4), sharey=True)
    for (n, ell, za, zb, slope), ax in zip(chain_rows, axes.flat, strict=False):
        ax.fill_between([0, ell], [za, zb], [za + 1, zb + 1], color=colors[(n - 1) % 20], linewidth=0)
        ax.axhline(0, color="#64748b", linewidth=1.0)
        ax.set_title(f"Chain {n}: {ell:.0f} m\n{za:.1f} m to {zb:.1f} m, slope {slope:.1f} %", fontsize=9)
        ax.set_xlim(0, ell)
        ax.set_ylim(-1, 25)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=8)
        if n in (9, 10, 11, 12):
            ax.set_xlabel("metres along the chain", fontsize=8)
    for i in (0, 4, 8):
        axes.flat[i].set_ylabel("metres above the ground", fontsize=8)
    fig.tight_layout()
    fig.savefig(HERE / "granville_from_5_heights.png", dpi=120)


if __name__ == "__main__":
    main()
