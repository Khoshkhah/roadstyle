"""Makes granville_vs_lidar.png and prints the table of docs/design/bridge_profile_edit.md: the profile that the engine makes for each chain of the Granville Bridge
next to the heights that the City of Vancouver LiDAR 2022 gives for the same road (docs/samples/bridge-profile/granville_lidar_samples.json, from urbanstyle's profile of the bridge). A chain is
the axis of urbanstyle's profile that has the same OSM ways. Run it again after a change of the height rules:

    python docs/img/bridge-height/granville_vs_lidar.py"""
import json
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from granville import chains_of

HERE = Path(__file__).resolve().parent
SAMPLES = HERE.parents[1] / "samples" / "bridge-profile"


def matched(chains, lidar):
    """For each chain (numbered from the longest) the axis of the LiDAR file with the most OSM ways in common."""
    out = []
    for c in chains:
        ways = {f["properties"]["osm_id"] for f in c["pieces"]}
        axis = max(lidar["axes"], key=lambda a: len(ways & {int(w[1:]) for w in a["ways"]}))
        out.append((c, axis, len(ways & {int(w[1:]) for w in axis["ways"]}) == len(ways)))
    return out


def main():
    chains = chains_of(gpd.read_parquet(SAMPLES / "granville_bridge_edges.parquet"))
    lidar = json.loads((SAMPLES / "granville_lidar_samples.json").read_text())
    full = chains[0]["pieces"][0]["properties"]["__rs_full"]
    print(f"H of the engine: {full:.1f} m\n| Chain | Axis of the LiDAR file | Length (engine, LiDAR) | Highest deck, engine | Highest deck, LiDAR |\n|---|---|---|---|---|")
    fig, axes = plt.subplots(3, 4, figsize=(12.5, 7.6), sharey=True)
    for n, ((c, axis, same), ax) in enumerate(zip(matched(chains, lidar), axes.flat, strict=False), 1):
        length = c["length"]
        xs, under = [], []
        for f in c["pieces"]:
            p = f["properties"]
            xs += [p["__rs_s0"] * length, p["__rs_s1"] * length]
            under += [full * p["__rs_lift0"], full * p["__rs_lift1"]]
        s, z = zip(*axis["samples"], strict=False)
        assert same, (n, axis["id"])
        ax.plot(xs, under, color="#f28c28", linewidth=2.2, label=f"engine (H = {full:.0f} m)")
        ax.plot(s, z, color="#2563eb", linewidth=1.6, label="LiDAR")
        ax.axhline(0, color="#64748b", linewidth=1.0)
        ax.set_title(f"Chain {n} = axis {axis['id']}: {length:.0f} m", fontsize=9)
        ax.set_xlim(0, max(length, axis["length_m"]))
        ax.set_ylim(-1, 42)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=8)
        if n > 8:
            ax.set_xlabel("metres along the chain", fontsize=8)
        if n % 4 == 1:
            ax.set_ylabel("metres above the ground", fontsize=8)
        print(f"| {n} | {axis['id']} | {length:.0f} m, {axis['length_m']:.0f} m | {max(under):.1f} m | {max(z):.1f} m |")
    axes.flat[0].legend(fontsize=8, loc="lower right", frameon=False)
    fig.tight_layout()
    fig.savefig(HERE / "granville_vs_lidar.png", dpi=120)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(HERE))
    main()
